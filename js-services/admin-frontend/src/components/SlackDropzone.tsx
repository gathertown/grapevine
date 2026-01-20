import { memo, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Flex, Text, Icon } from '@gathertown/gather-design-system';
import { newrelic } from '@corporate-context/frontend-common';

interface SlackDropzoneProps {
  onFileChange?: (file: File | null) => void;
  disabled?: boolean;
  hasError?: boolean;
  errorMessage?: string | null;
}

const MAX_SLACK_EXPORT_SIZE_GB = 50;

const SlackDropzone = memo<SlackDropzoneProps>(
  ({ onFileChange, disabled = false, hasError = false, errorMessage }) => {
    const onDrop = useCallback(
      (acceptedFiles: File[]) => {
        const file = acceptedFiles[0];
        if (file && onFileChange) {
          // Track file upload start
          newrelic.addPageAction('slackExportUploadStarted', {
            fileName: file.name,
            fileSize: file.size,
          });

          onFileChange(file);
        }
      },
      [onFileChange]
    );

    const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
      onDrop,
      accept: {
        'application/zip': ['.zip'],
      },
      multiple: false,
      disabled,
      maxSize: MAX_SLACK_EXPORT_SIZE_GB * 1000 * 1000 * 1000, // in GB
    });

    const getBorderStyle = () => {
      if (hasError || isDragReject) {
        return '2px dashed #ef5350';
      }
      if (isDragActive) {
        return '2px dashed #4caf50';
      }
      return '2px dashed #ccc';
    };

    const getBackgroundColor = () => {
      if (hasError || isDragReject) {
        return '#ffebee';
      }
      if (isDragActive) {
        return '#e8f5e8';
      }
      return disabled ? '#f0f0f0' : '#f5f5f5';
    };

    const getTextColor = () => {
      if (hasError || isDragReject) {
        return 'tertiary'; // Error color not supported, use tertiary
      }
      if (isDragActive) {
        return 'successPrimary';
      }
      return disabled ? 'tertiary' : 'secondary';
    };

    return (
      <Flex direction="column" gap={8}>
        <div
          {...getRootProps()}
          style={{
            padding: '48px 16px',
            border: getBorderStyle(),
            borderRadius: '8px',
            backgroundColor: getBackgroundColor(),
            cursor: disabled ? 'not-allowed' : 'pointer',
            textAlign: 'center',
            transition: 'all 0.2s ease-in-out',
            outline: 'none',
          }}
        >
          <input {...getInputProps()} />

          <Flex direction="column" align="center" gap={16}>
            <Icon
              name="upload"
              size="lg"
              color={hasError || isDragReject ? 'tertiary' : isDragActive ? 'tertiary' : 'tertiary'}
            />

            <Flex direction="column" align="center" gap={8}>
              <Text fontSize="md" fontWeight="semibold" color={getTextColor()}>
                {isDragActive
                  ? isDragReject
                    ? 'File type not supported'
                    : 'Drop your Slack export here'
                  : 'Drag & drop your Slack export zip file'}
              </Text>

              {!isDragActive && (
                <Text fontSize="sm" color={getTextColor()}>
                  or <span style={{ textDecoration: 'underline' }}>click to browse</span>
                </Text>
              )}

              <Text fontSize="xs" color="tertiary">
                Only .zip files up to {MAX_SLACK_EXPORT_SIZE_GB} GB are supported
              </Text>
            </Flex>
          </Flex>
        </div>

        {errorMessage && (
          <div
            style={{
              backgroundColor: '#ffebee',
              color: '#c62828',
              padding: '12px',
              borderRadius: '8px',
              border: '1px solid #ef5350',
            }}
          >
            <Text fontSize="sm">{errorMessage}</Text>
          </div>
        )}
      </Flex>
    );
  }
);

SlackDropzone.displayName = 'SlackDropzone';

export { SlackDropzone };
