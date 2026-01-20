import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { type CustomFieldDefinition } from '../../customDataApi';
import { FieldTypeBadge } from './FieldTypeBadge';
import { RequiredBadge } from './RequiredBadge';

interface CustomFieldItemProps {
  field: CustomFieldDefinition;
  onEdit: () => void;
  onDelete: () => void;
}

export const CustomFieldItem = ({ field, onEdit, onDelete }: CustomFieldItemProps) => {
  return (
    <Flex
      direction="row"
      gap={12}
      style={{
        padding: '12px',
        alignItems: 'center',
        backgroundColor: '#fff',
        borderBottom: '1px solid #eee',
      }}
    >
      {/* Drag handle */}
      <span style={{ color: '#ccc', cursor: 'grab', userSelect: 'none' }}>⋮⋮</span>

      {/* Field info */}
      <Flex direction="column" gap={2} style={{ flex: 1 }}>
        <Flex direction="row" gap={8} style={{ alignItems: 'center' }}>
          <Text fontSize="sm" fontWeight="medium">
            {field.name}
          </Text>
          <FieldTypeBadge type={field.type} />
          <RequiredBadge show={field.required} />
        </Flex>
        {field.description && (
          <Text fontSize="xs" color="secondary">
            {field.description}
          </Text>
        )}
      </Flex>

      {/* Actions */}
      <Flex direction="row" gap={4}>
        <Button
          onClick={onEdit}
          kind="secondary"
          size="sm"
          style={{ padding: '4px 8px', minWidth: 'auto' }}
        >
          ✎
        </Button>
        <Button
          onClick={onDelete}
          kind="secondary"
          size="sm"
          style={{ padding: '4px 8px', minWidth: 'auto', color: '#dc3545' }}
        >
          🗑
        </Button>
      </Flex>
    </Flex>
  );
};
