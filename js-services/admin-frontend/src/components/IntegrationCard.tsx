import React, { memo, useState } from 'react';
import type { FC, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Flex, Text, Icon, Badge } from '@gathertown/gather-design-system';
import { useIntegrations } from '../contexts/IntegrationsContext';
import { IntegrationAlertModal } from './IntegrationAlertModal';
import styles from './IntegrationCard.module.css';
import { useTrackEvent } from '../hooks/useTrackEvent';
import { zendeskPath } from '../connectors/zendesk/zendeskRoutes';
import { asanaPath } from '../connectors/asana/asanaRoutes';
import { snowflakePath } from '../connectors/snowflake/snowflakeRoutes';
import { firefliesPath } from '../connectors/fireflies/fiefliesRoutes';
import { customDataPath } from '../connectors/custom-data/customDataRoutes';
import { gitlabPath } from '../connectors/gitlab/gitlabRoutes';
import { clickupPath } from '../connectors/clickup/clickupRoutes';
import { pylonPath } from '../connectors/pylon/pylonRoutes';
import { mondayPath } from '../connectors/monday/mondayRoutes';
import { pipedrivePath } from '../connectors/pipedrive/pipedriveRoutes';
import { figmaPath } from '../connectors/figma/figmaRoutes';
import { POSTHOG_ROUTE_PATH } from '../connectors/posthog/posthogRoutes';
import { canvaPath } from '../connectors/canva/canvaRoutes';
import { teamworkPath } from '../connectors/teamwork/teamworkRoutes';

interface IntegrationCardProps {
  integrationId: string;
}

const IntegrationCard: FC<IntegrationCardProps> = memo(({ integrationId }) => {
  const { integrations } = useIntegrations();
  const { trackEvent } = useTrackEvent();
  const navigate = useNavigate();

  const [openIntegrationAlertModal, setOpenIntegrationAlertModal] = useState(false);

  const integration = integrations.find((int) => int.id === integrationId);

  if (!integration) {
    return null;
  }

  const { Icon: IntegrationIcon, name, state, contentCount } = integration;

  const handleSetupClick = () => {
    // Navigate to the integration-specific page
    const routeMap: Record<string, string> = {
      slack: '/integrations/slack-export',
      github: '/integrations/github',
      jira: '/integrations/jira',
      confluence: '/integrations/confluence',
      notion: '/integrations/notion',
      linear: '/integrations/linear',
      google_drive: '/integrations/google-drive',
      google_email: '/integrations/google-email',
      salesforce: '/integrations/salesforce',
      hubspot: '/integrations/hubspot',
      attio: '/integrations/attio',
      gong: '/integrations/gong',
      gather: '/integrations/gather',
      zendesk: zendeskPath,
      trello: '/integrations/trello',
      intercom: '/integrations/intercom',
      asana: asanaPath,
      snowflake: snowflakePath,
      fireflies: firefliesPath,
      custom_data: customDataPath,
      gitlab: gitlabPath,
      clickup: clickupPath,
      pylon: pylonPath,
      monday: mondayPath,
      pipedrive: pipedrivePath,
      figma: figmaPath,
      posthog: POSTHOG_ROUTE_PATH,
      canva: canvaPath,
      teamwork: teamworkPath,
    };

    const route = routeMap[integrationId];
    if (route) {
      navigate(route);
    }
  };

  const handleCardClick = () => {
    // If already connected, go directly to the integration page
    if (state === 'connected') {
      handleSetupClick();
      return;
    }
    if (integration.accessItems.length === 0 && !integration.comingSoon) {
      trackEvent('integration_requested', {
        requested_integrations: [integration.name],
      });
      handleSetupClick();
      return;
    }
    setOpenIntegrationAlertModal(true);
  };

  const getStatusIcon = (): ReactNode => {
    switch (state) {
      case 'connected':
        return <Icon name="checkCircle" size="lg" color="successPrimary" />;
      default:
        return null;
    }
  };

  const getStatusText = (): ReactNode => {
    switch (state) {
      case 'connected':
        return (
          <Flex direction="column" style={{ alignItems: 'center' }}>
            <Text fontSize="xs" color="tertiary">
              {contentCount}
            </Text>
          </Flex>
        );
      default:
        return null;
    }
  };

  return (
    <>
      <button
        style={{
          // @ts-ignore
          '--integration-color': integration.rgb,
        }}
        className={styles.integrationCardButton}
        onClick={handleCardClick}
      >
        <Flex
          direction="column"
          gap={8}
          style={{
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
          }}
        >
          {getStatusIcon() && (
            <Flex position="absolute" top="8px" left="8px">
              {getStatusIcon()}
            </Flex>
          )}

          {/* Main icon */}
          <Flex style={{ alignItems: 'center', justifyContent: 'center' }}>
            <IntegrationIcon size={32} />
          </Flex>

          {/* Integration name */}
          <Text fontSize="sm" textAlign="center" fontWeight="medium">
            {name}
          </Text>

          <Flex position="absolute" left={0} right={0} bottom={24} justify="center">
            {integration.comingSoon ? (
              <Badge text="Beta" kind="fill" color="accent" size="sm-square" />
            ) : (
              getStatusText()
            )}
          </Flex>
        </Flex>
      </button>
      <IntegrationAlertModal
        integration={integration}
        open={openIntegrationAlertModal}
        onDismiss={() => setOpenIntegrationAlertModal(false)}
        onSetup={handleSetupClick}
      />
    </>
  );
});

IntegrationCard.displayName = 'IntegrationCard';

export { IntegrationCard };
