/**
 * Shared types and constants for invitation management
 */

export const VALID_INVITATION_ROLES = ['admin', 'member'] as const;
export type InvitationRole = (typeof VALID_INVITATION_ROLES)[number];

export const DEFAULT_INVITATION_ROLE: InvitationRole = 'member';

export const INVITATION_EXPIRY_DAYS = 7;
