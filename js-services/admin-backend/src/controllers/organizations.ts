import { Router } from 'express';
import { requireAdmin, requireUser } from '../middleware/auth-middleware.js';
import { getWorkOSClient } from '../workos-client.js';
import { createTenantProvisioningRequest, getControlDbPool } from '../control-db.js';
import { logger, LogContext } from '../utils/logger.js';
import { getSqsClient } from '../jobs/sqs-client.js';
import { invalidate } from '@corporate-context/backend-common';
import { isValidSource, Source } from '@corporate-context/shared-common';

const organizationsRouter = Router();

// Organization creation endpoint
organizationsRouter.post('/create', requireUser, async (req, res) => {
  return LogContext.run(
    { operation: 'create-organization', endpoint: '/organizations/create' },
    async () => {
      const workos = getWorkOSClient();

      try {
        const { name, source } = req.body;

        // Basic validation
        if (!name) {
          return res.status(400).json({
            error: 'Organization name is required',
          });
        }

        let normalizedSource: Source | undefined = undefined;

        // Validate source if provided
        if (isValidSource(source)) {
          normalizedSource = source;
        }

        // Use verified user data from authentication middleware
        const userId = req.user?.id;
        if (!userId) {
          return res.status(401).json({ error: 'User not authenticated' });
        }

        if (!workos) {
          return res.status(500).json({
            error: 'WorkOS not configured. Please set WORKOS_API_KEY environment variable.',
          });
        }

        // Create organization in WorkOS
        const organizationData = {
          name: name.trim(),
        };

        logger.info('Creating WorkOS organization', { organizationData });

        const organization = await workos.organizations.createOrganization(organizationData);

        logger.info('Organization created successfully', { organizationId: organization.id });

        // Add the user as admin of the organization
        const membershipData = {
          userId,
          organizationId: organization.id,
          roleSlug: 'admin', // Make the creator an admin
        };

        logger.info('Adding user as organization admin', { membershipData });

        const membership = await workos.userManagement.createOrganizationMembership(membershipData);

        logger.info('User added as organization admin', { membershipId: membership.id });

        // Trigger tenant provisioning by writing to the control database
        // This also handles Notion and HubSpot CRM tracking
        logger.info('Triggering tenant provisioning for organization', {
          organizationId: organization.id,
          source: normalizedSource,
        });
        const provisioningResult = await createTenantProvisioningRequest(
          organization.id,
          'grapevine_managed',
          organization.name,
          req.user?.email ? [req.user.email] : [],
          req.user?.firstName,
          req.user?.lastName,
          normalizedSource
        );

        if (!provisioningResult) {
          logger.error('Failed to trigger tenant provisioning', {
            organizationId: organization.id,
          });
          return res.status(500).json({
            error: 'Failed to provision tenant for organization',
            details:
              process.env.NODE_ENV === 'development'
                ? 'Tenant provisioning is required but could not be triggered'
                : undefined,
          });
        }

        res.json({
          success: true,
          organization: {
            id: organization.id,
            name: organization.name,
            domains: organization.domains || [],
            createdAt: organization.createdAt,
          },
          membership: {
            id: membership.id,
            role: membership.role,
          },
          tenantId: provisioningResult.tenantId,
          message: `Organization "${name}" created successfully and you've been added as an admin.`,
        });
      } catch (error) {
        logger.error('Error creating organization', error);

        // Handle specific WorkOS errors
        if (error.code === 'entity_already_exists') {
          return res.status(409).json({
            error: 'An organization with this name or domain already exists.',
          });
        }

        res.status(500).json({
          error: 'Failed to create organization. Please try again.',
          details: process.env.NODE_ENV === 'development' ? error.message : undefined,
        });
      }
    }
  );
});

