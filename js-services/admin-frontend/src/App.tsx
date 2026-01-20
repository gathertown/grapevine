import { memo, useEffect } from 'react';
import type { FC } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { AuthKitProvider } from '@workos-inc/authkit-react';
import { AuthProvider } from './contexts/AuthContext';
import { UploadProvider } from './contexts/UploadContext';
import { IntegrationsProvider } from './contexts/IntegrationsContext';
import { OnboardingProvider } from './contexts/OnboardingContext';
import { SlackBotConfigProvider } from './contexts/SlackBotConfigContext';
import { ApiKeysProvider } from './contexts/ApiKeysContext';
import { AuthWrapper } from './components/AuthWrapper';
import { OnboardingSurvey } from './components/OnboardingSurvey';
import { Initializing } from './components/Initializing';
import { Layout } from './components/Layout';
import { HomePage } from './components/HomePage/HomePage';
import { StatsPage } from './components/StatsPage';
import { InviteAdmins } from './components/InviteAdmins';
import { GitHubRedirect } from './components/GitHubRedirect';
import { IntegrationsPage } from './components/IntegrationsPage';
import { SlackBotPage } from './components/SlackBotPage';
import { OnboardingSlackPage } from './components/onboarding/OnboardingSlackPage';
import { NotionIntegrationPage } from './components/integration-pages/NotionIntegrationPage';
import { SlackIntegrationPage } from './components/integration-pages/SlackIntegrationPage';
import { GitHubIntegrationPage } from './components/integration-pages/GitHubIntegrationPage';
import { JiraIntegrationPage } from './components/integration-pages/JiraIntegrationPage';
import { ConfluenceIntegrationPage } from './components/integration-pages/ConfluenceIntegrationPage';
import { LinearIntegrationPage } from './components/integration-pages/LinearIntegrationPage';
import { GoogleDriveIntegrationPage } from './components/integration-pages/GoogleDriveIntegrationPage';
import { GoogleEmailIntegrationPage } from './components/integration-pages/GoogleEmailIntegrationPage';
import { SalesforceIntegrationPage } from './components/integration-pages/SalesforceIntegrationPage';
import { SalesforceCallbackPage } from './components/integration-pages/SalesforceCallbackPage';
import { HubSpotIntegrationPage } from './components/integration-pages/HubSpotIntegrationPage';
import { AttioIntegrationPage } from './components/integration-pages/AttioIntegrationPage';
import { GongIntegrationPage } from './components/integration-pages/GongIntegrationPage';
import { GongOAuthComplete } from './components/integration-pages/GongOAuthComplete';
import { GatherIntegrationPage } from './components/integration-pages/GatherIntegrationPage';
import { TrelloIntegrationPage } from './components/integration-pages/TrelloIntegrationPage';
import { TrelloOAuthCallbackPage } from './components/integration-pages/TrelloOAuthCallbackPage';
import { IntercomIntegrationPage } from './components/integration-pages/IntercomIntegrationPage';
import { IntercomOAuthCallbackPage } from './components/integration-pages/IntercomOAuthCallbackPage';
import { LinearOAuthCallbackPage } from './components/integration-pages/LinearOAuthCallbackPage';
import { SlackOAuthComplete } from './components/SlackOAuthComplete';
import { TriageBotPage } from './components/TriageBotPage';
import './App.css';
import { useAuth } from './hooks/useAuth';
import { BillingPage } from './components/billing';
import { OrganizationSettings } from './components/OrganizationSettings';
import { ThemeProvider } from '@gathertown/gather-design-system';
import { SampleQuestionsPage } from './components/SampleQuestionsPage';
import { WebhooksPage } from './components/WebhooksPage';
import { ApiKeysPage } from './components/ApiKeysPage';
import { getRouteConfig } from './config/routes';
import { getConfig } from './lib/config';
import { IS_LOCAL, IS_STAGING } from './constants';
import { zendeskRoutes } from './connectors/zendesk/zendeskRoutes';
import { asanaRoutes } from './connectors/asana/asanaRoutes';
import { snowflakeRoutes } from './connectors/snowflake/snowflakeRoutes';
import { firefliesRoutes } from './connectors/fireflies/fiefliesRoutes';
import { pylonRoutes } from './connectors/pylon/pylonRoutes';
import { customDataRoutes } from './connectors/custom-data/customDataRoutes';
import { gitlabRoutes } from './connectors/gitlab/gitlabRoutes';
import { SlackBotAppPage } from './components/SlackBotAppPage';
import { connectorConfigQueryKey, useAllConfig } from './api/config';
import { AgentChatPage } from './components/AgentChatPage';
import { KnowledgeBaseListPage } from './components/KnowledgeBaseListPage';
import { KnowledgeBaseDetailsPage } from './components/KnowledgeBaseDetailsPage';
import { KnowledgeBaseConfigPage } from './components/KnowledgeBaseConfigPage';
import { ArticleViewPage } from './components/ArticleViewPage';
import { ArticleGeneratePage } from './components/ArticleGeneratePage';
import { EvalCapturePage } from './components/EvalCapturePage';
import { ReviewerFeedbackPage } from './components/ReviewerFeedbackPage';
import { useIsFeatureEnabled } from './api/features';
import { clickupRoutes } from './connectors/clickup/clickupRoutes';
import { mondayRoutes } from './connectors/monday/mondayRoutes';
import { pipedriveRoutes } from './connectors/pipedrive/pipedriveRoutes';
import { figmaRoutes } from './connectors/figma/figmaRoutes';
import { posthogRoutes } from './connectors/posthog/posthogRoutes';
import { canvaRoutes } from './connectors/canva/canvaRoutes';
import { teamworkRoutes } from './connectors/teamwork/teamworkRoutes';

