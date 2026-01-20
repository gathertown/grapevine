import { Router, Request, Response } from 'express';
import { getSqsClient, isSqsConfigured } from '../jobs/sqs-client.js';
import { ListQueuesCommand } from '@aws-sdk/client-sqs';
import { getOrInitializeRedis } from '../redis-client.js';

const healthRouter = Router();

// Liveness probe - simple server health check
healthRouter.get('/live', (_req: Request, res: Response) => {
  res.json({
    status: 'OK',
    message: 'Server is running',
  });
});

// Readiness probe - check dependencies (SQS)
healthRouter.get('/ready', async (_req: Request, res: Response) => {
  const dependencies: Record<string, { status: string; message: string }> = {};
  let overallStatus = 'ready';

  // Check SQS connectivity
  try {
    if (!isSqsConfigured()) {
      dependencies.sqs = {
        status: 'not_ready',
        message: 'SQS not configured - missing AWS credentials or region',
      };
      overallStatus = 'not_ready';
    } else {
      // Test SQS connectivity with a simple ListQueues operation
      const sqsClient = getSqsClient();
      await sqsClient.send(new ListQueuesCommand({}));
      dependencies.sqs = {
        status: 'ready',
        message: 'SQS client connected successfully',
      };
    }
  } catch (error) {
    dependencies.sqs = {
      status: 'not_ready',
      message: `SQS connectivity failed: ${(error as Error).message}`,
    };
    overallStatus = 'not_ready';
  }

  const responseCode = overallStatus === 'ready' ? 200 : 503;
  res.status(responseCode).json({
    status: overallStatus,
    dependencies,
  });
});

// Redis health check endpoint
healthRouter.get('/redis', async (_req: Request, res: Response) => {
  try {
    const redis = getOrInitializeRedis();

    if (!redis) {
      return res.status(503).json({
        status: 'not_ready',
        message: 'Redis not configured - REDIS_PRIMARY_ENDPOINT not set',
      });
    }

    // Test Redis connectivity with a simple PING operation
    const response = await redis.ping();
    if (response === 'PONG') {
      res.json({
        status: 'ready',
        message: 'Redis client connected successfully',
      });
    } else {
      res.status(503).json({
        status: 'not_ready',
        message: `Redis ping failed: expected PONG, got ${response}`,
      });
    }
  } catch (error) {
    res.status(503).json({
      status: 'not_ready',
      message: `Redis connectivity failed: ${(error as Error).message}`,
    });
  }
});

export { healthRouter };
