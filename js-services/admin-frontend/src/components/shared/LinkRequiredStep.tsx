import { type FC, type ReactNode } from 'react';
import { Flex, Text, Badge } from '@gathertown/gather-design-system';
import { Link } from './Link';

interface LinkRequiredStepProps {
  /** Text to display before the link */
  descriptionBefore: string;
  /** Text to display after the link */
  descriptionAfter?: string;
  /** The text to display for the clickable link */
  linkText: string;
  /** The URL to open when the link is clicked */
  linkUrl?: string;
  /** Optional additional content to show after the link */
  additionalContent?: ReactNode;
  /** Callback when the link is clicked - used for tracking */
  onLinkClick?: () => void;
  /** Optional badge to show additional context */
  badge?: {
    text: string;
    color: 'success' | 'gray' | 'danger' | 'accent' | 'warning' | 'light-gray';
  };
  /** Font size for the text and link */
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'inherit';
}

export const LinkRequiredStep: FC<LinkRequiredStepProps> = ({
  descriptionBefore,
  descriptionAfter,
  linkText,
  linkUrl,
  additionalContent,
  onLinkClick,
  badge,
  size = 'inherit',
}) => {
  const handleLinkClick = () => {
    onLinkClick?.();

    // Open the link in a new tab
    if (linkUrl) {
      window.open(linkUrl, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <Flex direction="column" gap={16}>
      <Text fontSize={size}>
        {descriptionBefore && `${descriptionBefore} `}
        <Link onClick={handleLinkClick} size={size}>
          {linkText}
        </Link>
        {descriptionAfter && ` ${descriptionAfter}`}
      </Text>

      {badge && <Badge color={badge.color} text={badge.text} />}

      {additionalContent && <div>{additionalContent}</div>}
    </Flex>
  );
};
