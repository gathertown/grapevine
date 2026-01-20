/**
 * Slack Bot Logger - Direct access to backend-common logger
 *
 * This module provides direct access to the backend-common logger infrastructure
 * for the slack-bot service. Use LogContext.run() for setting tenant context.
 */

import { createLogger, LogContext, ContextAwareLogger } from '@corporate-context/backend-common';

// Create and export singleton logger instance for slack-bot
export const logger = new ContextAwareLogger(createLogger('slack-bot'));

// Export LogContext for context management
export { LogContext };

// Export types for external use
export type LogContextType = Record<string, unknown>;
