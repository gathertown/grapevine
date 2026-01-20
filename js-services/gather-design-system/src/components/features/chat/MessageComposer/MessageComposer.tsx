import {
  BubbleMenu,
  EditorContent,
  isTextSelection,
  useEditor,
  useEditorState,
} from '@tiptap/react';
import { LayoutGroup, motion } from 'framer-motion';
import { noop } from 'lodash';
import { equals, isEmpty } from 'ramda';
import React, { memo, useCallback, useEffect, useImperativeHandle, useMemo, useRef } from 'react';

import {
  GATHER_AI_SUPPORTED_ATTACHMENT_MIME_TYPES,
  SUPPORTED_CHAT_ATTACHMENT_MIME_TYPES,
} from '../../../../utils/constants';
import { EmojiAttributes } from '../../../../utils/types';
import { compact, isBlank, isNil, isNilOrEmpty, isNotNil, just } from '../../../../utils/fpHelpers';
import { tokens } from '@gathertown/gather-design-foundations';
import { cx } from '../../../../helpers/classnames';
import { Box } from '../../../layout/Box/Box';
import { Flex } from '../../../layout/Flex/Flex';
import {
  ComposerAction,
  MessageComposerActionsToolbar,
} from '../MessageComposerActionsToolbar/MessageComposerActionsToolbar';
import { MessageComposerLinkModal } from '../MessageComposerLinkModal/MessageComposerLinkModal';
import { MessageComposerLinkPopover } from '../MessageComposerLinkPopover/MessageComposerLinkPopover';
import { messageContentStyle, messageEditorContainerRecipe } from './MessageComposer.css';
import { MessageComposerExtension } from './messageComposerConfig';

type EmojiPickerComponent = React.ComponentType<{
  onEmojiSelect: (emoji: { emoji: string; label: string; shortcode: string | null }) => void;
  onOpenChange?: (open: boolean) => void;
}>;

export type MessageComposerRef = {
  focus: () => void;
};

export type MessageComposerProps = {
  defaultMessage: string;
  placeholder: string;
  autoFocus?: boolean;
  onUpdate?: (message: string) => void;
  onSend?: (content: string, isEmpty: boolean) => void;
  onClickCancel?: () => void;
  onEscape?: () => void;
  onUpArrowToEdit?: () => void;
  maxHeight?: number;
  userMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
  channelMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
  userGroupMentionQueryFn: (args: { query: string }) => Array<{ id: string; label: string }>;
  emojiQueryFn: (args: { query: string }) => Array<EmojiAttributes>;
  getEmojiAttributeMap: () => Record<string, EmojiAttributes>;
  submitActionsType?: 'default' | 'edit';
  onFilesAdded?: (files: File[]) => Promise<void>;
  emojiPickerComponent?: EmojiPickerComponent;
  afterContent?: React.ReactNode;
  disableSendButton?: boolean;
  disableSendButtonIfEmpty?: boolean;
  showFormattingActionsInline?: boolean;
  showMentionsAction?: boolean;
  allowAttachments?: boolean;
  dataTestId?: string;
  messageComposerRef?: React.RefObject<MessageComposerRef | null>;
  onEnterBlockedDuringDisabled?: () => void;
  kind?: 'default' | 'gatherAI';
  showAbortButton?: boolean;
  handleAbort?: () => void;
  disabled?: boolean;
};