// Icon generation interface - no longer used
// interface GenerateIconResult {
//   iconUrl: string;
//   originalIconUrl: string;
// }

const AppContent = memo(() => {
  const queryClient = useQueryClient();
  const { data: configData, error } = useAllConfig();
  const { data: showInternalFeatures } = useIsFeatureEnabled('internal:features');
  const { data: isMondayEnabled } = useIsFeatureEnabled('connector:monday');
  const { data: isPipedriveEnabled } = useIsFeatureEnabled('connector:pipedrive');
  const { data: isFigmaEnabled } = useIsFeatureEnabled('connector:figma');
  const { data: isPostHogEnabled } = useIsFeatureEnabled('connector:posthog');
  const { data: isCanvaEnabled } = useIsFeatureEnabled('connector:canva');
  const { data: isTeamworkEnabled } = useIsFeatureEnabled('connector:teamwork');

  const { signOut, hasOrganization, tenantStatus, tenantError, isProvisioningComplete } = useAuth();
  const location = useLocation();
  const routeConfig = getRouteConfig(location.pathname);

  // Update document title with company name
  useEffect(() => {
    document.title = configData?.COMPANY_NAME
      ? `${configData.COMPANY_NAME} Grapevine`
      : 'Grapevine Admin';
  }, [configData?.COMPANY_NAME]);

  // Show tenant provisioning screen if user has org but tenant isn't ready
  if (hasOrganization && !isProvisioningComplete) {
    // Handle error state
    if (tenantStatus === 'error') {
      return (
        <Initializing error={tenantError ?? 'Tenant provisioning failed'} onSignOut={signOut} />
      );
    }

    // Handle pending state - let Initializing component handle rotating messages
    return <Initializing error={null} onSignOut={signOut} />;
  }

  // Show initializing screen until config is loaded
  if (!configData) {
    const isStatsRoute = location.pathname === '/stats';
    const initMessage = isStatsRoute
      ? 'Loading stats page...'
      : 'Fetching your Grapevine workspace...';

    return (
      <Initializing
        error={error ? 'Failed to load configuration' : null}
        message={initMessage}
        onSignOut={signOut}
        onRetry={() => queryClient.resetQueries({ queryKey: connectorConfigQueryKey })}
      />
    );
  }

  // Check if user has completed the onboarding survey
  // Show survey if user has organization, config is loaded, but hasn't completed survey
  if (hasOrganization && isProvisioningComplete && !!configData) {
    const hasCompletedSurvey = configData.HAS_COMPLETED_ONBOARDING_SURVEY === 'true';

    if (!hasCompletedSurvey) {
      return <OnboardingSurvey />;
    }
  }

  return (
    <Layout title={routeConfig?.title} subtitle={routeConfig?.subtitle}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route path="/slackbot" element={<SlackBotPage />} />
        <Route path="/apps/triage" element={<TriageBotPage />} />
        <Route path="/billing" element={<BillingPage />} />
        <Route path="/api-keys" element={<ApiKeysPage />} />
        <Route path="/organization-settings" element={<OrganizationSettings />} />
        <Route path="/invite" element={<InviteAdmins />} />
        <Route path="/github-redirect" element={<GitHubRedirect />} />
        <Route path="/prototype/sample-questions" element={<SampleQuestionsPage />} />
        <Route path="/webhooks" element={<WebhooksPage />} />
        <Route path="/prototype/webhooks" element={<Navigate to="/webhooks" replace />} />
        <Route path="/apps/ask-grapevine" element={<SlackBotAppPage />} />
        <Route path="/debug/agent-chat" element={<AgentChatPage />} />

        {/* Eval Capture - Non-production environments only */}
        {(IS_STAGING || IS_LOCAL) && <Route path="/eval-capture" element={<EvalCapturePage />} />}

        {/* Reviewer Feedback - Internal only */}
        {showInternalFeatures && <Route path="/apps/reviewer" element={<ReviewerFeedbackPage />} />}

        {/* Knowledge Base Routes */}
        <Route path="/knowledge-bases" element={<KnowledgeBaseListPage />} />
        <Route path="/knowledge-bases/:id" element={<KnowledgeBaseDetailsPage />} />
        <Route path="/knowledge-bases/:id/config" element={<KnowledgeBaseConfigPage />} />
        <Route path="/knowledge-bases/:id/articles/:articleId" element={<ArticleViewPage />} />
        <Route
          path="/knowledge-bases/:id/articles/:articleId/generate"
          element={<ArticleGeneratePage />}
        />

        {/* Integration Pages Routes */}
        <Route path="/integrations/notion" element={<NotionIntegrationPage />} />
        <Route path="/integrations/slack-export" element={<SlackIntegrationPage />} />
        <Route path="/integrations/github" element={<GitHubIntegrationPage />} />
        <Route path="/integrations/jira" element={<JiraIntegrationPage />} />
        <Route path="/integrations/confluence" element={<ConfluenceIntegrationPage />} />
        <Route path="/integrations/linear" element={<LinearIntegrationPage />} />
        <Route path="/integrations/linear/callback" element={<LinearOAuthCallbackPage />} />
        <Route path="/integrations/google-drive" element={<GoogleDriveIntegrationPage />} />
        <Route path="/integrations/google-email" element={<GoogleEmailIntegrationPage />} />
        <Route path="/integrations/salesforce" element={<SalesforceIntegrationPage />} />
        <Route path="/integrations/salesforce/callback" element={<SalesforceCallbackPage />} />
        <Route path="/integrations/hubspot" element={<HubSpotIntegrationPage />} />
        <Route path="/integrations/attio" element={<AttioIntegrationPage />} />
        <Route path="/integrations/gong" element={<GongIntegrationPage />} />
        <Route path="/integrations/gather" element={<GatherIntegrationPage />} />
        <Route path="/integrations/trello" element={<TrelloIntegrationPage />} />
        <Route path="/integrations/trello/callback" element={<TrelloOAuthCallbackPage />} />
        <Route path="/integrations/intercom" element={<IntercomIntegrationPage />} />
        <Route path="/integrations/intercom/callback" element={<IntercomOAuthCallbackPage />} />
        <Route path="/slack/oauth/complete" element={<SlackOAuthComplete />} />
        <Route path="/gong/oauth/complete" element={<GongOAuthComplete />} />

        {...zendeskRoutes}
        {...asanaRoutes}
        {...snowflakeRoutes}
        {...customDataRoutes}
        {...gitlabRoutes}
        {...firefliesRoutes}
        {...clickupRoutes}
        {isMondayEnabled && [...mondayRoutes]}
        {isPipedriveEnabled && [...pipedriveRoutes]}
        {isFigmaEnabled && [...figmaRoutes]}
        {isPostHogEnabled && [...posthogRoutes]}
        {isCanvaEnabled && [...canvaRoutes]}
        {isTeamworkEnabled && [...teamworkRoutes]}
        {...pylonRoutes}

        {/* Onboarding Routes */}
        <Route path="/onboarding/slack" element={<OnboardingSlackPage />} />
      </Routes>
    </Layout>
  );
});

