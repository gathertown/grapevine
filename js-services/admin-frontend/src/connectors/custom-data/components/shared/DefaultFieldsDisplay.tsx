import { Flex, Text } from '@gathertown/gather-design-system';
import { FieldTypeBadge } from './FieldTypeBadge';
import { RequiredBadge } from './RequiredBadge';

const DEFAULT_FIELDS = [
  {
    name: 'name',
    type: 'string' as const,
    label: 'Text',
    description: 'Document title displayed in search results',
  },
  {
    name: 'description',
    type: 'string' as const,
    label: 'Text',
    description: 'Brief summary of the document',
  },
  {
    name: 'content',
    type: 'text' as const,
    label: 'Text',
    description: 'Main content body (markdown preferred) - indexed for search',
  },
];

interface DefaultFieldsDisplayProps {
  showHeader?: boolean;
}

export const DefaultFieldsDisplay = ({ showHeader = true }: DefaultFieldsDisplayProps) => {
  return (
    <Flex direction="column" gap={12}>
      {showHeader && (
        <Flex direction="row" gap={8} style={{ alignItems: 'center' }}>
          <Text fontSize="sm" fontWeight="semibold">
            Default Fields
          </Text>
          <Flex
            style={{
              padding: '2px 8px',
              backgroundColor: '#f0f0f0',
              border: '1px solid #ccc',
              borderRadius: '4px',
            }}
          >
            <span style={{ fontSize: '11px', color: '#666' }}>Always included</span>
          </Flex>
        </Flex>
      )}

      <Flex
        direction="column"
        style={{
          backgroundColor: '#f8f9fa',
          border: '1px solid #dee2e6',
          borderRadius: '6px',
          overflow: 'hidden',
        }}
      >
        {DEFAULT_FIELDS.map((field, index) => (
          <Flex
            key={field.name}
            direction="row"
            gap={8}
            style={{
              padding: '12px',
              alignItems: 'center',
              borderBottom: index < DEFAULT_FIELDS.length - 1 ? '1px solid #eee' : undefined,
            }}
          >
            <Flex style={{ width: '24px', justifyContent: 'center' }}>
              <span style={{ fontSize: '14px' }}>🔒</span>
            </Flex>
            <Flex style={{ width: '100px' }}>
              <Text fontSize="sm" fontWeight="medium">
                {field.name}
              </Text>
            </Flex>
            <Flex style={{ width: '60px' }}>
              <FieldTypeBadge type={field.type} label={field.label} />
            </Flex>
            <Flex style={{ width: '70px' }}>
              <RequiredBadge />
            </Flex>
            <Flex style={{ flex: 1 }}>
              <Text fontSize="xs" color="secondary">
                {field.description}
              </Text>
            </Flex>
          </Flex>
        ))}
      </Flex>
    </Flex>
  );
};
