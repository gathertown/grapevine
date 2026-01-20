import * as DialogPrimitive from '@radix-ui/react-dialog';
import { VisuallyHidden } from '@radix-ui/react-visually-hidden';
import React from 'react';

import { tokens } from '@gathertown/gather-design-foundations';
import { usePortalContainer } from '../../../helpers/usePortalContainer';
import { Gothify } from '../../../providers/Gothify';
import { Flex } from '../../layout/Flex/Flex';
import { IconButton } from '../IconButton/IconButton';
import { Text } from '../Text/Text';
import {
  modalBodyStyle,
  modalFooterStyle,
  modalHeaderRecipe,
  ModalRecipe,
  modalRecipe,
  overlayStyle,
} from './Modal.css';

const ModalTrigger = React.memo(
  React.forwardRef<HTMLButtonElement, DialogPrimitive.DialogTriggerProps>(
    function ModalTrigger(props, forwardedRef) {
      return <DialogPrimitive.Trigger asChild {...props} ref={forwardedRef} />;
    }
  )
);
ModalTrigger.displayName = 'Modal.Trigger';

export type ModalContentProps = Omit<DialogPrimitive.DialogContentProps, 'className'> & {
  children: React.ReactNode;
  portalContainerId?: string;
  shouldFitToPortalContainer?: boolean;
  ariaDescription?: string;
  showOverlay?: boolean;
  theme?: 'dark';
  onOpenAutoFocus?: DialogPrimitive.DialogContentProps['onOpenAutoFocus'];
} & ModalRecipe;

const ModalContent = React.memo(
  React.forwardRef<HTMLDivElement, ModalContentProps>(function ModalContent(
    {
      children,
      portalContainerId,
      shouldFitToPortalContainer = false,
      ariaDescription,
      showOverlay = true,
      variant,
      theme,
      onOpenAutoFocus,
      ...props
    },
    forwardedRef
  ) {
    const portalContainer = usePortalContainer(portalContainerId);

    return (
      <DialogPrimitive.Portal container={portalContainer}>
        {showOverlay && (
          <DialogPrimitive.Overlay className={overlayStyle({ shouldFitToPortalContainer })} />
        )}
        <Gothify enabled={theme === 'dark'}>
          <DialogPrimitive.Content
            {...props}
            className={modalRecipe({ variant, shouldFitToPortalContainer })}
            ref={forwardedRef}
            aria-describedby={ariaDescription}
            onOpenAutoFocus={onOpenAutoFocus}
          >
            {children}
          </DialogPrimitive.Content>
        </Gothify>
      </DialogPrimitive.Portal>
    );
  })
);
ModalContent.displayName = 'Modal.Content';

const ModalHeader = React.memo(
  React.forwardRef(function ModalHeader(
    {
      beforeTitle,
      title,
      size = 'lg',
      afterTitle,
      hidden,
      withClose = true,
      noBorder = false,
      belowTitle,
      testId,
    }: {
      title: React.ReactNode;
      size?: Extract<keyof typeof tokens.fontSize, 'lg' | 'md'>;
      beforeTitle?: React.ReactNode;
      afterTitle?: React.ReactNode;
      belowTitle?: React.ReactNode;
      hidden?: boolean;
      withClose?: boolean;
      noBorder?: boolean;
      testId?: string;
    },
    containerRef: React.Ref<HTMLDivElement>
  ) {
    const e2eTestId = `${testId ?? title}-modal`;
    const headerContent = (
      <div
        className={modalHeaderRecipe({ size, noBorder })}
        ref={containerRef}
        data-testid={e2eTestId}
      >
        <Flex
          gap={8}
          align={belowTitle ? 'flex-start' : 'center'}
          justify="space-between"
          height="100%"
        >
          <Flex direction="column" gap={10}>
            <Flex gap={8} align="center" flexGrow={1}>
              {beforeTitle}
              <DialogPrimitive.Title>
                {typeof title === 'string' ? (
                  <Text fontSize="xl" fontWeight="semibold">
                    {title}
                  </Text>
                ) : (
                  <>{title}</>
                )}
              </DialogPrimitive.Title>
              {afterTitle}
            </Flex>
            {belowTitle}
          </Flex>

          {withClose && (
            <DialogPrimitive.Close
              aria-label={
                // TODO: Translation isn't supported in gather-design-system yet.
                // eslint-disable-next-line @gathertown/no-literal-string-in-jsx
                'Close'
              }
              asChild
              data-testid={`${e2eTestId}-close-button`}
            >
              <IconButton kind="transparent" icon="close" size="lg" />
            </DialogPrimitive.Close>
          )}
        </Flex>
      </div>
    );

    return hidden ? <VisuallyHidden>{headerContent}</VisuallyHidden> : headerContent;
  })
);
ModalHeader.displayName = 'Modal.Header';

const ModalBody = React.memo(function ModalBody({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div className={modalBodyStyle} style={style}>
      {children}
    </div>
  );
});
ModalBody.displayName = 'Modal.Body';

const ModalFooter = React.memo(function ModalFooter({ children }: { children: React.ReactNode }) {
  return <div className={modalFooterStyle}>{children}</div>;
});
ModalFooter.displayName = 'Modal.Footer';

const ModalRoot = DialogPrimitive.Root;
ModalRoot.displayName = 'Modal';

export interface ModalProps extends DialogPrimitive.DialogProps {}

// TODO [APP-8949]: Migrate to assignSlots
export const Modal = Object.assign(ModalRoot, {
  Content: ModalContent,
  Trigger: ModalTrigger,
  Header: ModalHeader,
  Body: ModalBody,
  Footer: ModalFooter,
});
