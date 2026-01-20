import { useEffect, useState } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Flex, Text, Loader, Button } from '@gathertown/gather-design-system';
import { connectorConfigQueryKey } from '../../api/config';

const GongOAuthComplete: FC = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');
  const [errorMessage, setErrorMessage] = useState<string>('');

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const success = urlParams.get('success');
    const error = urlParams.get('error');

    if (success === 'true') {
      setStatus('success');
      queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });

      const timer = setTimeout(() => {
        navigate('/integrations/gong', { replace: true });
      }, 2000);

      return () => clearTimeout(timer);
    }

    setStatus('error');
    setErrorMessage(
      error ? decodeURIComponent(error) : 'Unknown error occurred while connecting to Gong.'
    );
    return undefined;
  }, [queryClient, navigate]);

  if (status === 'processing') {
    return (
      <Flex direction="column" align="center" justify="center" gap={24} minHeight="100vh">
        <Loader size="md" />
        <Text fontSize="lg" fontWeight="semibold">
          Completing Gong connection...
        </Text>
      </Flex>
    );
  }

  if (status === 'success') {
    return (
      <Flex direction="column" align="center" justify="center" gap={24} minHeight="100vh">
        <Text fontSize="xl">✅</Text>
        <Text fontSize="lg" fontWeight="semibold">
          Gong successfully connected!
        </Text>
        <Text fontSize="md" color="secondary" textAlign="center">
          Redirecting back to your integrations page...
        </Text>
      </Flex>
    );
  }

  return (
    <Flex direction="column" align="center" justify="center" gap={24} minHeight="100vh">
      <Text fontSize="xl">❌</Text>
      <Text fontSize="lg" fontWeight="semibold">
        Gong connection failed
      </Text>
      <Flex maxWidth="400px">
        <Text fontSize="md" color="secondary" textAlign="center">
          {errorMessage}
        </Text>
      </Flex>
      <Button kind="primary" onClick={() => navigate('/integrations/gong', { replace: true })}>
        Back to Gong integration
      </Button>
    </Flex>
  );
};

export { GongOAuthComplete };
