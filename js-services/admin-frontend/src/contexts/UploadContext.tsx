import {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef,
  ReactNode,
  useCallback,
} from 'react';
import { UploadContextType, SlackUploadStatus, SlackExportInfo } from '../types';
import { apiClient } from '../api/client';
import { useAuth } from '../hooks/useAuth';
import { newrelic } from '@corporate-context/frontend-common';
import { useTrackEvent } from '../hooks/useTrackEvent';
import { checkIfWeShouldStartAnsweringSampleQuestions } from '../utils/sampleQuestions';

const UploadContext = createContext<UploadContextType | null>(null);

interface UploadProviderProps {
  children: ReactNode;
}

interface InternalSlackUploadStatus extends SlackUploadStatus {
  success: boolean;
  s3Location: string | null;
  uploadedAt?: string;
}

export const useUpload = (): UploadContextType => {
  const context = useContext(UploadContext);
  if (!context) {
    throw new Error('useUpload must be used within an UploadProvider');
  }
  return context;
};

export const UploadProvider = ({ children }: UploadProviderProps) => {
  const { isProvisioningComplete } = useAuth();
  const { trackEvent } = useTrackEvent();
  const [slackUploadStatus, setSlackUploadStatus] = useState<InternalSlackUploadStatus>({
    uploading: false,
    success: false,
    error: null,
    filename: null,
    s3Location: null,
    completed: false,
    progress: 0,
    xhr: null,
  });
  const activeXHRs = useRef<Set<XMLHttpRequest>>(new Set());

  const [slackExports, setSlackExports] = useState<SlackExportInfo[]>([]);
  const [elapsedTime, setElapsedTime] = useState(0);
  const elapsedInterval = useRef<number | null>(null);

  // Function to fetch all Slack exports
  const fetchSlackExports = useCallback(async (): Promise<void> => {
    try {
      const data = await apiClient.get<{ exports: SlackExportInfo[] }>('/api/slack-exports/list');
      setSlackExports(data.exports || []);
    } catch (error) {
      console.error('Error fetching Slack exports:', error);
    }
  }, []);

  // Fetch existing uploads only when tenant provisioning is complete
  useEffect(() => {
    if (isProvisioningComplete) {
      fetchSlackExports();
    }
  }, [isProvisioningComplete, fetchSlackExports]);

  // Handle elapsed time tracking
  useEffect(() => {
    if (slackUploadStatus.uploading) {
      const startTime = Date.now();
      elapsedInterval.current = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        setElapsedTime(elapsed);
      }, 1000);

      return () => {
        if (elapsedInterval.current) {
          clearInterval(elapsedInterval.current);
        }
      };
    } else {
      if (elapsedInterval.current) {
        clearInterval(elapsedInterval.current);
        elapsedInterval.current = null;
      }
      setElapsedTime(0);
      return undefined;
    }
  }, [slackUploadStatus.uploading]);

  const uploadSlackFile = async (file: File, fileName?: string): Promise<string> => {
    const actualFileName = fileName || file.name;
    const uploadStartTime = Date.now();

    try {
      // Set initial upload state
      setSlackUploadStatus((prev) => ({
        ...prev,
        uploading: true,
        success: false,
        error: null,
        progress: 0,
        xhr: null,
      }));

      // Step 1: Initiate multipart upload
      const initResponse = await apiClient.post<{
        success: boolean;
        uploadId: string;
        key: string;
        bucket: string;
      }>('/api/slack-export/multipart/initiate', {
        filename: actualFileName,
        contentType: file.type || 'application/zip',
      });

      if (!initResponse.success) {
        throw new Error('Failed to initiate upload');
      }

      const { uploadId, key } = initResponse;

      // Step 2: Calculate optimal chunk size (10MB min, 64MB max, target 40 chunks)
      const minChunkSize = 10 * 1024 * 1024; // 10MB
      const maxChunkSize = 64 * 1024 * 1024; // 64MB
      const chunkSize = Math.min(maxChunkSize, Math.max(minChunkSize, Math.ceil(file.size / 40)));
      const totalChunks = Math.ceil(file.size / chunkSize);

      // Step 3: Get all presigned URLs in one batch
      const presignedResponse = await apiClient.post<{
        success: boolean;
        presignedUrls: Array<{ partNumber: number; presignedUrl: string }>;
      }>('/api/slack-export/multipart/presigned-parts-batch', {
        key,
        uploadId,
        totalParts: totalChunks,
      });

      if (!presignedResponse.success) {
        throw new Error('Failed to get presigned URLs');
      }

      // Create a map for easy lookup
      const presignedUrlMap = new Map(
        presignedResponse.presignedUrls.map((item) => [item.partNumber, item.presignedUrl])
      );

      // Step 4: Upload chunks in parallel batches
      const concurrency = 6; // Upload up to 6 chunks at a time
      const chunks: Array<{ ETag: string; PartNumber: number }> = [];
      const chunkProgressMap = new Map<number, number>(); // Track progress per chunk

      // Function to upload a single chunk
      const uploadChunk = async (
        chunkIndex: number
      ): Promise<{ ETag: string; PartNumber: number }> => {
        const partNumber = chunkIndex + 1;
        const start = chunkIndex * chunkSize;
        const end = Math.min(start + chunkSize, file.size);
        const chunkSizeBytes = end - start;
        const chunk = file.slice(start, end);

        const presignedUrl = presignedUrlMap.get(partNumber);
        if (!presignedUrl) {
          throw new Error(`No presigned URL for part ${partNumber}`);
        }

        return new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          activeXHRs.current.add(xhr);

          // Track upload progress for this chunk
          xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable) {
              // Update progress for this specific chunk
              chunkProgressMap.set(chunkIndex, event.loaded);

              // Calculate total progress across all chunks
              let currentTotalBytes = 0;
              chunkProgressMap.forEach((bytes) => {
                currentTotalBytes += bytes;
              });

              const progress = Math.min(100, Math.round((currentTotalBytes / file.size) * 100));
              setSlackUploadStatus((prev) => ({
                ...prev,
                progress,
              }));
            }
          });

          xhr.addEventListener('load', () => {
            activeXHRs.current.delete(xhr);
            if (xhr.status >= 200 && xhr.status < 300) {
              const etag = xhr.getResponseHeader('ETag');
              if (!etag) {
                reject(new Error(`No ETag received for part ${partNumber}`));
                return;
              }

              // Mark this chunk as fully uploaded
              chunkProgressMap.set(chunkIndex, chunkSizeBytes);

              resolve({
                ETag: etag.replace(/"/g, ''), // Remove quotes from ETag
                PartNumber: partNumber,
              });
            } else {
              reject(new Error(`Failed to upload part ${partNumber}: ${xhr.statusText}`));
            }
          });

          xhr.addEventListener('error', () => {
            activeXHRs.current.delete(xhr);
            reject(new Error(`Failed to upload part ${partNumber}: Network error`));
          });

          xhr.addEventListener('abort', () => {
            activeXHRs.current.delete(xhr);
            reject(new Error(`Upload aborted for part ${partNumber}`));
          });

          xhr.open('PUT', presignedUrl);
          xhr.setRequestHeader('Content-Type', file.type || 'application/zip');
          xhr.send(chunk);
        });
      };

      // Upload chunks with controlled concurrency
      const chunkQueue = Array.from({ length: totalChunks }, (_, i) => i);
      let activeCount = 0;
      let completedCount = 0;

      // Create a promise that resolves when all chunks are uploaded
      await new Promise<void>((resolve, reject) => {
        const startNextChunks = () => {
          // Start chunks while we have them and are under concurrency limit
          while (chunkQueue.length > 0 && activeCount < concurrency) {
            const chunkIndex = chunkQueue.shift();
            if (chunkIndex === undefined) continue;
            activeCount++;

            uploadChunk(chunkIndex)
              .then((result) => {
                activeCount--;
                completedCount++;
                chunks.push(result);

                // If all chunks are done, resolve
                if (completedCount === totalChunks) {
                  resolve();
                } else {
                  // Otherwise, try to start more chunks
                  startNextChunks();
                }
              })
              .catch((error) => {
                reject(error);
              });
          }
        };

        // Start initial uploads
        startNextChunks();
      });

      // Sort chunks by part number to ensure correct order
      chunks.sort((a, b) => a.PartNumber - b.PartNumber);

      // Step 5: Complete multipart upload
      const completeResponse = await apiClient.post<{
        success: boolean;
        location: string;
      }>('/api/slack-export/multipart/complete', {
        key,
        uploadId,
        parts: chunks,
      });

      if (!completeResponse.success) {
        throw new Error('Failed to complete multipart upload');
      }

      // Step 6: Confirm upload and trigger processing
      const confirmResponse = await apiClient.post<{
        success: boolean;
        message: string;
        filename: string;
        location: string;
        jobId: string;
        jobStatus: string;
        uploadId: string;
        uploadedAt: string;
      }>('/api/slack-export/confirm', {
        filename: actualFileName,
        key,
        size: file.size,
      });

      if (!confirmResponse.success) {
        throw new Error('Failed to confirm upload');
      }

      // Track successful upload completion
      const uploadDuration = Math.round((Date.now() - uploadStartTime) / 1000);

      newrelic.addPageAction('slackExportUploadCompleted', {
        fileName: actualFileName,
        fileSize: file.size,
        uploadDuration,
      });

      // Track Amplitude event for Slack export success
      trackEvent('slack_export_success', {
        file_name: actualFileName,
        file_size_mb: Math.round((file.size / (1024 * 1024)) * 100) / 100, // Convert to MB with 2 decimal places
        upload_duration_seconds: uploadDuration,
      });

      // Update final state
      setSlackUploadStatus((prev) => ({
        ...prev,
        uploading: false,
        success: true,
        completed: true,
        filename: actualFileName,
        s3Location: confirmResponse.location,
        uploadedAt: confirmResponse.uploadedAt,
        progress: 100,
      }));

      // Clean up
      activeXHRs.current.clear();

      // Refresh the exports list
      await fetchSlackExports();

      // Check if we should trigger sample questions job now that Slack export is complete
      checkIfWeShouldStartAnsweringSampleQuestions();

      return confirmResponse.location;
    } catch (error) {
      // Track failed upload
      const errorMessage = error instanceof Error ? error.message : 'Upload failed';

      newrelic.addPageAction('slackExportUploadFailed', {
        fileName: actualFileName,
        errorMessage,
      });

      // Abort all active requests on error
      activeXHRs.current.forEach((xhr) => xhr.abort());
      activeXHRs.current.clear();

      setSlackUploadStatus((prev) => ({
        ...prev,
        uploading: false,
        error: errorMessage,
      }));
      throw error;
    }
  };

  const resetUpload = (): void => {
    // Track upload cancellation if there was an active upload
    if (slackUploadStatus.uploading && slackUploadStatus.filename) {
      const cancelledAfter = Math.round(elapsedTime);
      newrelic.addPageAction('slackExportUploadCancelled', {
        fileName: slackUploadStatus.filename,
        cancelledAfter,
      });
    }

    // Cancel all active XHRs
    activeXHRs.current.forEach((xhr) => xhr.abort());
    activeXHRs.current.clear();

    // Cancel ongoing upload if any (legacy support)
    if (slackUploadStatus.xhr) {
      slackUploadStatus.xhr.abort();
    }

    // Clear intervals
    if (elapsedInterval.current) {
      clearInterval(elapsedInterval.current);
      elapsedInterval.current = null;
    }

    // Reset state
    setSlackUploadStatus({
      uploading: false,
      success: false,
      error: null,
      filename: null,
      s3Location: null,
      completed: false,
      progress: 0,
      xhr: null,
    });
    setElapsedTime(0);
  };

  const handleSlackUpload = (file: File): void => {
    uploadSlackFile(file, file.name).catch((error) => {
      console.error('Slack upload error:', error);
    });
  };

  const resetSlackUpload = (): void => {
    resetUpload();
  };

  // Map to the UploadContextType interface
  const value: UploadContextType = {
    uploadStatus: slackUploadStatus.uploading
      ? 'uploading'
      : slackUploadStatus.error
        ? 'error'
        : slackUploadStatus.success
          ? 'success'
          : 'idle',
    uploadProgress: slackUploadStatus.progress,
    uploadError: slackUploadStatus.error,
    uploadedFileUrl: slackUploadStatus.s3Location,
    resetUpload,
    slackUploadStatus: {
      uploading: slackUploadStatus.uploading,
      completed: slackUploadStatus.completed,
      progress: slackUploadStatus.progress,
      filename: slackUploadStatus.filename,
      error: slackUploadStatus.error,
      xhr: slackUploadStatus.xhr,
    },
    slackExports,
    elapsedTime,
    handleSlackUpload,
    resetSlackUpload,
    fetchSlackExports,
  };

  return <UploadContext.Provider value={value}>{children}</UploadContext.Provider>;
};
