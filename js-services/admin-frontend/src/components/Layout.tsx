import { memo } from 'react';
import type { FC, ReactNode } from 'react';
import { Flex, Text } from '@gathertown/gather-design-system';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useQAOnboarding } from '../contexts/OnboardingContext';
import { useDevMode } from '../hooks/useDevMode';

interface LayoutProps {
  children: ReactNode;
  title?: string;
  subtitle?: string | ReactNode;
}

const Layout: FC<LayoutProps> = memo(({ children, title, subtitle }) => {
  const { steps } = useQAOnboarding();
  const isDevMode = useDevMode();

  // Hide sidebar until steps 1-3 are complete
  const sidebarStepsCompleted = steps.step1 && steps.step2 && steps.step3;
  const showSidebar = sidebarStepsCompleted || isDevMode;

  return (
    <Flex width="100vw" height="100vh" backgroundColor="secondary" direction="column">
      <Header />
      <Flex flex={1}>
        {showSidebar && (
          <div style={{ width: '262px', height: '100%' }}>
            <Sidebar />
          </div>
        )}
        <div style={{ flex: 1, padding: showSidebar ? '0 8px 8px 0' : '0 8px 8px 8px' }}>
          <Flex
            flex={1}
            backgroundColor="primary"
            overflow="auto"
            borderColor="tertiary"
            borderRadius={12}
            borderWidth={1}
            borderStyle="solid"
            style={{ height: 'calc(100vh - 52px)' }}
          >
            <Flex
              maxWidth="800px"
              mx="auto"
              width="100%"
              direction="column"
              style={{ gap: 44 }}
              pt={48}
              px={24}
            >
              {(title || subtitle) && (
                <Flex direction="column" gap={4}>
                  {title && (
                    <div style={{ fontSize: '1.5rem' }}>
                      <Text fontSize="xxl" fontWeight="semibold">
                        {title}
                      </Text>
                    </div>
                  )}
                  {subtitle && <Text color="tertiary">{subtitle}</Text>}
                </Flex>
              )}
              <Flex pb={16}>{children}</Flex>
            </Flex>
          </Flex>
        </div>
      </Flex>
    </Flex>
  );
});

Layout.displayName = 'Layout';

export { Layout };
