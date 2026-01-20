import { initializeNewRelicIfEnabled } from '@corporate-context/backend-common';
initializeNewRelicIfEnabled('grapevine-slack-bot');

import { createSlackEventProcessor } from './jobs/slackEventProcessor';
import express from 'express';
import { getTenantSlackAppManager } from './tenantSlackAppManager';
import { config, IS_DEBUG_MODE } from './config';
import { startDebugSlackApp } from './debugIndex';
import { logger } from './utils/logger';

// Initialize Express app
const expressApp = express();

// Health check endpoints
expressApp.get('/health/live', (_req, res) => {
  return res.status(200).json({ status: 'live' });
});

let processorRef: ReturnType<typeof createSlackEventProcessor> | null = null;
expressApp.get('/health/ready', (_req, res) => {
  if (processorRef?.isRunning()) {
    return res.status(200).json({ status: 'ready' });
  }
  return res.status(503).json({ status: 'not_ready' });
});

// Start Express server
const expressServer = expressApp.listen(config.port, () => {
  logger.info(`Express server running on port ${config.port}`, { operation: 'server-start' });

  // Log race mode status on startup
  if (config.enableAskAgentRaceMode) {
    logger.info('Ask Agent Race Mode is enabled');
  }
});

process.on('uncaughtException', (error) => {
  if (error.message.includes('shutdown') || error.message.includes('db_termination')) {
    logger.info('Database connection terminated, continuing...', { operation: 'db-termination' });
    // Don't exit the process for database termination errors
    return;
  }
  logger.error('Uncaught Exception', error, { operation: 'uncaught-exception' });
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  logger.error(
    'Unhandled Rejection',
    reason instanceof Error ? reason : new Error(String(reason)),
    {
      operation: 'unhandled-rejection',
    }
  );
});

// Check if we should run in debug mode (single-tenant with Socket Mode)
if (IS_DEBUG_MODE || config.socketMode) {
  logger.info('Debug mode detected - starting single-tenant Slack app with Socket Mode', {
    operation: 'debug-mode-start',
  });
  startDebugSlackApp().catch((error) => {
    logger.error('Debug Slack app error', error, { operation: 'debug-app-start' });
    process.exit(1);
  });
} else {
  // Production mode: Start SQS job processor if queue ARN is provided
  const sqsQueueArn = process.env.SLACK_JOBS_QUEUE_ARN;
  if (sqsQueueArn) {
    logger.info('Starting production SQS job processor...', {
      operation: 'sqs-processor-start',
      sqsQueueArn,
    });
    const jobProcessor = createSlackEventProcessor(sqsQueueArn);
    processorRef = jobProcessor;

    // Start job processor in background
    jobProcessor.start().catch((error) => {
      logger.error('SQS job processor error', error, { operation: 'sqs-processor-start' });
    });
  } else {
    logger.info('No SLACK_JOBS_QUEUE_ARN provided, skipping job processor initialization', {
      operation: 'sqs-processor-skip',
    });
  }
}

// Graceful shutdown handlers
process.on('SIGINT', async () => {
  logger.info('Received SIGINT, gracefully shutting down...', {
    operation: 'shutdown',
    signal: 'SIGINT',
  });
  if (processorRef) {
    await processorRef.shutdown();
  }
  const appManager = getTenantSlackAppManager();
  await appManager.shutdown();
  expressServer.close(() => {
    logger.info('Express server stopped', { operation: 'shutdown' });
  });
  process.exit(0);
});

process.on('SIGTERM', async () => {
  logger.info('Received SIGTERM, gracefully shutting down...', {
    operation: 'shutdown',
    signal: 'SIGTERM',
  });
  if (processorRef) {
    await processorRef.shutdown();
  }
  const appManager = getTenantSlackAppManager();
  await appManager.shutdown();
  expressServer.close(() => {
    logger.info('Express server stopped', { operation: 'shutdown' });
  });
  process.exit(0);
});
