import { useMemo } from 'react';

import { AllPossibleProps, StyleEnum } from './layoutTypes';
import { getSprinkleStyle, translateStyleProps } from './layoutUtils';

export const useLayoutComponentStyles = <ComponentAtomicProps>({
  defaultProps = {},
  layoutProps,
  style,
  styleMap,
  getAtomicStyles,
}: {
  defaultProps?: Partial<AllPossibleProps>;
  layoutProps: Partial<AllPossibleProps>;
  style?: React.CSSProperties;
  styleMap: Record<string, StyleEnum[] | StyleEnum>;
  getAtomicStyles: (props: ComponentAtomicProps) => string;
}) => {
  const combinedProps = useMemo(
    () => ({ ...defaultProps, ...layoutProps }),
    [defaultProps, layoutProps]
  );
  const atomicStyles = useMemo(
    () =>
      getAtomicStyles(
        getSprinkleStyle<AllPossibleProps, ComponentAtomicProps>(combinedProps, styleMap)
      ),
    [combinedProps, getAtomicStyles, styleMap]
  );
  const variableStyles = useMemo(
    () => ({ ...translateStyleProps(combinedProps, styleMap), ...style }),
    [combinedProps, style, styleMap]
  );

  return {
    atomicStyles,
    variableStyles,
  };
};
