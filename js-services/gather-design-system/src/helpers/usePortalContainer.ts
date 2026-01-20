import React, { useContext } from 'react';

import { FloatingContainerContext } from './FloatingContainerContext';

export const PORTAL_ROOT_ID = 'portal-root';

export const usePortalContainer = (id: string = PORTAL_ROOT_ID) => {
  const [portalContainer, setPortalContainer] = React.useState<HTMLElement | null>(null);
  const floatingContainerContext = useContext(FloatingContainerContext);

  React.useEffect(() => {
    const container =
      floatingContainerContext.rootFloatingPortalElement?.querySelector<HTMLElement>(`#${id}`) ??
      document.getElementById(id) ??
      document.body;
    setPortalContainer(container);

    return () => {
      setPortalContainer(null);
    };
  }, [id, floatingContainerContext.rootFloatingPortalElement]);

  return portalContainer;
};
