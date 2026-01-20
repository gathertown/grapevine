import { EditorContent, JSONContent, useEditor } from '@tiptap/react';
import React, { memo, useCallback, useEffect, useMemo, useState } from 'react';

import { isNilOrEmpty } from '../../../../utils/fpHelpers';
import { tokens } from '@gathertown/gather-design-foundations';
import { Icon } from '../../../base/Icon/Icon';
import { Box } from '../../../layout/Box/Box';
import { transientMessageEditorContainerRecipe } from './TransientMessageComposer.css';
import { TransientMessageComposerExtension } from './transientMessageComposerConfig';

export type TransientMessageComposerProps = {
  placeholder: string;
  autoFocus?: boolean;
  onUpdate?: (content: { text: string; json: JSONContent }) => void;
  onSend?: (content: string, isEmpty: boolean) => void;
  userMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
  disableSend?: boolean;
};

export const TransientMessageComposer: React.FC<TransientMessageComposerProps> = memo(
  function TransientMessageComposer({
    placeholder,
    autoFocus,
    onUpdate,
    onSend,
    userMentionQueryFn,
    disableSend,
  }) {
    const [hasMentions, setHasMentions] = useState(false);

    const extensions = useMemo(
      () => [
        TransientMessageComposerExtension.configure({
          placeholder,
          userMentionQueryFn,
        }),
      ],
      [placeholder, userMentionQueryFn]
    );

    const editor = useEditor({
      extensions,
      content: undefined,
      autofocus: autoFocus,
      onUpdate: ({ editor }) => {
        const json = editor.getJSON();
        const text = editor.getText();

        onUpdate?.({ text, json });

        // Check for actual mention nodes in the document
        const hasActualMentions = JSON.stringify(json).includes('"type":"genericMention"');

        // Set hasMentions if there are actual mentions
        setHasMentions(hasActualMentions);
      },
      editorProps: {
        attributes: {
          class: transientMessageEditorContainerRecipe({
            hasMentions,
          }),
        },
      },
      immediatelyRender: true,
      // This allows us to only rerender the editor when necessary, rather than on every keystroke.
      // Docs: https://tiptap.dev/docs/examples/advanced/react-performance#react-tiptap-editor-integration
      shouldRerenderOnTransaction: false,
      onCreate: ({ editor }) => {
        editor.commands.focus('end');
      },
    });

    const handleSend = useCallback(() => {
      if (disableSend) return;
      const textContent = editor.getText();

      const isEmpty = isNilOrEmpty(textContent);

      const content = editor.getHTML();

      onSend?.(content, isEmpty);
      editor.commands.clearContent();
      setHasMentions(false);
    }, [editor, onSend, disableSend]);

    useEffect(() => {
      editor.on('onSubmit', () => {
        handleSend();
      });

      editor.on('destroy', () => {
        editor.off('onSubmit');
      });

      return () => {
        editor.off('onSubmit');
      };
    }, [editor, handleSend]);

    return (
      <Box position="relative">
        <Box position="absolute" left={tokens.scale[10]} top={tokens.scale[8]}>
          <Icon
            name={hasMentions ? 'handWave' : 'chatBubbleDashed'}
            size="md"
            color={hasMentions ? 'handraisePrimary' : 'secondaryOnDark'}
          />
        </Box>
        <EditorContent editor={editor} />
      </Box>
    );
  }
);
