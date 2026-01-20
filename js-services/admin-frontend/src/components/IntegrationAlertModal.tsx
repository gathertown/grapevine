import { Flex, Text, Icon, Modal, Button, Box } from '@gathertown/gather-design-system';
import { useEffect } from 'react';

import type { Integration } from '../types';
import { useTrackEvent } from '../hooks/useTrackEvent';
import { useTrackIntegrationRequest } from '../hooks/useTrackIntegrationRequest';

type IntegrationAlertModalProps = {
  integration: Integration;
  open: boolean;
  onDismiss: VoidFunction;
  onSetup: VoidFunction;
};
export const IntegrationAlertModal = ({
  integration,
  open,
  onDismiss,
  onSetup,
}: IntegrationAlertModalProps) => {
  const { trackEvent } = useTrackEvent();
  const { trackIntegrationRequest } = useTrackIntegrationRequest();

  // Fire event when modal renders and is open
  useEffect(() => {
    if (open) {
      trackEvent('integration_alert_modal_viewed', {
        integration_name: integration.name,
        integration_type: integration.name.toLowerCase(),
        is_coming_soon: integration.comingSoon || false,
      });
    }
  }, [open, integration.name, integration.comingSoon, trackEvent]);

  const handleSetupClick = () => {
    trackEvent('integration_alert_modal_setup_clicked', {
      integration_name: integration.name,
      integration_type: integration.name.toLowerCase(),
      is_coming_soon: integration.comingSoon || false,
    });

    // Track integration request in Notion CRM when "Book a call" is clicked for coming soon integrations
    if (integration.comingSoon) {
      trackIntegrationRequest(integration.id);
    }

    onSetup();
  };
  return (
    <Modal open={open} onOpenChange={onDismiss}>
      <Modal.Content
        variant="default"
        showOverlay
        style={{ height: 'auto', maxHeight: 'none', maxWidth: 400 }}
      >
        <Modal.Body style={{ padding: 16, gap: 16 }}>
          <Flex direction="column" gap={16}>
            <Text fontSize="md" fontWeight="semibold">
              {integration.comingSoon
                ? `The ${integration.name} integration is in beta`
                : `What will Grapevine access from ${integration.name}?`}
            </Text>
            {integration.comingSoon ? (
              <Text color="tertiary" fontSize="sm">
                We'll reach out as soon as its ready for primetime! If you're interested in helping
                us test, book a call and tell us about your requirements!
              </Text>
            ) : (
              <Flex direction="column" gap={4}>
                {integration.accessItems.map((item) => {
                  return (
                    <Flex pl={8} direction="row" gap={4}>
                      <Box pt={1}>
                        <Icon name="check" size="xs" />
                      </Box>
                      <Text key={item} fontSize="sm">
                        {item}
                      </Text>
                    </Flex>
                  );
                })}
              </Flex>
            )}
          </Flex>

          {!integration.comingSoon && (
            <Text color="tertiary" textAlign="left" fontSize="xs">
              You can revoke Grapevine's access to your {integration.name} anytime. We'll never
              train models using your data.
            </Text>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Flex gap={8} justify="flex-end">
            <Button kind="secondary" onClick={onDismiss}>
              Cancel
            </Button>
            <Button onClick={handleSetupClick}>
              {integration.comingSoon ? 'Book a call' : `Setup ${integration.name}`}
            </Button>
          </Flex>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
};
