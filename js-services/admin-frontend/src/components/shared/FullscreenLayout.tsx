import { FC, ReactNode } from 'react';
import { Flex, Button } from '@gathertown/gather-design-system';
import { useAuth } from '../../hooks/useAuth';

interface FullscreenLayoutProps {
  children: ReactNode;
  showSignOut?: boolean;
}

const FullscreenLayout: FC<FullscreenLayoutProps> = ({ children, showSignOut = false }) => {
  const { signOut } = useAuth();

  const handleLogout = async (): Promise<void> => {
    try {
      await signOut();
    } catch (error) {
      console.error('Logout failed:', error);
    }
  };

  return (
    <Flex
      width="100vw"
      minHeight="100vh"
      backgroundColor="secondary"
      align="center"
      justify="flex-start"
      position="relative"
      style={{ overflowY: 'auto' }}
    >
      {showSignOut && (
        <Button
          size="sm"
          kind="secondary"
          onClick={handleLogout}
          style={{
            position: 'absolute',
            top: '16px',
            right: '16px',
            zIndex: 10,
          }}
        >
          Sign Out
        </Button>
      )}

      <Flex width="100%" align="center" justify="center" py={8}>
        {children}
      </Flex>
    </Flex>
  );
};

export { FullscreenLayout };
