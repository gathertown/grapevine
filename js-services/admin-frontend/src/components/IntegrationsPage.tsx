import { memo } from 'react';
import type { FC } from 'react';
import { Flex, Text, Box } from '@gathertown/gather-design-system';
import { IntegrationCard } from './IntegrationCard';
import { RequestIntegrationForm } from './RequestIntegrationForm';
import { useIntegrations } from '../contexts/IntegrationsContext';

const IntegrationsPage: FC = memo(() => {
  const { connectedIntegrations, availableIntegrations, hasConnectedIntegrations } =
    useIntegrations();

  return (
    <Flex direction="column" width="100%" style={{ gap: 44 }}>
      {/* Connected Section */}
      {hasConnectedIntegrations && (
        <Flex direction="column" style={{ gap: 8 }}>
          <Text fontSize="xxs" color="successPrimary" fontWeight="semibold">
            CONNECTED
          </Text>
          <Box
            borderRadius={8}
            borderColor="successPrimary"
            borderStyle="solid"
            borderWidth={1}
            p={16}
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(142px, 1fr))',
              gap: 12,
            }}
          >
            {connectedIntegrations.map((integration) => (
              <IntegrationCard key={integration.id} integrationId={integration.id} />
            ))}
          </Box>
        </Flex>
      )}

      {/* Available Section */}

      <Flex direction="column" gap={8} pb={24}>
        <Text fontSize="xxs" color="tertiary" fontWeight="semibold">
          AVAILABLE
        </Text>
        <Flex
          borderRadius={8}
          borderColor="tertiary"
          borderStyle="solid"
          borderWidth={1}
          p={16}
          gap={24}
          direction="column"
        >
          {availableIntegrations.length > 0 ? (
            <Box
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(142px, 1fr))',
                gap: 12,
              }}
            >
              {availableIntegrations.map((integration) => (
                <IntegrationCard key={integration.id} integrationId={integration.id} />
              ))}
            </Box>
          ) : null}
          <RequestIntegrationForm />
        </Flex>
      </Flex>
    </Flex>
  );
});

IntegrationsPage.displayName = 'IntegrationsPage';

export { IntegrationsPage };
