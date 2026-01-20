import { Flex } from '@gathertown/gather-design-system';
import { type CustomFieldType, getFieldTypeLabel } from '../../customDataApi';

interface FieldTypeBadgeProps {
  type: CustomFieldType | 'string';
  label?: string;
}

export const FieldTypeBadge = ({ type, label }: FieldTypeBadgeProps) => {
  // Handle default fields which use 'string' type
  const displayLabel =
    label || (type === 'string' ? 'Text' : getFieldTypeLabel(type as CustomFieldType));

  return (
    <Flex
      style={{
        padding: '2px 6px',
        backgroundColor: '#fff',
        border: '1px solid #dee2e6',
        borderRadius: '4px',
      }}
    >
      <span style={{ fontSize: '12px', color: '#666' }}>{displayLabel}</span>
    </Flex>
  );
};
