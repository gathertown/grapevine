import { useState, useEffect, useRef, ReactNode } from 'react';
import { useAuth as useWorkOSAuth } from '@workos-inc/authkit-react';
import { useNavigate } from 'react-router-dom';
import { AuthContext } from './AuthContextDefinition';
import { AuthContextType, User, Organization } from '../types';
import { apiClient } from '../api/client';
import { getTenantStatus } from '../api/organizations';
import { identify, clearUser, newrelic } from '@corporate-context/frontend-common';

const INTENDED_URL_KEY = 'grapevine_intended_url';

interface AuthProviderProps {
  children: ReactNode;
}

interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  organization: string | null;
  organizationId: string | null;
  hasOrganization: boolean;
  organizationData: Organization | null;
  accessToken: string | null;
  isLoading: boolean;
  tenantStatus: 'provisioned' | 'pending' | 'error' | null;
  tenantError: string | null;
  isProvisioningComplete: boolean;
}

interface OrganizationData {
  success: boolean;
  organizations: Array<{
    organization: {
      id: string;
      name: string;
      domains?: Array<{
        domain: string;
        state: 'verified' | 'pending' | 'unverified';
      }>;
      isVerified?: boolean;
    };
    membership?: {
      role: {
        slug: string;
      };
      createdAt: string;
    };
  }>;
}

// Helper functions for URL preservation and session tracking
const saveIntendedUrl = (url: string): void => {
  try {
    localStorage.setItem(INTENDED_URL_KEY, url);
  } catch (error) {
    console.warn('Failed to save intended URL:', error);
  }
};

const getIntendedUrl = (): string | null => {
  try {
    return localStorage.getItem(INTENDED_URL_KEY);
  } catch (error) {
    console.warn('Failed to get intended URL:', error);
    return null;
  }
};

const clearIntendedUrl = (): void => {
  try {
    localStorage.removeItem(INTENDED_URL_KEY);
  } catch (error) {
    console.warn('Failed to clear intended URL:', error);
  }
};

/**
 * Identify user in analytics services (PostHog, Amplitude) and monitoring (New Relic)
 * Centralizes user identification to ensure consistent tracking across all services
 */
const identifyUserInAnalytics = (
  user: User,
  options: {
    organizationName?: string;
    hasOrganization: boolean;
  }
): void => {
  if (!user.id) {
    return;
  }

  // Identify in PostHog/Amplitude (via shared identify function)
  identify(user.id, {
    email: user.email,
    first_name: user.firstName,
    last_name: user.lastName,
    organization_id: user.organizationId,
    organization_name: options.organizationName,
    tenant_id: user.tenantId,
    has_organization: options.hasOrganization,
  });

  // Identify in New Relic (no PII)
  newrelic.setUser(user.id, {
    ...(user.organizationId && { organizationId: user.organizationId }),
    ...(options.organizationName && { organizationName: options.organizationName }),
    ...(user.tenantId && { tenantId: user.tenantId }),
    hasOrganization: options.hasOrganization,
  });
};