AppContent.displayName = 'AppContent';

// See: https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults
const tenSecondsMs = 10 * 1000;
const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: tenSecondsMs } },
});

export const App: FC = () => {
  const config = getConfig();
  const workOSClientId: string = config.WORKOS_CLIENT_ID || '';
  const workOSApiHostname: string = config.WORKOS_API_HOSTNAME || 'api.workos.com';
  const redirectUri: string = config.FRONTEND_URL || window.location.origin;

  // Authenticated application shell rendered for all non-SSO popup routes
  const AuthenticatedShell: FC = () => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthWrapper>
          <SlackBotConfigProvider>
            <UploadProvider>
              <ApiKeysProvider>
                <IntegrationsProvider>
                  <OnboardingProvider>
                    <AppContent />
                    <div id="portal-root" />
                  </OnboardingProvider>
                </IntegrationsProvider>
              </ApiKeysProvider>
            </UploadProvider>
          </SlackBotConfigProvider>
        </AuthWrapper>
      </AuthProvider>
    </QueryClientProvider>
  );

  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthKitProvider
          clientId={workOSClientId}
          apiHostname={workOSApiHostname}
          redirectUri={redirectUri}
          devMode={true} // if you don't have a custom Authentication API domain set up, use devMode. This keeps the
          // refresh token in memory rather than storing it in an http-only cookie.
          // when we set up a custom Auth API domain, restore this to use devMode only in local:
          // window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        >
          <Routes>
            <Route path="/*" element={<AuthenticatedShell />} />
          </Routes>
        </AuthKitProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
};
