import { memo } from 'react';
import type { FC } from 'react';
import { Button, Flex, Modal, Text } from '@gathertown/gather-design-system';

type Props = {
  isOpen: boolean;
  onClose: VoidFunction;
  onConfirm: VoidFunction;
  isProcessing?: boolean;
};

export const BillingCancelModal: FC<Props> = memo(function BillingCancelModal({
  isOpen,
  onClose,
  onConfirm,
  isProcessing = false,
}) {
  return (
    <Modal open={isOpen} onOpenChange={onClose}>
      <Modal.Content style={{ width: '400px' }} variant="auto">
        <Modal.Header title="Cancel your plan" />
        <Modal.Body>
          <Flex direction="column" gap={16} align="center">
            <Text>
              Are you sure you want to cancel your Grapevine plan? Your plan will remain active
              until the end of the current billing period.
            </Text>
            <Flex gap={8} width="100%" justify="flex-end">
              <Button kind="secondary" onClick={onClose} disabled={isProcessing}>
                Keep plan
              </Button>
              <Button kind="danger" onClick={onConfirm} disabled={isProcessing}>
                {isProcessing ? 'Cancelling...' : 'Cancel plan'}
              </Button>
            </Flex>
          </Flex>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
});

BillingCancelModal.displayName = 'BillingCancelModal';
