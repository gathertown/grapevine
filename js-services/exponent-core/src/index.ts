/**
 * Exponent Core - Shared task extraction utilities
 *
 * Provides extraction strategies, prompts, Linear operations, and utilities
 * shared across services (Slack bot triage, eval tooling, document processors).
 */

// Core types
export * from './types';

// Strategy
export {
  SingleAgentStrategy,
  type LinearContext,
  type TaskSourceMetadata,
  type ProcessResult,
} from './SingleAgentStrategy';

// Linear executor (moved from triage)
export { LinearOperationExecutor } from './LinearOperationExecutor';

// Prompts
export { buildSingleAgentMeetingPrompt } from './prompts/meetingTranscriptExtraction';
export { buildSingleAgentSlackPrompt } from './prompts/slackMessageExtraction';
export { buildSingleAgentGithubPrompt } from './prompts/githubPrExtraction';

// Search
export * from './search/types';
export * from './search/provider';
export { createLinearTaskLookupTool } from './mcp/linearTaskLookup';

// Utils
export * from './utils/deduplication';
export { getTeamStateInfo, type TeamStateInfo, type StateKey } from './utils/teamStateCache';
export { mapSlackToLinearId, mapLinearToSlackId, type UserMapping } from './utils/userMapping';
export {
  assessFreshness,
  formatFreshnessForLogging,
  type FreshnessEvaluation,
} from './utils/freshness';
export {
  enhanceOperations,
  enhanceTaskDescription,
  type EnhancementInput,
  type EnhancedDescription,
  type AskAgentFastOptions,
} from './utils/descriptionEnhancer';
