import React, { useContext } from 'react';

import { textRecipe, TextVariants } from './Text.css';
import { TextNestingContext } from './TextNestingContext';

export type TextAs = 'p' | 'span' | 'div' | 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';

type TextProps = TextVariants & {
  children: React.ReactNode;
  as?: TextAs;
  id?: string;
  selectable?: boolean;
  flexShrink?: number;
  display?: React.CSSProperties['display'];
};

export const Text = React.memo(
  React.forwardRef<HTMLParagraphElement, TextProps>(function Text(
    {
      children,
      as: Component = 'span',
      color,
      fontSize,
      fontWeight,
      truncate,
      textAlign,
      textWrap,
      wordBreak,
      textDecorationStyle,
      lineHeight,
      id,
      selectable,
      textTransform,
      flexShrink,
      display,
      fontStyle,
      ...rest
    },
    ref
  ) {
    const isNestedInAnotherText = useContext(TextNestingContext);

    const finalColor = color ?? 'inherit';
    const finalFontSize = fontSize ?? (isNestedInAnotherText ? 'inherit' : 'md');
    const finalFontWeight = fontWeight ?? (isNestedInAnotherText ? 'inherit' : 'normal');

    const resolvedClassName = textRecipe({
      color: finalColor,
      fontSize: finalFontSize,
      fontWeight: finalFontWeight,
      truncate,
      textAlign,
      textWrap,
      wordBreak,
      textDecorationStyle,
      lineHeight,
      selectable,
      textTransform,
      flexShrink,
      display,
      fontStyle,
    });

    return (
      // Provide `true` so that any descendant <Text> sees that they're nested
      <TextNestingContext.Provider value={true}>
        <Component ref={ref} className={resolvedClassName} id={id} {...rest}>
          {children}
        </Component>
      </TextNestingContext.Provider>
    );
  })
);
