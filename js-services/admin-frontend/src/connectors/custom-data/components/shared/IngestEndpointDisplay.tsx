import { Flex, Text } from '@gathertown/gather-design-system';
import { buildIngestEndpoint } from '../../constants';
import { CODE_BLOCK_STYLES } from './styles';

interface IngestEndpointDisplayProps {
  tenantId: string;
  slug: string;
  variant?: 'inline' | 'block';
  showLabel?: boolean;
}

export const IngestEndpointDisplay = ({
  tenantId,
  slug,
  variant = 'inline',
  showLabel = false,
}: IngestEndpointDisplayProps) => {
  const endpoint = buildIngestEndpoint(tenantId, slug);
  const styles = variant === 'block' ? CODE_BLOCK_STYLES.block : CODE_BLOCK_STYLES.inline;

  if (showLabel) {
    return (
      <Flex direction="column" gap={4}>
        <Text fontSize="sm" fontWeight="semibold">
          Ingest Endpoint:
        </Text>
        <code style={styles}>{endpoint}</code>
      </Flex>
    );
  }

  return <code style={styles}>{endpoint}</code>;
};
