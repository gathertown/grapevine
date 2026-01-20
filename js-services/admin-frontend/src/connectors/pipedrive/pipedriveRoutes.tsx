import { Route } from 'react-router-dom';
import { PipedriveIntegrationPage } from './components/PipedriveIntegrationPage';

const pipedrivePath = '/integrations/pipedrive';

const pipedriveRoutes = [
  <Route key="pipedrive-integration" path={pipedrivePath} element={<PipedriveIntegrationPage />} />,
];

export { pipedrivePath, pipedriveRoutes };
