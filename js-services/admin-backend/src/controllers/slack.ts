import { Router } from 'express';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { getConfigValue, saveConfigValue } from '../config/index.js';
import { getSqsClient, isSqsConfigured } from '../jobs/sqs-client.js';
import {
  getS3Client,
  isS3Configured,
  getS3BucketName,
  CreateMultipartUploadCommand,
  UploadPartCommand,
  CompleteMultipartUploadCommand,
  getSignedUrl,
} from '../s3-client.js';
import crypto from 'node:crypto';
import { logger, LogContext } from '../utils/logger.js';

const slackRouter = Router();

// Initiate multipart upload
slackRouter.post('/multipart/initiate', requireAdmin, async (req, res) => {
  const { filename, contentType } = req.body;

  if (!filename) {
    return res.status(400).json({
      error: 'Filename is required',
    });
  }

  const s3LogContext = { operation: 'multipart-upload-initiate', filename, contentType };
  await LogContext.run(s3LogContext, async () => {
    try {
      logger.info('Initiating multipart upload for Slack export');

      // Generate S3 key with timestamp
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const s3Key = `slack-exports/${timestamp}/${filename}`;

      // Create multipart upload
      const createCommand = new CreateMultipartUploadCommand({
        Bucket: getS3BucketName(),
        Key: s3Key,
        ContentType: contentType || 'application/zip',
      });

      const response = await getS3Client().send(createCommand);

      logger.info('Successfully initiated multipart upload', {
        uploadId: response.UploadId,
        s3Key,
      });

      res.json({
        success: true,
        uploadId: response.UploadId,
        key: s3Key,
        bucket: getS3BucketName(),
      });
    } catch (error) {
      logger.error('Error initiating multipart upload', error);
      res.status(500).json({
        error: 'Failed to initiate multipart upload. Please try again.',
      });
    }
  });
});

// Get presigned URLs for multiple upload parts in batch
slackRouter.post('/multipart/presigned-parts-batch', requireAdmin, async (req, res) => {
  const { key, uploadId, totalParts } = req.body;

  if (!key || !uploadId || !totalParts) {
    return res.status(400).json({
      error: 'Key, uploadId, and totalParts are required',
    });
  }
  if (totalParts < 1 || totalParts > 1000) {
    return res.status(400).json({
      error: 'Total parts must be between 1 and 1000',
    });
  }

  if (!isS3Configured()) {
    return res.status(500).json({
      error: 'Storage not configured. Please configure S3 credentials in your environment.',
    });
  }

  await LogContext.run(
    {
      operation: 'multipart-presigned-urls-batch',
      key,
      uploadId,
      totalParts,
    },
    async () => {
      try {
        logger.info('Generating presigned URLs for multipart upload parts');

        // Generate presigned URLs for all parts in parallel
        const presignedUrlPromises = [];
        for (let partNumber = 1; partNumber <= totalParts; partNumber++) {
          // Create upload part command
          const uploadPartCommand = new UploadPartCommand({
            Bucket: getS3BucketName(),
            Key: key,
            UploadId: uploadId,
            PartNumber: partNumber,
          });

          // Generate presigned URL (valid for 2 hours)
          const promise = getSignedUrl(getS3Client(), uploadPartCommand, {
            expiresIn: 60 * 60 * 2, // 2 hours
          }).then((presignedUrl) => ({
            partNumber,
            presignedUrl,
          }));

          presignedUrlPromises.push(promise);
        }

        // Wait for all presigned URLs to be generated
        const presignedUrls = await Promise.all(presignedUrlPromises);

        logger.info('Successfully generated presigned URLs for all parts', {
          urlCount: presignedUrls.length,
        });

        res.json({
          success: true,
          presignedUrls,
        });
      } catch (error) {
        logger.error('Error generating presigned URLs for parts', error);
        res.status(500).json({
          error: 'Failed to generate presigned URLs for parts. Please try again.',
        });
      }
    }
  );
});

// Complete multipart upload
slackRouter.post('/multipart/complete', requireAdmin, async (req, res) => {
  const { key, uploadId, parts } = req.body;

  if (!key || !uploadId || !parts || !Array.isArray(parts)) {
    return res.status(400).json({
      error: 'Key, uploadId, and parts array are required',
    });
  }

  if (!isS3Configured()) {
    return res.status(500).json({
      error: 'Storage not configured. Please configure S3 credentials in your environment.',
    });
  }

  await LogContext.run(
    {
      operation: 'multipart-upload-complete',
      key,
      uploadId,
      partsCount: parts.length,
    },
    async () => {
      try {
        logger.info('Completing multipart upload');

        // Complete multipart upload
        const completeCommand = new CompleteMultipartUploadCommand({
          Bucket: getS3BucketName(),
          Key: key,
          UploadId: uploadId,
          MultipartUpload: {
            Parts: parts,
          },
        });

        const response = await getS3Client().send(completeCommand);
        const location = response.Location || `s3://${getS3BucketName()}/${key}`;

        logger.info('Successfully completed multipart upload', {
          location,
        });

        res.json({
          success: true,
          location,
        });
      } catch (error) {
        logger.error('Error completing multipart upload', error);
        res.status(500).json({
          error: 'Failed to complete multipart upload. Please try again.',
        });
      }
    }
  );
});

