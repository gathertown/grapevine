import { Button, Flex, Text, Modal } from '@gathertown/gather-design-system';
import { useUpdateSemanticModel, SemanticModelState, type SemanticModel } from '../../snowflakeApi';
import { SEMANTIC_MODEL_CONSTANTS } from './constants';

interface DeleteSemanticModelModalProps {
  model: SemanticModel;
  onClose: () => void;
  onSuccess: () => void;
}

export const DeleteSemanticModelModal = ({
  model,
  onClose,
  onSuccess,
}: DeleteSemanticModelModalProps) => {
  const { mutate: updateModel, isPending, error } = useUpdateSemanticModel();

  const handleDelete = () => {
    updateModel(
      { id: model.id, params: { state: SemanticModelState.DELETED } },
      {
        onSuccess: () => {
          onSuccess();
        },
      }
    );
  };

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content variant="default" showOverlay style={{ maxWidth: 600 }}>
        <Modal.Header title={`Delete Semantic ${model.type === 'model' ? 'Model' : 'View'}`} />
        <Modal.Body style={{ padding: 16, gap: 16 }}>
          <Flex direction="column" gap={16}>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm">
                Are you sure you want to delete the semantic{' '}
                {model.type === 'model' ? 'model' : 'view'}{' '}
                <Text as="span" fontWeight="semibold">
                  {model.name}
                </Text>
                ?
              </Text>
              <Text fontSize="sm" color="secondary">
                This will mark the {model.type === 'model' ? 'model' : 'view'} as deleted and remove
                it from your list. The {model.type === 'model' ? 'YAML file' : 'semantic view'} in
                Snowflake will not be affected.
              </Text>
            </Flex>

            <Flex
              direction="column"
              gap={8}
              style={{
                padding: '12px',
                backgroundColor: '#f8f9fa',
                borderRadius: '8px',
                border: '1px solid #dee2e6',
              }}
            >
              <Text fontSize="sm" fontWeight="semibold">
                {model.type === 'model' ? 'Model Details:' : 'View Details:'}
              </Text>
              {model.type === 'model' ? (
                <Text fontSize="sm" color="secondary">
                  Stage Path:{' '}
                  {model.stage_path || SEMANTIC_MODEL_CONSTANTS.MISSING_VALUE_PLACEHOLDER}
                </Text>
              ) : (
                <Text fontSize="sm" color="secondary">
                  Location:{' '}
                  {model.database_name && model.schema_name && model.name
                    ? `${model.database_name}.${model.schema_name}.${model.name}`
                    : SEMANTIC_MODEL_CONSTANTS.MISSING_VALUE_PLACEHOLDER}
                </Text>
              )}
              {model.description && (
                <Text fontSize="sm" color="secondary">
                  Description: {model.description}
                </Text>
              )}
            </Flex>

            {error && (
              <Flex
                direction="column"
                gap={8}
                style={{
                  padding: '12px',
                  backgroundColor: '#f8d7da',
                  borderRadius: '8px',
                  border: '1px solid #f5c2c7',
                }}
              >
                <Text color="dangerPrimary" fontWeight="semibold">
                  Error: {error.message}
                </Text>
              </Flex>
            )}
          </Flex>
        </Modal.Body>
        <Modal.Footer>
          <Flex gap={8} style={{ justifyContent: 'flex-end' }}>
            <Button onClick={onClose} kind="secondary" size="sm" disabled={isPending}>
              Cancel
            </Button>
            <Button onClick={handleDelete} kind="danger" size="sm" loading={isPending}>
              Delete {model.type === 'model' ? 'Model' : 'View'}
            </Button>
          </Flex>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
};
