import React from 'react';
import * as PanelPrimitive from 'react-resizable-panels';

import { panelResizeHandleRecipe } from './ResizablePanel.css';

type ResizablePanelProps = Pick<
  PanelPrimitive.PanelGroupProps,
  'autoSaveId' | 'direction' | 'style' | 'children'
>;

export const ResizablePanelRoot: React.FC<ResizablePanelProps> = React.memo(
  function ResizablePanelRoot(props) {
    return <PanelPrimitive.PanelGroup {...props} />;
  }
);

ResizablePanelRoot.displayName = 'ResizablePanel';

const Panel = React.memo(function Panel({
  children,
  ...restProps
}: Pick<
  PanelPrimitive.PanelProps,
  'id' | 'order' | 'maxSize' | 'minSize' | 'defaultSize' | 'style' | 'children'
>) {
  return <PanelPrimitive.Panel {...restProps}>{children}</PanelPrimitive.Panel>;
});
Panel.displayName = 'ResizablePanel.Panel';

const ResizeHandle = React.memo(function ResizeHandle(
  props: Pick<PanelPrimitive.PanelResizeHandleProps, 'style'>
) {
  const [isHovered, setIsHovered] = React.useState(false);
  const [isDragging, setIsDragging] = React.useState(false);

  const isHighlighted = isHovered || isDragging;

  return (
    <PanelPrimitive.PanelResizeHandle
      className={panelResizeHandleRecipe({ highlighted: isHighlighted })}
      onDragging={setIsDragging}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      hitAreaMargins={{ coarse: 1, fine: 1 }}
      {...props}
    />
  );
});
ResizeHandle.displayName = 'ResizablePanel.ResizeHandle';

export const ResizablePanel = Object.assign(ResizablePanelRoot, {
  Panel,
  ResizeHandle,
});