// Get all Slack exports endpoint
slackRouter.get('/list', requireAdmin, async (req, res) => {
  // Get tenant ID from authenticated user
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({
      error: 'No tenant found for organization',
    });
  }

  await LogContext.run(
    {
      operation: 'slack-exports-list',
    },
    async () => {
      try {
        logger.info('Retrieving Slack exports list');

        // Get the uploads array from config (automatically routed to database as non-sensitive)
        const uploadsJson = await getConfigValue('SLACK_EXPORTS_UPLOADED', tenantId);

        if (!uploadsJson) {
          logger.info('No Slack exports found for tenant');
          return res.json({
            exports: [],
            message: 'No Slack exports have been uploaded yet',
          });
        }

        const exports = JSON.parse(uploadsJson as string);

        logger.info('Successfully retrieved Slack exports list', {
          count: exports.length,
        });

        return res.json({
          exports,
          count: exports.length,
        });
      } catch (error) {
        logger.error('Error getting Slack exports list', error);
        res.status(500).json({
          error: 'Failed to get Slack exports list',
        });
      }
    }
  );
});

// Confirm upload endpoint - called after successful client upload
slackRouter.post('/confirm', requireAdmin, async (req, res) => {
  const { filename, key, size } = req.body;

  if (!filename || !key) {
    return res.status(400).json({
      error: 'Filename and key are required',
    });
  }

  // Get tenant ID from authenticated user
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({
      error: 'No tenant found for organization',
    });
  }

  await LogContext.run(
    {
      operation: 'slack-export-confirm',
      filename,
      key,
    },
    async () => {
      try {
        logger.info('Confirming Slack export upload');

        // Create upload info with unique ID
        const uploadInfo = {
          id: crypto.randomUUID(),
          filename,
          location: `s3://${getS3BucketName()}/${key}`,
          size: size || 0,
          uploadedAt: new Date().toISOString(),
        };

        // Get existing uploads array or create new one
        const existingUploadsJson = await getConfigValue('SLACK_EXPORTS_UPLOADED', tenantId);
        const existingUploads = existingUploadsJson
          ? JSON.parse(existingUploadsJson as string)
          : [];

        // Append new upload to array
        const updatedUploads = [...existingUploads, uploadInfo];

        // Save updated array back to config (automatically routed to database as non-sensitive)
        await saveConfigValue('SLACK_EXPORTS_UPLOADED', JSON.stringify(updatedUploads), tenantId);

        logger.info('Slack export confirmed and saved to config', {
          uploadId: uploadInfo.id,
          location: uploadInfo.location,
          size: uploadInfo.size,
        });

        // Trigger processing job via SQS
        try {
          // Check if SQS is configured
          if (!isSqsConfigured()) {
            logger.error('SQS not configured - processing cannot be started');
            return res.status(500).json({
              error: 'SQS not configured - missing AWS credentials or region',
            });
          }

          const sqsClient = getSqsClient();
          // Always use the S3 object path directly instead of presigned URL
          const jobUri = uploadInfo.location;

          logger.info('Sending Slack export job to SQS queue', {
            jobUri,
          });

          // Send the job to SQS - leave message_limit undefined as requested
          await sqsClient.sendSlackExportIngestJob(tenantId, jobUri, undefined);

          logger.info('Slack export job queued successfully');

          // Generate a simple job reference for tracking
          const jobRef = `slack-export-${tenantId}-${Date.now()}`;
          await saveConfigValue('SLACK_EXPORT_JOB_ID', jobRef, tenantId);

          res.json({
            success: true,
            message: 'Slack export uploaded successfully and processing job has been queued.',
            filename,
            location: uploadInfo.location,
            jobId: jobRef,
            jobStatus: 'queued',
            uploadId: uploadInfo.id,
            uploadedAt: uploadInfo.uploadedAt,
          });
        } catch (sqsError) {
          logger.error('Error sending job to SQS', sqsError);

          res.status(500).json({
            error: `Failed to queue processing job: ${sqsError.message}`,
          });
        }
      } catch (error) {
        logger.error('Error confirming Slack export', error);
        res.status(500).json({
          error: 'Failed to confirm Slack export. Please try again.',
        });
      }
    }
  );
});

export { slackRouter };
