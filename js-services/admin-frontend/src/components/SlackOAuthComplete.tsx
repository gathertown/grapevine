import { useEffect, useState } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Flex, Text, Loader, Button } from '@gathertown/gather-design-system';

const SlackOAuthComplete: FC = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');
  const [errorMessage, setErrorMessage] = useState<string>('');

  useEffect(() => {
    // Check URL params for success/error status
    const urlParams = new URLSearchParams(window.location.search);
    const success = urlParams.get('success');
    const error = urlParams.get('error');

    let resultStatus: 'success' | 'error';
    let message = '';

    if (success === 'true') {
      resultStatus = 'success';
    } else if (error) {
      resultStatus = 'error';
      message = decodeURIComponent(error);
    } else {
      resultStatus = 'error';
      message = 'Unknown error occurred';
    }

    setStatus(resultStatus);
    setErrorMessage(message);

    // Redirect immediately on success
    if (resultStatus === 'success') {
      navigate('/onboarding/slack');
    }
    // For errors, let user see the message and manually navigate
  }, [navigate]);

  if (status === 'processing') {
    return (
      <Flex direction="column" align="center" justify="center" gap={24} minHeight="100vh">
        <Loader size="md" />
        <Text fontSize="lg" fontWeight="semibold">
          Completing Slack installation...
        </Text>
      </Flex>
    );
  }

  if (status === 'success') {
    return (
      <Flex direction="column" align="center" justify="center" gap={24} minHeight="100vh">
        <Text fontSize="xl">✅</Text>
        <Text fontSize="lg" fontWeight="semibold">
          Slack successfully connected!
        </Text>
        <Text fontSize="md" color="secondary" textAlign="center">
          Redirecting to homepage...
        </Text>
      </Flex>
    );
  }

  // Error state
  return (
    <Flex direction="column" align="center" justify="center" gap={24} minHeight="100vh">
      <Text fontSize="xl">❌</Text>
      <Text fontSize="lg" fontWeight="semibold">
        Connection failed
      </Text>
      <Flex maxWidth="400px">
        <Text fontSize="md" color="secondary" textAlign="center">
          {errorMessage || 'An error occurred while connecting to Slack.'}
        </Text>
      </Flex>
      <Button onClick={() => navigate('/')}>Go to Home</Button>
    </Flex>
  );
};

export { SlackOAuthComplete };
