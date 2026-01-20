import { memo } from 'react';
import type { FC } from 'react';
import { Link } from 'react-router-dom';
import { Button, Menu, Flex, Icon, Text, Avatar } from '@gathertown/gather-design-system';
import { useAuth } from '../hooks/useAuth';
import { useTrackEvent } from '../hooks/useTrackEvent';
import grapevinelogo from '../assets/grapevine_purp.png';
import { DOCS_URL, SUPPORT_EMAIL } from '../constants';
import styles from './Header.module.css';

const Header: FC = memo(() => {
  const { user, signOut } = useAuth();
  const { trackEvent } = useTrackEvent();

  const handleHelpButtonClick = () => {
    trackEvent('help_button_clicked', {
      user_id: user?.id,
      location: 'header',
    });
  };

  const handleEmailUsClick = () => {
    if (!SUPPORT_EMAIL) return;
    trackEvent('help_email_clicked', {
      user_id: user?.id,
    });
    window.open(`mailto:${SUPPORT_EMAIL}`, '_blank');
  };

  const handleDocsClick = () => {
    if (!DOCS_URL) return;
    window.open(DOCS_URL, '_blank');
  };

  return (
    <Flex
      justify="space-between"
      align="center"
      width="100%"
      minHeight={44}
      p={8}
      position="sticky"
      top={0}
    >
      {/* Logo and Brand */}
      <Flex
        as={memo((props) => (
          <Link {...props} to="/" />
        ))}
        align="center"
        gap={8}
      >
        <img src={grapevinelogo} alt="Grapevine Logo" style={{ height: '24px', width: 'auto' }} />
        <Text fontSize="lg" fontWeight="normal" color="primary">
          Grapevine
        </Text>
      </Flex>

      <Flex align="center" gap={8} color="primary">
        {/* Invite Button */}
        <Link to="/invite">
          <Button size="md" kind="secondary" leadingIcon="userPlus">
            Invite
          </Button>
        </Link>

        {/* Help Menu */}
        <Menu>
          <Menu.Trigger asChild>
            <Button
              size="md"
              kind="secondary"
              leadingIcon="questionMark"
              onClick={handleHelpButtonClick}
            >
              Get help
            </Button>
          </Menu.Trigger>
          <Menu.Content align="end" sideOffset={8} width={200}>
            <Menu.Label>Get help</Menu.Label>
            <Menu.Item icon="globe" onSelect={handleDocsClick}>
              Developer docs
            </Menu.Item>
            <Menu.Item icon="envelope" onSelect={handleEmailUsClick}>
              Email Us
            </Menu.Item>
          </Menu.Content>
        </Menu>

        {/* User Profile Dropdown */}
        <Menu>
          <Menu.Trigger asChild>
            <button onClick={handleHelpButtonClick} className={styles.avatarButton}>
              <Avatar name={user?.email} size="xs" />
            </button>
          </Menu.Trigger>
          <Menu.Content align="end" sideOffset={8} width={228}>
            <Menu.Label>{user?.email}</Menu.Label>
            <Menu.Separator />
            <Menu.Item onClick={signOut}>
              <Icon name="signOut" />
              Sign Out
            </Menu.Item>
          </Menu.Content>
        </Menu>
      </Flex>
    </Flex>
  );
});

Header.displayName = 'Header';

export { Header };
