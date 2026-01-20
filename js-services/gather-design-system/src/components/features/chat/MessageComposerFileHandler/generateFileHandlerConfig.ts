import { Extension } from '@tiptap/core';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { isEmpty } from 'ramda';

type PluginProps = {
  onFilesAdded: (files: File[]) => void;
};

export type MessageComposerFileHandlerOptions = {
  onFilesAdded: (files: File[]) => void;
};

const createProseMirrorPlugin = ({ onFilesAdded }: PluginProps) =>
  new Plugin({
    key: new PluginKey('messageComposer'),
    props: {
      handleDrop(_view, event) {
        const files = Array.from(event.dataTransfer?.files ?? []);

        if (isEmpty(files)) return false;

        onFilesAdded(Array.from(files));

        event.preventDefault();
        event.stopPropagation();

        return true;
      },
      handlePaste(_view, event) {
        const files = Array.from(event.clipboardData?.files ?? []);

        if (isEmpty(files)) return false;

        onFilesAdded(files);

        event.preventDefault();
        event.stopPropagation();

        return true;
      },
    },
  });

export const MessageComposerFileHandlerExtension =
  Extension.create<MessageComposerFileHandlerOptions>({
    name: 'messageComposerFileHandler',

    addOptions() {
      return {
        onFilesAdded: () => {},
      };
    },

    addProseMirrorPlugins() {
      return [
        createProseMirrorPlugin({
          onFilesAdded: this.options.onFilesAdded,
        }),
      ];
    },
  });
