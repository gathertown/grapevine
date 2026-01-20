import { Router } from 'express';
import { snowflakeOauthRouter } from './snowflake-oauth-router';
import { snowflakeSemanticModelsRouter } from './snowflake-semantic-models-router';

const snowflakeRouter = Router();

snowflakeRouter.use('', snowflakeOauthRouter);
snowflakeRouter.use('/semantic-models', snowflakeSemanticModelsRouter);

export { snowflakeRouter };
