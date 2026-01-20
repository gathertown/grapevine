import { Route } from 'react-router-dom';
import { TeamworkIntegrationPage } from './components/TeamworkIntegrationPage';

const teamworkPath = '/integrations/teamwork';

const teamworkRoutes = [
  <Route key="teamwork-integration" path={teamworkPath} element={<TeamworkIntegrationPage />} />,
];

export { teamworkPath, teamworkRoutes };
