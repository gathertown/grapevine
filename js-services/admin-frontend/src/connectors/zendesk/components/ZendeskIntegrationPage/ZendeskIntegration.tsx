import { ConnectStep } from './zendeskSteps';
import { Integration } from '../../../../types';
import { ZendeskConfig } from '../../zendeskConfig';
import { SetupHeader } from '../../../../components/shared/SetupHeader';
import { Flex } from '@gathertown/gather-design-system';

interface ZendeskIntegrationProps {
  integration: Integration;
  config: ZendeskConfig;
}

const ZendeskIntegration = ({ config, integration }: ZendeskIntegrationProps) => {
  return (
    <Flex direction="column" gap={24}>
      <SetupHeader
        title={`Set up ${integration.name}`}
        primaryIcon={<integration.Icon size={48} />}
        showGrapevine
        showConnection
      />
      <Flex direction="column" gap={16}>
        <ConnectStep config={config} />
      </Flex>
    </Flex>
  );
};

export { ZendeskIntegration };
