import React, { memo } from 'react';

import { IconButton } from '../../../base/IconButton/IconButton';
import { Text } from '../../../base/Text/Text';
import { Flex } from '../../../layout/Flex/Flex';
import { linkStyle } from './MessageComposerLinkPopover.css';

type MessageComposerLinkPopoverProps = {
  url: string;
  onClickEdit: () => void;
};

export const MessageComposerLinkPopover: React.FC<MessageComposerLinkPopoverProps> = memo(
  function MessageComposerLinkPopover({ url, onClickEdit }) {
    return (
      <Flex
        pl={8}
        backgroundColor="primary"
        borderColor="tertiary"
        borderWidth={1}
        borderStyle="solid"
        borderRadius={4}
        overflow="hidden"
        align="center"
      >
        <Text color="tertiary" fontSize="xs" truncate>
          <a href={url} rel="noopener noreferrer" target="_blank" className={linkStyle}>
            {url}
          </a>
        </Text>
        <Flex flexShrink={0} py={2} pr={2}>
          <IconButton
            icon="pen"
            size="xs"
            kind="transparent"
            // TODO [CHAT-93]: Pass in i18n text from some config
            tooltip="Edit link"
            onClick={onClickEdit}
          />
        </Flex>
      </Flex>
    );
  }
);
