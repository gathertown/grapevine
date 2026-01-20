import React from 'react';

import { labelRecipe, LabelVariants, requiredStyle } from './Label.css';

type LabelProps = Omit<React.LabelHTMLAttributes<HTMLLabelElement>, 'className'> &
  LabelVariants & {
    required?: boolean;
    hasCursor?: boolean;
  };

export const Label = React.memo(
  React.forwardRef<HTMLLabelElement, LabelProps>(function Label(
    { children, required, size, hasCursor, ...props },
    ref
  ) {
    return (
      <label ref={ref} className={labelRecipe({ size, hasCursor })} {...props}>
        {children}
        {/* eslint-disable-next-line @gathertown/no-literal-string-in-jsx */}
        {required && <span className={requiredStyle}>*</span>}
      </label>
    );
  })
);
