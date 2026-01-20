import { Route } from 'react-router-dom';
import { GitLabIntegrationPage } from './GitLabIntegrationPage';
import { GitLabOAuthCallbackPage } from './GitLabOAuthCallbackPage';

export const gitlabPath = '/integrations/gitlab';

export const gitlabRoutes = [
  <Route key="gitlab" path={gitlabPath} element={<GitLabIntegrationPage />} />,
  <Route
    key="gitlab-callback"
    path="/integrations/gitlab/callback"
    element={<GitLabOAuthCallbackPage />}
  />,
];
