import { memo } from 'react';
import type { FC, CSSProperties } from 'react';

interface StepScreenshotProps {
  src: string;
  alt: string;
  style?: CSSProperties;
}

const StepScreenshot: FC<StepScreenshotProps> = memo(({ src, alt, style }) => {
  return (
    <img
      src={src}
      alt={alt}
      style={{
        width: '100%',
        borderRadius: '8px',
        border: '1px solid #e1e5e9',
        ...style,
      }}
    />
  );
});

StepScreenshot.displayName = 'StepScreenshot';

export { StepScreenshot };
