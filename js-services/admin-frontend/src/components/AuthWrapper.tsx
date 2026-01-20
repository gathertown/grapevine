import { ReactNode } from 'react';
import { useAuth } from '../hooks/useAuth';
import { OrganizationSetup } from './OrganizationSetup';
import { MemberAccessDenied } from './MemberAccessDenied';
import { Initializing } from './Initializing';

interface AuthWrapperProps {
  children: ReactNode;
}

const AuthWrapper = ({ children }: AuthWrapperProps) => {
  const { isAuthenticated, isLoading, user, hasOrganization } = useAuth();

  if (isLoading) {
    return <Initializing />;
  }

  if (!isAuthenticated) {
    return <Initializing />;
  }

  // Check if user has an organization
  // If user is authenticated but has no organization, show organization setup
  if (user && !hasOrganization) {
    return <OrganizationSetup />;
  }

  // Check if user is an admin - block non-admins from accessing the UI
  if (user && user.role !== 'admin') {
    return <MemberAccessDenied />;
  }

  return <>{children}</>;
};

export { AuthWrapper };
