import React from 'react';

import { loaderRecipe } from './Loader.css';

type LoaderProps = {
  size?: 'sm' | 'md';
};

export const Loader = React.memo(function Loader({ size }: LoaderProps) {
  return (
    <span
      className={loaderRecipe({ size })}
      style={{
        height: size,
        width: size,
      }}
      aria-hidden="true"
    />
  );
});
