import React, { memo, useEffect, useState } from 'react';

import { Button } from '../../../base/Button/Button';
import { Modal } from '../../../base/Modal/Modal';
import { Input } from '../../../form/Input/Input';
import { Flex } from '../../../layout/Flex/Flex';

type MessageComposerLinkModalProps = {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
  onSetLink: (link: string, text: string) => void;
  defaultValues?: {
    link: string;
    text: string;
  };
};

export const MessageComposerLinkModal: React.FC<MessageComposerLinkModalProps> = memo(
  function MessageComposerLinkModal({ isOpen, setIsOpen, defaultValues, onSetLink }) {
    const shouldResetValueRef = React.useRef(false);
    const [linkValue, setLinkValue] = useState(defaultValues?.link ?? '');
    const [textValue, setTextValue] = useState(defaultValues?.text ?? '');
    const [focusedInput, setFocusedInput] = useState<'link' | 'text' | null>('link');

    // Once the modal opens, we want to set the values to the initial values
    if (isOpen && shouldResetValueRef.current) {
      setLinkValue(defaultValues?.link ?? '');
      setTextValue(defaultValues?.text ?? '');
      shouldResetValueRef.current = false;

      if (!defaultValues?.text) {
        // If the text is empty, focus the text input.
        setFocusedInput('text');
      } else {
        // Otherwise focus the link input.
        setFocusedInput('link');
      }
    }

    useEffect(() => {
      if (!isOpen) {
        shouldResetValueRef.current = true;
        setFocusedInput(null);
      }
    }, [isOpen]);

    const handleLinkInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
      const { value } = event.target;
      setLinkValue(value);
    };

    const handleTextInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
      const { value } = event.target;
      setTextValue(value);
    };

    // The type of this will be from the form submission event
    const handleSave = (
      event: React.FormEvent<HTMLFormElement> | React.MouseEvent<HTMLButtonElement, MouseEvent>
    ) => {
      event.preventDefault();

      onSetLink(linkValue, textValue);
      setIsOpen(false);
    };

    return (
      <Modal open={isOpen} onOpenChange={() => setIsOpen(false)}>
        <Modal.Content showOverlay variant="auto">
          {/* TODO [CHAT-93]: Pass in i18n text from some config */}
          <Modal.Header title="Edit link" size="md" />
          <form onSubmit={handleSave}>
            <Flex direction="column" gap={24} p={16} width={360}>
              <Flex flexGrow={1} direction="column" gap={8}>
                {/* TODO [CHAT-93]: Pass in i18n text from some config */}
                <Input
                  label="Text"
                  value={textValue}
                  fullWidth
                  onChange={handleTextInputChange}
                  autoFocus={focusedInput === 'text'}
                />
                {/* TODO [CHAT-93]: Pass in i18n text from some config */}
                <Input
                  label="Link"
                  value={linkValue}
                  fullWidth
                  onChange={handleLinkInputChange}
                  autoFocus={focusedInput === 'link'}
                />
              </Flex>
              <Flex gap={4} justify="flex-end">
                {/* TODO [CHAT-93]: Pass in i18n text from some config */}
                <Button type="button" kind="secondary" onClick={() => setIsOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit">Save</Button>
              </Flex>
            </Flex>
          </form>
        </Modal.Content>
      </Modal>
    );
  }
);
