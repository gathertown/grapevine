export interface WorkOSOrganization {
  id: string;
  name: string;
  domains?: WorkOSDomain[];
  createdAt?: string;
}

export interface WorkOSDomain {
  domain: string;
  state: 'verified' | 'unverified' | 'pending';
}

export interface WorkOSMembership {
  id: string;
  userId: string;
  organizationId: string;
  role: string;
  status?: string;
  createdAt?: string;
}

export interface WorkOSInvitation {
  id: string;
  email: string;
  organizationId: string;
  token?: string;
  expiresAt?: string;
}
