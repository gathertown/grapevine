import { InputRule, Node, PasteRule } from '@tiptap/core';
import { DOMOutputSpec, Node as ProseMirrorNode } from '@tiptap/pm/model';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Suggestion, SuggestionOptions } from '@tiptap/suggestion';

import { EmojiAttributes } from '../../../../../utils/types';
import { isNil } from '../../../../../utils/fpHelpers';

export interface EmojiOptions<SuggestionItem = EmojiAttributes> {
  suggestion: Omit<SuggestionOptions<SuggestionItem>, 'editor'>;
  renderText: (props: { node: ProseMirrorNode }) => string;
  renderHTML: (props: {
    attributes: Record<string, string>;
    node: ProseMirrorNode;
  }) => DOMOutputSpec;

  /**
   * Gets emoji attributes by its shortcode.
   */
  getEmojiByShortcode: (shortcode: string) => EmojiAttributes | undefined;
}

const EmojiPluginKey = new PluginKey('emoji');
const EmojiPmPluginKey = new PluginKey('emojiProseMirror');

const emojiShortcodeInputRegex = /:([a-zA-Z0-9_\-+]+):$/;
const emojiShortcodePasteRegex = /:([a-zA-Z0-9_\-+]+):/g;

/**
 * This extension allows you to insert emojis in the chat composer.
 *
 * Inspiration and code samples taken from open source TipTap extensions such as mention:
 * - https://github.com/ueberdosis/tiptap/blob/main/packages/extension-mention/src/mention.ts
 */
export const Emoji = Node.create<EmojiOptions>({
  name: 'emoji',

  group: 'inline',
  inline: true,
  selectable: false,
  atom: true,

  addOptions() {
    return {
      renderText({ node }) {
        return node.attrs.emoji ?? node.attrs.shortcode;
      },
      renderHTML({ attributes, node }) {
        return ['span', attributes, node.attrs.emoji ?? node.attrs.shortcode];
      },
      suggestion: {
        char: ':',
        pluginKey: EmojiPluginKey,
        command: ({ editor, range, props }) => {
          // increase range.to by one when the next node is of type "text" and starts with a space
          // character
          const nodeAfter = editor.view.state.selection.$to.nodeAfter;
          const overrideSpace = nodeAfter?.text?.startsWith(' ');

          if (overrideSpace) {
            range.to += 1;
          }

          editor
            .chain()
            .focus()
            .insertContentAt(range, [
              {
                type: this.name,
                attrs: props,
              },
              {
                type: 'text',
                text: ' ',
              },
            ])
            .run();

          // get reference to `window` object from editor element, to support cross-frame JS usage
          editor.view.dom.ownerDocument.defaultView?.getSelection()?.collapseToEnd();
        },
        allow: ({ state, range }) => {
          const $from = state.doc.resolve(range.from);
          const type = state.schema.nodes[this.name];

          if (isNil(type)) return false;

          const allow = !!$from.parent.type.contentMatch.matchType(type);

          return allow;
        },
      },
      getEmojiByShortcode: () => undefined,
    };
  },

  addInputRules() {
    return [
      new InputRule({
        find: emojiShortcodeInputRegex,
        handler: ({ match, range, chain }) => {
          const shortcode = match[1];

          if (!shortcode) return;

          const potentialEmoji = this.options.getEmojiByShortcode(shortcode);

          if (!potentialEmoji) return;

          chain()
            .insertContentAt(
              range,
              {
                type: this.name,
                attrs: {
                  shortcode: potentialEmoji.shortcode,
                  emoji: potentialEmoji.emoji ?? null,
                },
              },
              { updateSelection: false }
            )
            .command(({ tr, state }) => {
              // Ensure that the `storedMarks` are set to the currently selected marks on input rule,
              // so that we retain the previous formatting after inserting the emoji.
              // ProseMirror reference: https://prosemirror.net/docs/ref/#state.EditorState.storedMarks
              tr.setStoredMarks(state.doc.resolve(state.selection.to - 1).marks());

              return true;
            })
            .run();
        },
      }),
    ];
  },

  addPasteRules() {
    return [
      new PasteRule({
        find: emojiShortcodePasteRegex,
        handler: ({ match, chain, range }) => {
          const shortcode = match[1];

          if (!shortcode) return;

          const potentialEmoji = this.options.getEmojiByShortcode(shortcode);

          if (!potentialEmoji) return;

          chain()
            .insertContentAt(
              range,
              {
                type: this.name,
                attrs: {
                  shortcode: potentialEmoji.shortcode,
                  emoji: potentialEmoji.emoji ?? null,
                },
              },
              { updateSelection: false }
            )
            .command(({ tr, state }) => {
              // Ensure that the `storedMarks` are set to the currently selected marks on paste, so
              // that we retain the previous formatting after inserting the emoji.
              // ProseMirror reference: https://prosemirror.net/docs/ref/#state.EditorState.storedMarks
              tr.setStoredMarks(state.doc.resolve(state.selection.to - 1).marks());

              return true;
            })
            .run();
        },
      }),
    ];
  },

  addAttributes() {
    return {
      shortcode: {
        default: null,
        parseHTML: (element) => element.getAttribute('data-shortcode'),
        renderHTML: (attributes) => {
          if (!attributes.shortcode) return {};

          return {
            'data-shortcode': attributes.shortcode,
          };
        },
      },

      emoji: {
        default: null,
        parseHTML: (element) => element.getAttribute('data-emoji'),
        renderHTML: (attributes) => {
          if (!attributes.emoji) return {};

          return {
            'data-emoji': attributes.emoji,
          };
        },
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: `span[data-type="${this.name}"]`,
      },
    ];
  },

  renderHTML({ node }) {
    const attributes = {
      'data-type': this.name,
      'data-shortcode': node.attrs.shortcode,
      'data-emoji': node.attrs.emoji,
    };

    const html = this.options.renderHTML({ attributes, node });

    if (typeof html === 'string') return ['span', attributes, html];

    return html;
  },

  renderText({ node }) {
    return this.options.renderText({ node });
  },

  addProseMirrorPlugins() {
    return [
      Suggestion({
        editor: this.editor,
        ...this.options.suggestion,
      }),

      new Plugin({
        key: EmojiPmPluginKey,

        props: {
          // Handle double-clicks on emoji nodes to select the entire emoji
          handleDoubleClickOn: (_view, pos, node) => {
            if (node.type !== this.type) return false;

            const from = pos;
            const to = from + node.nodeSize;

            this.editor.commands.setTextSelection({ from, to });

            return true;
          },
        },
      }),
    ];
  },
});
