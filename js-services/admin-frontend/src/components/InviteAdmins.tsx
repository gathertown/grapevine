import React, { useState, useEffect, FC, ChangeEvent, FormEvent } from 'react';
import {
  Flex,
  Text,
  Input,
  Button,
  Box,
  Badge,
  Menu,
  SegmentedControl,
} from '@gathertown/gather-design-system';
import { DOCS_URL } from '../constants';
import {
  sendInvitation,
  revokeInvitation,
  getOrganizationMembers,
  OrganizationMember,
} from '../api/organizations';
import { ApiError } from '../api/client';
import { useTrackEvent } from '../hooks/useTrackEvent';
import {
  hashString,
  InvitationRole,
  DEFAULT_INVITATION_ROLE,
} from '@corporate-context/shared-common';
import { useAuth } from '../hooks/useAuth';

// Constants
const COLORS = {
  border: '#E5E7EB',
  background: {
    white: '#FFFFFF',
    gray: '#F9FAFB',
    error: '#FEF2F2',
    success: '#F0FDF4',
  },
  borderColors: {
    error: '#FECACA',
    success: '#BBF7D0',
  },
} as const;

const TABLE_STYLES = {
  border: `1px solid ${COLORS.border}`,
  borderRadius: '8px',
  padding: '12px 16px',
} as const;

const ERROR_MAPPINGS: Record<number, { type: string; message: string }> = {
  409: {
    type: 'already_exists',
    message: 'An invitation has already been sent to this email or user already exists',
  },
  403: {
    type: 'forbidden',
    message: 'Only organization admins can send invitations',
  },
  400: {
    type: 'invalid_email',
    message: 'Invalid email address',
  },
};

// Helper Components
const AlertBox: FC<{ type: 'error' | 'success'; message: string }> = ({ type, message }) => (
  <Box
    style={{
      padding: TABLE_STYLES.padding,
      backgroundColor: type === 'error' ? COLORS.background.error : COLORS.background.success,
      borderRadius: TABLE_STYLES.borderRadius,
      border: `1px solid ${type === 'error' ? COLORS.borderColors.error : COLORS.borderColors.success}`,
    }}
  >
    <Text fontSize="sm" color={type === 'error' ? 'dangerPrimary' : 'successPrimary'}>
      {message}
    </Text>
  </Box>
);

const EmptyState: FC<{ message: string }> = ({ message }) => (
  <Box p={16} style={{ textAlign: 'center' }}>
    <Text fontSize="sm" color="tertiary">
      {message}
    </Text>
  </Box>
);

interface TableCellProps {
  flex?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
}

const TableCell: FC<TableCellProps> = ({ flex = '1', style, children }) => (
  <Box
    style={{
      flex,
      minWidth: 0,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      ...style,
    }}
  >
    {children}
  </Box>
);

const TableHeader: FC = () => {
  const columns = [
    { label: 'EMAIL', flex: '2' },
    { label: 'NAME', flex: '1.5' },
    { label: 'ROLE', flex: '1' },
    { label: 'STATUS', flex: '1' },
    { label: 'DATE', flex: '1.5' },
  ];

  return (
    <Flex
      style={{
        padding: TABLE_STYLES.padding,
        backgroundColor: COLORS.background.gray,
        borderBottom: TABLE_STYLES.border,
      }}
    >
      {columns.map(({ label, flex }) => (
        <Box key={label} style={{ flex, minWidth: 0 }}>
          <Text fontSize="xs" fontWeight="semibold" color="secondary">
            {label}
          </Text>
        </Box>
      ))}
      <Box style={{ width: '48px', flexShrink: 0 }} />
    </Flex>
  );
};

interface MemberRowProps {
  member: OrganizationMember;
  index: number;
  totalCount: number;
  isRevoking: boolean;
  onRevoke: (id: string) => void;
}

