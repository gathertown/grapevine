import { useState } from 'react';
import { Button, Flex, Text, Input, Modal } from '@gathertown/gather-design-system';
import {
  useCreateCustomDocumentType,
  generateSlug,
  type CustomFieldDefinition,
} from '../customDataApi';
import { DefaultFieldsDisplay, CustomFieldsList, IngestEndpointDisplay } from './shared';
import { useAuth } from '../../../hooks/useAuth';

interface CreateDocumentTypeModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export const CreateDocumentTypeModal = ({ onClose, onSuccess }: CreateDocumentTypeModalProps) => {
  const { user } = useAuth();
  const tenantId = user?.tenantId || '';
  const [displayName, setDisplayName] = useState('');
  const [description, setDescription] = useState('');
  const [customFields, setCustomFields] = useState<CustomFieldDefinition[]>([]);

  const { mutate: createType, isPending, error } = useCreateCustomDocumentType();

  const slug = generateSlug(displayName);
  const canSubmit = displayName.trim().length > 0 && !isPending;

  const handleSubmit = () => {
    if (!canSubmit) return;

    createType(
      {
        display_name: displayName.trim(),
        description: description.trim() || undefined,
        custom_fields: customFields.length > 0 ? { fields: customFields, version: 1 } : undefined,
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
        <Modal.Header title="Create Data Type" />
        <Modal.Body style={{ padding: 0 }}>
          <Flex direction="column" style={{ maxHeight: '70vh', overflow: 'auto' }}>
            {/* Header section */}
            <Flex
              direction="column"
              gap={4}
              style={{ padding: '16px 24px', borderBottom: '1px solid #eee' }}
            >
              <Text fontSize="sm" color="secondary">
                Define a schema for your custom documents
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
                <Text fontSize="xs" color="secondary">
                  This will be used to identify the document type
                </Text>
                {slug && (
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
                    <IngestEndpointDisplay tenantId={tenantId} slug={slug} variant="inline" />
                  </Flex>
                )}
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
              Create Data Type
            </Button>
          </Flex>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
};
