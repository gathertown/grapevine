import { Route } from 'react-router-dom';
import { CustomDataIntegrationPage } from './components/CustomDataIntegrationPage';
import { DocumentTypeDetailsPage } from './components/DocumentTypeDetailsPage';

const customDataPath = '/integrations/custom-data';

const customDataRoutes = [
  <Route
    key="custom-data-integration"
    path={customDataPath}
    element={<CustomDataIntegrationPage />}
  />,
  <Route
    key="custom-data-type-details"
    path={`${customDataPath}/types/:id`}
    element={<DocumentTypeDetailsPage />}
  />,
];

export { customDataPath, customDataRoutes };