const MemberRow: FC<MemberRowProps> = ({ member, index, totalCount, isRevoking, onRevoke }) => {
  const isExpiredInvitation =
    member.type === 'invitation' && member.expiresAt && isExpired(member.expiresAt);

  const displayName =
    member.firstName || member.lastName
      ? `${member.firstName || ''} ${member.lastName || ''}`.trim()
      : '—';

  const displayDate =
    member.type === 'member'
      ? member.joinedAt
        ? formatDate(member.joinedAt)
        : '—'
      : member.createdAt
        ? formatDate(member.createdAt)
        : '—';

  const getBadgeColor = () => {
    if (member.type === 'member' && member.status === 'active') return 'success';
    if (member.status === 'pending') return 'warning';
    return 'accent';
  };

  return (
    <Flex
      align="center"
      style={{
        padding: TABLE_STYLES.padding,
        backgroundColor: COLORS.background.white,
        borderBottom: index < totalCount - 1 ? TABLE_STYLES.border : 'none',
      }}
    >
      <TableCell flex="2">
        <Text fontSize="sm">{member.email}</Text>
      </TableCell>

      <TableCell flex="1.5">
        <Text fontSize="sm" color={displayName === '—' ? 'tertiary' : 'primary'}>
          {displayName}
        </Text>
      </TableCell>

      <TableCell flex="1" style={{ textTransform: 'capitalize' }}>
        <Text fontSize="sm" color={member.role ? 'primary' : 'tertiary'}>
          {member.role || '—'}
        </Text>
      </TableCell>

      <TableCell flex="1">
        <Badge color={getBadgeColor()} text={isExpiredInvitation ? 'Expired' : member.status} />
      </TableCell>

      <Flex style={{ flex: '1.5', minWidth: 0 }} direction="column" gap={4}>
        <Text fontSize="xs" color="secondary">
          {displayDate}
        </Text>
        {member.type === 'invitation' && member.expiresAt && !isExpiredInvitation && (
          <Text fontSize="xs" color="tertiary">
            Expires: {formatDate(member.expiresAt)}
          </Text>
        )}
      </Flex>

      <Box style={{ width: '48px', flexShrink: 0 }}>
        {member.type === 'invitation' && (
          <Menu>
            <Menu.Trigger asChild>
              <Button kind="transparent" size="sm" disabled={isRevoking}>
                •••
              </Button>
            </Menu.Trigger>
            <Menu.Content align="end" sideOffset={4} width={160}>
              <Menu.Item
                icon="close"
                onSelect={() => onRevoke(member.id)}
                disabled={!!isExpiredInvitation}
              >
                {isRevoking ? 'Revoking...' : 'Revoke'}
              </Menu.Item>
            </Menu.Content>
          </Menu>
        )}
      </Box>
    </Flex>
  );
};

