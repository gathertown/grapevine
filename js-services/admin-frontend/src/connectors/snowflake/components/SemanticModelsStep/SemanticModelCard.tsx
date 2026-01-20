import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { type SemanticModel } from '../../snowflakeApi';
import { SEMANTIC_MODEL_CONSTANTS } from './constants';

interface SemanticModelCardProps {
  model: SemanticModel;
  onEdit: () => void;
  onDelete: () => void;
}

export const SemanticModelCard = ({ model, onEdit, onDelete }: SemanticModelCardProps) => {
  return (
    <Flex
      direction="column"
      gap={12}
      style={{
        padding: '16px',
        backgroundColor: '#ffffff',
        borderRadius: '8px',
        border: '1px solid #dee2e6',
      }}
    >
      <Flex direction="row" style={{ justifyContent: 'space-between', alignItems: 'start' }}>
        <Flex direction="column" gap={4}>
          <Flex direction="row" gap={8} style={{ alignItems: 'center' }}>
            <Text fontSize="md" fontWeight="semibold">
              {model.name}
            </Text>
            {/* Type badge */}
            <Flex
              style={{
                padding: '2px 8px',
                backgroundColor: model.type === 'model' ? '#e3f2fd' : '#f3e5f5',
                borderRadius: '4px',
                border: `1px solid ${model.type === 'model' ? '#2196f3' : '#9c27b0'}`,
              }}
            >
              <span
                style={{ fontSize: '12px', color: model.type === 'model' ? '#1976d2' : '#7b1fa2' }}
              >
                {model.type === 'model' ? 'Model' : 'View'}
              </span>
            </Flex>
            {/* Status badge */}
            <Flex
              style={{
                padding: '2px 8px',
                backgroundColor:
                  model.state === 'enabled'
                    ? '#e8f5e9' // Green
                    : model.state === 'disabled'
                      ? '#fce4ec' // Pink
                      : model.state === 'error'
                        ? '#ffebee' // Red
                        : '#f5f5f5', // Gray for deleted
                borderRadius: '4px',
                border: `1px solid ${
                  model.state === 'enabled'
                    ? '#4caf50' // Green
                    : model.state === 'disabled'
                      ? '#e91e63' // Pink
                      : model.state === 'error'
                        ? '#f44336' // Red
                        : '#9e9e9e' // Gray for deleted
                }`,
              }}
            >
              <span
                style={{
                  fontSize: '12px',
                  color:
                    model.state === 'enabled'
                      ? '#2e7d32' // Green
                      : model.state === 'disabled'
                        ? '#c2185b' // Pink
                        : model.state === 'error'
                          ? '#c62828' // Red
                          : '#616161', // Gray for deleted
                }}
              >
                {model.state.charAt(0).toUpperCase() + model.state.slice(1)}
              </span>
            </Flex>
          </Flex>
          <Text fontSize="sm" color="secondary">
            {model.type === 'model'
              ? model.stage_path || SEMANTIC_MODEL_CONSTANTS.MISSING_VALUE_PLACEHOLDER
              : model.database_name && model.schema_name && model.name
                ? `${model.database_name}.${model.schema_name}.${model.name}`
                : SEMANTIC_MODEL_CONSTANTS.MISSING_VALUE_PLACEHOLDER}
          </Text>
        </Flex>

        <Flex direction="row" gap={8}>
          <Button onClick={onEdit} kind="secondary" size="sm">
            Edit
          </Button>
          <Button onClick={onDelete} kind="danger" size="sm">
            Delete
          </Button>
        </Flex>
      </Flex>

      {model.description && (
        <Text fontSize="sm" color="secondary">
          {model.description}
        </Text>
      )}

      {model.warehouse && (
        <Flex direction="row" gap={4} style={{ alignItems: 'center' }}>
          <Text fontSize="xs" color="secondary" fontWeight="semibold">
            Warehouse:
          </Text>
          <Text fontSize="xs" color="secondary">
            {model.warehouse}
          </Text>
        </Flex>
      )}
    </Flex>
  );
};
