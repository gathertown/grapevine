import { PluginKey } from '@tiptap/pm/state';
import { ReactRenderer } from '@tiptap/react';
import { SuggestionKeyDownProps, SuggestionProps } from '@tiptap/suggestion';
import { pick } from 'ramda';
import { ComponentProps, createRef } from 'react';
import tippy from 'tippy.js';

import { isNil, just } from '../../../../utils/fpHelpers';
import { PORTAL_ROOT_ID } from '../../../../helpers/usePortalContainer';
import { MessageComposerMention } from './MessageComposerMention';

export interface BaseQueryItem {
  id: string;
  label: string;
  // Optional type to distinguish between different mention types
  type?: 'userMention' | 'userGroupMention' | 'channelMention';
}

type MentionConfigOptions<QueryItem extends BaseQueryItem> = {
  char: string;
  pluginKeyName: string;
  queryFn: ({ query }: { query: string }) => QueryItem[];
};

export const generateMentionSuggestionConfig = <TQueryItem extends BaseQueryItem>(
  options: MentionConfigOptions<TQueryItem>
) => ({
  ...pick(['char'], options),

  pluginKey: new PluginKey(options.pluginKeyName),

  items: options.queryFn,

  render: () => {
    let component: ReactRenderer<{}, ComponentProps<typeof MessageComposerMention>>;
    const componentRef = createRef<{
      onKeyDown: ({ event }: { event: KeyboardEvent }) => boolean;
    }>();
    let popup: ReturnType<typeof tippy>;

    const getPopup = () => just(popup[0], 'No popup found, did you forget to call `onStart`?');

    /**
     * Note: If you're modifying code here, you might also consider updating the similar suggestion
     * code for emojis in the `generateEmojiConfig` code. There is likely a way to DRY this mode but
     * for simplicity for now we'll keep the code separate.
     */
    return {
      onStart: (props: SuggestionProps<TQueryItem>) => {
        component = new ReactRenderer(MessageComposerMention, {
          props: { ...props, ref: componentRef },
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
