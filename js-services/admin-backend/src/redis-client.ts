/**
 * Redis Client Singleton
 *
 * Provides a singleton Redis client for admin backend operations.
 */

import Redis from 'ioredis';
import { logger } from './utils/logger.js';

// Redis client singleton
let redisClient: Redis | null = null;

/**
 * Get or initialize Redis client
 */
export function getOrInitializeRedis(): Redis | null {
  if (!redisClient) {
    const redisUrl = process.env.REDIS_PRIMARY_ENDPOINT;

    if (!redisUrl) {
      logger.warn('REDIS_PRIMARY_ENDPOINT not configured - Redis operations will be disabled');
      return null;
    }

    try {
      // Parse Redis URL if it includes redis:// protocol
      if (redisUrl.startsWith('redis://')) {
        redisClient = new Redis(redisUrl, { lazyConnect: true });
      } else {
        // Handle host:port format
        const [host, port] = redisUrl.split(':');
        redisClient = new Redis({
          host: host || 'localhost',
          port: parseInt(port || '6379', 10),
          lazyConnect: true,
          maxRetriesPerRequest: 3,
        });
      }

      // Error handling
      redisClient.on('error', (err) => {
        logger.error('Redis connection error:', err);
      });

      redisClient.on('connect', () => {
        logger.info('Connected to Redis');
      });

      logger.info('Redis client initialized');
    } catch (error) {
      logger.error('Failed to initialize Redis client:', error);
      return null;
    }
  }

  return redisClient;
}

/**
 * Cleanup Redis connection
 * Should be called when the application shuts down
 */
export function closeRedisConnection(): void {
  if (redisClient) {
    redisClient.disconnect();
    redisClient = null;
    logger.info('Redis connection closed');
  }
}
