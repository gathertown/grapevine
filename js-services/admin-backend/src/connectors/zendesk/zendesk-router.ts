import { Router } from 'express';
import { zendeskOauthRouter } from './zendesk-oauth-router';
import { zendeskBackfillRouter } from './zendesk-backfill-router';

const zendeskRouter = Router();

zendeskRouter.use('', zendeskOauthRouter);
zendeskRouter.use('', zendeskBackfillRouter);

export { zendeskRouter };
