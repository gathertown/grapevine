import { Route } from 'react-router-dom';
import { SnowflakeIntegrationPage } from './components/SnowflakeIntegrationPage';

const snowflakePath = '/integrations/snowflake';

const snowflakeRoutes = [
  <Route key="snowflake-integration" path={snowflakePath} element={<SnowflakeIntegrationPage />} />,
];

export { snowflakePath, snowflakeRoutes };
