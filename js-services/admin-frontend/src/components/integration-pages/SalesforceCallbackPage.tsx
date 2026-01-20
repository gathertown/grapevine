import { useEffect, useState } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Flex, Text, Loader, Button } from '@gathertown/gather-design-system';
import { SALESFORCE_ENABLED } from '../../constants';
import {
  handleSalesforceOAuthCallback,
  extractSalesforceTokens,
} from '../../utils/salesforceOAuth';
import { apiClient } from '../../api/client';
import { ConfigData, connectorConfigQueryKey } from '../../api/config';

const SalesforceCallbackPage: FC = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'processing' | 'error'>('processing');
  const [errorMessage, setErrorMessage] = useState<string>('');

  useEffect(() => {
    let cancelled = false;

    (async () => {
      // Redirect to integrations page if Salesforce is not enabled
      if (!SALESFORCE_ENABLED) {
        navigate('/integrations');
        return;
      }

      try {
        // Use oidc-client-ts to handle the OAuth callback
        const user = await handleSalesforceOAuthCallback();
        if (cancelled) return;

        if (!user) {
          throw new Error('No user data received from Salesforce');
        }

        // Extract tokens from the user object
        const tokens = extractSalesforceTokens(user);
        const refreshToken = tokens.refresh_token;
        if (!refreshToken) {
          throw new Error('No refresh token received from Salesforce');
        }

        // Send tokens to backend for secure storage
        await apiClient.post('/api/salesforce/config', {
          access_token: tokens.access_token,
          refresh_token: refreshToken,
          instance_url: tokens.instance_url,
          org_id: tokens.org_id,
          user_id: tokens.user_id,
        });
        if (cancelled) return;

        // Given the request above succeeded, update our local state to reflect the new changes as well
        queryClient.setQueryData<ConfigData>(connectorConfigQueryKey, (previous) => ({
          ...previous,
          SALESFORCE_REFRESH_TOKEN: refreshToken,
          SALESFORCE_INSTANCE_URL: tokens.instance_url,
          SALESFORCE_ORG_ID: tokens.org_id,
          SALESFORCE_USER_ID: tokens.user_id,
        }));

        // Redirect to Salesforce integration page
        navigate('/integrations/salesforce');
      } catch (error) {
        console.error('Error handling Salesforce OAuth callback:', error);
        setStatus('error');
        setErrorMessage(error instanceof Error ? error.message : 'Unknown error occurred');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [navigate, queryClient]);

  const handleRetry = () => {
    navigate('/integrations/salesforce');
  };

  const handleBackToIntegrations = () => {
    navigate('/integrations');
  };

  // Don't render if Salesforce is not enabled
  if (!SALESFORCE_ENABLED) {
    return null;
  }

  if (status === 'processing') {
    return (
      <Flex direction="column" align="center" justify="center" gap={24} minHeight="400px">
        <Loader size="md" />
        <Text fontSize="lg" fontWeight="semibold">
          Connecting to Salesforce...
        </Text>
        <Flex maxWidth="400px">
          <Text fontSize="md" color="secondary" textAlign="center">
            Please wait while we complete your Salesforce connection. This should only take a few
            seconds.
          </Text>
        </Flex>
      </Flex>
    );
  }

  // Error state
  return (
    <Flex direction="column" align="center" justify="center" gap={24} minHeight="400px">
      <Text fontSize="xl" fontWeight="bold">
        ❌ Connection Failed
      </Text>
      <Text fontSize="lg" fontWeight="semibold">
        Unable to connect to Salesforce
      </Text>
      <Flex maxWidth="400px">
        <Text fontSize="md" color="secondary" textAlign="center">
          {errorMessage || 'An unexpected error occurred while connecting to Salesforce.'}
        </Text>
      </Flex>
      <Flex gap={16}>
        <Button kind="outlineSecondary" onClick={handleRetry}>
          Try Again
        </Button>
        <Button onClick={handleBackToIntegrations}>Back to Integrations</Button>
      </Flex>
    </Flex>
  );
};

export { SalesforceCallbackPage };
