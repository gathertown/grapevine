import { style } from '@vanilla-extract/css';

import {
  dropdownContainerStyle as mentionDropdownContainerStyle,
  dropdownItemRecipe as mentionDropdownItemRecipe,
} from '../MessageComposerMention/MessageComposerMention.css';

// For now, let's just pull styles from the MessageComposerMention component
export const dropdownContainerStyle = style([
  mentionDropdownContainerStyle,
  // This currently needs a fixed width because simplebar has an inner container that has a
  // particular width dependant on the parent.
  { width: 264, overflowY: 'hidden' },
]);
export const dropdownItemRecipe = mentionDropdownItemRecipe;