export const AuthProvider = ({ children }: AuthProviderProps) => {
  const workOSAuth = useWorkOSAuth();
  const navigate = useNavigate();
  const previousOrgIdRef = useRef<string | null>(null);
  const hasNavigatedRef = useRef<boolean>(false);
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    user: null,
    organization: null,
    organizationId: null,
    hasOrganization: false,
    organizationData: null,
    accessToken: null,
    isLoading: true,
    tenantStatus: null,
    tenantError: null,
    isProvisioningComplete: false,
  });

  useEffect(() => {
    const updateAuthState = async () => {
      if (workOSAuth.isLoading) {
        return;
      }

      if (workOSAuth.user) {
        let token = null;
        try {
          token = await workOSAuth.getAccessToken();

          // Configure API client with token provider
          apiClient.setTokenProvider(async () => {
            try {
              return await workOSAuth.getAccessToken();
            } catch (error) {
              console.error('Token provider error:', error);
              return null;
            }
          });

          // Wait a moment for token provider to be ready
          await new Promise((resolve) => setTimeout(resolve, 100));
        } catch (error) {
          console.error('Failed to get access token:', error);
        }

        // Check for organization membership via authenticated API
        let orgId: string | null = null;
        let hasOrg = false;
        let orgData = null;
        let userRole: string | undefined = undefined;

        if (token && workOSAuth.user?.id) {
          try {
            // Debug: Log token availability for troubleshooting
            // Token available for organization fetch

            // Ensure the API client token is immediately available for this request
            const orgResponse = await apiClient.get<OrganizationData>(
              `/api/organizations/user/${workOSAuth.user.id}`
            );
            if (
              orgResponse.success &&
              orgResponse.organizations &&
              orgResponse.organizations.length > 0
            ) {
              // Check if WorkOS has a current organization set
              const currentWorkOSOrgId = workOSAuth.organizationId;

              // Find the organization matching the current WorkOS org ID
              const matchingOrg = currentWorkOSOrgId
                ? orgResponse.organizations.find(
                    (org) => org.organization.id === currentWorkOSOrgId
                  )
                : null;

              // Use the matching org if found, otherwise use the first one
              const targetOrg = matchingOrg || orgResponse.organizations[0];

              if (targetOrg?.organization?.id) {
                const targetOrgId = targetOrg.organization.id;

                // Switch to the target org if it's different from the current WorkOS org
                // and different from what we previously tried to switch to
                if (
                  targetOrgId !== currentWorkOSOrgId &&
                  targetOrgId !== previousOrgIdRef.current
                ) {
                  try {
                    console.log(`Switching to organization: ${targetOrgId}`);
                    previousOrgIdRef.current = targetOrgId;
                    // Reset navigation state on organization switch
                    hasNavigatedRef.current = false;
                    await workOSAuth.switchToOrganization({ organizationId: targetOrgId });
                    console.log('AuthContext - switched to organization:', targetOrgId);
                    // The switch will trigger a re-render, so return early
                    return;
                  } catch (error) {
                    console.error('Failed to switch organization:', error);
                    // Reset the ref on error so we can retry
                    previousOrgIdRef.current = currentWorkOSOrgId;
                  }
                }

                orgId = targetOrgId;
                hasOrg = true;
                // Map to our Organization type format
                const primaryDomain = targetOrg.organization.domains?.[0]?.domain || '';
                orgData = {
                  id: targetOrg.organization.id,
                  name: targetOrg.organization.name,
                  domain: primaryDomain,
                  createdAt: '',
                  updatedAt: '',
                };

                // Extract role from organization membership
                if (targetOrg.membership?.role) {
                  userRole = targetOrg.membership.role.slug;

                  console.log('[AuthContext] Extracted user role from membership:', {
                    role: userRole,
                    organizationId: orgId,
                  });
                }

                // Found user organizations successfully
              }
            } else {
              // No organizations found for user
            }
          } catch (error) {
            console.error('Failed to fetch user organizations:', error);

            // For now, if we can't fetch organizations, we'll still allow the user to proceed
            // This prevents blocking the auth flow entirely
            console.warn('Proceeding without organization data due to API error');
          }
        }

        const authState: AuthState = {
          isAuthenticated: true,
          user: {
            ...(workOSAuth.user as User),
            ...(orgId ? { organizationId: orgId } : {}),
            ...(userRole ? { role: userRole } : {}),
          },
          organization: orgId,
          organizationId: orgId,
          hasOrganization: hasOrg,
          organizationData: orgData,
          accessToken: token,
          isLoading: false,
          tenantStatus: null, // Will be updated by polling
          tenantError: null, // Will be updated by polling
          isProvisioningComplete: false, // Will be updated by polling
        };

        console.log('AuthContext: Setting auth state', {
          userId: authState.user?.id,
          email: authState.user?.email,
          role: authState.user?.role,
          roleType: typeof authState.user?.role,
          organizationId: authState.user?.organizationId,
          tenantId: authState.user?.tenantId,
          hasOrganization: authState.hasOrganization,
          tenantStatus: authState.tenantStatus,
        });
        setAuthState(authState);

        // Identify user in monitoring services
        if (authState.user) {
          identifyUserInAnalytics(authState.user, {
            organizationName: orgData?.name,
            hasOrganization: authState.hasOrganization,
          });
        }
      } else {
        setAuthState({
          isAuthenticated: false,
          user: null,
          organization: null,
          organizationId: null,
          hasOrganization: false,
          organizationData: null,
          accessToken: null,
          isLoading: false,
          tenantStatus: null,
          tenantError: null,
          isProvisioningComplete: false,
        });
      }
    };

    updateAuthState();
  }, [workOSAuth.user, workOSAuth.isLoading, workOSAuth.organizationId, workOSAuth]);

  // Handle navigation after authentication completes
  useEffect(() => {
    if (authState.isAuthenticated && authState.hasOrganization && !hasNavigatedRef.current) {
      const intendedUrl = getIntendedUrl();
      console.log('AuthContext: Navigation check', {
        isAuthenticated: authState.isAuthenticated,
        hasOrganization: authState.hasOrganization,
        hasNavigated: hasNavigatedRef.current,
        intendedUrl,
        currentPath: window.location.pathname,
      });
      if (intendedUrl && intendedUrl !== '/' && intendedUrl !== window.location.pathname) {
        console.log('AuthContext: Navigating to intended URL:', intendedUrl);
        hasNavigatedRef.current = true;
        navigate(intendedUrl);
        clearIntendedUrl();
      }
    }
  }, [authState.isAuthenticated, authState.hasOrganization, navigate]);

  // Tenant status polling - poll when user has organization but no provisioned tenant
  useEffect(() => {
    let pollInterval: number | null = null;
    let pollCount = 0;
    const maxPolls = 60; // 2 minutes at 2-second intervals

    const pollTenantStatus = async () => {
      if (
        !authState.isAuthenticated ||
        !authState.hasOrganization ||
        authState.isProvisioningComplete
      ) {
        return;
      }

      try {
        console.log('Polling tenant status...');
        const statusResponse = await getTenantStatus();

        console.log('AuthContext: Tenant status response', {
          status: statusResponse.status,
          tenantId: statusResponse.tenantId,
          errorMessage: statusResponse.errorMessage,
        });

        setAuthState((prev) => ({
          ...prev,
          user: prev.user
            ? {
                ...prev.user,
                ...(statusResponse.tenantId ? { tenantId: statusResponse.tenantId } : {}),
              }
            : prev.user,
          tenantStatus: statusResponse.status,
          tenantError: statusResponse.errorMessage || null,
          isProvisioningComplete: statusResponse.status === 'provisioned',
        }));

        if (statusResponse.status === 'provisioned') {
          console.log('AuthContext: Tenant provisioning complete!', {
            tenantId: statusResponse.tenantId,
          });

          // Track tenant provisioning completion
          if (statusResponse.tenantId) {
            newrelic.addPageAction('tenantProvisioningCompleted', {
              tenantId: statusResponse.tenantId,
            });
          }

          // Re-identify user in analytics with now-available tenantId
          if (authState.user && statusResponse.tenantId) {
            identifyUserInAnalytics(
              { ...authState.user, tenantId: statusResponse.tenantId },
              {
                organizationName: authState.organizationData?.name,
                hasOrganization: authState.hasOrganization,
              }
            );
          }

          if (pollInterval) {
            window.clearInterval(pollInterval);
            pollInterval = null;
          }
        } else if (statusResponse.status === 'error') {
          console.error('Tenant provisioning failed:', statusResponse.errorMessage);
          if (pollInterval) {
            window.clearInterval(pollInterval);
            pollInterval = null;
          }
        }
      } catch (error) {
        console.error('Error polling tenant status:', error);
      }

      pollCount++;
      if (pollCount >= maxPolls) {
        console.warn('Tenant polling timeout reached');
        if (pollInterval) {
          window.clearInterval(pollInterval);
          pollInterval = null;
        }
      }
    };

    // Start polling if user has organization but tenant isn't provisioned yet
    if (
      authState.isAuthenticated &&
      authState.hasOrganization &&
      !authState.isProvisioningComplete
    ) {
      console.log('Starting tenant status polling...');
      pollTenantStatus(); // Check immediately
      pollInterval = window.setInterval(pollTenantStatus, 2000); // Then every 2 seconds
    }

    return () => {
      if (pollInterval) {
        window.clearInterval(pollInterval);
      }
    };
    // Intentionally excluding authState.user to prevent infinite re-renders when
    // `user` object ref changes during provisioning. This is safe b/c we only need it for analytics.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    authState.isAuthenticated,
    authState.hasOrganization,
    authState.isProvisioningComplete,
    authState.organizationData?.name,
  ]);

  useEffect(() => {
    if (!workOSAuth.isLoading && !workOSAuth.user) {
      // Save the current URL before redirecting to auth
      saveIntendedUrl(window.location.pathname + window.location.search);
      workOSAuth.signIn({ state: { returnTo: window.location.origin } });
    }
  }, [workOSAuth.isLoading, workOSAuth.user, workOSAuth]);

  const signIn = async (): Promise<void> => {
    try {
      // Track sign-in initiation
      newrelic.addPageAction('userSignInInitiated', {
        hasOrganization: authState.hasOrganization,
      });

      // Save the current URL before redirecting to auth
      saveIntendedUrl(window.location.pathname + window.location.search);
      await workOSAuth.signIn({ state: { returnTo: window.location.origin } });
    } catch (error) {
      console.error('Sign in failed:', error);
      throw error;
    }
  };

  const signUp = async (): Promise<void> => {
    try {
      // Track sign-up initiation
      newrelic.addPageAction('userSignUpInitiated');

      // Save the current URL before redirecting to auth
      saveIntendedUrl(window.location.pathname + window.location.search);
      await workOSAuth.signUp({ state: { returnTo: window.location.origin } });
    } catch (error) {
      console.error('Sign up failed:', error);
      throw error;
    }
  };

  const signOut = async (): Promise<void> => {
    try {
      // Track sign-out completion
      newrelic.addPageAction('userSignOutCompleted');

      // Clear intended URL when signing out
      clearIntendedUrl();
      hasNavigatedRef.current = false;

      // Clear user from monitoring services
      clearUser();
      newrelic.clearUser();

      await workOSAuth.signOut({ returnTo: window.location.origin });
      setAuthState({
        isAuthenticated: false,
        user: null,
        organization: null,
        organizationId: null,
        hasOrganization: false,
        organizationData: null,
        accessToken: null,
        isLoading: false,
        tenantStatus: null,
        tenantError: null,
        isProvisioningComplete: false,
      });
    } catch (error) {
      console.error('Sign out failed:', error);
      throw error;
    }
  };

  const getAccessToken = async (): Promise<string | null> => {
    try {
      const token = await workOSAuth.getAccessToken();
      return token;
    } catch (error) {
      console.error('Failed to get access token:', error);
      return null;
    }
  };

  const switchToOrganization = async (organizationId: string): Promise<void> => {
    try {
      // Track organization switch
      if (authState.organizationId) {
        newrelic.addPageAction('organizationSwitchInitiated', {
          fromOrgId: authState.organizationId,
          toOrgId: organizationId,
        });
      }

      await workOSAuth.switchToOrganization({
        organizationId,
        signInOpts: { state: { returnTo: window.location.origin } },
      });
    } catch (error) {
      console.error('Failed to switch organization:', error);
      throw error;
    }
  };

  const value: AuthContextType = {
    ...authState,
    signIn,
    signUp,
    signOut,
    getAccessToken,
    switchToOrganization,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
