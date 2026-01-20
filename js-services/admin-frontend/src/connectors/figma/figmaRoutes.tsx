import { Route } from 'react-router-dom';
import { FigmaIntegrationPage } from './components/FigmaIntegrationPage';

const figmaPath = '/integrations/figma';

const figmaRoutes = [
  <Route key="figma-integration" path={figmaPath} element={<FigmaIntegrationPage />} />,
];

export { figmaPath, figmaRoutes };
