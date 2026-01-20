import { useState, FC, ChangeEvent, useEffect, FormEvent } from 'react';
import { Flex, Input, Button, Checkbox, Text } from '@gathertown/gather-design-system';

interface OrganizationFormProps {
  initialOrgName?: string;
  initialDataUsageInsightsEnabled?: boolean;
  onSubmit: (data: { orgName: string; dataUsageInsightsEnabled?: boolean }) => Promise<void>;
  submitButtonText?: string;
  isLoading?: boolean;
  error?: string | null;
  disabled?: boolean;
  showDataUsageSection?: boolean;
}

const OrganizationForm: FC<OrganizationFormProps> = ({
  initialOrgName = '',
  initialDataUsageInsightsEnabled = true,
  onSubmit,
  submitButtonText = 'Save Organization',
  isLoading = false,
  error = null,
  disabled = false,
  showDataUsageSection = true,
}) => {
  const [orgName, setOrgName] = useState<string>(initialOrgName);
  const [dataUsageInsightsEnabled, setDataUsageInsightsEnabled] = useState<boolean>(
    initialDataUsageInsightsEnabled
  );

  // Update form values when initial props change
  useEffect(() => {
    setOrgName(initialOrgName);
    setDataUsageInsightsEnabled(initialDataUsageInsightsEnabled);
  }, [initialOrgName, initialDataUsageInsightsEnabled]);

  const handleSubmit = async (e?: FormEvent): Promise<void> => {
    e?.preventDefault();
    if (!orgName.trim()) {
      return;
    }

    const submitData: { orgName: string; dataUsageInsightsEnabled?: boolean } = {
      orgName: orgName.trim(),
    };

    // Only include dataUsageInsightsEnabled if showDataUsageSection is true
    if (showDataUsageSection) {
      submitData.dataUsageInsightsEnabled = dataUsageInsightsEnabled;
    }

    await onSubmit(submitData);
  };

  const handleOrgNameChange = (e: ChangeEvent<HTMLInputElement>): void => {
    setOrgName(e.target.value);
  };

  const handleDataUsageInsightsEnabledChange = (e: ChangeEvent<HTMLInputElement>): void => {
    setDataUsageInsightsEnabled(e.target.checked);
  };

  return (
    <form onSubmit={handleSubmit} style={{ width: '100%' }}>
      <Flex direction="column" width="100%" gap={10}>
        {/* General Error Message */}
        {error && (
          <Flex
            backgroundColor="dangerSecondary"
            p={4}
            align="center"
            gap={2}
            borderRadius={8}
            borderColor="dangerPrimary"
            borderWidth={1}
          >
            <Text fontSize="sm">⚠️ {error}</Text>
          </Flex>
        )}

        {/* Organization Name Input */}
        <Input
          placeholder="e.g., Acme Corporation"
          value={orgName}
          label="Organization Name"
          onChange={handleOrgNameChange}
          disabled={isLoading || disabled}
          error={!orgName.trim() && error ? 'Organization name is required' : undefined}
        />

        {/* Data Sharing Section */}
        {showDataUsageSection && (
          <Flex direction="column" gap={2} mt={4}>
            <Flex width="100%" flexShrink={0}>
              <Checkbox
                checked={dataUsageInsightsEnabled}
                onChange={handleDataUsageInsightsEnabledChange}
                disabled={isLoading || disabled}
                label="Share samples to improve bot"
                hint="Allow Grapevine employees to analyze the content of your bot's questions and answers to improve response quality. We will not train LLM's on your data, and your data will be strictly used to improve the product."
              />
            </Flex>
          </Flex>
        )}

        {/* Submit Button */}
        <Flex mt={4}>
          <Button
            type="submit"
            disabled={isLoading || !orgName.trim() || disabled}
            size="lg"
            fullWidth
          >
            {isLoading ? `${submitButtonText}...` : submitButtonText}
          </Button>
        </Flex>
      </Flex>
    </form>
  );
};

export { OrganizationForm };