export const MessageComposer = memo(function MessageComposer({
  defaultMessage,
  placeholder,
  autoFocus,
  onUpdate,
  onSend,
  onClickCancel,
  onEscape,
  onUpArrowToEdit,
  maxHeight = 200,
  userMentionQueryFn,
  channelMentionQueryFn,
  userGroupMentionQueryFn,
  emojiQueryFn,
  getEmojiAttributeMap,
  onFilesAdded,
  showFormattingActionsInline = true,
  submitActionsType = 'default',
  emojiPickerComponent,
  disableSendButton,
  disableSendButtonIfEmpty,
  afterContent,
  allowAttachments = true,
  showMentionsAction = true,
  dataTestId,
  messageComposerRef,
  onEnterBlockedDuringDisabled,
  kind = 'default',
  showAbortButton = false,
  handleAbort,
  disabled = false,
}: MessageComposerProps) {
  const [isLinkModelOpen, setIsLinkModelOpen] = React.useState(false);
  const [hasExpanded, setHasExpanded] = React.useState(false);
  const fileSelectorRef = React.useRef<HTMLInputElement>(null);

  const isGatherAI = kind === 'gatherAI';

  const showActionsInline = isGatherAI && !hasExpanded && !afterContent;

  const extensions = useMemo(
    () => [
      MessageComposerExtension.configure({
        placeholder,
        userMentionQueryFn,
        channelMentionQueryFn,
        userGroupMentionQueryFn,
        emojiQueryFn,
        getEmojiAttributeMap,
        onFilesAdded,
      }),
    ],
    [
      channelMentionQueryFn,
      emojiQueryFn,
      getEmojiAttributeMap,
      onFilesAdded,
      placeholder,
      userGroupMentionQueryFn,
      userMentionQueryFn,
    ]
  );

  // TODO [CHAT-386]: The following is a hack that Brent put in place to paper over a current
  // limitation of MessageComposer. In some parent component, I'd like to be able to ask "what is
  // the current content in the MessageComposer?", but since we can't make that empirical call, I
  // was relying on onUpdate calls to notify me of changes and then save those changes into state.
  // This mostly works, but it fails to capture initial state – prior to user-initiated updates –
  // that are caused via a non-nil defaultMessage. To paper over this limitation, we fire an
  // onUpdate call when the component mounts.
  const sentInitialOnUpdateRef = useRef(false);
  useEffect(() => {
    if (sentInitialOnUpdateRef.current) return;

    if (defaultMessage) {
      onUpdate?.(defaultMessage);
    }

    sentInitialOnUpdateRef.current = true;
  }, [defaultMessage, onUpdate]);

  const editor = useEditor({
    extensions,
    content: defaultMessage,
    autofocus: autoFocus,
    onUpdate: ({ editor }) => {
      const html = editor.getHTML();
      onUpdate?.(html);
    },
    editorProps: {
      attributes: {
        class: cx(messageContentStyle, messageEditorContainerRecipe({ showActionsInline })),
        style: `max-height: ${maxHeight}px;`,
        ...(dataTestId && { 'data-testid': dataTestId }),
      },
      handleKeyDown: (view, event) => {
        if (event.key === 'Enter' && sendButtonDisabled) {
          onEnterBlockedDuringDisabled?.();
          return true;
        }

        if (event.key === 'Escape') {
          // Start by blurring the editor.
          view.dom.blur();

          // Then, call the optional onEscape handler.
          onEscape?.();

          // Prevent the default behavior of the escape key.
          return true;
        }

        if (event.key === 'ArrowUp') {
          const isEmpty = isBlank(view.state.doc.textContent);

          if (isEmpty) {
            onUpArrowToEdit?.();
            return true;
          }
        }

        // Let other keys be handled normally.
        return false;
      },
    },
    immediatelyRender: true,
    // This allows us to only rerender the editor when necessary, rather than on every keystroke.
    // Docs: https://tiptap.dev/docs/examples/advanced/react-performance#react-tiptap-editor-integration
    shouldRerenderOnTransaction: false,
    onCreate: ({ editor }) => {
      if (autoFocus) {
        editor.commands.focus('end');
      }
    },
    editable: !disabled,
  });
  // Expose the editor instance to the parent
  useImperativeHandle(
    messageComposerRef,
    () => ({
      focus: () => editor.commands.focus('end'),
    }),
    [editor]
  );

  const handleSend = useCallback(() => {
    if (disabled) return;
    const textContent = editor.getText();

    const isEmpty = isNilOrEmpty(textContent);

    const content = editor.getHTML();

    onSend?.(content, isEmpty);
    editor.commands.clearContent();
  }, [editor, onSend, disabled]);

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

  // This allows us to pull the editor state and only rerender the component when the state that we
  // care about changes.
  const currentEditorState = useEditorState({
    editor,
    selector: (ctx) => ({
      isBold: ctx.editor.isActive('bold'),
      isItalic: ctx.editor.isActive('italic'),
      isStrike: ctx.editor.isActive('strike'),
      isCode: ctx.editor.isActive('code'),
      isOrderedList: ctx.editor.isActive('orderedList'),
      isBulletList: ctx.editor.isActive('bulletList'),
      isBlockQuote: ctx.editor.isActive('blockquote'),
      isCodeBlock: ctx.editor.isActive('codeBlock'),
      isLink: ctx.editor.isActive('link'),
      linkUrl: ctx.editor.getAttributes('link').href,
      selectedText: ctx.editor.state.doc.textBetween(
        ctx.editor.state.selection.from,
        ctx.editor.state.selection.to
      ),
      isEmpty: ctx.editor.isEmpty,
      isBlank: editor.getText().length === 0, // includes whitespace and newlines
      isCurrentlyMultiLine: (() => {
        const dom = ctx.editor.view?.dom;
        if (!dom) return false;
        // Chose 50 because it's in between 1 and 2 lines of text
        // Sometimes a line can be taller if it's a codeblock
        return dom.scrollHeight > 50;
      })(),
    }),
    equalityFn: equals,
  });

  // ChatGPT-like expansion behavior: expand once and stay expanded until completely cleared
  useEffect(() => {
    if (currentEditorState.isCurrentlyMultiLine) {
      setHasExpanded((prevHasExpanded) => (!prevHasExpanded ? true : prevHasExpanded));
    }
    if (currentEditorState.isBlank && isNil(afterContent)) {
      setHasExpanded((prevHasExpanded) => (prevHasExpanded ? false : prevHasExpanded));
    }
  }, [currentEditorState.isCurrentlyMultiLine, currentEditorState.isBlank, afterContent]);

  const handleOpenLinkModal = useCallback(() => {
    editor
      .chain()
      .focus()
      .extendMarkRange('link')
      .callbackOnFocus(() => {
        setIsLinkModelOpen(true);
      })
      .run();
  }, [editor]);

  const handleSetLink = useCallback(
    (link: string, text: string) => {
      if (isNilOrEmpty(link)) return;

      editor
        .chain()
        .focus()
        .extendMarkRange('link')
        .setLink({ href: link })
        .command(({ tr }) => {
          tr.insertText(text);
          return true;
        })
        .run();
    },
    [editor]
  );

  const handleClickUpload = useCallback((event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    fileSelectorRef.current?.click();
    event.currentTarget.blur(); // blur the button to remove focus and fix tooltip from staying shown
  }, []);

  const handleFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.target.files ?? []);

      if (isEmpty(files)) return;

      onFilesAdded?.(files);

      just(fileSelectorRef.current).value = ''; // clear input
    },
    [onFilesAdded]
  );

  const handleClickInsertMention = useCallback(() => {
    const { from, to } = editor.view.state.selection;
    const isAtStartOfLine = from === to && from === editor.state.selection.$from.start();
    const isAtSpaceBeforeCursor = from > 0 && editor.state.doc.textBetween(from - 1, from) === ' ';
    const currentNode = editor.view.state.selection.$to.node();

    if (currentNode.type.name !== 'paragraph') {
      // If we're not in a paragraph, we need to insert a new paragraph in order for the mention to
      // work.
      editor
        .chain()
        .insertContentAt(editor.state.selection.to, { type: 'paragraph' })
        .setTextSelection(editor.state.selection.to + 2) // +2 to go past the paragraph opening tag
        .run();
    } else if (!isAtStartOfLine && !isAtSpaceBeforeCursor) {
      // If we're not at the start of a new line and there isn't a space before the cursor, we need
      // to insert a space order for the mention to work.
      editor.chain().focus().insertContent(' ').run();
    }

    editor.chain().focus().insertContent(`@`).run();
  }, [editor]);

  const formattingActions: ComposerAction[] = [
    {
      type: 'action',
      icon: 'bold',
      // TODO [CHAT-93]: Pass in i18n text from some config
      name: 'Bold',
      isActive: currentEditorState.isBold,
      onClick: () => editor.chain().focus().toggleBold().run(),
    },
    {
      type: 'action',
      icon: 'italic',
      // TODO [CHAT-93]: Pass in i18n text from some config
      name: 'Italic',
      isActive: currentEditorState.isItalic,
      onClick: () => editor.chain().focus().toggleItalic().run(),
    },
    {
      type: 'action',
      icon: 'strikethrough',
      // TODO [CHAT-93]: Pass in i18n text from some config
      name: 'Strikethrough',
      isActive: currentEditorState.isStrike,
      onClick: () => editor.chain().focus().toggleStrike().run(),
    },
    {
      type: 'action',
      icon: 'link',
      // TODO [CHAT-93]: Pass in i18n text from some config
      name: 'Link',
      isActive: currentEditorState.isLink,
      onClick: handleOpenLinkModal,
    },
    {
      type: 'divider',
    },
    {
      type: 'action',
      icon: 'listNumbered',
      // TODO [CHAT-93]: Pass in i18n text from some config
      name: 'Ordered List',
      isActive: currentEditorState.isOrderedList,
      onClick: () => editor.chain().focus().toggleOrderedList().run(),
    },
    {
      type: 'action',
      icon: 'list',
      name: 'Bulleted List',
      isActive: currentEditorState.isBulletList,
      onClick: () => editor.chain().focus().toggleBulletList().run(),
    },
    {
      type: 'action',
      icon: 'blockQuote',
      name: 'Quote',
      isActive: currentEditorState.isBlockQuote,
      onClick: () => editor.chain().focus().toggleBlockquote().run(),
    },
    {
      type: 'action',
      icon: 'codeInline',
      // TODO [CHAT-93]: Pass in i18n text from some config
      name: 'Code',
      isActive: currentEditorState.isCode,
      onClick: () => editor.chain().focus().toggleCode().run(),
    },
    {
      type: 'action',
      icon: 'blockCode',
      name: 'Code Block',
      isActive: currentEditorState.isCodeBlock,
      onClick: () => editor.chain().focus().toggleCodeBlock().run(),
    },
  ] as const;

  const composerActions: ComposerAction[] = [
    ...compact([
      isNotNil(handleClickUpload) &&
        allowAttachments &&
        ({
          type: 'action',
          icon: 'paperClip',
          // TODO [CHAT-93]: Pass in i18n text from some config
          name: 'Attach',
          onClick: handleClickUpload,
          isDisabled: disabled,
        } as const),
      showMentionsAction &&
        ({
          type: 'action',
          icon: 'at',
          // TODO [CHAT-93]: Pass in i18n text from some config
          name: 'Mention',
          onClick: handleClickInsertMention,
        } as const),
      isNotNil(emojiPickerComponent) &&
        ({
          type: 'component',
          render: () => {
            const EmojiPicker = emojiPickerComponent;
            return (
              <EmojiPicker
                onEmojiSelect={({ emoji }) => {
                  editor.chain().focus().insertContent(emoji).run();
                }}
              />
            );
          },
        } as const),
    ] as const),
    ...(showFormattingActionsInline ? ([{ type: 'divider' }, ...formattingActions] as const) : []),
  ];

  const sendButtonDisabled =
    (currentEditorState.isEmpty && disableSendButtonIfEmpty) || disableSendButton;

  const endActions: ComposerAction[] =
    submitActionsType === 'default'
      ? isGatherAI
        ? [
            showAbortButton
              ? {
                  type: 'action',
                  icon: 'stop',
                  // TODO [CHAT-93]: Pass in i18n text from some config
                  name: 'Stop',
                  isActive: true,
                  onClick: handleAbort ?? noop,
                }
              : {
                  type: 'action',
                  icon: 'arrowUp',
                  // TODO [CHAT-93]: Pass in i18n text from some config
                  name: 'Send',
                  isPrimary: true,
                  onClick: handleSend,
                  isDisabled: sendButtonDisabled || disabled,
                },
          ]
        : [
            {
              type: 'action',
              icon: 'sendAltFilled',
              // TODO [CHAT-93]: Pass in i18n text from some config
              name: 'Send',
              isPrimary: true,
              onClick: handleSend,
              isDisabled: sendButtonDisabled || disabled,
            },
          ]
      : [
          {
            type: 'buttonAction',
            name: 'Cancel',
            onClick: onClickCancel ?? noop,
          },
          {
            type: 'buttonAction',
            name: 'Save',
            isPrimary: true,
            onClick: handleSend,
            isDisabled: sendButtonDisabled,
          },
        ];

  const tippyBubbleMenuOptions = {
    // "auto" is a valid value, but it looks like the types on this component are incorrect.
    // eslint-disable-next-line @typescript-eslint/consistent-type-assertions, @typescript-eslint/no-explicit-any
    zIndex: 'auto' as unknown as any,
  } as const;

  return (
    <>
      <Box
        borderColor="tertiary"
        borderWidth={1}
        borderStyle="solid"
        borderRadius={isGatherAI ? '16px' : '10px'}
        width="100%"
        style={
          isGatherAI
            ? {
                boxShadow: tokens.boxShadow.xs,
              }
            : {}
        }
        opacity={disabled ? 0.6 : 1}
      >
        <LayoutGroup>
          <Flex
            gap={showActionsInline ? 4 : 0}
            py={showActionsInline ? 4 : 0}
            px={showActionsInline ? 10 : 0}
            align={showActionsInline ? 'center' : 'stretch'}
            direction={showActionsInline ? 'row' : 'column'}
          >
            {showActionsInline && (
              <motion.div layout="position" transition={{ duration: 0.2, ease: 'easeOut' }}>
                <MessageComposerActionsToolbar composerActionsStart={composerActions} isInline />
              </motion.div>
            )}
            <motion.div
              layout="position"
              style={{ flex: showActionsInline ? 1 : 'none', minWidth: 0, overflow: 'hidden' }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <EditorContent editor={editor} />
            </motion.div>

            {showActionsInline ? (
              <motion.div layout="position" transition={{ duration: 0.2, ease: 'easeOut' }}>
                <MessageComposerActionsToolbar composerActionsStart={endActions} isInline />
              </motion.div>
            ) : (
              <>
                {afterContent}
                <Flex pb={4} px={4}>
                  <MessageComposerActionsToolbar
                    composerActionsStart={composerActions}
                    composerActionsEnd={endActions}
                    useResponsiveFormatting={showFormattingActionsInline}
                  />
                </Flex>
              </>
            )}
          </Flex>
        </LayoutGroup>

        <BubbleMenu
          editor={editor}
          shouldShow={({ editor }) => editor.isActive('link')}
          tippyOptions={tippyBubbleMenuOptions}
        >
          <MessageComposerLinkPopover
            url={currentEditorState.linkUrl}
            onClickEdit={handleOpenLinkModal}
          />
        </BubbleMenu>
        <BubbleMenu
          editor={editor}
          shouldShow={({ editor, element, state, view, from, to }) => {
            if (editor.isActive('link') || showFormattingActionsInline) return false;

            /**
             * Source for default `shouldShow` logic used below:
             * https://github.com/ueberdosis/tiptap/blob/main/packages/extension-bubble-menu/src/bubble-menu-plugin.ts#L80
             */

            const { doc, selection } = state;
            const { empty } = selection;

            // Sometime check for `empty` is not enough.
            // Doubleclick an empty paragraph returns a node size of 2.
            // So we check also for an empty text size.
            const isEmptyTextBlock =
              !doc.textBetween(from, to).length && isTextSelection(state.selection);

            // When clicking on an element inside the bubble menu the editor "blur" event
            // is called and the bubble menu item is focussed. In this case we should
            // consider the menu as part of the editor and keep showing the menu
            const isChildOfMenu = element.contains(document.activeElement);

            const hasEditorFocus = view.hasFocus() || isChildOfMenu;

            if (!hasEditorFocus || empty || isEmptyTextBlock || !editor.isEditable) return false;

            return true;
          }}
          tippyOptions={tippyBubbleMenuOptions}
        >
          <Box
            borderColor="tertiary"
            borderWidth={1}
            borderStyle="solid"
            borderRadius={10}
            backgroundColor="primary"
            p={4}
          >
            <MessageComposerActionsToolbar composerActionsStart={formattingActions} />
          </Box>
        </BubbleMenu>

        <MessageComposerLinkModal
          isOpen={isLinkModelOpen}
          setIsOpen={setIsLinkModelOpen}
          defaultValues={{
            link: currentEditorState.linkUrl,
            text: currentEditorState.selectedText,
          }}
          onSetLink={handleSetLink}
        />
      </Box>
      <input
        type="file"
        ref={fileSelectorRef}
        onChange={handleFileChange}
        multiple
        style={{ display: 'none' }}
        accept={
          isGatherAI
            ? GATHER_AI_SUPPORTED_ATTACHMENT_MIME_TYPES.join(',')
            : SUPPORTED_CHAT_ATTACHMENT_MIME_TYPES.join(',')
        }
        disabled={disabled}
      />
    </>
  );
});
