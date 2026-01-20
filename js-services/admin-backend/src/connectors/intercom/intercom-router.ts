import { Router } from 'express';
import { intercomOAuthRouter } from './intercom-oauth-router';

const intercomRouter = Router();

// Mount OAuth routes
intercomRouter.use('', intercomOAuthRouter);

export { intercomRouter };
