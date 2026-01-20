import { useTrackEvent } from '../hooks/useTrackEvent';
import { useState } from 'react';
import { Text, Flex, Input, Button } from '@gathertown/gather-design-system';

export const RequestIntegrationForm = () => {
  const [otherSource, setOtherSource] = useState('');
  const [isRequestSent, setIsRequestSent] = useState(false);
  const { trackEvent } = useTrackEvent();

  const handleRequestSubmit = () => {
    const requests: string[] = [];
    if (otherSource.trim()) {
      requests.push(otherSource.trim());
    }

    if (requests.length > 0) {
      console.log(`Requested integrations: ${requests.join(', ')}`);

      // Track the integration request event
      trackEvent('integration_requested', {
        requested_integrations: [],
        freeform_requested_integration: otherSource.trim() || undefined,
      });

      setOtherSource('');
      setIsRequestSent(true);
      setTimeout(() => {
        setIsRequestSent(false);
      }, 3000);
    }
  };

  const hasRequests = otherSource.trim().length > 0;

  return (
    <Flex direction="column" gap={4}>
      <Text fontSize="xs" color="tertiary">
        Don't see an integration you need?
      </Text>
      <Flex direction="column" gap={8}>
        <Input
          fullWidth
          placeholder="Let us know which integrations you need, and we'll get back to you"
          value={otherSource}
          onChange={(e) => {
            setOtherSource(e.target.value);
            setIsRequestSent(false);
          }}
        />
        <Flex justify="flex-end">
          <Button
            kind={isRequestSent ? 'primary' : 'secondary'}
            leadingIcon={isRequestSent ? 'check' : 'send'}
            onClick={handleRequestSubmit}
            disabled={!hasRequests || isRequestSent}
          >
            {isRequestSent ? 'Request Sent!' : 'Send'}
          </Button>
        </Flex>
      </Flex>
    </Flex>
  );
};
