import { FC } from 'react';
import { Flex, Text } from '@gathertown/gather-design-system';
import { useAuth } from '../hooks/useAuth';
import { FullscreenLayout } from './shared/FullscreenLayout';
import { SUPPORT_EMAIL } from '../constants';
import grapevinelogo from '../assets/grapevine_purp.png';

const MemberAccessDenied: FC = () => {
  const { user } = useAuth();

  return (
    <FullscreenLayout showSignOut={true}>
      <Flex direction="column" align="center" maxWidth="500px" width="100%" px={6} gap={32}>
        {/* Header with Logo */}
        <Flex direction="column" align="center" gap={16} width="100%">
          <img
            src={grapevinelogo}
            alt="Grapevine Logo"
            style={{ height: '64px', width: 'auto', marginBottom: '16px' }}
          />
          <Flex direction="column" gap={10}>
            <Text fontSize="xxl" textAlign="center" fontWeight="semibold">
              Welcome to Grapevine
            </Text>
            <Text fontSize="md" textAlign="center" color="secondary">
              {user?.email}
            </Text>
          </Flex>
        </Flex>

        {/* Access Denied Message */}
        <Flex
          direction="column"
          width="100%"
          gap={16}
          borderRadius={12}
          p={32}
          backgroundColor="primary"
          borderColor="tertiary"
          borderWidth={1}
        >
          <Text fontSize="lg" textAlign="center" fontWeight="semibold">
            Admin Access Required
          </Text>
          <Text fontSize="md" textAlign="center" color="secondary">
            You don't have permission to access the admin dashboard. Please contact your workspace
            administrator to request access.
          </Text>

          <Flex direction="column" gap={8} mt={16}>
            <Text fontSize="sm" textAlign="center" color="tertiary">
              Need help? Contact your admin or{' '}
              <a
                href={`mailto:${SUPPORT_EMAIL}`}
                style={{ color: '#3B82F6', textDecoration: 'underline' }}
              >
                reach out to support
              </a>
              .
            </Text>
          </Flex>
        </Flex>
      </Flex>
    </FullscreenLayout>
  );
};

export { MemberAccessDenied };
