import { createLogger, LogContext, ContextAwareLogger } from '@corporate-context/backend-common';

// Create logger instance for admin-backend
const baseLogger = createLogger('admin-backend');

// Export the context-aware logger
export const logger = new ContextAwareLogger(baseLogger);

// Export the raw winston logger for cases where direct access is needed
export const rawLogger = baseLogger;

// Export the LoggerContext for creating scoped contexts
export { LogContext };
