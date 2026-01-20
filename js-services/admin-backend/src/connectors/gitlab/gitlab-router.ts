import { Router } from 'express';
import { gitlabOAuthRouter } from './gitlab-oauth-router.js';

const gitlabRouter = Router();

// Mount OAuth routes
gitlabRouter.use('/', gitlabOAuthRouter);

export { gitlabRouter };
