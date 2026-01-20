import { useNavigate } from 'react-router-dom';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { DocumentTypesManager } from './DocumentTypesManager';

export const CustomDataIntegrationPage = () => {
  const navigate = useNavigate();

  return (
    <Flex direction="column" gap={24} style={{ maxWidth: '800px', margin: '0 auto' }}>
      {/* Back button */}
      <Button
        onClick={() => navigate('/integrations')}
        kind="secondary"
        size="sm"
        style={{ alignSelf: 'flex-start' }}
      >
        &larr; Back to Integrations
      </Button>

      {/* Page header */}
      <Flex direction="column" gap={8}>
        <Text fontSize="xl" fontWeight="semibold">
          Custom Data
        </Text>
        <Text fontSize="sm" color="secondary">
          Define custom data types to ingest your own data into Grapevine. Create schemas for
          runbooks, policies, FAQs, or any structured content that doesn&apos;t fit existing
          connectors.
        </Text>
      </Flex>

      {/* How it works */}
      <Flex
        direction="column"
        gap={12}
        style={{
          padding: '16px',
          backgroundColor: '#f8f9fa',
          borderRadius: '8px',
          border: '1px solid #dee2e6',
        }}
      >
        <Text fontSize="sm" fontWeight="semibold">
          How it works
        </Text>
        <Flex direction="column" gap={8}>
          <Flex direction="row" gap={8} style={{ alignItems: 'flex-start' }}>
            <Flex style={{ minWidth: '20px' }}>
              <Text fontSize="sm" color="secondary">
                1.
              </Text>
            </Flex>
            <Text fontSize="sm" color="secondary">
              <strong>Create a Data Type</strong> - Define the schema with custom fields (e.g.,
              &quot;Runbook&quot; with severity, service, owner fields)
            </Text>
          </Flex>
          <Flex direction="row" gap={8} style={{ alignItems: 'flex-start' }}>
            <Flex style={{ minWidth: '20px' }}>
              <Text fontSize="sm" color="secondary">
                2.
              </Text>
            </Flex>
            <Text fontSize="sm" color="secondary">
              <strong>Get your API key</strong> - Go to{' '}
              <a href="/settings/api-keys" style={{ color: '#6366f1' }}>
                Settings → API Keys
              </a>{' '}
              to create an API key for authentication
            </Text>
          </Flex>
          <Flex direction="row" gap={8} style={{ alignItems: 'flex-start' }}>
            <Flex style={{ minWidth: '20px' }}>
              <Text fontSize="sm" color="secondary">
                3.
              </Text>
            </Flex>
            <Text fontSize="sm" color="secondary">
              <strong>Send data via API</strong> - POST JSON documents to your endpoint with the{' '}
              <code style={{ backgroundColor: '#e9ecef', padding: '2px 4px', borderRadius: '4px' }}>
                X-API-Key
              </code>{' '}
              header
            </Text>
          </Flex>
        </Flex>
      </Flex>

      {/* Data Types Manager */}
      <DocumentTypesManager />
    </Flex>
  );
};
