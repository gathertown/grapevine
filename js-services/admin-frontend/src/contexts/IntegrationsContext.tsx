import { createContext, useContext, useEffect, useState, useCallback, memo } from 'react';
import type { FC, ReactNode } from 'react';
import { useBillingStatus } from '../hooks/useBillingStatus';
import { useSourceStats } from '../hooks/useSourceStats';
import {
  isDataSourceComplete,
  isSlackBotConfigured,
  getCompletedDataSourcesCount,
} from '../utils/validation';
import {
  SlackIcon,
  NotionIcon,
  LinearIcon,
  GoogleDriveIcon,
  GitHubIcon,
  SalesforceIcon,
  JiraIcon,
  HubSpotIcon,
  GoogleEmailIcon,
  ConfluenceIcon,
  AsanaIcon,
  GongIcon,
  GranolaIcon,
  IntercomIcon,
  TrelloIcon,
  ZendeskIcon,
  GatherIcon,
  SnowflakeIcon,
  AttioIcon,
  FirefliesIcon,
  PylonIcon,
  MondayIcon,
  PipedriveIcon,
  FigmaIcon,
  PostHogIcon,
  CanvaIcon,
  TeamworkIcon,
  CustomDocumentsIcon,
  GitLabIcon,
  ClickupIcon,
} from '../assets/icons';
import { SALESFORCE_ENABLED, INTERCOM_ENABLED, GITLAB_ENABLED } from '../constants';
import type { Integration, IntegrationsContextType, CompletedSteps } from '../types';
import { useAllConfig, useConnectorStatuses } from '../api/config';
import { useFeatures } from '../api/features';

const IntegrationsContext = createContext<IntegrationsContextType | null>(null);

interface IntegrationsProviderProps {
  children: ReactNode;
}

