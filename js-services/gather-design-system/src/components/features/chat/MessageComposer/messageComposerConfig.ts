import { Editor, Extension } from '@tiptap/core';
import { Blockquote } from '@tiptap/extension-blockquote';
import { BulletList } from '@tiptap/extension-bullet-list';
import { Code } from '@tiptap/extension-code';
import { Document } from '@tiptap/extension-document';
import { Gapcursor } from '@tiptap/extension-gapcursor';
import { History } from '@tiptap/extension-history';
import { Link } from '@tiptap/extension-link';
import { ListItem } from '@tiptap/extension-list-item';
import { Mention, MentionOptions } from '@tiptap/extension-mention';
import { OrderedList } from '@tiptap/extension-ordered-list';
import { Paragraph } from '@tiptap/extension-paragraph';
import { Placeholder } from '@tiptap/extension-placeholder';
import { Strike } from '@tiptap/extension-strike';
import { Text } from '@tiptap/extension-text';

import { EmojiAttributes } from '../../../../utils/types';
import { chatMentionRecipe } from '../ChatMention/ChatMention.css';
import { generateEmojiSuggestionConfig } from '../MessageComposerEmoji/generateEmojiConfig';
import { MessageComposerFileHandlerExtension } from '../MessageComposerFileHandler/generateFileHandlerConfig';
import { generateMentionSuggestionConfig } from '../MessageComposerMention/generateMentionConfig';
import { Bold } from './extensions/boldExtension';
import { CodeBlock } from './extensions/codeBlockExtension';
import { Emoji } from './extensions/emojiExtension';
import { HardBreak } from './extensions/hardBreak';
import { Italic } from './extensions/italicExtension';

declare module '@tiptap/core' {
  interface EditorEvents {
    onSubmit: { editor: Editor };
  }

  interface Commands<ReturnType> {
    custom: {
      callbackOnFocus: (callback: () => void) => ReturnType;
    };
  }
}

export type MessageComposerOptions = {
  placeholder: string;
  userMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
  channelMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
  userGroupMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
  onFilesAdded: (files: File[]) => void;
  emojiQueryFn: (args: { query: string }) => Array<EmojiAttributes>;
  getEmojiAttributeMap: () => Record<string, EmojiAttributes>;
};

type UserAndUserGroupMentionExtensionOptions = {
  userMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
  userGroupMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
};

const UserAndUserGroupMention = Extension.create<UserAndUserGroupMentionExtensionOptions>({
  name: 'userAndUserGroupMentionWithOptions',
  addExtensions() {
    return [
      Mention.extend({
        name: 'userAndUserGroupMention',
        addAttributes() {
          return {
            ...this.parent?.(),
            type: {
              default: null,
              parseHTML: (element) => element.getAttribute('data-type'),
              renderHTML: ({ type }) => (type ? { 'data-type': type } : {}),
            },
          };
        },
        parseHTML() {
          return [
            { tag: `span[data-type="userMention"]` },
            { tag: `span[data-type="userGroupMention"]` },
          ];
        },
      }).configure({
        HTMLAttributes: { class: chatMentionRecipe({ highlighted: false }) },
        suggestion: generateMentionSuggestionConfig({
          char: '@',
          pluginKeyName: 'userAndUserGroupMention',
          queryFn: (queryArgs) => [
            ...this.options.userMentionQueryFn(queryArgs).map((item) => ({
              ...item,
              type: 'userMention' as const,
            })),
            ...this.options.userGroupMentionQueryFn(queryArgs).map((item) => ({
              ...item,
              type: 'userGroupMention' as const,
            })),
          ],
        }),
      }),
    ];
  },
});

type ChannelMentionExtensionOptions = MentionOptions & {
  queryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
};

const ChannelMention = Extension.create<ChannelMentionExtensionOptions>({
  name: 'channelMentionWithOptions',
  addExtensions() {
    return [
      Mention.extend({
        name: 'channelMention',
      }).configure({
        HTMLAttributes: { class: chatMentionRecipe({ highlighted: false }) },
        suggestion: generateMentionSuggestionConfig({
          char: '#',
          pluginKeyName: 'channelMention',
          queryFn: this.options.queryFn,
        }),
      }),
    ];
  },
});

const KeyboardShortcuts = Extension.create({
  name: 'keyboardHandler',

  addKeyboardShortcuts() {
    const handleEnter = () =>
      this.editor.commands.first(({ commands }) => [
        () => commands.newlineInCode(),
        () => commands.splitListItem('listItem'),
        () => commands.createParagraphNear(),
        () => commands.liftEmptyBlock(),
        () => commands.splitBlock(),
      ]);

    return {
      Enter: () => {
        this.editor.emit('onSubmit', { editor: this.editor });

        return true;
      },
      'Shift-Enter': handleEnter,
      'Mod-Enter': handleEnter,
      'Control-Enter': handleEnter,
    };
  },
});

export const MessageComposerExtension = Extension.create<MessageComposerOptions>({
  name: 'messageComposer',

  addExtensions() {
    return [
      Document,
      Blockquote,
      Bold,
      Italic,
      BulletList,
      Code,
      Gapcursor,
      History,
      ListItem,
      OrderedList,
      Paragraph,
      Strike,
      Text,
      KeyboardShortcuts,
      // The order here is important. `CodeBlock` should come after `KeyboardShortcuts` so that the
      // triple-enter to exit the code block functions as expected.
      CodeBlock,
      Link.configure({
        openOnClick: false,
        autolink: true,
      }),
      Placeholder.configure({
        placeholder: this.options.placeholder,
      }),
      UserAndUserGroupMention.configure({
        userMentionQueryFn: this.options.userMentionQueryFn,
        userGroupMentionQueryFn: this.options.userGroupMentionQueryFn,
      }),
      ChannelMention.configure({
        queryFn: this.options.channelMentionQueryFn,
      }),
      MessageComposerFileHandlerExtension.configure({
        onFilesAdded: this.options.onFilesAdded,
      }),
      Emoji.configure({
        getEmojiByShortcode: (shortcode) => this.options.getEmojiAttributeMap()[shortcode],
        suggestion: generateEmojiSuggestionConfig({
          char: ':',
          queryFn: this.options.emojiQueryFn,
        }),
      }),
      HardBreak,
    ];
  },
  addCommands() {
    return {
      callbackOnFocus:
        (callback) =>
        ({ editor }) => {
          const editorElement = editor.view.dom;

          const onFocusHandler = () => {
            callback();
          };

          editorElement.addEventListener('focus', onFocusHandler, { once: true });

          return true;
        },
    };
  },
});
