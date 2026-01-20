/**
 * Utility functions for mapping between Slack and Linear user identifiers
 * Ported from @exponent/task-extraction/src/utils/userMapping.ts
 */
import { linearSlackUserMapping } from '../primitives/linear-slack-user-mapping.js';

export interface UserMapping {
  linearId: string;
  linearName: string;
  linearDisplayName: string;
  linearEmail: string;
  slackUserId: string | null;
  slackUserName: string | null;
  slackRealName: string | null;
  slackEmail: string | null;
}

/**
 * Map a Slack identifier (user ID, username, or real name) to a Linear user ID
 *
 * @param slackIdentifier - Can be a Slack user ID (U0180NKJP89), username (kumail), or real name (Kumail Jaffer)
 * @returns Linear user UUID if found, null otherwise
 */
export function mapSlackToLinearId(slackIdentifier: string | null | undefined): string | null {
  if (!slackIdentifier) {
    return null;
  }

  const normalized = slackIdentifier.toLowerCase().trim();

  // Try to find a match by:
  // 1. Slack user ID (exact match)
  // 2. Slack username (case-insensitive)
  // 3. Slack real name (case-insensitive)
  // 4. First name from real name (case-insensitive)
  const match = linearSlackUserMapping.find((user) => {
    if (user.slackUserId && user.slackUserId.toLowerCase() === normalized) {
      return true;
    }
    if (user.slackUserName && user.slackUserName.toLowerCase() === normalized) {
      return true;
    }
    if (user.slackRealName && user.slackRealName.toLowerCase() === normalized) {
      return true;
    }
    // Check first name from real name (e.g., "Kumail" from "Kumail Jaffer")
    if (user.slackRealName) {
      const firstName = user.slackRealName.split(' ')[0]?.toLowerCase();
      if (firstName && firstName === normalized) {
        return true;
      }
    }
    return false;
  });

  return match?.linearId ?? null;
}

/**
 * Map a Linear user ID to Slack user information
 *
 * @param linearId - Linear user UUID
 * @returns UserMapping if found, null otherwise
 */
export function mapLinearToSlackId(linearId: string | null | undefined): UserMapping | null {
  if (!linearId) {
    return null;
  }

  return linearSlackUserMapping.find((user) => user.linearId === linearId) ?? null;
}