// Helper Functions
const formatDate = (dateString: string): string => {
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const isExpired = (expiresAt: string): boolean => {
  return new Date(expiresAt) < new Date();
};

const getMemberPriority = (member: OrganizationMember): number => {
  if (member.type === 'member' && member.status === 'active') return 0;
  if (member.type === 'invitation' && member.status === 'pending') return 1;
  return 2;
};

const sortMembers = (members: OrganizationMember[]): OrganizationMember[] => {
  return [...members].sort((a, b) => {
    const priorityDiff = getMemberPriority(a) - getMemberPriority(b);
    if (priorityDiff !== 0) return priorityDiff;

    // Sort by date within same priority (newest first)
    const dateA = new Date(a.joinedAt || a.createdAt || 0).getTime();
    const dateB = new Date(b.joinedAt || b.createdAt || 0).getTime();
    return dateB - dateA;
  });
};

const getErrorInfo = (err: unknown): { type: string; message: string } => {
  if (err instanceof ApiError && err.status in ERROR_MAPPINGS) {
    const mapping = ERROR_MAPPINGS[err.status as keyof typeof ERROR_MAPPINGS];
    if (!mapping) {
      return {
        type: 'unknown_error',
        message: 'Failed to send invitation. Please try again or contact support.',
      };
    }
    return {
      type: mapping.type,
      message: err.message || mapping.message,
    };
  }
  return {
    type: 'unknown_error',
    message:
      err instanceof ApiError
        ? err.message || 'Failed to send invitation. Please try again.'
        : 'Failed to send invitation. Please try again or contact support.',
  };
};

const InviteAdmins: FC = () => {
  const [email, setEmail] = useState<string>('');
  const [selectedRole, setSelectedRole] = useState<InvitationRole>(DEFAULT_INVITATION_ROLE);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState<boolean>(true);
  const [revokingIds, setRevokingIds] = useState<Set<string>>(new Set());

  const { trackEvent } = useTrackEvent();
  const { user, organizationId } = useAuth();

  // Load members and invitations on component mount
  useEffect(() => {
    loadMembers();
  }, []);

  const loadMembers = async (): Promise<void> => {
    try {
      setLoadingMembers(true);
      const response = await getOrganizationMembers();
      setMembers(sortMembers(response.members));
    } catch (error) {
      console.error('Failed to load members:', error);
    } finally {
      setLoadingMembers(false);
    }
  };

  const handleEmailChange = (e: ChangeEvent<HTMLInputElement>): void => {
    setEmail(e.target.value);
    // Clear messages when user starts typing
    if (error || success) {
      setError(null);
      setSuccess(null);
    }
  };

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email.trim());
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();

    if (!email.trim()) {
      setError('Email is required');
      return;
    }

    if (!validateEmail(email)) {
      setError('Please enter a valid email address');
      return;
    }

    setIsLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await sendInvitation(email.trim(), selectedRole);
      setSuccess(`Invitation sent successfully to ${email} as ${selectedRole}`);

      // Track successful invitation
      trackEvent('admin_invitation_sent', {
        user_id: user?.id,
        invitation_email_hash: hashString(email.trim()),
        organization_id: organizationId || undefined,
      });

      setEmail(''); // Clear form
      setSelectedRole(DEFAULT_INVITATION_ROLE); // Reset role to default

      // Refresh the members list
      await loadMembers();
    } catch (err) {
      console.error('Failed to send invitation:', err);

      const errorInfo = getErrorInfo(err);
      setError(errorInfo.message);

      // Track invitation failure
      trackEvent('admin_invitation_failed', {
        user_id: user?.id,
        invitation_email_hash: hashString(email.trim()),
        organization_id: organizationId || undefined,
        error_type: errorInfo.type,
        error_message: errorInfo.message,
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleRevokeInvitation = async (invitationId: string): Promise<void> => {
    setRevokingIds((prev) => new Set(prev).add(invitationId));

    // Find the invitation to get the email for tracking
    const invitation = members.find((m) => m.id === invitationId && m.type === 'invitation');

    try {
      await revokeInvitation(invitationId);

      // Track successful revocation
      if (invitation) {
        trackEvent('admin_invitation_revoked', {
          user_id: user?.id,
          invitation_email_hash: hashString(invitation.email),
          organization_id: organizationId || undefined,
          invitation_id: invitationId,
        });
      }

      // Refresh the members list
      await loadMembers();
      setSuccess('Invitation revoked successfully');
    } catch (error) {
      console.error('Failed to revoke invitation:', error);
      setError('Failed to revoke invitation. Please try again.');
    } finally {
      setRevokingIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(invitationId);
        return newSet;
      });
    }
  };

  return (
    <Flex direction="column" gap={24} width="100%">
      {/* Invite Form */}
      <Flex direction="column" gap={16}>
        <form onSubmit={handleSubmit}>
          <Flex direction="column" gap={16}>
            {/* Role Selection */}
            <Flex direction="column" gap={12}>
              <Text fontSize="sm" fontWeight="medium" color="primary">
                Role
              </Text>
              <SegmentedControl
                defaultValue={selectedRole}
                onSegmentChange={(value) => setSelectedRole(value as InvitationRole)}
                segments={[
                  { label: 'Member', value: 'member' },
                  { label: 'Admin', value: 'admin' },
                ]}
              />
              <Text fontSize="xs" color="secondary">
                {selectedRole === 'member'
                  ? 'Can be invited but will not have access to the admin dashboard.'
                  : 'Can manage integrations, invite users, and configure workspace settings.'}
                {DOCS_URL && (
                  <>
                    {' '}
                    <a
                      href={`${DOCS_URL}/getting-started/security-privacy#member-roles`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: '#3B82F6', textDecoration: 'underline' }}
                    >
                      Learn more →
                    </a>
                  </>
                )}
              </Text>
            </Flex>

            {/* Email Input */}
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="medium" color="primary">
                Email Address
              </Text>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={handleEmailChange}
                placeholder="Enter email address"
                disabled={isLoading}
                required
              />
            </Flex>

            {error && <AlertBox type="error" message={error} />}
            {success && <AlertBox type="success" message={success} />}

            <Flex justify="flex-start">
              <Button type="submit" kind="primary" disabled={isLoading || !email.trim()}>
                {isLoading ? 'Sending Invitation...' : 'Send Invitation'}
              </Button>
            </Flex>
          </Flex>
        </form>
      </Flex>

      {/* Organization Members and Invitations */}
      <Flex direction="column" gap={16}>
        <Text fontSize="lg" fontWeight="semibold">
          Team Members
        </Text>

        {loadingMembers ? (
          <EmptyState message="Loading members..." />
        ) : members.length === 0 ? (
          <EmptyState message="No members found." />
        ) : (
          <Box
            style={{
              border: TABLE_STYLES.border,
              borderRadius: TABLE_STYLES.borderRadius,
              overflow: 'hidden',
            }}
          >
            <TableHeader />
            {members.map((member, index) => (
              <MemberRow
                key={member.id}
                member={member}
                index={index}
                totalCount={members.length}
                isRevoking={revokingIds.has(member.id)}
                onRevoke={handleRevokeInvitation}
              />
            ))}
          </Box>
        )}
      </Flex>
    </Flex>
  );
};

export { InviteAdmins };
