import { Flex } from '@gathertown/gather-design-system';

interface CustomFieldsCountBadgeProps {
  count: number;
}

export const CustomFieldsCountBadge = ({ count }: CustomFieldsCountBadgeProps) => {
  return (
    <Flex
      style={{
        padding: '2px 8px',
        backgroundColor: '#e3f2fd',
        borderRadius: '4px',
        border: '1px solid #2196f3',
      }}
    >
      <span style={{ fontSize: '12px', color: '#1976d2' }}>
        {count} custom {count === 1 ? 'field' : 'fields'}
      </span>
    </Flex>
  );
};
