import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import {
  useCustomDocumentType,
  useCustomDocumentTypeStats,
  useUpdateCustomDocumentType,
  CustomDocumentTypeState,
} from '../customDataApi';
import { EditDocumentTypeModal } from './EditDocumentTypeModal';
import { DeleteDocumentTypeModal } from './DeleteDocumentTypeModal';
import {
  DefaultFieldsDisplay,
  FieldTypeBadge,
  RequiredBadge,
  StatusBadge,
  CODE_BLOCK_STYLES,
} from './shared';
import { customDataPath } from '../customDataRoutes';
import { buildCurlExample, EXAMPLE_FIELD_VALUES, getCustomDataEndpoints } from '../constants';
import { useAuth } from '../../../hooks/useAuth';

export const DocumentTypeDetailsPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const { data, isLoading, error, refetch } = useCustomDocumentType(id || '');
  const { data: stats } = useCustomDocumentTypeStats(id || '');
  const { mutate: updateType, isPending: isUpdating } = useUpdateCustomDocumentType();

  const tenantId = user?.tenantId || '';

  const documentType = data?.documentType;
  const documentCount = stats?.documentCount ?? 0;
  const customFields = documentType?.custom_fields?.fields || [];

  const isEnabled = documentType?.state === CustomDocumentTypeState.ENABLED;

  const handleToggleState = () => {
    if (!documentType) return;
    const newState = isEnabled ? CustomDocumentTypeState.DISABLED : CustomDocumentTypeState.ENABLED;
    updateType(
      { id: documentType.id, params: { state: newState } },
      {
        onSuccess: () => refetch(),
      }
    );
  };

  if (isLoading) {
    return (
      <Flex direction="column" gap={16} style={{ padding: '24px' }}>
        <Text>Loading...</Text>
      </Flex>
    );
  }

  if (error || !documentType) {
    return (
      <Flex direction="column" gap={16} style={{ padding: '24px' }}>
        <Text color="dangerPrimary">Error loading data type</Text>
        <Button onClick={() => navigate(customDataPath)} kind="secondary" size="sm">
          Back to Custom Data
        </Button>
      </Flex>
    );
  }

  const examplePayload = {
    name: `Example ${documentType.display_name}`,
    description: `Description for this ${documentType.display_name.toLowerCase()}`,
    content: `# ${documentType.display_name}\\n\\nMarkdown content goes here...`,
    ...Object.fromEntries(
      customFields.map((field) => {
        if (field.type === 'number') return [field.name, EXAMPLE_FIELD_VALUES.number];
        if (field.type === 'date') return [field.name, EXAMPLE_FIELD_VALUES.date];
        return [field.name, EXAMPLE_FIELD_VALUES.text(field.name)];
      })
    ),
  };

  const curlExample = buildCurlExample(tenantId, documentType.slug, examplePayload);

  return (
    <Flex direction="column" gap={24} style={{ padding: '24px', maxWidth: '900px' }}>
      {/* Back button */}
      <Button
        onClick={() => navigate(customDataPath)}
        kind="secondary"
        size="sm"
        style={{ alignSelf: 'flex-start' }}
      >
        &larr; Back to Custom Data
      </Button>

      {/* Header */}
      <Flex direction="row" style={{ justifyContent: 'space-between', alignItems: 'start' }}>
        <Flex direction="column" gap={4}>
          <Flex direction="row" gap={12} style={{ alignItems: 'center' }}>
            <Text fontSize="xl" fontWeight="bold">
              {documentType.display_name}
            </Text>
            <StatusBadge state={documentType.state} />
          </Flex>
          {documentType.description && (
            <Text fontSize="sm" color="secondary">
              {documentType.description}
            </Text>
          )}
        </Flex>
        <Flex direction="row" gap={8}>
          <Button onClick={handleToggleState} kind="secondary" size="sm" loading={isUpdating}>
            {isEnabled ? 'Disable' : 'Enable'}
          </Button>
          <Button onClick={() => setShowEditModal(true)} kind="secondary" size="sm">
            Edit
          </Button>
          <Button onClick={() => setShowDeleteModal(true)} kind="danger" size="sm">
            Delete
          </Button>
        </Flex>
      </Flex>

      {/* Stats */}
      <Text fontSize="sm">
        <strong>Documents:</strong> {documentCount}
      </Text>

      {/* API Endpoints */}
      <Flex direction="column" gap={12}>
        <Text fontSize="md" fontWeight="semibold">
          API Endpoints
        </Text>
        <Flex
          direction="column"
          style={{
            backgroundColor: '#fff',
            borderRadius: '8px',
            border: '1px solid #dee2e6',
            overflow: 'hidden',
          }}
        >
          {getCustomDataEndpoints(tenantId, documentType.slug).map((endpoint, index, arr) => (
            <Flex
              key={`${endpoint.method}-${endpoint.path}`}
              direction="row"
              gap={16}
              style={{
                padding: '12px 16px',
                borderBottom: index < arr.length - 1 ? '1px solid #eee' : 'none',
                alignItems: 'center',
              }}
            >
              <span
                style={{
                  padding: '4px 8px',
                  backgroundColor:
                    endpoint.method === 'POST'
                      ? '#dcfce7'
                      : endpoint.method === 'GET'
                        ? '#dbeafe'
                        : endpoint.method === 'PUT'
                          ? '#fef3c7'
                          : '#fee2e2',
                  color:
                    endpoint.method === 'POST'
                      ? '#166534'
                      : endpoint.method === 'GET'
                        ? '#1e40af'
                        : endpoint.method === 'PUT'
                          ? '#92400e'
                          : '#991b1b',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: 600,
                  fontFamily: 'monospace',
                  minWidth: '60px',
                  textAlign: 'center',
                }}
              >
                {endpoint.method}
              </span>
              <Flex direction="column" gap={2} style={{ flex: 1 }}>
                <code style={{ fontSize: '13px', color: '#374151' }}>{endpoint.path}</code>
                <Text fontSize="xs" color="secondary">
                  {endpoint.description}
                </Text>
              </Flex>
            </Flex>
          ))}
        </Flex>
      </Flex>

      {/* Default Fields */}
      <DefaultFieldsDisplay />

      {/* Custom Fields */}
      <Flex direction="column" gap={12}>
        <Text fontSize="md" fontWeight="semibold">
          Custom Fields ({customFields.length})
        </Text>
        {customFields.length === 0 ? (
          <Text fontSize="sm" color="secondary">
            No custom fields defined
          </Text>
        ) : (
          <Flex
            direction="column"
            style={{
              backgroundColor: '#fff',
              borderRadius: '8px',
              border: '1px solid #dee2e6',
              overflow: 'hidden',
            }}
          >
            {customFields.map((field, index) => (
              <Flex
                key={field.name}
                direction="column"
                gap={4}
                style={{
                  padding: '12px 16px',
                  borderBottom: index < customFields.length - 1 ? '1px solid #eee' : 'none',
                }}
              >
                <Flex direction="row" gap={8} style={{ alignItems: 'center' }}>
                  <Text fontSize="sm" fontWeight="semibold">
                    {field.name}
                  </Text>
                  <FieldTypeBadge type={field.type} />
                  {field.required && <RequiredBadge />}
                </Flex>
                {field.description && (
                  <Text fontSize="xs" color="secondary">
                    {field.description}
                  </Text>
                )}
              </Flex>
            ))}
          </Flex>
        )}
      </Flex>

      {/* API Example */}
      <Flex direction="column" gap={12}>
        <Text fontSize="md" fontWeight="semibold">
          API Example
        </Text>
        <Text fontSize="sm" color="secondary">
          Use the following example to ingest documents of this type via the API.
        </Text>
        <pre style={CODE_BLOCK_STYLES.dark}>{curlExample}</pre>
        <Flex direction="row" gap={8} style={{ alignItems: 'flex-start' }}>
          <Text fontSize="sm" color="secondary">
            Get your API key from{' '}
            <a href="/settings/api-keys" style={{ color: '#6366f1' }}>
              Settings → API Keys
            </a>
          </Text>
        </Flex>
        <Flex
          direction="row"
          gap={8}
          style={{
            padding: '12px 16px',
            backgroundColor: '#fef3c7',
            borderRadius: '8px',
            border: '1px solid #f59e0b',
            alignItems: 'center',
            color: '#92400e',
          }}
        >
          <Text fontSize="sm" color="inherit">
            <strong>Note:</strong> Maximum request size is 2MB per API call.
          </Text>
        </Flex>
      </Flex>

      {/* Modals */}
      {showEditModal && (
        <EditDocumentTypeModal
          documentType={documentType}
          onClose={() => setShowEditModal(false)}
          onSuccess={() => {
            setShowEditModal(false);
            refetch();
          }}
        />
      )}
      {showDeleteModal && (
        <DeleteDocumentTypeModal
          documentType={documentType}
          onClose={() => setShowDeleteModal(false)}
          onSuccess={() => {
            setShowDeleteModal(false);
            navigate(customDataPath);
          }}
        />
      )}
    </Flex>
  );
};
