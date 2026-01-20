import { memo } from 'react';
import type { FC } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Flex,
  Icon,
  Box,
  Text,
  IconName,
  Indicator,
  Badge,
} from '@gathertown/gather-design-system';
import { useOnboardingStepCount } from '../contexts/OnboardingContext';
import styles from './Sidebar.module.css';
import { useIsFeatureEnabled } from '../api/features';
import { useDevMode } from '../hooks/useDevMode';
import { useBillingEnabled } from '../hooks/useBillingEnabled';
import { compact } from 'lodash';
import { IS_STAGING, IS_LOCAL, DOCS_URL } from '../constants';

type NavigationItemLink = {
  path: string;
  label: string;
  icon: IconName;
  indicatorText?: string;
  external?: boolean;
};

const NavigationItem = ({
  path,
  label,
  icon,
  active,
  indicatorCount,
  indicatorText,
  external,
}: {
  path: string;
  label: string;
  icon: IconName;
  active: boolean;
  indicatorCount?: number;
  indicatorText?: string;
  external?: boolean;
}) => {
  const shouldShowIndicator = indicatorText || (indicatorCount !== undefined && indicatorCount > 0);

  const content = (
    <>
      <Flex align="center" gap={8}>
        <Icon name={icon} size="sm" color="primary" />
        <Text fontSize="sm" fontWeight="normal">
          {label}
        </Text>
        {external && <Icon name="arrowUpRight" size="xs" color="tertiary" />}
      </Flex>
      {shouldShowIndicator &&
        (indicatorText ? (
          <Badge color="gray" size="sm" text={indicatorText} />
        ) : (
          <Indicator count={indicatorCount} />
        ))}
    </>
  );

  if (external) {
    return (
      <a
        href={path}
        target="_blank"
        rel="noopener noreferrer"
        className={`${styles.sidebarLink} ${active ? styles.sidebarLinkActive : ''}`}
      >
        {content}
      </a>
    );
  }

  return (
    <Link to={path} className={`${styles.sidebarLink} ${active ? styles.sidebarLinkActive : ''}`}>
      {content}
    </Link>
  );
};

const Sidebar: FC = memo(() => {
  const location = useLocation();
  const { completedStepsCount, visibleStepsCount } = useOnboardingStepCount();
  const { data: showInternalFeatures } = useIsFeatureEnabled('internal:features');
  const isDevMode = useDevMode();
  const { isBillingEnabled } = useBillingEnabled();

  const isItemActive = (itemPath: string, currentPath: string) => {
    if (itemPath === '/slackbot') {
      return currentPath === '/slackbot' || currentPath.startsWith('/onboarding/slack');
    }
    if (itemPath === '/integrations') {
      return currentPath === '/integrations';
    }
    if (itemPath === '/knowledge-bases') {
      return currentPath.startsWith('/knowledge-bases');
    }
    return currentPath === itemPath;
  };

  const navigationItems: NavigationItemLink[] = compact([
    {
      path: '/',
      label: 'Home',
      icon: 'home',
      indicatorText: `${completedStepsCount}/${visibleStepsCount}`,
    },
    !isDevMode ? { path: '/stats', label: 'Stats', icon: 'playlist' } : null,
  ]);

  const settingsItems: NavigationItemLink[] = compact([
    { path: '/integrations', label: 'Integrations', icon: 'puzzle' },
    isBillingEnabled ? { path: '/billing', label: 'Billing', icon: 'creditCard' } : null,
    { path: '/organization-settings', label: 'General', icon: 'settings' },
  ]);

  const developersItems: NavigationItemLink[] = compact([
    { path: '/api-keys', label: 'API Keys', icon: 'codeInline' },
    { path: '/webhooks', label: 'Webhooks', icon: 'link' },
    DOCS_URL ? { path: DOCS_URL, label: 'Docs', icon: 'globe', external: true } : null,
    IS_STAGING || IS_LOCAL
      ? {
          path: '/eval-capture',
          label: 'Exponent Eval Capture (internal)',
          icon: 'mediaLibraryStar',
        }
      : null,
  ]);

  const appItems: NavigationItemLink[] = compact([
    { path: '/apps/ask-grapevine', label: 'Ask Grapevine', icon: 'chatMultiple' },
    showInternalFeatures
      ? { path: '/apps/reviewer', label: 'Reviewer (internal)', icon: 'codeInline' }
      : null,
    showInternalFeatures
      ? { path: '/debug/agent-chat', label: 'Agent Chat (internal)', icon: 'chatBubble' }
      : null,
    showInternalFeatures
      ? { path: '/knowledge-bases', label: 'Knowledge Bases (internal)', icon: 'bookmark' }
      : null,
  ]);

  return (
    <Flex direction="column" width="100%" height="100%" px={8} py={16} gap={14}>
      {/* Main Navigation */}
      <Flex direction="column">
        {navigationItems.map((item) => (
          <NavigationItem
            key={item.path}
            path={item.path}
            label={item.label}
            icon={item.icon}
            active={!item.external && isItemActive(item.path, location.pathname)}
            indicatorCount={
              'indicatorCount' in item && typeof item.indicatorCount === 'number'
                ? item.indicatorCount
                : undefined
            }
            indicatorText={
              'indicatorText' in item && typeof item.indicatorText === 'string'
                ? item.indicatorText
                : undefined
            }
            external={item.external}
          />
        ))}
      </Flex>

      {/* Apps Section */}
      {appItems.length > 0 && (
        <Flex direction="column">
          <Box px={8} mb={4}>
            <Text fontSize="xxs" color="tertiary">
              Apps
            </Text>
          </Box>
          {appItems.map((item) => (
            <NavigationItem
              key={item.path}
              path={item.path}
              label={item.label}
              icon={item.icon}
              active={isItemActive(item.path, location.pathname)}
            />
          ))}
        </Flex>
      )}

      {/* Developers Section */}
      <Flex direction="column">
        <Box px={8} mb={4}>
          <Text fontSize="xxs" color="tertiary">
            Developers
          </Text>
        </Box>
        {developersItems.map((item) => (
          <NavigationItem
            key={item.path}
            path={item.path}
            label={item.label}
            icon={item.icon}
            active={!item.external && isItemActive(item.path, location.pathname)}
            external={item.external}
          />
        ))}
      </Flex>

      {/* Settings Section */}
      <Flex direction="column">
        <Box px={8} mb={4}>
          <Text fontSize="xxs" color="tertiary">
            Settings
          </Text>
        </Box>
        {settingsItems.map((item) => (
          <NavigationItem
            key={item.path}
            path={item.path}
            label={item.label}
            icon={item.icon}
            active={isItemActive(item.path, location.pathname)}
          />
        ))}
      </Flex>
    </Flex>
  );
});

Sidebar.displayName = 'Sidebar';

export { Sidebar };