// Get user's organizations endpoint
organizationsRouter.get('/user/:userId', requireUser, async (req, res) => {
  return LogContext.run(
    { operation: 'get-user-organizations', endpoint: '/organizations/user/:userId' },
    async () => {
      const workos = getWorkOSClient();

      try {
        const { userId } = req.params;

        // Ensure user can only access their own organizations
        if (!userId || userId !== req.user?.id) {
          return res.status(403).json({
            error: 'Forbidden: You can only access your own organization data',
          });
        }

        if (!workos) {
          return res.status(500).json({
            error: 'WorkOS not configured.',
          });
        }

        // Get user's organization memberships
        const workosClient = workos;
        const memberships = await workosClient.userManagement.listOrganizationMemberships({
          userId,
        });

        // Get organization details for each membership
        const organizationsWithMemberships = await Promise.all(
          memberships.data.map(async (membership) => {
            try {
              const organization = await workosClient.organizations.getOrganization(
                membership.organizationId
              );
              return {
                organization: {
                  id: organization.id,
                  name: organization.name,
                  domains: organization.domains || [],
                },
                membership: {
                  id: membership.id,
                  role: membership.role,
                  status: membership.status,
                  createdAt: membership.createdAt,
                },
              };
            } catch (error) {
              logger.error('Error fetching organization', error, {
                organizationId: membership.organizationId,
              });
              return null;
            }
          })
        );

        // Filter out any failed organization fetches
        const validOrganizations = organizationsWithMemberships.filter((item) => item !== null);

        res.json({
          success: true,
          organizations: validOrganizations,
          count: validOrganizations.length,
        });
      } catch (error) {
        logger.error('Error getting user organizations', error);
        res.status(500).json({
          error: 'Failed to get user organizations.',
          details: process.env.NODE_ENV === 'development' ? error.message : undefined,
        });
      }
    }
  );
});

// Check if account is frozen
organizationsRouter.get('/freeze-status', requireAdmin, async (req, res) => {
  return LogContext.run(
    { operation: 'get-freeze-status', endpoint: '/organizations/freeze-status' },
    async () => {
      try {
        const userId = req.user?.id;
        if (!userId) {
          return res.status(401).json({ error: 'User not authenticated' });
        }

        // Get tenant ID from authenticated user
        const tenantId = req.user?.tenantId;
        if (!tenantId) {
          return res.status(400).json({
            error: 'No tenant found for organization',
          });
        }

        // Check if account is frozen in control DB
        const controlDbPool = getControlDbPool();
        if (!controlDbPool) {
          return res.status(500).json({
            error: 'Control database not available',
          });
        }

        const result = await controlDbPool.query('SELECT deleted_at FROM tenants WHERE id = $1', [
          tenantId,
        ]);

        const isFrozen = result.rows.length > 0 && result.rows[0].deleted_at !== null;

        res.json({ isFrozen, deletedAt: result.rows[0]?.deleted_at || null });
      } catch (error) {
        logger.error('Error checking freeze status', error, {
          userId: req.user?.id,
          userEmail: req.user?.email,
        });
        res.status(500).json({
          error: 'Failed to check freeze status. Please try again.',
          details: process.env.NODE_ENV === 'development' ? error.message : undefined,
        });
      }
    }
  );
});

// Unfreeze account endpoint
organizationsRouter.post('/unfreeze-account', requireAdmin, async (req, res) => {
  return LogContext.run(
    { operation: 'unfreeze-account', endpoint: '/organizations/unfreeze-account' },
    async () => {
      try {
        const userId = req.user?.id;
        if (!userId) {
          return res.status(401).json({ error: 'User not authenticated' });
        }

        // Get tenant ID from authenticated user
        const tenantId = req.user?.tenantId;
        if (!tenantId) {
          return res.status(400).json({
            error: 'No tenant found for organization',
          });
        }

        logger.info('Account unfreeze requested', {
          userId,
          userEmail: req.user?.email,
          tenantId,
        });

        // Unfreeze account in control DB (set deleted_at to NULL)
        const controlDbPool = getControlDbPool();
        if (!controlDbPool) {
          return res.status(500).json({
            error: 'Control database not available',
          });
        }
        await controlDbPool.query('UPDATE tenants SET deleted_at = NULL WHERE id = $1', [tenantId]);

        // Invalidate the cached deletion status
        await invalidate(`tenant:deleted:${tenantId}`);

        logger.info('Tenant unfrozen in control DB', {
          userId,
          tenantId,
        });

        res.json({ success: true });
      } catch (error) {
        logger.error('Error processing account unfreeze', error, {
          userId: req.user?.id,
          userEmail: req.user?.email,
        });
        res.status(500).json({
          error: 'Failed to unfreeze account. Please try again.',
          details: process.env.NODE_ENV === 'development' ? error.message : undefined,
        });
      }
    }
  );
});

