import { ConfigKey, ConfigValue } from '../../config/types';
import { isSlackComplete } from '../slack/slack-config';
import { isNotionComplete } from '../notion/notion-config';
import { isGithubComplete } from '../github/github-config';
import { isConfluenceComplete } from '../confluence/confluence-config';
import { isGatherComplete } from '../gather/gather-config';
import { isGongComplete } from '../gong/gong-config';
import { isGoogleDriveComplete } from '../google-drive/google-drive-config';
import { isGoogleEmailComplete } from '../google-email/google-email-config';
import { isHubspotComplete } from '../hubspot/hubspot-config';
import { isJiraComplete } from '../jira/jira-config';
import { isLinearComplete } from '../linear/linear-config';
import { isSalesforceComplete } from '../salesforce/salesforce-config';
import { isTrelloComplete } from '../trello/trello-config';
import { isZendeskComplete } from '../zendesk/zendesk-config';
import { isAsanaComplete } from '../asana/asana-config';
import { isSnowflakeComplete } from '../snowflake/snowflake-config';
import { isIntercomComplete } from '../intercom/intercom-config';
import { isAttioComplete } from '../attio/attio-config';
import { isFirefliesComplete } from '../fireflies/fireflies-config';
import { isPylonComplete } from '../pylon/pylon-config';
import { isCustomDataComplete } from '../custom-data/custom-data-config';
import { isGitlabComplete } from '../gitlab/gitlab-config';
import { isClickupComplete } from '../clickup/clickup-config';
import { isMondayComplete } from '../monday/monday-config';
import { isPipedriveComplete } from '../pipedrive/pipedrive-config';
import { isFigmaComplete } from '../figma/figma-config';
import { isPostHogComplete } from '../posthog/posthog-config';
import { isCanvaComplete } from '../canva/canva-config';
import { isTeamworkComplete } from '../teamwork/teamwork-config';

interface Connector {
  source: string;
  isComplete(
    config: Record<ConfigKey, ConfigValue>,
    // @deprecated here for gh, please make all completion status rely on config only
    additionalInfo: Record<string, unknown>
  ): boolean;
}

const allConnectors: Connector[] = [
  {
    source: 'confluence',
    isComplete: isConfluenceComplete,
  },
  {
    source: 'gather',
    isComplete: isGatherComplete,
  },
  {
    source: 'github',
    isComplete: isGithubComplete,
  },
  {
    source: 'gitlab',
    isComplete: isGitlabComplete,
  },
  {
    source: 'gong',
    isComplete: isGongComplete,
  },
  {
    source: 'google_drive',
    isComplete: isGoogleDriveComplete,
  },
  {
    source: 'google_email',
    isComplete: isGoogleEmailComplete,
  },
  {
    source: 'hubspot',
    isComplete: isHubspotComplete,
  },
  {
    source: 'jira',
    isComplete: isJiraComplete,
  },
  {
    source: 'linear',
    isComplete: isLinearComplete,
  },
  {
    source: 'notion',
    isComplete: isNotionComplete,
  },
  {
    source: 'salesforce',
    isComplete: isSalesforceComplete,
  },
  {
    source: 'slack',
    isComplete: isSlackComplete,
  },
  {
    source: 'trello',
    isComplete: isTrelloComplete,
  },
  {
    source: 'zendesk',
    isComplete: isZendeskComplete,
  },
  {
    source: 'asana',
    isComplete: isAsanaComplete,
  },
  {
    source: 'snowflake',
    isComplete: isSnowflakeComplete,
  },
  {
    source: 'intercom',
    isComplete: isIntercomComplete,
  },
  {
    source: 'attio',
    isComplete: isAttioComplete,
  },
  {
    source: 'fireflies',
    isComplete: isFirefliesComplete,
  },
  {
    source: 'custom_data',
    isComplete: isCustomDataComplete,
  },
  {
    source: 'clickup',
    isComplete: isClickupComplete,
  },
  {
    source: 'pylon',
    isComplete: isPylonComplete,
  },
  {
    source: 'monday',
    isComplete: isMondayComplete,
  },
  {
    source: 'pipedrive',
    isComplete: isPipedriveComplete,
  },
  {
    source: 'figma',
    isComplete: isFigmaComplete,
  },
  {
    source: 'posthog',
    isComplete: isPostHogComplete,
  },
  {
    source: 'canva',
    isComplete: isCanvaComplete,
  },
  {
    source: 'teamwork',
    isComplete: isTeamworkComplete,
  },
];

class ConnectorStore {
  async getAllConnectors(): Promise<Connector[]> {
    return Object.values(allConnectors);
  }

  async getConnector(source: string): Promise<Connector> {
    const connector = allConnectors.find((c) => c.source === source);

    if (!connector) {
      throw new Error(`Connector with source '${source}' not found.`);
    }

    return connector;
  }
}

export { ConnectorStore };
