/**
 * Invitations Controller
 * Handles organization invitations using WorkOS and optionally Mailgun
 *
 * WorkOS always creates the invitation record. Email delivery:
 * - WorkOS may send emails based on platform configuration (not controlled here)
 * - If Mailgun is configured, we also send an email via Mailgun
 */

import { Router, Request, Response } from 'express';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { getWorkOSClient } from '../workos-client.js';
import { sendTemplateEmail, isMailgunConfigured } from '../mailgun-client.js';
import {
  VALID_INVITATION_ROLES,
  DEFAULT_INVITATION_ROLE,
  InvitationRole,
  INVITATION_EXPIRY_DAYS,
} from '@corporate-context/shared-common';

const invitationsRouter = Router();

/**
 * Helper function to create invitation success message
 */
const createInvitationMessage = (email: string, role: InvitationRole, orgName?: string): string => {
  const baseMessage = `Invitation sent to ${email} as ${role}`;
  return orgName ? `${baseMessage} for organization ${orgName}` : baseMessage;
};

/**
 * Send an invitation to join the organization
 * POST /api/invitations/send
 *
 * Creates invitation via WorkOS (which may send email based on platform config).
 * If Mailgun is configured, also sends email via Mailgun.
 */
invitationsRouter.post('/send', requireAdmin, async (req: Request, res: Response) => {
  try {
    const { email, role: requestedRole } = req.body;

    // Validate email
    if (!email || typeof email !== 'string' || !email.trim()) {
      return res.status(400).json({
        error: 'Email is required',
      });
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email.trim())) {
      return res.status(400).json({
        error: 'Please provide a valid email address',
      });
    }

    // Validate and normalize role
    const role: InvitationRole =
      requestedRole && VALID_INVITATION_ROLES.includes(requestedRole as InvitationRole)
        ? (requestedRole as InvitationRole)
        : DEFAULT_INVITATION_ROLE;

    if (requestedRole && !VALID_INVITATION_ROLES.includes(requestedRole as InvitationRole)) {
      return res.status(400).json({
        error: 'Invalid role. Must be either "admin" or "member"',
      });
    }

    // Get user's organization ID
    const user = req.user;
    if (!user?.organizationId) {
      return res.status(400).json({
        error: 'No organization found for current user',
      });
    }

    const workos = getWorkOSClient();
    if (!workos) {
      return res.status(500).json({
        error: 'WorkOS not configured. Please set WORKOS_API_KEY environment variable.',
      });
    }

    // Check if user has admin role in the organization
    try {
      const memberships = await workos.userManagement.listOrganizationMemberships({
        userId: user.id,
        organizationId: user.organizationId,
        statuses: ['active'],
      });

      const userMembership = memberships.data.find(
        (membership) =>
          membership.userId === user.id && membership.organizationId === user.organizationId
      );

      if (!userMembership || userMembership.role?.slug !== 'admin') {
        return res.status(403).json({
          error: 'Only organization admins can send invitations',
        });
      }
    } catch (error) {
      console.error('Error checking user permissions:', error);
      return res.status(500).json({
        error: 'Failed to verify permissions',
      });
    }

    // Get organization details for email template
    let organization;
    try {
      organization = await workos.organizations.getOrganization(user.organizationId);
    } catch (error) {
      console.error('Error fetching organization:', error);
      return res.status(500).json({
        error: 'Failed to fetch organization details',
      });
    }

    // Create invitation via WorkOS
    let invitation;
    try {
      invitation = await workos.userManagement.sendInvitation({
        email: email.trim(),
        organizationId: user.organizationId,
        expiresInDays: INVITATION_EXPIRY_DAYS,
        roleSlug: role,
      });
    } catch (error: unknown) {
      console.error('Error creating WorkOS invitation:', error);

      // Handle specific WorkOS errors
      if (error && typeof error === 'object' && 'code' in error) {
        if (error.code === 'invitation_already_exists') {
          return res.status(409).json({
            error: 'An invitation has already been sent to this email address',
          });
        }

        if (error.code === 'user_already_exists') {
          return res.status(409).json({
            error: 'A user with this email is already a member of the organization',
          });
        }
      }

      return res.status(500).json({
        error: 'Failed to create invitation',
        details:
          process.env.NODE_ENV === 'development' &&
          error &&
          typeof error === 'object' &&
          'message' in error
            ? error.message
            : undefined,
      });
    }

    // If Mailgun is configured, also send invitation email via Mailgun
    let mailgunSent = false;
    if (isMailgunConfigured()) {
      try {
        await sendTemplateEmail(email.trim(), 'grapevine-invite', {
          org_name: organization.name,
          invite_link: invitation.acceptInvitationUrl,
        });
        mailgunSent = true;
      } catch (emailError) {
        // Log warning but don't fail - WorkOS may still send email via platform config
        console.warn('Failed to send invitation email via Mailgun:', emailError);
      }
    }

    const emailNote = mailgunSent ? ' (email sent via Mailgun)' : '';
    console.log(`✅ ${createInvitationMessage(email, role, organization.name)}${emailNote}`);

    res.json({
      success: true,
      invitation: {
        id: invitation.id,
        email: invitation.email,
        organizationId: invitation.organizationId,
        expiresAt: invitation.expiresAt,
        status: invitation.state,
        role,
      },
      message: `${createInvitationMessage(email, role)} successfully`,
    });
  } catch (error) {
    console.error('Error sending invitation:', error);
    res.status(500).json({
      error: 'Failed to send invitation. Please try again.',
      details: process.env.NODE_ENV === 'development' ? (error as Error).message : undefined,
    });
  }
});