// Delete data endpoint
organizationsRouter.delete('/delete-data', requireAdmin, async (req, res) => {
  return LogContext.run(
    { operation: 'delete-data', endpoint: '/organizations/delete-data' },
    async () => {
      try {
        const userId = req.user?.id;
        if (!userId) {
          return res.status(401).json({ error: 'User not authenticated' });
        }

        // Get tenant ID from authenticated user
        const tenantId = req.user?.tenantId;
        if (!tenantId) {
          return res.status(400).json({
            error: 'No tenant found for organization',
          });
        }

        logger.info('Data deletion requested', {
          userId,
          userEmail: req.user?.email,
          tenantId,
        });

        // Mark tenant as deleted in control DB
        const controlDbPool = getControlDbPool();
        if (!controlDbPool) {
          return res.status(500).json({
            error: 'Control database not available',
          });
        }
        await controlDbPool.query('UPDATE tenants SET deleted_at = NOW() WHERE id = $1', [
          tenantId,
        ]);

        // Invalidate the cached deletion status
        await invalidate(`tenant:deleted:${tenantId}`);

        logger.info('Tenant marked as deleted in control DB', {
          userId,
          tenantId,
        });

        // Send tenant data deletion job to SQS
        const sqsClient = getSqsClient();
        await sqsClient.sendTenantDataDeletionJob(tenantId);

        logger.info('Tenant data deletion job queued successfully', {
          userId,
          tenantId,
        });

        res.json({ success: true });
      } catch (error) {
        logger.error('Error processing data deletion', error, {
          userId: req.user?.id,
          userEmail: req.user?.email,
        });
        res.status(500).json({
          error: 'Failed to process data deletion request. Please try again.',
          details: process.env.NODE_ENV === 'development' ? error.message : undefined,
        });
      }
    }
  );
});

// Get organization members and pending invitations
organizationsRouter.get('/members', requireAdmin, async (req, res) => {
  return LogContext.run(
    { operation: 'get-organization-members', endpoint: '/organizations/members' },
    async () => {
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

        // Fetch active members
        const membershipsResponse = await workos.userManagement.listOrganizationMemberships({
          organizationId: user.organizationId,
        });

        // Fetch user details for each member
        const membersWithDetails = await Promise.all(
          membershipsResponse.data.map(async (membership) => {
            try {
              const userDetails = await workos.userManagement.getUser(membership.userId);
              return {
                type: 'member' as const,
                id: membership.id,
                userId: membership.userId,
                email: userDetails.email,
                firstName: userDetails.firstName || undefined,
                lastName: userDetails.lastName || undefined,
                role: membership.role?.slug || 'member',
                status: membership.status,
                joinedAt: membership.createdAt,
              };
            } catch (error) {
              logger.error('Error fetching user details for member', error, {
                userId: membership.userId,
                membershipId: membership.id,
              });
              // Return member without full details if user fetch fails
              return {
                type: 'member' as const,
                id: membership.id,
                userId: membership.userId,
                email: 'Unknown',
                role: membership.role?.slug || 'member',
                status: membership.status,
                joinedAt: membership.createdAt,
              };
            }
          })
        );

        // Fetch pending invitations
        const invitationsResponse = await workos.userManagement.listInvitations({
          organizationId: user.organizationId,
        });

        const invitations = invitationsResponse.data
          .filter((invitation) => invitation.state === 'pending')
          .map((invitation) => ({
            type: 'invitation' as const,
            id: invitation.id,
            email: invitation.email,
            role: undefined, // Role not available until invitation is accepted
            status: invitation.state,
            createdAt: invitation.createdAt,
            expiresAt: invitation.expiresAt,
          }));

        // Combine members and invitations
        const allMembers = [...membersWithDetails, ...invitations];

        res.json({
          success: true,
          members: allMembers,
          count: allMembers.length,
        });
      } catch (error) {
        logger.error('Error fetching organization members', error);
        res.status(500).json({
          error: 'Failed to fetch organization members. Please try again.',
          details: process.env.NODE_ENV === 'development' ? error.message : undefined,
        });
      }
    }
  );
});

export { organizationsRouter };
