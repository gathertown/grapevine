import { useState } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import {
  useCustomDocumentTypes,
  useUpdateCustomDocumentType,
  CustomDocumentTypeState,
  type CustomDocumentType,
} from '../customDataApi';
import { DocumentTypeCard } from './DocumentTypeCard';
import { CreateDocumentTypeModal } from './CreateDocumentTypeModal';
import { EditDocumentTypeModal } from './EditDocumentTypeModal';
import { DeleteDocumentTypeModal } from './DeleteDocumentTypeModal';
import { useAuth } from '../../../hooks/useAuth';

export const DocumentTypesManager = () => {
  const { user } = useAuth();
  const tenantId = user?.tenantId || '';
  const { data, isLoading, error, refetch } = useCustomDocumentTypes();
  const {
    mutate: updateType,
    isPending: isUpdating,
    variables: updatingVariables,
  } = useUpdateCustomDocumentType();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [editingType, setEditingType] = useState<CustomDocumentType | null>(null);
  const [deletingType, setDeletingType] = useState<CustomDocumentType | null>(null);

  const handleToggleState = (type: CustomDocumentType) => {
    const newState =
      type.state === CustomDocumentTypeState.ENABLED
        ? CustomDocumentTypeState.DISABLED
        : CustomDocumentTypeState.ENABLED;
    updateType({ id: type.id, params: { state: newState } }, { onSuccess: () => refetch() });
  };

  const documentTypes = (data?.documentTypes || []).filter(
    (type) => type.state !== CustomDocumentTypeState.DELETED
  );

  // Loading state
  if (isLoading) {
    return (
      <Flex direction="column" gap={8}>
        <Text fontSize="sm">Loading document types...</Text>
      </Flex>
    );
  }

  // Error state - still show UI with ability to create
  if (error) {
    return (
      <Flex
        direction="column"
        style={{
          backgroundColor: '#fff',
          borderRadius: '12px',
          padding: '24px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        }}
      >
        {/* Header */}
        <Flex
          direction="row"
          style={{
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: '20px',
          }}
        >
          <Flex direction="column" gap={4}>
            <Text fontSize="lg" fontWeight="semibold">
              Custom Data Types
            </Text>
            <Text fontSize="sm" color="secondary">
              Define schemas for your custom data sources and ingest documents via API
            </Text>
          </Flex>
          <Button onClick={() => setIsCreateModalOpen(true)} kind="primary" size="sm">
            + Create Data Type
          </Button>
        </Flex>

        {/* Error message */}
        <Flex
          direction="column"
          gap={8}
          style={{
            padding: '16px',
            backgroundColor: '#fff5f5',
            borderRadius: '8px',
            border: '1px solid #fed7d7',
          }}
        >
          <Text fontSize="sm" color="dangerPrimary">
            Unable to load document types. The backend API may not be available yet.
          </Text>
          <Button
            onClick={() => refetch()}
            kind="secondary"
            size="sm"
            style={{ alignSelf: 'flex-start' }}
          >
            Retry
          </Button>
        </Flex>

        {/* Create modal */}
        {isCreateModalOpen && (
          <CreateDocumentTypeModal
            onClose={() => setIsCreateModalOpen(false)}
            onSuccess={() => {
              setIsCreateModalOpen(false);
              refetch();
            }}
          />
        )}
      </Flex>
    );
  }

  // Empty state
  if (documentTypes.length === 0) {
    return (
      <Flex
        direction="column"
        style={{
          backgroundColor: '#fff',
          borderRadius: '12px',
          padding: '24px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        }}
      >
        {/* Header */}
        <Flex
          direction="row"
          style={{
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: '40px',
          }}
        >
          <Flex direction="column" gap={4}>
            <Text fontSize="lg" fontWeight="semibold">
              Custom Data Types
            </Text>
            <Text fontSize="sm" color="secondary">
              Define schemas for your custom data sources and ingest documents via API
            </Text>
          </Flex>
          <Button onClick={() => setIsCreateModalOpen(true)} kind="primary" size="sm">
            + Create Data Type
          </Button>
        </Flex>

        {/* Empty state content */}
        <Flex
          direction="column"
          gap={16}
          style={{
            alignItems: 'center',
            padding: '40px 20px',
          }}
        >
          <span style={{ fontSize: '48px' }}>📄</span>
          <Text fontSize="md" fontWeight="semibold">
            No custom document types yet
          </Text>
          <Text fontSize="sm" color="secondary">
            Create a document type to start ingesting your custom data via API
          </Text>
          <Button onClick={() => setIsCreateModalOpen(true)} kind="primary" size="md">
            + Create Your First Data Type
          </Button>
        </Flex>

        {/* Create modal */}
        {isCreateModalOpen && (
          <CreateDocumentTypeModal
            onClose={() => setIsCreateModalOpen(false)}
            onSuccess={() => {
              setIsCreateModalOpen(false);
              refetch();
            }}
          />
        )}
      </Flex>
    );
  }

  // List state
  return (
    <Flex
      direction="column"
      style={{
        backgroundColor: '#fff',
        borderRadius: '12px',
        padding: '24px',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      }}
    >
      {/* Header */}
      <Flex
        direction="row"
        style={{ justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}
      >
        <Flex direction="column" gap={4}>
          <Text fontSize="lg" fontWeight="semibold">
            Custom Data Types
          </Text>
          <Text fontSize="sm" color="secondary">
            Define schemas for your custom data sources and ingest documents via API
          </Text>
        </Flex>
        <Button onClick={() => setIsCreateModalOpen(true)} kind="primary" size="sm">
          + Create Data Type
        </Button>
      </Flex>

      {/* Document type cards */}
      <Flex direction="column" gap={12}>
        {documentTypes.map((type) => (
          <DocumentTypeCard
            key={type.id}
            documentType={type}
            tenantId={tenantId}
            onEdit={() => setEditingType(type)}
            onDelete={() => setDeletingType(type)}
            onToggleState={() => handleToggleState(type)}
            isToggling={isUpdating && updatingVariables?.id === type.id}
          />
        ))}
      </Flex>

      {/* Modals */}
      {isCreateModalOpen && (
        <CreateDocumentTypeModal
          onClose={() => setIsCreateModalOpen(false)}
          onSuccess={() => {
            setIsCreateModalOpen(false);
            refetch();
          }}
        />
      )}

      {editingType && (
        <EditDocumentTypeModal
          documentType={editingType}
          onClose={() => setEditingType(null)}
          onSuccess={() => {
            setEditingType(null);
            refetch();
          }}
        />
      )}

      {deletingType && (
        <DeleteDocumentTypeModal
          documentType={deletingType}
          onClose={() => setDeletingType(null)}
          onSuccess={() => {
            setDeletingType(null);
            refetch();
          }}
        />
      )}
    </Flex>
  );
};
