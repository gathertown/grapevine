import { useState, FC, useRef } from 'react';
import { Flex, Text } from '@gathertown/gather-design-system';
import { useAuth } from '../hooks/useAuth';
import { createOrganization } from '../api/organizations';
import { ApiError } from '../api/client';
import { OrganizationForm } from './OrganizationForm';
import { FullscreenLayout } from './shared/FullscreenLayout';
import grapevinelogo from '../assets/grapevine_purp.png';
import { useTrackEvent } from '../hooks/useTrackEvent';
import { useAnalytics } from '@corporate-context/frontend-common';
import { isValidSource, Source } from '@corporate-context/shared-common';

/**
 * Extract the 'source' parameter from the intendedUrl stored in localStorage
 */
const getSourceFromIntendedUrl = (): Source | undefined => {
  try {
    const intendedUrl = localStorage.getItem('grapevine_intended_url');
    if (!intendedUrl) return undefined;

    const url = new URL(intendedUrl, window.location.origin);
    const sourceParam = url.searchParams.get('source');

    if (isValidSource(sourceParam)) {
      return sourceParam;
    }
    return undefined;
  } catch (error) {
    console.warn('Failed to extract mode from intendedUrl:', error);
    return undefined;
  }
};

const OrganizationSetup: FC = () => {
  const { switchToOrganization } = useAuth();
  const { trackEvent } = useTrackEvent();
  const { setUserProperty } = useAnalytics();
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const isSubmittingRef = useRef<boolean>(false);

  const handleCreateOrganization = async (data: {
    orgName: string;
    dataUsageInsightsEnabled?: boolean;
  }): Promise<void> => {
    // Prevent concurrent submissions
    if (isSubmittingRef.current) {
      return;
    }

    isSubmittingRef.current = true;
    setIsLoading(true);
    setError(null);

    try {
      // Extract source parameter from intendedUrl
      const source = getSourceFromIntendedUrl();

      // Use the authenticated API to create organization
      const result = await createOrganization(data.orgName, source);

      console.warn('Organization created successfully:', result);

      // Associate tenant_id and organization_name with user identity
      setUserProperty('tenant_id', result.tenantId);
      setUserProperty('organization_name', result.organization.name);

      // Track organization creation success
      trackEvent('organization_created', {
        organization_id: result.organization.id,
        organization_name: result.organization.name,
        tenant_id: result.tenantId,
        ...(source && { source }),
      });

      try {
        await switchToOrganization(result.organization.id);
        // Don't reset isSubmittingRef here - component will unmount
      } catch (switchError) {
        console.error('Failed to switch to organization, but it was created:', switchError);
        // Even on switch error, don't reset ref to prevent duplicate creation
      }
    } catch (err) {
      console.error('Failed to create organization:', err);

      // Handle API errors with better messaging
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setError('An organization with this name or domain already exists.');
        } else if (err.status === 400) {
          setError('Invalid organization details. Please check your input.');
        } else if (err.status === 401) {
          setError('Authentication expired. Please sign in again.');
        } else {
          setError(err.message || 'Failed to create organization. Please try again.');
        }
      } else {
        setError('Failed to create organization. Please try again or contact support.');
      }

      // Only reset on error, not on success
      isSubmittingRef.current = false;
      setIsLoading(false);
    }
  };

  return (
    <FullscreenLayout showSignOut={true}>
      <Flex direction="column" align="center" maxWidth="400px" width="100%" px={6} gap={32}>
        {/* Header with Logo */}
        <Flex direction="column" align="center" gap={16} width="100%">
          <img
            src={grapevinelogo}
            alt="Grapevine Logo"
            style={{ height: '64px', width: 'auto', marginBottom: '16px' }}
          />
          <Flex direction="column" gap={10}>
            <Text fontSize="xxl" textAlign="center" fontWeight="semibold">
              Welcome to Grapevine
            </Text>
            <Text fontSize="md" textAlign="center">
              Tell us about your company to get started
            </Text>
          </Flex>
        </Flex>

        {/* Organization Creation Form */}
        <Flex
          direction="column"
          width="100%"
          gap={10}
          borderRadius={12}
          p={32}
          backgroundColor="primary"
          borderColor="tertiary"
          borderWidth={1}
        >
          <OrganizationForm
            onSubmit={handleCreateOrganization}
            submitButtonText="Create Organization"
            isLoading={isLoading || isSubmittingRef.current}
            error={error}
            showDataUsageSection={false}
          />
        </Flex>
      </Flex>
    </FullscreenLayout>
  );
};

export { OrganizationSetup };
