import { useEffect, useState, useRef } from 'react';
import type { FC } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Flex, Text, Loader, Button, Icon } from '@gathertown/gather-design-system';
import { apiClient } from '../../api/client';

enum CallbackStatus {
  Processing = 'processing',
  Success = 'success',
  Error = 'error',
}

const LinearOAuthCallbackPage: FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<CallbackStatus>(CallbackStatus.Processing);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [redirectTo, setRedirectTo] = useState<string>('/integrations/linear');
  const hasProcessed = useRef(false);

  useEffect(() => {
    // Prevent duplicate processing
    if (hasProcessed.current) {
      return;
    }

    const handleCallback = async () => {
      hasProcessed.current = true;

      const code = searchParams.get('code');
      const state = searchParams.get('state');
      const error = searchParams.get('error');

      // Handle OAuth error
      if (error) {
        setStatus(CallbackStatus.Error);
        setErrorMessage(`OAuth error: ${error}`);
        setTimeout(() => {
          navigate('/integrations/linear?error=true');
        }, 3000);
        return;
      }

      // Validate required parameters
      if (!code || !state) {
        setStatus(CallbackStatus.Error);
        setErrorMessage('Missing authorization code or state');
        setTimeout(() => {
          navigate('/integrations/linear?error=true');
        }, 3000);
        return;
      }

      try {
        // Exchange code for tokens via backend
        const response = await apiClient.post<{ success: boolean; redirectTo?: string | null }>(
          '/api/linear/callback',
          { code, state }
        );

        // Use redirectTo from backend response, default to /integrations/linear
        const destination = response.redirectTo || '/integrations/linear';
        setRedirectTo(destination);
        setStatus(CallbackStatus.Success);

        setTimeout(() => {
          navigate(`${destination}?success=true`);
        }, 2000);
      } catch (error) {
        setStatus(CallbackStatus.Error);
        setErrorMessage('Failed to complete Linear authorization. Please try again.');
        console.error('Failed to complete Linear OAuth:', error);

        setTimeout(() => {
          navigate('/integrations/linear?error=true');
        }, 3000);
      }
    };

    handleCallback();
  }, [searchParams, navigate]);

  if (status === CallbackStatus.Processing) {
    return (
      <Flex direction="column" mx="auto">
        <Flex direction="column" align="center" justify="center" gap={24}>
          <Loader size="md" />
          <Text fontSize="lg" fontWeight="semibold">
            Completing Linear authorization...
          </Text>
        </Flex>
      </Flex>
    );
  }

  if (status === CallbackStatus.Success) {
    const isTriageBot = redirectTo === '/apps/triage';

    return (
      <Flex direction="column" maxWidth="800px" mx="auto">
        <Flex
          direction="column"
          gap={8}
          style={{
            padding: '16px',
            backgroundColor: '#d4edda',
            borderRadius: '8px',
            border: '1px solid #c3e6cb',
            maxWidth: '500px',
          }}
        >
          <Flex direction="row" align="center" gap={8}>
            <Icon name="checkCircle" size="md" color="successPrimary" />
            <Text fontSize="md" fontWeight="semibold" color="successPrimary">
              {isTriageBot ? 'Triage Bot Connected' : 'Linear Account Connected'}
            </Text>
          </Flex>
          <Text fontSize="sm" color="secondary">
            {isTriageBot
              ? 'Your triage bot is now connected to Linear with write access.'
              : 'Your Linear account is successfully connected and indexing data.'}
          </Text>
        </Flex>
        <Flex justify="center" style={{ marginTop: '10px' }}>
          <Text fontSize="sm" color="secondary" textAlign="center">
            {isTriageBot
              ? 'Redirecting back to triage bot page...'
              : 'Redirecting back to your integrations page...'}
          </Text>
        </Flex>
      </Flex>
    );
  }

  return (
    <Flex direction="column" maxWidth="800px" mx="auto" gap={24}>
      <Flex
        direction="column"
        gap={8}
        style={{
          padding: '16px',
          backgroundColor: '#f8d7da',
          borderRadius: '8px',
          border: '1px solid #f5c6cb',
          maxWidth: '500px',
          width: '100%',
        }}
      >
        <Text fontSize="md" fontWeight="semibold" color="dangerPrimary">
          Linear Authorization Failed
        </Text>
        <Text fontSize="sm" color="secondary">
          {errorMessage}
        </Text>
      </Flex>
      <Button kind="primary" onClick={() => navigate('/integrations/linear', { replace: true })}>
        Back to Linear integration
      </Button>
    </Flex>
  );
};

export { LinearOAuthCallbackPage };
