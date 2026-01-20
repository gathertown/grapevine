import type { FC, ReactNode } from 'react';
import { Flex, Modal } from '@gathertown/gather-design-system';
import { theme, tokens } from '@gathertown/gather-design-foundations';

interface IntegrationModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
  footer?: ReactNode;
  title?: string;
  width?: string | number;
}

export const IntegrationModal: FC<IntegrationModalProps> = ({
  open,
  onOpenChange,
  children,
  footer,
  title,
  width,
}) => {
  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <Modal.Content
        variant="default"
        showOverlay
        style={{
          outline: `1px solid ${theme.border.tertiary}`,
          border: `8px solid ${theme.bg.secondary}`,
          ...(width ? { width } : {}),
        }}
      >
        {title && <Modal.Header title={title} />}
        <Modal.Body>{children}</Modal.Body>
        <Flex
          backgroundColor="primary"
          style={{
            display: 'flex',
            flexDirection: 'row',
            justifyContent: 'flex-end',
            padding: `${tokens.scale[12]} ${tokens.scale[16]}`,
            bottom: 0,
            position: 'sticky',
          }}
        >
          {footer && footer}
        </Flex>
      </Modal.Content>
    </Modal>
  );
};
