import { useState, FC, useEffect } from 'react';
import { Flex, Text, Input, Button, ToggleSwitch, Modal } from '@gathertown/gather-design-system';
import { CompanyContextForm } from './shared';
import { ApiError, apiClient } from '../api/client';
import { useTrackEvent } from '../hooks/useTrackEvent';
import { useAuth } from '../hooks/useAuth';
import { useAllConfig, useSetConfigValue } from '../api/config';

const OrganizationSettings: FC = () => {
  const { data: configData } = useAllConfig();
  const { mutateAsync: updateConfigValue } = useSetConfigValue();
  const { trackEvent } = useTrackEvent();
  const { user } = useAuth();

  // State for organization name section
  const [orgName, setOrgName] = useState<string>('');
  const [originalOrgName, setOriginalOrgName] = useState<string>('');
  const [orgNameLoading, setOrgNameLoading] = useState<boolean>(false);
  const [orgNameError, setOrgNameError] = useState<string | null>(null);
  const [orgNameSuccess, setOrgNameSuccess] = useState<string | null>(null);

  // State for data sharing section
  const [dataUsageInsightsEnabled, setDataUsageInsightsEnabled] = useState<boolean>(false);
  const [dataUsageLoading, setDataUsageLoading] = useState<boolean>(false);
  const [dataUsageError, setDataUsageError] = useState<string | null>(null);
  const [dataUsageSuccess, setDataUsageSuccess] = useState<string | null>(null);

  // State for delete data section
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState<boolean>(false);
  const [deleteLoading, setDeleteLoading] = useState<boolean>(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // State for freeze status
  const [isFrozen, setIsFrozen] = useState<boolean>(false);
  const [freezeStatusLoading, setFreezeStatusLoading] = useState<boolean>(true);
  const [unfreezeLoading, setUnfreezeLoading] = useState<boolean>(false);
  const [unfreezeError, setUnfreezeError] = useState<string | null>(null);
  const [unfreezeSuccess, setUnfreezeSuccess] = useState<string | null>(null);

  // Check freeze status on mount
  useEffect(() => {
    const checkFreezeStatus = async (): Promise<void> => {
      try {
        const response = await apiClient.get<{ isFrozen: boolean; deletedAt: string | null }>(
          '/api/organizations/freeze-status'
        );
        setIsFrozen(response.isFrozen);
      } catch (err) {
        console.error('Failed to check freeze status:', err);
      } finally {
        setFreezeStatusLoading(false);
      }
    };

    checkFreezeStatus();
  }, []);

  // Initialize form values from config
  useEffect(() => {
    setOrgName(configData?.COMPANY_NAME || '');
    setOriginalOrgName(configData?.COMPANY_NAME || '');
    setDataUsageInsightsEnabled(configData?.ALLOW_DATA_SHARING_FOR_IMPROVEMENTS === 'true');
  }, [configData]);

  // Clear success messages after delay
  useEffect(() => {
    if (orgNameSuccess) {
      const timer = setTimeout(() => setOrgNameSuccess(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [orgNameSuccess]);

  useEffect(() => {
    if (dataUsageSuccess) {
      const timer = setTimeout(() => setDataUsageSuccess(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [dataUsageSuccess]);

  useEffect(() => {
    if (unfreezeSuccess) {
      const timer = setTimeout(() => setUnfreezeSuccess(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [unfreezeSuccess]);

  const handleUpdateOrgName = async (): Promise<void> => {
    if (!orgName.trim()) return;

    setOrgNameLoading(true);
    setOrgNameError(null);
    setOrgNameSuccess(null);

    try {
      await updateConfigValue({
        key: 'COMPANY_NAME',
        value: orgName.trim(),
      });

      setOriginalOrgName(orgName.trim());
      setOrgNameSuccess('saved');

      // Track organization name update
      trackEvent('organization_name_updated', {
        user_id: user?.id,
        name_length: orgName.trim().length,
      });
    } catch (err) {
      console.error('Failed to update organization name:', err);

      if (err instanceof ApiError) {
        setOrgNameError(err.message || 'Failed to update organization name. Please try again.');
      } else {
        setOrgNameError('Failed to update organization name. Please try again.');
      }
    } finally {
      setOrgNameLoading(false);
    }
  };

  const handleUpdateDataUsage = async (enabled?: boolean): Promise<void> => {
    setDataUsageLoading(true);
    setDataUsageError(null);
    setDataUsageSuccess(null);

    const newEnabled = enabled !== undefined ? enabled : dataUsageInsightsEnabled;

    try {
      const dataUsageValue = newEnabled ? 'true' : '';
      await updateConfigValue({
        key: 'ALLOW_DATA_SHARING_FOR_IMPROVEMENTS',
        value: dataUsageValue,
      });

      setDataUsageSuccess('Data sharing preferences updated successfully!');

      // Track data sharing toggle
      trackEvent('data_sharing_toggled', {
        user_id: user?.id,
        enabled: newEnabled,
      });
    } catch (err) {
      console.error('Failed to update data sharing preferences:', err);

      if (err instanceof ApiError) {
        setDataUsageError(
          err.message || 'Failed to update data sharing preferences. Please try again.'
        );
      } else {
        setDataUsageError('Failed to update data sharing preferences. Please try again.');
      }
    } finally {
      setDataUsageLoading(false);
    }
  };

  const handleDeleteData = async (): Promise<void> => {
    setDeleteLoading(true);
    setDeleteError(null);

    try {
      await apiClient.delete('/api/organizations/delete-data');

      // Close modal and show success state
      setIsDeleteModalOpen(false);
      setIsFrozen(true);

      // Show success message
      alert(
        'Account frozen successfully - your existing data is being deleted. No new data will be ingested until you unfreeze your account. You can unfreeze later to resume data ingestion, but you will need to redo setup for all integrations in order to recover data. This may take a few minutes to complete.'
      );
    } catch (err) {
      console.error('Failed to delete data:', err);

      if (err instanceof ApiError) {
        setDeleteError(err.message || 'Failed to delete data. Please try again.');
      } else {
        setDeleteError('Failed to delete data. Please try again.');
      }
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleUnfreezeAccount = async (): Promise<void> => {
    setUnfreezeLoading(true);
    setUnfreezeError(null);
    setUnfreezeSuccess(null);

    try {
      await apiClient.post('/api/organizations/unfreeze-account');

      setIsFrozen(false);
      setUnfreezeSuccess(
        'Account unfrozen successfully! Data ingestion from integrations has resumed.'
      );
    } catch (err) {
      console.error('Failed to unfreeze account:', err);

      if (err instanceof ApiError) {
        setUnfreezeError(err.message || 'Failed to unfreeze account. Please try again.');
      } else {
        setUnfreezeError('Failed to unfreeze account. Please try again.');
      }
    } finally {
      setUnfreezeLoading(false);
    }
  };

  return (
    <Flex direction="column" width="100%" style={{ gap: 44 }}>
      {/* Company Context Section */}
      <Flex direction="column" gap={8}>
        <Text fontSize="lg" color="primary" fontWeight="semibold">
          Company Context
        </Text>
        <Flex direction="column" width="100%" maxWidth="600px">
          <CompanyContextForm inSettingsPage={true} />
        </Flex>
      </Flex>

      {/* Change Organization Name Section */}
      <Flex direction="column" gap={8}>
        <Text fontSize="lg" color="primary" fontWeight="semibold">
          Change organization name
        </Text>
        <Flex direction="column" width="100%" maxWidth="600px" gap={16}>
          {/* Error Message */}
          {orgNameError && (
            <Flex
              backgroundColor="dangerSecondary"
              p={4}
              align="center"
              gap={2}
              borderRadius={8}
              borderColor="dangerPrimary"
              borderWidth={1}
            >
              <Text fontSize="sm">⚠️ {orgNameError}</Text>
            </Flex>
          )}

          <Flex direction="row" gap={12} align="center" justify="space-between">
            <Input
              placeholder="e.g., Acme Corporation"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              disabled={orgNameLoading}
              size="lg"
              error={orgNameError || undefined}
              fullWidth
            />
            <Button
              onClick={handleUpdateOrgName}
              disabled={orgNameLoading || !orgName.trim() || orgName === originalOrgName}
            >
              {orgNameLoading ? 'Saving...' : orgNameSuccess ? 'Saved' : 'Save'}
            </Button>
          </Flex>
        </Flex>
      </Flex>

      {/* Data Sharing with Gather Section */}
      <Flex direction="column" gap={8}>
        <Text fontSize="lg" color="primary" fontWeight="semibold">
          Data sharing with Grapevine
        </Text>
        <Flex direction="column" width="100%" maxWidth="600px" gap={16} align="flex-start">
          {/* Success Message */}
          {dataUsageSuccess && (
            <Flex
              backgroundColor="successSecondary"
              p={4}
              align="center"
              gap={2}
              borderRadius={8}
              borderColor="successPrimary"
              borderWidth={1}
            >
              <Text fontSize="sm">✅ {dataUsageSuccess}</Text>
            </Flex>
          )}

          {/* Error Message */}
          {dataUsageError && (
            <Flex
              backgroundColor="dangerSecondary"
              p={4}
              align="center"
              gap={2}
              borderRadius={8}
              borderColor="dangerPrimary"
              borderWidth={1}
            >
              <Text fontSize="sm">⚠️ {dataUsageError}</Text>
            </Flex>
          )}

          <Flex direction="row" justify="space-between" align="flex-start">
            <Flex direction="column" gap={2} style={{ flex: 1 }}>
              <Text fontWeight="medium">Share bot questions and answers</Text>
              <Text color="tertiary">
                Allow Grapevine employees to analyze the content of your bot's questions and answers
                to improve response quality. We will not train LLM's on your data, and your data
                will be strictly used to improve the product.
              </Text>
            </Flex>
            <ToggleSwitch
              checked={dataUsageInsightsEnabled}
              onChange={async (e) => {
                setDataUsageInsightsEnabled(e.target.checked);
                await handleUpdateDataUsage(e.target.checked);
              }}
              disabled={dataUsageLoading}
            />
          </Flex>
        </Flex>
      </Flex>

      {/* Account Freeze/Unfreeze Section */}
      {!freezeStatusLoading && (
        <>
          {isFrozen ? (
            // Unfreeze Section
            <Flex direction="column" gap={8}>
              <Text fontSize="lg" color="primary" fontWeight="semibold">
                Account Frozen
              </Text>
              <Flex direction="column" width="100%" maxWidth="600px" gap={16}>
                {/* Success Message */}
                {unfreezeSuccess && (
                  <Flex
                    backgroundColor="successSecondary"
                    p={4}
                    align="center"
                    gap={2}
                    borderRadius={8}
                    borderColor="successPrimary"
                    borderWidth={1}
                  >
                    <Text fontSize="sm">✅ {unfreezeSuccess}</Text>
                  </Flex>
                )}

                {/* Error Message */}
                {unfreezeError && (
                  <Flex
                    backgroundColor="dangerSecondary"
                    p={4}
                    align="center"
                    gap={2}
                    borderRadius={8}
                    borderColor="dangerPrimary"
                    borderWidth={1}
                  >
                    <Text fontSize="sm">⚠️ {unfreezeError}</Text>
                  </Flex>
                )}

                <Flex
                  backgroundColor="warningSecondary"
                  p={4}
                  align="center"
                  gap={2}
                  borderRadius={8}
                  borderColor="warningPrimary"
                  borderWidth={1}
                >
                  <Text fontSize="sm">
                    ⚠️ Your account is currently frozen. No new data is being ingested from your
                    integrations.
                  </Text>
                </Flex>

                <Text color="tertiary">
                  Unfreeze your account to resume data ingestion from your connected integrations.
                  Note: After unfreezing, you will need to go back and redo setup for all
                  integrations in order to recover data.
                </Text>

                <Flex direction="row" justify="flex-start">
                  <Button onClick={handleUnfreezeAccount} disabled={unfreezeLoading}>
                    {unfreezeLoading ? 'Unfreezing...' : 'Unfreeze Account'}
                  </Button>
                </Flex>
              </Flex>
            </Flex>
          ) : (
            // Delete Data Section
            <Flex direction="column" gap={8}>
              <Text fontSize="lg" color="primary" fontWeight="semibold">
                Delete your data
              </Text>
              <Flex direction="column" width="100%" maxWidth="600px" gap={16}>
                <Text color="tertiary">
                  This will <strong>freeze your account and delete all your existing data</strong>{' '}
                  from Grapevine. While frozen, no new data will be ingested from your integrations.
                  You can unfreeze your account later to resume data ingestion, but you will need to
                  redo setup for all integrations in order to recover data.
                </Text>
                <Flex direction="row" justify="flex-start">
                  <Button
                    kind="danger"
                    onClick={() => setIsDeleteModalOpen(true)}
                    disabled={deleteLoading}
                  >
                    Delete Data
                  </Button>
                </Flex>
              </Flex>
            </Flex>
          )}
        </>
      )}

      {/* Delete Confirmation Modal */}
      <Modal open={isDeleteModalOpen} onOpenChange={setIsDeleteModalOpen}>
        <Modal.Content variant="default" showOverlay style={{ height: 'auto', maxHeight: 'none' }}>
          <Modal.Body>
            <Flex direction="column" gap={24}>
              <Text fontSize="lg" fontWeight="semibold">
                Delete all your data?
              </Text>
              <Text color="secondary">
                This will <strong>freeze your account and delete all your existing data</strong>{' '}
                from Grapevine. While frozen, no new data will be ingested from your integrations.
                You can unfreeze your account later from this settings page to resume data
                ingestion, but you will need to redo setup for all integrations in order to recover
                data.
              </Text>

              {/* Error Message */}
              {deleteError && (
                <Flex
                  backgroundColor="dangerSecondary"
                  p={4}
                  align="center"
                  gap={2}
                  borderRadius={8}
                  borderColor="dangerPrimary"
                  borderWidth={1}
                >
                  <Text fontSize="sm">⚠️ {deleteError}</Text>
                </Flex>
              )}

              <Flex direction="row" gap={12} justify="flex-end">
                <Button
                  kind="secondary"
                  onClick={() => setIsDeleteModalOpen(false)}
                  disabled={deleteLoading}
                >
                  Cancel
                </Button>
                <Button kind="danger" onClick={handleDeleteData} disabled={deleteLoading}>
                  {deleteLoading ? 'Deleting...' : 'Delete'}
                </Button>
              </Flex>
            </Flex>
          </Modal.Body>
        </Modal.Content>
      </Modal>
    </Flex>
  );
};

export { OrganizationSettings };
