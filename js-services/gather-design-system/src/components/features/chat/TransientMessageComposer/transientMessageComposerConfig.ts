import { Extension } from '@tiptap/core';
import { Document } from '@tiptap/extension-document';
import { Mention, MentionOptions } from '@tiptap/extension-mention';
import { Paragraph } from '@tiptap/extension-paragraph';
import { Placeholder } from '@tiptap/extension-placeholder';
import { Text } from '@tiptap/extension-text';

import { generateMentionSuggestionConfig } from '../MessageComposerMention/generateMentionConfig';
import { transientMentionStyle } from './TransientMessageComposer.css';

export type MessageComposerOptions = {
  placeholder: string;
  userMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
};

type MentionExtensionOptions = MentionOptions & {
  queryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
};

const GenericMention = Extension.create<MentionExtensionOptions>({
  name: 'genericMentionWithOptions',
  addExtensions() {
    return [
      Mention.extend({
        name: 'genericMention',
      }).configure({
        HTMLAttributes: { class: transientMentionStyle },
        suggestion: generateMentionSuggestionConfig({
          char: '@',
          pluginKeyName: 'genericMention',
          queryFn: this.options.queryFn,
        }),
      }),
    ];
  },
});

const KeyboardShortcuts = Extension.create({
  name: 'keyboardHandler',

  addKeyboardShortcuts() {
    return {
      Enter: () => {
        this.editor.emit('onSubmit', { editor: this.editor });

        return true;
      },
    };
  },
});

export const TransientMessageComposerExtension = Extension.create<MessageComposerOptions>({
  name: 'transientMessageComposer',

  addExtensions() {
    return [
      Document,
      Paragraph,
      Text,
      Placeholder.configure({
        placeholder: this.options.placeholder,
      }),
      KeyboardShortcuts,
      GenericMention.configure({
        queryFn: this.options.userMentionQueryFn,
      }),
    ];
  },
});
