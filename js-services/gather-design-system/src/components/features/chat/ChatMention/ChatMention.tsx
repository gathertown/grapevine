import React, { memo } from 'react';

import { doIt, isNotNil } from '../../../../utils/fpHelpers';
import { Uuid } from '../../../../utils/uuid';
import { chatMentionRecipe } from './ChatMention.css';

type ChatMentionProps = {
  id: Uuid;
  type: 'userMention' | 'channelMention' | 'userGroupMention';
  onClick?: () => void;
};

export type ChannelMentionMap = Readonly<Record<Uuid, string>>;
export type UserMentionMap = Readonly<Record<Uuid, string>>;
export type UserGroupMentionMap = Readonly<Record<Uuid, string>>;

type ChatMentionContextType = {
  channelMentionMap: ChannelMentionMap;
  userMentionMap: UserMentionMap;
  userGroupMentionMap: UserGroupMentionMap;
  defaultUserMentionLabel?: string;
  defaultUserGroupMentionLabel?: string;
  defaultChannelMentionLabel?: string;
  highlightUserId?: string;
};

export const ChatMentionContext = React.createContext<ChatMentionContextType>({
  channelMentionMap: {},
  userMentionMap: {},
  userGroupMentionMap: {},
  defaultUserMentionLabel: undefined,
  defaultChannelMentionLabel: undefined,
  defaultUserGroupMentionLabel: undefined,
  highlightUserId: undefined,
});
export const ChatMentionProvider = ChatMentionContext.Provider;

export const ChatMention: React.FC<ChatMentionProps> = memo(function ChatMention({
  id,
  type,
  onClick,
}) {
  const {
    channelMentionMap,
    userMentionMap,
    userGroupMentionMap,
    defaultUserMentionLabel,
    defaultChannelMentionLabel,
    defaultUserGroupMentionLabel,
    highlightUserId,
  } = React.useContext(ChatMentionContext);
  const label = doIt(() => {
    switch (type) {
      case 'userMention':
        return userMentionMap[id] ?? defaultUserMentionLabel;
      case 'channelMention':
        return channelMentionMap[id] ?? defaultChannelMentionLabel;
      case 'userGroupMention':
        return userGroupMentionMap[id] ?? defaultUserGroupMentionLabel;
    }
  });

  const isHighlighted = type === 'userMention' && id === highlightUserId;

  const mentionContainerClass = chatMentionRecipe({
    highlighted: isHighlighted,
    isClickable: isNotNil(onClick),
  });

  return (
    // The data-type and data-id attributes in a <span> are used to identify the mention in the HTML
    // representation of the message, which Tiptap will use if someone copies and pastes this message
    // into the editor.
    <span
      className={mentionContainerClass}
      data-type={type}
      data-id={id}
      data-label={label}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {type === 'channelMention' ? '#' : '@'}
      {label}
    </span>
  );
});
