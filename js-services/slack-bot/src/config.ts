import path from 'path';
import fs from 'fs';

export const IS_DEBUG_MODE = !!process.env.DEBUG_MODE;

/**
 * Returns true if progress bar and translation features should be enabled.
 * Controlled via ENABLE_PROGRESS_BAR_AND_TRANSLATION environment variable.
 */
export function shouldUseProgressBarAndTranslation(): boolean {
  return process.env.ENABLE_PROGRESS_BAR_AND_TRANSLATION === 'true';
}

export type FinalAnswerBehavior = 'replace' | 'new_reply';

const FINAL_ANSWER_BEHAVIOR_ENV = process.env.SLACK_FINAL_ANSWER_BEHAVIOR;
const FINAL_ANSWER_BEHAVIOR: FinalAnswerBehavior =
  FINAL_ANSWER_BEHAVIOR_ENV === 'replace' ? 'replace' : 'new_reply';

// Debug mode: Load JWT keys from file paths if specified
if (IS_DEBUG_MODE) {
  if (process.env.INTERNAL_JWT_PRIVATE_KEY_PATH && !process.env.INTERNAL_JWT_PRIVATE_KEY) {
    const keyPath = path.resolve(process.cwd(), process.env.INTERNAL_JWT_PRIVATE_KEY_PATH);
    if (fs.existsSync(keyPath)) {
      process.env.INTERNAL_JWT_PRIVATE_KEY = fs.readFileSync(keyPath, 'utf8');
    }
  }

  if (process.env.INTERNAL_JWT_PUBLIC_KEY_PATH && !process.env.INTERNAL_JWT_PUBLIC_KEY) {
    const keyPath = path.resolve(process.cwd(), process.env.INTERNAL_JWT_PUBLIC_KEY_PATH);
    if (fs.existsSync(keyPath)) {
      process.env.INTERNAL_JWT_PUBLIC_KEY = fs.readFileSync(keyPath, 'utf8');
    }
  }
}

export const config = {
  get openaiApiKey(): string {
    return process.env.OPENAI_API_KEY || '';
  },
  get backendUrl(): string {
    return process.env.MCP_BASE_URL || '';
  },
  get amplitudeApiKey(): string {
    return process.env.VITE_AMPLITUDE_API_KEY || '';
  },
  get baseDomain(): string {
    const baseDomain = process.env.BASE_DOMAIN;
    if (!baseDomain) {
      throw new Error('BASE_DOMAIN environment variable is required');
    }
    return baseDomain;
  },
  get frontendUrl(): string {
    const frontendUrl = process.env.FRONTEND_URL;
    if (!frontendUrl) {
      throw new Error('FRONTEND_URL environment variable is required');
    }
    return frontendUrl;
  },

  port: parseInt(process.env.PORT || '8000', 10),
  socketMode: process.env.SOCKET_MODE ? true : false,

  // JWT configuration for MCP authentication (RSA only)
  internalJwtPrivateKey: process.env.INTERNAL_JWT_PRIVATE_KEY,
  internalJwtPublicKey: process.env.INTERNAL_JWT_PUBLIC_KEY,
  internalJwtIssuer: process.env.INTERNAL_JWT_ISSUER,
  internalJwtAudience: process.env.INTERNAL_JWT_AUDIENCE,
  internalJwtExpiry: process.env.INTERNAL_JWT_EXPIRY || '1h',

  // Feature flags
  enableSlackFeedbackButtons: process.env.ENABLE_SLACK_FEEDBACK_BUTTONS === 'true', // Default to false
  enableAskAgentRaceMode: process.env.ENABLE_ASK_AGENT_RACE_MODE === 'true', // Default to false
  finalAnswerBehavior: FINAL_ANSWER_BEHAVIOR,
} as const;
