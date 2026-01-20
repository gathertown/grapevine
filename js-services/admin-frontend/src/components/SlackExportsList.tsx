import { memo } from 'react';
import type { FC } from 'react';
import { Flex, Text, Badge } from '@gathertown/gather-design-system';
import type { SlackExportInfo } from '../types';

interface SlackExportsListProps {
  exports: SlackExportInfo[];
  isLoading?: boolean;
}

const SlackExportsList: FC<SlackExportsListProps> = memo(({ exports, isLoading = false }) => {
  // Format file size
  const formatFileSize = (bytes: number): string => {
    if (bytes <= 0) return '0 Bytes';
    const units = ['Bytes', 'KB', 'MB', 'GB'];
    const index = Math.min(Math.floor(Math.log2(bytes) / 10), units.length - 1);
    const size = bytes / 1000 ** index;
    return `${size < 10 ? size.toFixed(1) : Math.round(size)} ${units[index]}`;
  };

  // Format upload date
  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
  };

  if (isLoading) {
    return (
      <Flex direction="column" gap={16}>
        <Text fontSize="md" fontWeight="semibold">
          Previous Exports
        </Text>
        <Text fontSize="sm" color="tertiary">
          Loading exports...
        </Text>
      </Flex>
    );
  }

  if (exports.length === 0) {
    return (
      <Flex direction="column" gap={16}>
        <Text fontSize="md" fontWeight="semibold">
          Previous Exports
        </Text>
        <Flex
          direction="column"
          gap={8}
          p={16}
          style={{
            backgroundColor: '#f5f5f5',
            border: '1px solid #e0e0e0',
            borderRadius: '8px',
          }}
        >
          <Text fontSize="sm" color="tertiary" textAlign="center">
            No exports uploaded yet
          </Text>
        </Flex>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={16}>
      <Text fontSize="md" fontWeight="semibold">
        Previous Exports ({exports.length})
      </Text>

      <Flex direction="column" gap={8}>
        {exports.map((exportInfo) => (
          <Flex
            key={exportInfo.id}
            direction="column"
            gap={8}
            p={16}
            style={{
              backgroundColor: 'white',
              border: '1px solid #e0e0e0',
              borderRadius: '8px',
            }}
          >
            <Flex direction="row" justify="space-between" align="center">
              <Flex direction="column" gap={4}>
                <Text fontSize="md" fontWeight="semibold">
                  📦 {exportInfo.filename}
                </Text>
                <Text fontSize="sm" color="tertiary">
                  Uploaded: {formatDate(exportInfo.uploadedAt)} • Size:{' '}
                  {formatFileSize(exportInfo.size)}
                </Text>
              </Flex>

              <Badge color="success" text="Uploaded" />
            </Flex>
          </Flex>
        ))}
      </Flex>

      <div style={{ fontStyle: 'italic' }}>
        <Text fontSize="xs" color="tertiary">
          Uploaded exports are processed automatically in the background. More detailed progress
          tracking coming soon.
        </Text>
      </div>
    </Flex>
  );
});

SlackExportsList.displayName = 'SlackExportsList';

export { SlackExportsList };
