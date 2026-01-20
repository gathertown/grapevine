const RADIX_SELECTORS = [
  // Portal containers and wrappers
  '[data-radix-portal]',
  '[data-radix-popper-content-wrapper]',
  '[data-radix-aspect-ratio-wrapper]',

  // Select component selectors
  '[data-radix-select-viewport]',
  '[data-radix-select-content]',
  '[data-radix-select-item]',
  '[data-radix-select-trigger]',
  '[data-radix-select-value]',
  '[data-radix-select-icon]',
  '[data-radix-select-scroll-up-button]',
  '[data-radix-select-scroll-down-button]',

  // Other common Radix components that might be used
  '[data-radix-dropdown-menu-content]',
  '[data-radix-dropdown-menu-item]',
  '[data-radix-dropdown-menu-trigger]',
  '[data-radix-popover-content]',
  '[data-radix-popover-trigger]',
  '[data-radix-dialog-content]',
  '[data-radix-tooltip-content]',
  '[data-radix-context-menu-content]',
  '[data-radix-menubar-content]',
];

export const isRadixElement = (target: Element): boolean =>
  target.closest(RADIX_SELECTORS.join(', ')) !== null;
