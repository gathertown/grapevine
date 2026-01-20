import { useEffect, useState, useRef } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Flex, Text, Loader, Button, Icon } from '@gathertown/gather-design-system';
import { validateTrelloToken } from '../../utils/trelloOAuth';
import { apiClient } from '../../api/client';

enum CallbackStatus {
  Processing = 'processing',
  Success = 'success',
  Error = 'error',
}

const TrelloOAuthCallbackPage: FC = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState<CallbackStatus>(CallbackStatus.Processing);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const hasProcessed = useRef(false);

  useEffect(() => {
    // Prevent duplicate processing
    if (hasProcessed.current) {
      return;
    }

    const handleCallback = async () => {
      hasProcessed.current = true;

      const fragment = window.location.hash.substring(1);
      const params = new URLSearchParams(fragment);
      const token = params.get('token');

      if (!token) {
        setStatus(CallbackStatus.Error);
        setErrorMessage('No token found in authorization response');
        return;
      }

      if (!validateTrelloToken(token)) {
        setStatus(CallbackStatus.Error);
        setErrorMessage('Invalid token format received from Trello');
        return;
      }

      try {
        await apiClient.post('/api/config/save', {
          key: 'TRELLO_ACCESS_TOKEN',
          value: token,
        });

        setStatus(CallbackStatus.Success);

        setTimeout(() => {
          navigate('/integrations/trello?success=true');
        }, 2000);
      } catch (error) {
        setStatus(CallbackStatus.Error);
        setErrorMessage('Failed to save Trello access token. Please try again.');
        console.error('Failed to save Trello access token:', error);

        // Redirect back with error param after delay
        setTimeout(() => {
          navigate('/integrations/trello?error=true');
        }, 3000);
      }
    };

    handleCallback();
  }, [navigate]);

  if (status === CallbackStatus.Processing) {
    return (
      <Flex direction="column" mx="auto">
        <Flex direction="column" align="center" justify="center" gap={24}>
          <Loader size="md" />
          <Text fontSize="lg" fontWeight="semibold">
            Completing Trello authorization...
          </Text>
        </Flex>
      </Flex>
    );
  }

  if (status === CallbackStatus.Success) {
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
              Trello Account Connected
            </Text>
          </Flex>
          <Text fontSize="sm" color="secondary">
            Your Trello account is successfully connected and indexing data.
          </Text>
        </Flex>
        <Flex justify="center" style={{ marginTop: '10px' }}>
          <Text fontSize="sm" color="secondary" textAlign="center">
            Redirecting back to your integrations page...
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
          Trello Authorization Failed
        </Text>
        <Text fontSize="sm" color="secondary">
          {errorMessage}
        </Text>
      </Flex>
      <Button kind="primary" onClick={() => navigate('/integrations/trello', { replace: true })}>
        Back to Trello integration
      </Button>
    </Flex>
  );
};

export { TrelloOAuthCallbackPage };
