import { Mark, markInputRule, markPasteRule, mergeAttributes } from '@tiptap/core';

export interface BoldOptions {
  /**
   * HTML attributes to add to the bold element.
   * @default {}
   * @example { class: 'foo' }
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  HTMLAttributes: Record<string, any>;
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    bold: {
      /**
       * Set a bold mark
       */
      setBold: () => ReturnType;
      /**
       * Toggle a bold mark
       */
      toggleBold: () => ReturnType;
      /**
       * Unset a bold mark
       */
      unsetBold: () => ReturnType;
    };
  }
}

/**
 * Matches a bold to a *bold* on input.
 */
export const starInputRegex = /(?:^|\s)(\*(?!\s+\*)((?:[^*]+))\*(?!\s+\*))$/;

/**
 * Matches a bold to a *bold* on paste.
 */
export const starPasteRegex = /(?:^|\s)(\*(?!\s+\*)((?:[^*]+))\*(?!\s+\*))/g;

/**
 * This extension allows you to mark text as bold. It was copied and modified from the official
 * TipTap bold extension.
 * Source: https://github.com/ueberdosis/tiptap/blob/eb4e97d5f279610058fdde4fc2683a0cc553d9e9/packages/extension-bold/src/bold.ts
 * @see https://tiptap.dev/api/marks/bold
 */
export const Bold = Mark.create<BoldOptions>({
  name: 'bold',

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  parseHTML() {
    return [
      {
        tag: 'strong',
      },
      {
        tag: 'b',
        // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
        getAttrs: (node) => (node as HTMLElement).style.fontWeight !== 'normal' && null,
      },
      {
        style: 'font-weight=400',
        clearMark: (mark) => mark.type.name === this.name,
      },
      {
        style: 'font-weight',
        // eslint-disable-next-line @typescript-eslint/consistent-type-assertions
        getAttrs: (value) => /^(bold(er)?|[5-9]\d{2,})$/.test(value as string) && null,
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ['strong', mergeAttributes(this.options.HTMLAttributes, HTMLAttributes), 0];
  },

  addCommands() {
    return {
      setBold:
        () =>
        ({ commands }) =>
          commands.setMark(this.name),
      toggleBold:
        () =>
        ({ commands }) =>
          commands.toggleMark(this.name),
      unsetBold:
        () =>
        ({ commands }) =>
          commands.unsetMark(this.name),
    };
  },

  addKeyboardShortcuts() {
    return {
      'Mod-b': () => this.editor.commands.toggleBold(),
      'Mod-B': () => this.editor.commands.toggleBold(),
    };
  },

  addInputRules() {
    return [
      markInputRule({
        find: starInputRegex,
        type: this.type,
      }),
    ];
  },

  addPasteRules() {
    return [
      markPasteRule({
        find: starPasteRegex,
        type: this.type,
      }),
    ];
  },
});
