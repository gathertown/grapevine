import { Editor, Mark, markInputRule, markPasteRule, mergeAttributes } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';

export interface ItalicOptions {
  /**
   * HTML attributes to add to the italic element.
   * @default {}
   * @example { class: 'foo' }
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  HTMLAttributes: Record<string, any>;
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    italic: {
      /**
       * Set an italic mark
       * @example editor.commands.setItalic()
       */
      setItalic: () => ReturnType;
      /**
       * Toggle an italic mark
       * @example editor.commands.toggleItalic()
       */
      toggleItalic: () => ReturnType;
      /**
       * Unset an italic mark
       * @example editor.commands.unsetItalic()
       */
      unsetItalic: () => ReturnType;
    };
  }
}

/**
 * Matches an italic to a _italic_ on input.
 */
export const underscoreInputRegex = /(?:^|\s)(_(?!\s+_)((?:[^_]+))_(?!\s+_))$/;

/**
 * Matches an italic to a _italic_ on paste.
 */
export const underscorePasteRegex = /(?:^|\s)(_(?!\s+_)((?:[^_]+))_(?!\s+_))/g;

const handleKeyboardShortcut = (editor: Editor) => {
  editor.commands.toggleItalic();
  // HACK:return false so that handleKeyDown callback gets called which has access to the event
  // and can call stopPropagation. We don't want this keyboard shortcut to propagate to our input strategies.
  // TODO: Cleanup when we have context aware input strategies so that we can avoid calling overlapping keyboard shortcuts
  // when message composer is focused. https://linear.app/gather-town/issue/PDCT-84/implement-context-aware-input-strategies
  return false;
};

/**
 * This extension allows you to create italic text. It was copied and modified from the official
 * TipTap italic extension.
 * Source: https://github.com/ueberdosis/tiptap/blob/eb4e97d5f279610058fdde4fc2683a0cc553d9e9/packages/extension-italic/src/italic.ts
 * @see https://www.tiptap.dev/api/marks/italic
 */
export const Italic = Mark.create<ItalicOptions>({
  name: 'italic',

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey('italic'),
        props: {
          handleKeyDown: (_view, event) => {
            if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'i') {
              // stop propagation of the event since it is tied to busy mode
              event.stopPropagation();
              return true;
            }
            return false;
          },
        },
      }),
    ];
  },

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  parseHTML() {
    return [
      {
        tag: 'em',
      },
      {
        tag: 'i',
        // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
        getAttrs: (node) => (node as HTMLElement).style.fontStyle !== 'normal' && null,
      },
      {
        style: 'font-style=normal',
        clearMark: (mark) => mark.type.name === this.name,
      },
      {
        style: 'font-style=italic',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ['em', mergeAttributes(this.options.HTMLAttributes, HTMLAttributes), 0];
  },

  addCommands() {
    return {
      setItalic:
        () =>
        ({ commands }) =>
          commands.setMark(this.name),
      toggleItalic:
        () =>
        ({ commands }) =>
          commands.toggleMark(this.name),
      unsetItalic:
        () =>
        ({ commands }) =>
          commands.unsetMark(this.name),
    };
  },

  addKeyboardShortcuts() {
    return {
      'Mod-i': () => handleKeyboardShortcut(this.editor),
      'Mod-I': () => handleKeyboardShortcut(this.editor),
    };
  },

  addInputRules() {
    return [
      markInputRule({
        find: underscoreInputRegex,
        type: this.type,
      }),
    ];
  },

  addPasteRules() {
    return [
      markPasteRule({
        find: underscorePasteRegex,
        type: this.type,
      }),
    ];
  },
});
