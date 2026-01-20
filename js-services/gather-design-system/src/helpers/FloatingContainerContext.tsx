import { createContext } from 'react';

interface FloatingContainerContextType {
  // The root element where `<FloatingPortal />` components should
  // be rendered. If this is `null`, the default container will be
  // the `document.body`.
  //
  // Otherwise, this is intended to override the 'root' property of the floating-ui
  // <FloatingPortal /> component:
  // https://floating-ui.com/docs/floatingportal
  rootFloatingPortalElement: HTMLElement | null;
}

// Create the context with a default value - `null` means that
// the `document.body` will be used as the default container
// for floating-ui pop-ups.
export const FloatingContainerContext = createContext<FloatingContainerContextType>({
  rootFloatingPortalElement: null,
});