/**
 * List pending invitations for the organization
 * GET /api/invitations
 */
invitationsRouter.get('/', requireAdmin, async (req: Request, res: Response) => {
  try {
    const user = req.user;
    if (!user?.organizationId) {
      return res.status(400).json({
        error: 'No organization found for current user',
      });
    }

    const workos = getWorkOSClient();
    if (!workos) {
      return res.status(500).json({
        error: 'WorkOS not configured. Please set WORKOS_API_KEY environment variable.',
      });
    }

    // Check if user has admin role
    try {
      const memberships = await workos.userManagement.listOrganizationMemberships({
        userId: user.id,
        organizationId: user.organizationId,
        statuses: ['active'],
      });

      const userMembership = memberships.data.find(
        (membership) =>
          membership.userId === user.id && membership.organizationId === user.organizationId
      );

      if (!userMembership || userMembership.role?.slug !== 'admin') {
        return res.status(403).json({
          error: 'Only organization admins can view invitations',
        });
      }
    } catch (error) {
      console.error('Error checking user permissions:', error);
      return res.status(500).json({
        error: 'Failed to verify permissions',
      });
    }

    // Get invitations from WorkOS
    const invitations = await workos.userManagement.listInvitations({
      organizationId: user.organizationId,
    });

    const formattedInvitations = invitations.data
      .filter((inv) => inv.state === 'pending')
      .map((inv) => ({
        id: inv.id,
        email: inv.email,
        organizationId: inv.organizationId,
        expiresAt: inv.expiresAt,
        status: inv.state,
        createdAt: inv.createdAt,
      }));

    res.json({
      success: true,
      invitations: formattedInvitations,
      count: formattedInvitations.length,
    });
  } catch (error) {
    console.error('Error fetching invitations:', error);
    res.status(500).json({
      error: 'Failed to fetch invitations. Please try again.',
      details: process.env.NODE_ENV === 'development' ? (error as Error).message : undefined,
    });
  }
});

/**
 * Revoke a pending invitation
 * DELETE /api/invitations/:id
 */
invitationsRouter.delete('/:id', requireAdmin, async (req: Request, res: Response) => {
  try {
    const { id } = req.params;

    if (!id || !id.trim()) {
      return res.status(400).json({
        error: 'Invitation ID is required',
      });
    }

    const user = req.user;
    if (!user?.organizationId) {
      return res.status(400).json({
        error: 'No organization found for current user',
      });
    }

    const workos = getWorkOSClient();
    if (!workos) {
      return res.status(500).json({
        error: 'WorkOS not configured. Please set WORKOS_API_KEY environment variable.',
      });
    }

    // Check if user has admin role
    try {
      const memberships = await workos.userManagement.listOrganizationMemberships({
        userId: user.id,
        organizationId: user.organizationId,
      });

      const userMembership = memberships.data.find(
        (membership) =>
          membership.userId === user.id && membership.organizationId === user.organizationId
      );

      if (!userMembership || userMembership.role?.slug !== 'admin') {
        return res.status(403).json({
          error: 'Only organization admins can revoke invitations',
        });
      }
    } catch (error) {
      console.error('Error checking user permissions:', error);
      return res.status(500).json({
        error: 'Failed to verify permissions',
      });
    }

    // Revoke the invitation
    try {
      await workos.userManagement.revokeInvitation(id.trim());

      console.log(`✅ Invitation ${id} revoked by ${user.email}`);

      res.json({
        success: true,
        message: 'Invitation revoked successfully',
      });
    } catch (error: unknown) {
      console.error('Error revoking invitation:', error);

      if (
        error &&
        typeof error === 'object' &&
        'code' in error &&
        error.code === 'invitation_not_found'
      ) {
        return res.status(404).json({
          error: 'Invitation not found',
        });
      }

      throw error;
    }
  } catch (error) {
    console.error('Error revoking invitation:', error);
    res.status(500).json({
      error: 'Failed to revoke invitation. Please try again.',
      details: process.env.NODE_ENV === 'development' ? (error as Error).message : undefined,
    });
  }
});

export { invitationsRouter };
