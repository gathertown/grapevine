import { ReactRenderer } from '@tiptap/react';
import { SuggestionKeyDownProps, SuggestionProps } from '@tiptap/suggestion';
import { pick } from 'ramda';
import { ComponentProps, createRef } from 'react';
import tippy from 'tippy.js';

import type { EmojiAttributes } from '../../../../utils/types';
import { isNil, just } from '../../../../utils/fpHelpers';
import { PORTAL_ROOT_ID } from '../../../../helpers/usePortalContainer';
import { MessageComposerEmoji } from './MessageComposerEmoji';

export type BaseQueryItem = EmojiAttributes;

type EmojiConfigOptions<QueryItem extends BaseQueryItem> = {
  char: string;
  queryFn: ({ query }: { query: string }) => QueryItem[];
};

export const generateEmojiSuggestionConfig = <TQueryItem extends BaseQueryItem>(
  options: EmojiConfigOptions<TQueryItem>
) => ({
  ...pick(['char'], options),

  items: options.queryFn,

  render: () => {
    let component: ReactRenderer<{}, ComponentProps<typeof MessageComposerEmoji>>;
    const componentRef = createRef<{
      onKeyDown: ({ event }: { event: KeyboardEvent }) => boolean;
    }>();
    let popup: ReturnType<typeof tippy>;

    const getPopup = () => just(popup[0], 'No popup found, did you forget to call `onStart`?');

    /**
     * Note: If you're modifying code here, you might also consider updating the similar suggestion
     * code for mentions in the `generateMentionConfig` code. There is likely a way to DRY this mode
     * but for simplicity for now we'll keep the code separate.
     */
    return {
      onStart: (props: SuggestionProps<TQueryItem>) => {
        component = new ReactRenderer(MessageComposerEmoji, {
          props: { ...props, char: options.char, ref: componentRef },
          editor: props.editor,
        });

        if (isNil(props.clientRect)) return;

        const guaranteedGetClientRect = () => just(just(props.clientRect)());

        // Tippy is used here because we don't yet have a non-React popover library (we're using
        // Radix right now which is bound to React) and the `BubbleMenu` component that Tiptap uses
        // also uses this library under the hood.
        popup = tippy(`#${PORTAL_ROOT_ID}`, {
          getReferenceClientRect: guaranteedGetClientRect,
          appendTo: () =>
            just(
              document.getElementById(PORTAL_ROOT_ID),
              `Portal root (at #${PORTAL_ROOT_ID}) not found`
            ),
          content: component.element,
          showOnCreate: true,
          interactive: true,
          trigger: 'manual',
          placement: 'bottom-start',
        });
      },

      onUpdate(props: SuggestionProps<TQueryItem>) {
        component.updateProps(props);

        if (isNil(props.clientRect)) return;

        const guaranteedGetClientRect = () => just(just(props.clientRect)());

        getPopup().setProps({
          getReferenceClientRect: guaranteedGetClientRect,
        });
      },

      onKeyDown(props: SuggestionKeyDownProps) {
        if (props.event.key === 'Escape') {
          getPopup().hide();

          return true;
        }

        return componentRef.current?.onKeyDown(props) ?? false;
      },

      onExit() {
        getPopup().destroy();
        component.destroy();
      },
    };
  },
});
