import { useState } from 'react';
import { Button, Flex, Text, Input, Modal } from '@gathertown/gather-design-system';
import {
  useUpdateCustomDocumentType,
  type CustomDocumentType,
  type CustomFieldDefinition,
} from '../customDataApi';
import { DefaultFieldsDisplay, CustomFieldsList, IngestEndpointDisplay } from './shared';
import { useAuth } from '../../../hooks/useAuth';

interface EditDocumentTypeModalProps {
  documentType: CustomDocumentType;
  onClose: () => void;
  onSuccess: () => void;
}

export const EditDocumentTypeModal = ({
  documentType,
  onClose,
  onSuccess,
}: EditDocumentTypeModalProps) => {
  const { user } = useAuth();
  const tenantId = user?.tenantId || '';
  const [displayName, setDisplayName] = useState(documentType.display_name);
  const [description, setDescription] = useState(documentType.description || '');
  const [customFields, setCustomFields] = useState<CustomFieldDefinition[]>(
    documentType.custom_fields?.fields || []
  );

  const { mutate: updateType, isPending, error } = useUpdateCustomDocumentType();

  const canSubmit = displayName.trim().length > 0 && !isPending;

  const handleSubmit = () => {
    if (!canSubmit) return;

    updateType(
      {
        id: documentType.id,
        params: {
          display_name: displayName.trim(),
          description: description.trim() || null,
          custom_fields: {
            fields: customFields,
            version: (documentType.custom_fields?.version ?? 0) + 1,
          },
        },
      },
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
        <Modal.Header title="Edit Data Type" />
        <Modal.Body style={{ padding: 0 }}>
          <Flex direction="column" style={{ maxHeight: '70vh', overflow: 'auto' }}>
            {/* Header section */}
            <Flex
              direction="column"
              gap={4}
              style={{ padding: '16px 24px', borderBottom: '1px solid #eee' }}
            >
              <Text fontSize="sm" color="secondary">
                Update the schema for {documentType.display_name}
              </Text>
            </Flex>

            {/* Form content */}
            <Flex direction="column" gap={20} style={{ padding: '24px' }}>
              {/* Name input */}
              <Flex direction="column" gap={6}>
                <Text fontSize="sm" fontWeight="semibold">
                  Name <span style={{ color: '#dc3545' }}>*</span>
                </Text>
                <Input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="e.g., Runbook, Policy Document, FAQ"
                  disabled={isPending}
                />
                <Flex
                  direction="row"
                  gap={8}
                  style={{
                    padding: '10px 12px',
                    backgroundColor: '#f8f9fa',
                    border: '1px solid #dee2e6',
                    borderRadius: '6px',
                    marginTop: '4px',
                    alignItems: 'center',
                  }}
                >
                  <Text fontSize="xs" color="secondary">
                    API Endpoint:
                  </Text>
                  <IngestEndpointDisplay
                    tenantId={tenantId}
                    slug={documentType.slug}
                    variant="inline"
                  />
                </Flex>
                <Text fontSize="xs" color="secondary">
                  Note: The slug cannot be changed after creation.
                </Text>
              </Flex>

              {/* Description input */}
              <Flex direction="column" gap={6}>
                <Text fontSize="sm" fontWeight="semibold">
                  Description
                </Text>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe the purpose of this document type..."
                  disabled={isPending}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #dee2e6',
                    borderRadius: '6px',
                    fontSize: '14px',
                    fontFamily: 'inherit',
                    resize: 'vertical',
                    minHeight: '80px',
                  }}
                />
              </Flex>

              {/* Divider */}
              <div style={{ borderTop: '1px solid #eee', margin: '4px 0' }} />

              {/* Default fields */}
              <DefaultFieldsDisplay />

              {/* Divider */}
              <div style={{ borderTop: '1px solid #eee', margin: '4px 0' }} />

              {/* Custom fields */}
              <CustomFieldsList fields={customFields} onChange={setCustomFields} />

              {/* Error display */}
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
          </Flex>
        </Modal.Body>
        <Modal.Footer>
          <Flex gap={8} style={{ justifyContent: 'flex-end' }}>
            <Button onClick={onClose} kind="secondary" size="sm" disabled={isPending}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              kind="primary"
              size="sm"
              loading={isPending}
              disabled={!canSubmit}
            >
              Save Changes
            </Button>
          </Flex>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
};
