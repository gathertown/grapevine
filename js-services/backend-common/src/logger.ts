import winston from 'winston';
import { AsyncLocalStorage } from 'async_hooks';

// Custom log levels for New Relic integration
const logLevels = {
  error: 0,
  warn: 1,
  info: 2,
  debug: 3,
};

// Colors for console output in development
const logColors = {
  error: 'red',
  warn: 'yellow',
  info: 'green',
  debug: 'blue',
};

winston.addColors(logColors);

/**
 * Safe JSON stringification that handles circular references
 * Replaces circular references with '[Circular]' markers
 */
function safeStringify(obj: unknown, indent?: string | number): string {
  const seen = new WeakSet();

  return JSON.stringify(
    obj,
    (_key, value) => {
      // Handle null and primitives
      if (value === null || typeof value !== 'object') {
        return value;
      }

      // Detect circular reference
      if (seen.has(value)) {
        return '[Circular]';
      }

      seen.add(value);
      return value;
    },
    indent
  );
}

/**
 * Logger context manager using AsyncLocalStorage for automatic context inheritance
 * Provides Python-like context management for structured logging.
 *
 * @example Basic usage
 * ```typescript
 * // Add context for a block of code
 * LogContext.run({ userId: '123', operation: 'upload' }, () => {
 *   logger.info('Starting upload'); // Automatically includes userId and operation
 *
 *   // Nested contexts inherit parent context
 *   LogContext.run({ filename: 'data.csv' }, () => {
 *     logger.info('Processing file'); // Includes userId, operation, AND filename
 *   });
 * });
 * ```
 */
export class LogContext {
  private static storage = new AsyncLocalStorage<Record<string, unknown>>();

  /**
   * Run a function with additional logging context
   * Context is automatically inherited by all nested calls
   *
   * @param context - Key-value pairs to add to the logging context
   * @param fn - Function to run within the context
   * @returns The return value of the function
   */
  static run<T>(context: Record<string, unknown>, fn: () => T | Promise<T>): T | Promise<T> {
    const currentContext = this.storage.getStore() || {};
    const mergedContext = { ...currentContext, ...context };
    return this.storage.run(mergedContext, fn);
  }

  /**
   * Get the current logging context
   *
   * @returns The current context object, or an empty object if no context is set
   */
  static getContext(): Record<string, unknown> {
    return this.storage.getStore() || {};
  }

  /**
   * Check if we're currently in a logging context
   *
   * @returns true if running within a LogContext.run() call
   */
  static hasContext(): boolean {
    return this.storage.getStore() !== undefined;
  }
}

// Get log level from environment or default to 'info'
const getLogLevel = (): string => {
  const envLevel = process.env.LOG_LEVEL?.toLowerCase();
  return Object.keys(logLevels).includes(envLevel || '') ? (envLevel as string) : 'info';
};

// Check if we're in production environment
const isProduction = process.env.NODE_ENV === 'production';

// Create custom format for development (human-readable)
const devFormat = winston.format.combine(
  winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
  winston.format.colorize({ all: true }),
  winston.format.printf(({ timestamp, level, message, context, ...meta }) => {
    let logMessage = `[${timestamp}] ${level}: ${message}`;

    // Add context if provided
    if (context) {
      logMessage += ` [${context}]`;
    }

    // Add metadata if present
    const metaStr = Object.keys(meta).length > 0 ? safeStringify(meta, 2) : '';
    if (metaStr) {
      logMessage += `\n${metaStr}`;
    }

    return logMessage;
  })
);

// Create format for production (structured JSON for New Relic)
const prodFormat = winston.format.combine(
  winston.format.timestamp(),
  winston.format.errors({ stack: true }),
  winston.format.printf((info) => {
    // Use safeStringify to handle circular references explicitly
    return safeStringify(info);
  })
);

/**
 * Create a logger instance for a specific service
 */
export function createLogger(serviceName: string): winston.Logger {
  return winston.createLogger({
    levels: logLevels,
    level: getLogLevel(),
    format: isProduction ? prodFormat : devFormat,
    defaultMeta: {
      service: serviceName,
    },
    transports: [
      new winston.transports.Console({
        handleExceptions: true,
        handleRejections: true,
      }),
    ],
    exitOnError: false,
  });
}

/**
 * Context-aware logger that automatically merges AsyncLocalStorage context
 * with any additional context provided to individual log calls
 */
export class ContextAwareLogger {
  protected baseLogger: winston.Logger;

  constructor(baseLogger: winston.Logger) {
    this.baseLogger = baseLogger;
  }

  private formatMessage(
    message: string,
    additionalContext?: Record<string, unknown>
  ): [string, Record<string, unknown>] {
    // Get context from AsyncLocalStorage
    const autoContext = LogContext.getContext();

    // Merge with any additional context provided
    const meta = { ...autoContext, ...additionalContext };

    // Add context to message for development (visual indicator)
    if (!isProduction) {
      const contextParts = [];
      if (meta.requestId) contextParts.push(`req:${meta.requestId}`);
      if (meta.tenantId) contextParts.push(`tenant:${meta.tenantId}`);
      if (meta.operation) contextParts.push(`op:${meta.operation}`);

      if (contextParts.length > 0) {
        meta.context = contextParts.join('|');
      }
    }

    return [message, meta];
  }

  error(
    message: string,
    error?: Error | unknown,
    additionalContext?: Record<string, unknown>
  ): void {
    const [msg, meta] = this.formatMessage(message, additionalContext);

    if (error) {
      if (error instanceof Error) {
        meta.error = {
          message: error.message,
          stack: error.stack,
          name: error.name,
        };
      } else {
        meta.error = String(error);
      }
    }

    this.baseLogger.error(msg, meta);
  }

  warn(message: string, additionalContext?: Record<string, unknown>): void {
    const [msg, meta] = this.formatMessage(message, additionalContext);
    this.baseLogger.warn(msg, meta);
  }

  info(message: string, additionalContext?: Record<string, unknown>): void {
    const [msg, meta] = this.formatMessage(message, additionalContext);
    this.baseLogger.info(msg, meta);
  }

  debug(message: string, additionalContext?: Record<string, unknown>): void {
    const [msg, meta] = this.formatMessage(message, additionalContext);
    this.baseLogger.debug(msg, meta);
  }
}

// Create a default context-aware logger for backend-common
const baseLogger = createLogger('backend-common');
export const logger = new ContextAwareLogger(baseLogger);

// Export the raw winston logger creation function
export { winston };
