import React, { type FC, type ReactNode } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Text } from '@gathertown/gather-design-system';

interface LinkProps {
  /** Content to render inside the link */
  children: ReactNode;
  /** External URL for external links */
  href?: string;
  /** Internal route for react-router links */
  to?: string;
  /** Custom click handler */
  onClick?: () => void;
  /** Target attribute for external links */
  target?: string;
  /** Rel attribute for external links */
  rel?: string;
  /** Additional CSS classes */
  className?: string;
  /** Additional inline styles */
  style?: React.CSSProperties;
  /** Font size - defaults to inherit */
  size?: 'inherit' | 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxxs' | 'xxs' | 'xxl';
}

const linkBaseStyles: React.CSSProperties = {
  color: '#007bff',
  textDecoration: 'underline',
  cursor: 'pointer',
  background: 'none',
  border: 'none',
  padding: 0,
  transition: 'color 0.15s ease-in-out',
};

const linkHoverStyles: React.CSSProperties = {
  color: '#0056b3',
};

export const Link: FC<LinkProps> = ({
  children,
  href,
  to,
  onClick,
  target,
  rel,
  className,
  style = {},
  size = 'inherit',
}) => {
  const [isHovered, setIsHovered] = React.useState(false);

  const handleMouseEnter = () => setIsHovered(true);
  const handleMouseLeave = () => setIsHovered(false);

  const combinedStyles = {
    ...linkBaseStyles,
    ...(isHovered ? linkHoverStyles : {}),
    ...style,
  };

  const handleClick = (e: React.MouseEvent) => {
    if (onClick) {
      e.preventDefault();
      onClick();
    }
  };

  // External link
  if (href) {
    return (
      <Text as="span" fontSize={size}>
        <a
          href={href}
          target={target}
          rel={rel}
          className={className}
          style={combinedStyles}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          onClick={handleClick}
        >
          {children}
        </a>
      </Text>
    );
  }

  // Internal react-router link
  if (to) {
    return (
      <Text as="span" fontSize={size}>
        <RouterLink
          to={to}
          className={className}
          style={combinedStyles}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          onClick={handleClick}
        >
          {children}
        </RouterLink>
      </Text>
    );
  }

  // Button-style link (for custom click handlers)
  return (
    <Text as="span" fontSize={size}>
      <button
        type="button"
        className={className}
        style={combinedStyles}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
      >
        {children}
      </button>
    </Text>
  );
};
