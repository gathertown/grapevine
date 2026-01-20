import { Button, Flex, Text, Modal } from '@gathertown/gather-design-system';
import {
  useDeleteCustomDocumentType,
  useCustomDocumentTypeStats,
  type CustomDocumentType,
} from '../customDataApi';

interface DeleteDocumentTypeModalProps {
  documentType: CustomDocumentType;
  onClose: () => void;
  onSuccess: () => void;
}

export const DeleteDocumentTypeModal = ({
  documentType,
  onClose,
  onSuccess,
}: DeleteDocumentTypeModalProps) => {
  const { mutate: deleteType, isPending, error } = useDeleteCustomDocumentType();
  const { data: stats, isLoading: isLoadingStats } = useCustomDocumentTypeStats(documentType.id);

  const documentCount = stats?.documentCount ?? 0;

  const handleDelete = () => {
    deleteType(documentType.id, {
      onSuccess: () => {
        onSuccess();
      },
    });
  };

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content variant="auto" showOverlay style={{ maxWidth: 480 }}>
        <Modal.Header title="Delete Data Type" />
        <Modal.Body style={{ padding: '16px 24px' }}>
          <Flex direction="column" gap={12}>
            <Text fontSize="sm">
              Are you sure you want to delete <strong>{documentType.display_name}</strong>?
            </Text>

            <Flex
              style={{
                padding: '10px 12px',
                backgroundColor: '#fff3cd',
                border: '1px solid #ffc107',
                borderRadius: '6px',
              }}
            >
              <span style={{ fontSize: '14px', color: '#856404' }}>
                <strong>Warning:</strong> This will permanently delete the schema
                {isLoadingStats
                  ? ' and any associated documents'
                  : documentCount > 0
                    ? ` and ${documentCount} document${documentCount !== 1 ? 's' : ''}`
                    : ''}
                .
              </span>
            </Flex>

            {error && (
              <Text fontSize="sm" color="dangerPrimary">
                Error: {error.message}
              </Text>
            )}
          </Flex>
        </Modal.Body>
        <Modal.Footer>
          <Flex gap={8} style={{ justifyContent: 'flex-end' }}>
            <Button onClick={onClose} kind="secondary" size="sm" disabled={isPending}>
              Cancel
            </Button>
            <Button onClick={handleDelete} kind="danger" size="sm" loading={isPending}>
              Delete
            </Button>
          </Flex>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
};
