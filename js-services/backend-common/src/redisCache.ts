/**
 * Redis caching utilities.
 *
 * Provides helper functions for caching values in Redis with automatic fallback.
 */

import { createClient, RedisClientType } from 'redis';
import { createLogger } from './logger';

const logger = createLogger('redisCache');

let redisClient: RedisClientType | null = null;
let redisConnecting: Promise<RedisClientType> | null = null;

/**
 * Get or create Redis client
 */
async function getRedisClient(): Promise<RedisClientType | null> {
  if (redisClient && redisClient.isOpen) {
    return redisClient;
  }

  const redisUrl = process.env.REDIS_PRIMARY_ENDPOINT;
  if (!redisUrl) {
    logger.debug('REDIS_PRIMARY_ENDPOINT not configured - Redis caching disabled');
    return null;
  }

  try {
    // Wait for any ongoing connection attempt
    if (redisConnecting) {
      await redisConnecting;
      return redisClient;
    }

    // Parse Redis URL - handle both redis:// protocol and host:port format
    const url = redisUrl.startsWith('redis://') ? redisUrl : `redis://${redisUrl}`;

    redisClient = createClient({ url });

    // Error handling
    redisClient.on('error', (err) => {
      logger.debug('Redis connection error', { error: err });
    });

    // Connect to Redis
    redisConnecting = redisClient.connect();
    await redisConnecting;
    redisConnecting = null;

    return redisClient;
  } catch (error) {
    logger.debug('Failed to initialize Redis client', { error });
    redisConnecting = null;
    return null;
  }
}

/**
 * Get a value from Redis cache or compute it if not found.
 *
 * This function implements a standard cache-aside pattern:
 * 1. Try to get the value from Redis
 * 2. If not found, compute the value using the provided function
 * 3. Store the computed value in Redis with the specified TTL
 * 4. Return the value
 *
 * @param cacheKey - Redis key to use for caching
 * @param computeFn - Async function to compute the value if cache miss
 * @param serializeFn - Function to serialize the value to a string for Redis
 * @param deserializeFn - Function to deserialize the Redis string back to value
 * @param ttlSeconds - Time-to-live in seconds for the cached value
 * @returns The cached or computed value
 *
 * @example
 * ```typescript
 * const user = await getOrCompute(
 *   `user:${userId}`,
 *   () => fetchUserFromDb(userId),
 *   (u) => JSON.stringify(u),
 *   (s) => JSON.parse(s),
 *   60
 * );
 * ```
 */
export async function getOrCompute<T>(
  cacheKey: string,
  computeFn: () => Promise<T>,
  serializeFn: (value: T) => string,
  deserializeFn: (str: string) => T,
  ttlSeconds: number
): Promise<T> {
  // Try Redis cache first
  try {
    const redis = await getRedisClient();
    if (redis) {
      const cachedValue = await redis.get(cacheKey);

      if (cachedValue !== null) {
        // Cache hit - deserialize and return
        logger.debug(`Cache hit for key: ${cacheKey}`);
        return deserializeFn(cachedValue);
      }
    }
  } catch (error) {
    logger.debug(`Redis unavailable for cache lookup: ${error}`);
    // Fall through to compute
  }

  // Cache miss or Redis unavailable - compute value
  logger.debug(`Cache miss for key: ${cacheKey}`);
  const value = await computeFn();

  // Populate cache for future requests
  try {
    const redis = await getRedisClient();
    if (redis) {
      const serializedValue = serializeFn(value);
      await redis.set(cacheKey, serializedValue, { EX: ttlSeconds });
      logger.debug(`Cached value for key: ${cacheKey} (TTL: ${ttlSeconds}s)`);
    }
  } catch (error) {
    logger.debug(`Failed to cache value: ${error}`);
    // Not critical - continue without caching
  }

  return value;
}

/**
 * Invalidate a cache entry by deleting it from Redis.
 *
 * @param cacheKey - Redis key to invalidate
 * @returns True if the key was deleted, False otherwise
 */
export async function invalidate(cacheKey: string): Promise<boolean> {
  try {
    const redis = await getRedisClient();
    if (redis) {
      const result = await redis.del(cacheKey);
      if (result > 0) {
        logger.debug(`Invalidated cache key: ${cacheKey}`);
      }
      return result > 0;
    }
    return false;
  } catch (error) {
    logger.debug(`Failed to invalidate cache key ${cacheKey}: ${error}`);
    return false;
  }
}
