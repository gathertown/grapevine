/**
 * Organization API methods
 * Provides methods for organization management using the authenticated API client
 */

import { apiClient } from './client';
import { InvitationRole, Source } from '@corporate-context/shared-common';

// Type definitions
export interface Organization {
  id: string;
  name: string;
  domain?: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreateOrganizationResponse {
  success: boolean;
  organization: Organization;
  tenantId: string;
  message?: string;
}

export interface UserOrganizationsResponse {
  success: boolean;
  organizations: Array<{
    organization: {
      id: string;
      name: string;
      domains?: Array<{
        domain: string;
        state: 'verified' | 'pending' | 'unverified';
      }>;
      isVerified: boolean;
    };
    membership: {
      id: string;
      role: string;
      status: string;
      createdAt: string;
    };
  }>;
}

export interface TenantStatusResponse {
  status: 'provisioned' | 'pending' | 'error' | null;
  tenantId?: string;
  message: string;
  errorMessage?: string;
}

/**
 * Create a new organization
 */
export async function createOrganization(
  name: string,
  source?: Source
): Promise<CreateOrganizationResponse> {
  if (!name || !name.trim()) {
    throw new Error('Organization name is required');
  }

  const payload = {
    name: name.trim(),
    ...(source && { source }),
  };

  return apiClient.post<CreateOrganizationResponse>('/api/organizations/create', payload);
}

/**
 * Get organizations for the authenticated user
 */
export async function getUserOrganizations(userId: string): Promise<UserOrganizationsResponse> {
  if (!userId || !userId.trim()) {
    throw new Error('User ID is required');
  }

  return apiClient.get<UserOrganizationsResponse>(`/api/organizations/user/${userId}`);
}

/**
 * Get tenant provisioning status for the current organization
 */
export async function getTenantStatus(): Promise<TenantStatusResponse> {
  return apiClient.get<TenantStatusResponse>('/api/tenant/status');
}

// Invitation types and API methods
export interface Invitation {
  id: string;
  email: string;
  organizationId: string;
  expiresAt: string;
  status: string;
  createdAt: string;
}

export interface SendInvitationResponse {
  success: boolean;
  invitation: Invitation;
  message: string;
}

export interface ListInvitationsResponse {
  success: boolean;
  invitations: Invitation[];
  count: number;
}

export interface RevokeInvitationResponse {
  success: boolean;
  message: string;
}

/**
 * Send an invitation to join the organization
 */
export async function sendInvitation(
  email: string,
  role: InvitationRole
): Promise<SendInvitationResponse> {
  if (!email || !email.trim()) {
    throw new Error('Email is required');
  }

  const payload = {
    email: email.trim(),
    role,
  };

  return apiClient.post<SendInvitationResponse>('/api/invitations/send', payload);
}

/**
 * Get list of pending invitations for the organization
 */
export async function getInvitations(): Promise<ListInvitationsResponse> {
  return apiClient.get<ListInvitationsResponse>('/api/invitations');
}

/**
 * Revoke a pending invitation
 */
export async function revokeInvitation(invitationId: string): Promise<RevokeInvitationResponse> {
  if (!invitationId || !invitationId.trim()) {
    throw new Error('Invitation ID is required');
  }

  return apiClient.delete<RevokeInvitationResponse>(`/api/invitations/${invitationId}`);
}

// Organization member types and API methods
export interface OrganizationMember {
  type: 'member' | 'invitation';
  id: string;
  userId?: string;
  email: string;
  firstName?: string;
  lastName?: string;
  role?: string; // Role not available for pending invitations
  status: string;
  joinedAt?: string;
  createdAt?: string;
  expiresAt?: string;
}

export interface ListMembersResponse {
  success: boolean;
  members: OrganizationMember[];
  count: number;
}

/**
 * Get organization members and pending invitations
 */
export async function getOrganizationMembers(): Promise<ListMembersResponse> {
  return apiClient.get<ListMembersResponse>('/api/organizations/members');
}