export const IntegrationsProvider: FC<IntegrationsProviderProps> = memo(({ children }) => {
  const { data: configData } = useAllConfig();
  const { data: featuresData } = useFeatures();
  const { billingStatus } = useBillingStatus();
  const { data: sourceStats } = useSourceStats({ enabled: !!configData });

  const { data: connectorStatuses = [] } = useConnectorStatuses();

  const allIntegrations: Omit<Integration, 'state' | 'contentCount'>[] = [
    // Non-beta integrations first
    {
      id: 'notion',
      name: 'Notion',
      Icon: ({ size = 64 }: { size?: number }) => <NotionIcon size={size} />,
      rgb: '40, 40, 41',
      accessItems: [
        'Read all pages (and sub-pages) you grant access to',
        'Read all users in your workspace',
      ],
    },
    {
      id: 'slack',
      name: 'Slack Export',
      Icon: ({ size = 64 }: { size?: number }) => <SlackIcon size={size} />,
      rgb: '46, 182, 125',
      accessItems: [
        `Read public channel messages and attached files (excluding Slack Connect channels)`,
        `Read all users in your workspace`,
      ],
    },
    {
      id: 'linear',
      name: 'Linear',
      Icon: ({ size = 64 }: { size?: number }) => <LinearIcon size={size} />,
      rgb: '40, 40, 41',
      accessItems: [`Read issues from public teams`, `Read all users in your workspace`],
    },
    {
      id: 'google_drive',
      name: 'Google Drive',
      Icon: ({ size = 64 }: { size?: number }) => <GoogleDriveIcon size={size} />,
      rgb: '69, 134, 242',
      accessItems: [
        `Read files shared company-wide in every user's "My Drive"`,
        `Read files shared company-wide in every Shared Drive`,
        `Read all users in your workspace`,
      ],
    },
    {
      id: 'github',
      name: 'Github',
      Icon: ({ size = 64 }: { size?: number }) => <GitHubIcon size={size} />,
      rgb: '130, 77, 159',
      accessItems: [
        `Read pull requests and code from repositories that you grant access to`,
        `Read all users in workspace`,
      ],
    },
    {
      id: 'gather',
      name: 'Gather',
      Icon: ({ size = 64 }: { size?: number }) => <GatherIcon size={size} />,
      rgb: '76, 112, 238',
      accessItems: [
        `Read meeting messages and transcripts`,
        `Read meeting participants and metadata`,
      ],
    },
    {
      id: 'zendesk',
      name: 'Zendesk',
      Icon: ({ size = 64 }: { size?: number }) => <ZendeskIcon size={size} />,
      rgb: '3, 54, 61',
      accessItems: [
        'Read support tickets and their comments',
        'Read ticket metadata and status information',
        'Read all users in your account',
      ],
    },
    {
      id: 'asana',
      name: 'Asana',
      Icon: ({ size = 64 }: { size?: number }) => <AsanaIcon size={size} />,
      rgb: '255, 88, 74',
      accessItems: [
        'Read workspaces and projects',
        'Read user, team and membership metadata',
        'Read tasks, subtasks, comments and attachments',
      ],
    },
    {
      id: 'fireflies',
      name: 'Fireflies',
      Icon: ({ size = 64 }: { size?: number }) => <FirefliesIcon size={size} />,
      rgb: '234, 65, 143',
      accessItems: ['Read transcripts and summaries', 'Read meeting participants'],
    },
    {
      id: 'pylon',
      name: 'Pylon',
      Icon: ({ size = 64 }: { size?: number }) => <PylonIcon size={size} />,
      rgb: '79, 70, 229',
      accessItems: [
        'Read support issues and messages',
        'Read customer accounts and contacts',
        'Read team member assignments',
      ],
    },
    // Beta integrations (comingSoon: true or feature flag dependent)
    {
      id: 'google_email',
      name: 'Gmail',
      Icon: ({ size = 64 }: { size?: number }) => <GoogleEmailIcon size={size} />,
      rgb: '234, 67, 53',
      accessItems: [`Read all emails in your inbox`, `Read all users in your workspace`],
      comingSoon: false,
    },
    {
      id: 'salesforce',
      name: 'Salesforce',
      Icon: ({ size = 64 }: { size?: number }) => <SalesforceIcon size={size} />,
      rgb: '23, 156, 215',
      accessItems: [`Read Account, Contact, Opportunity, Lead, and Case objects in your org`],
      comingSoon: !SALESFORCE_ENABLED,
    },
    {
      id: 'jira',
      name: 'Jira',
      Icon: ({ size = 64 }: { size?: number }) => <JiraIcon size={size} />,
      rgb: '24, 104, 219',
      accessItems: [
        `Read issues shared site-wide`,
        `Read all projects in your site`,
        `Read all users in your site`,
      ],
      comingSoon: false,
    },
    {
      id: 'hubspot',
      name: 'HubSpot',
      Icon: ({ size = 64 }: { size?: number }) => <HubSpotIcon size={size} />,
      rgb: '255, 122, 89',
      accessItems: [
        'Read Contacts, Companies, Deals, and Tickets in your account',
        'Read all users in your account',
      ],
      comingSoon: false,
    },
    {
      id: 'attio',
      name: 'Attio',
      Icon: ({ size = 64 }: { size?: number }) => <AttioIcon size={size} />,
      rgb: '93, 95, 239',
      accessItems: [
        'Read Companies, People, and Deals in your workspace',
        'Read Notes and Tasks attached to records',
        'Read all users in your workspace',
      ],
      oauth: true,
      comingSoon: false,
    },
    {
      id: 'gong',
      name: 'Gong',
      Icon: ({ size = 64 }: { size?: number }) => <GongIcon size={size} />,
      rgb: '128, 57, 233',
      accessItems: [
        'Read call recordings, transcripts, and meeting metadata',
        'Read all public library folders',
        'Read all your workspaces',
        'Read all users in your workspaces',
      ],
      oauth: true,
      comingSoon: false,
    },
    {
      id: 'confluence',
      name: 'Confluence',
      Icon: ({ size = 64 }: { size?: number }) => <ConfluenceIcon size={size} />,
      rgb: '24, 104, 219',
      accessItems: [
        `Read pages shared site-wide`,
        `Read all spaces in your site`,
        `Read all users in your site`,
      ],
      comingSoon: false,
    },
    {
      id: 'snowflake',
      name: 'Snowflake',
      Icon: ({ size = 64 }: { size?: number }) => <SnowflakeIcon size={size} />,
      rgb: '41, 181, 232',
      accessItems: [
        'Query your Snowflake data warehouse with natural language',
        'Execute SQL queries on your data',
        'Access tables, views, and semantic models',
      ],
      oauth: true,
      comingSoon: false,
    },
    {
      id: 'granola',
      name: 'Granola',
      Icon: ({ size = 64 }: { size?: number }) => <GranolaIcon size={size} />,
      rgb: '0, 75, 36',
      accessItems: [],
      comingSoon: true,
    },
    {
      id: 'trello',
      name: 'Trello',
      Icon: ({ size = 64 }: { size?: number }) => <TrelloIcon size={size} />,
      rgb: '21, 88, 188',
      accessItems: [
        'Read all boards you have access to',
        'Read card descriptions, comments, and checklists',
        'Read workspace and board metadata',
      ],
      comingSoon: false,
    },
    {
      id: 'intercom',
      name: 'Intercom',
      Icon: ({ size = 64 }: { size?: number }) => <IntercomIcon size={size} />,
      rgb: '1, 198, 208',
      accessItems: [
        'Read conversations and messages',
        'Read contacts and users',
        'Read articles and help center content',
      ],
      comingSoon: !INTERCOM_ENABLED,
    },
    {
      id: 'gitlab',
      name: 'GitLab',
      Icon: ({ size = 64 }: { size?: number }) => <GitLabIcon size={size} />,
      rgb: '226, 67, 41',
      accessItems: [
        'Read merge requests and code from repositories',
        'Read issues and project metadata',
        'Read all users in your workspace',
      ],
      oauth: true,
      comingSoon: !GITLAB_ENABLED,
    },
    {
      id: 'custom_data',
      name: 'Custom Data',
      Icon: ({ size = 64 }: { size?: number }) => <CustomDocumentsIcon size={size} />,
      rgb: '99, 102, 241',
      accessItems: [
        'Define custom document types with flexible schemas',
        'Ingest documents via REST API',
        'Index custom content for AI-powered search',
      ],
    },
    {
      id: 'clickup',
      name: 'ClickUp',
      Icon: ({ size = 64 }: { size?: number }) => <ClickupIcon size={size} />,
      rgb: '253, 56, 142',
      accessItems: [
        "Read enabled space's Folders, Lists, and Tasks",
        'Read Tasks metadata',
        'Read Permissions to determine Task visibility',
      ],
    },
    {
      id: 'monday',
      name: 'Monday.com',
      Icon: ({ size = 64 }: { size?: number }) => <MondayIcon size={size} />,
      rgb: '255, 56, 100',
      accessItems: [
        'Read boards, items (tasks), and updates (comments)',
        'Read workspaces and team metadata',
        'Read all users in your account',
      ],
      oauth: true,
      comingSoon: !featuresData?.['connector:monday'],
    },
    {
      id: 'pipedrive',
      name: 'Pipedrive',
      Icon: ({ size = 64 }: { size?: number }) => <PipedriveIcon size={size} />,
      rgb: '0, 212, 149',
      accessItems: [
        'Read deals, persons (contacts), and organizations',
        'Read activities and notes attached to records',
        'Read all users in your account',
      ],
      oauth: true,
      comingSoon: !featuresData?.['connector:pipedrive'],
    },
    {
      id: 'figma',
      name: 'Figma',
      Icon: ({ size = 64 }: { size?: number }) => <FigmaIcon size={size} />,
      rgb: '162, 89, 255',
      accessItems: [
        'Read design files and their metadata',
        'Read file comments and discussions',
        'Read teams and projects you have access to',
      ],
      oauth: true,
      comingSoon: !featuresData?.['connector:figma'],
    },
    {
      id: 'posthog',
      name: 'PostHog',
      Icon: ({ size = 64 }: { size?: number }) => <PostHogIcon size={size} />,
      rgb: '29, 74, 255',
      accessItems: [
        'Read dashboards and insights',
        'Read feature flags and experiments',
        'Read surveys and annotations',
      ],
      comingSoon: !featuresData?.['connector:posthog'],
    },
    {
      id: 'canva',
      name: 'Canva',
      Icon: ({ size = 64 }: { size?: number }) => <CanvaIcon size={size} />,
      rgb: '123, 47, 247',
      accessItems: [
        'Read design files and their metadata',
        'Read design titles and descriptions',
        'Access designs owned by the connecting user',
      ],
      oauth: true,
      comingSoon: !featuresData?.['connector:canva'],
    },
    {
      id: 'teamwork',
      name: 'Teamwork',
      Icon: ({ size = 64 }: { size?: number }) => <TeamworkIcon size={size} />,
      rgb: '74, 144, 226',
      accessItems: [
        'Read projects, tasks, and milestones',
        'Read comments and task updates',
        'Read all users in your workspace',
      ],
      oauth: true,
      comingSoon: !featuresData?.['connector:teamwork'],
    },
  ];

  // Calculate integration states
  const getIntegrationState = useCallback(
    (source: string): 'available' | 'connected' => {
      return isDataSourceComplete(source, connectorStatuses ?? []) ? 'connected' : 'available';
    },
    [connectorStatuses]
  );

  // Helper function to format numbers with thousands separators
  const formatNumber = useCallback((num: number): string => {
    return num.toLocaleString();
  }, []);

  // Get content count for connected integrations
  const getContentCount = useCallback(
    (source: string): string | undefined => {
      if (!isDataSourceComplete(source, connectorStatuses ?? [])) {
        return undefined;
      }

      // Use real discovered entity counts from API if available
      const apiSourceName = source;
      if (sourceStats && sourceStats[apiSourceName]?.discovered) {
        // Calculate total discovered entities across all entity types
        const discovered = sourceStats[apiSourceName].discovered;
        const totalDiscovered = Object.values(discovered).reduce((sum, count) => sum + count, 0);

        if (totalDiscovered > 0) {
          return `${formatNumber(totalDiscovered)} items`;
        }
      }

      return '';
    },
    [connectorStatuses, sourceStats, formatNumber]
  );

  // Build the complete integrations list with current states
  const integrations: Integration[] = allIntegrations
    .map((integration) => ({
      ...integration,
      state: getIntegrationState(integration.id),
      contentCount: getContentCount(integration.id),
    }))
    .sort((a, b) => {
      if (a.comingSoon && !b.comingSoon) return 1;
      if (!a.comingSoon && b.comingSoon) return -1;
      return 0;
    });

  // Calculate derived values
  const connectedIntegrations = integrations.filter(
    (integration) => integration.state === 'connected'
  );
  const availableIntegrations = integrations.filter(
    (integration) => integration.state === 'available'
  );
  const hasConnectedIntegrations = connectedIntegrations.length > 0;
  const completedDataSourcesCount = getCompletedDataSourcesCount(connectorStatuses ?? []);

  // Calculate onboarding step completion
  const checkStepCompletion = useCallback((): CompletedSteps => {
    // Count completed data sources using shared validation logic
    const completedSources = getCompletedDataSourcesCount(connectorStatuses ?? []);

    // Check Slack bot configuration
    const slackBotComplete = !!configData && isSlackBotConfigured(configData);

    // Check if billing plan is selected
    const hasBillingPlan = billingStatus?.subscription.hasActiveSubscription || false;

    return {
      step1: slackBotComplete, // Slack bot configuration
      step2: completedSources >= 3, // Data sources (requires 3+ sources)
      step3: !!(configData?.COMPANY_CONTEXT && configData?.COMPANY_CONTEXT.length >= 10), // Company context
      step4: hasBillingPlan, // Billing plan selected
    };
  }, [connectorStatuses, configData, billingStatus]);

  const [completedSteps, setCompletedSteps] = useState<CompletedSteps>({
    step1: false,
    step2: false,
    step3: false,
    step4: false,
  });

  // Update completion status when config data or billing status changes
  const isInitialized = !!configData;
  useEffect(() => {
    if (isInitialized) {
      const newCompletionStatus = checkStepCompletion();
      setCompletedSteps(newCompletionStatus);
    }
  }, [isInitialized, checkStepCompletion]);

  const contextValue: IntegrationsContextType = {
    integrations,
    connectedIntegrations,
    availableIntegrations,
    hasConnectedIntegrations,
    completedDataSourcesCount,
    completedSteps,
    isInitialized,
  };

  return (
    <IntegrationsContext.Provider value={contextValue}>{children}</IntegrationsContext.Provider>
  );
});

IntegrationsProvider.displayName = 'IntegrationsProvider';

export const useIntegrations = (): IntegrationsContextType => {
  const context = useContext(IntegrationsContext);
  if (!context) {
    throw new Error('useIntegrations must be used within an IntegrationsProvider');
  }
  return context;
};

export { IntegrationsContext };
