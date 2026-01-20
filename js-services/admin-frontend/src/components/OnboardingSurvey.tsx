import { useState, FC, ChangeEvent } from 'react';
import { Flex, Text, Button, TextArea, Select, RadioGroup } from '@gathertown/gather-design-system';
import type { SelectOption } from '@gathertown/gather-design-system';
import { FullscreenLayout } from './shared/FullscreenLayout';
import grapevinelogo from '../assets/grapevine_purp.png';
import { useAnalytics } from '@corporate-context/frontend-common';
import { useTrackEvent } from '../hooks/useTrackEvent';
import { useSetConfigValue } from '../api/config';

const COMPANY_SIZE_OPTIONS: SelectOption[] = [
  { label: '1–10', value: '1–10' },
  { label: '11–25', value: '11–25' },
  { label: '26–100', value: '26–100' },
  { label: '101–1,000', value: '101–1,000' },
  { label: '1,000+', value: '1,000+' },
];

const ROLE_OPTIONS: SelectOption[] = [
  { label: 'Individual Contributor', value: 'Individual Contributor' },
  { label: 'Manager', value: 'Manager' },
  { label: 'Director/Exec', value: 'Director/Exec' },
  { label: 'Founder', value: 'Founder' },
];

const HDYHAU_OPTIONS: SelectOption[] = [
  { label: 'Word of Mouth', value: 'Word of Mouth' },
  { label: 'Google Search', value: 'Google Search' },
  { label: 'AI Search (ChatGPT, Perplexity etc)', value: 'AI Search (ChatGPT, Perplexity etc)' },
  { label: 'Social', value: 'Social' },
  { label: 'Media / Blog', value: 'Media / Blog' },
  { label: 'Gather AI', value: 'Gather AI' },
  { label: 'Ad', value: 'Ad' },
  { label: 'Other (Please Specify)', value: 'Other (Please Specify)' },
];

const SOCIAL_PLATFORM_OPTIONS: SelectOption[] = [
  { label: 'LinkedIn', value: 'LinkedIn' },
  { label: 'X', value: 'X' },
  { label: 'TikTok', value: 'TikTok' },
  { label: 'Instagram', value: 'Instagram' },
  { label: 'Reddit', value: 'Reddit' },
  { label: 'YouTube', value: 'YouTube' },
  { label: 'Other', value: 'Other' },
];

const OnboardingSurvey: FC = () => {
  const { mutateAsync: updateConfigValue, isPending: isLoading } = useSetConfigValue();
  const { setUserProperty } = useAnalytics();
  const { trackEvent } = useTrackEvent();

  // Survey fields
  const [companySize, setCompanySize] = useState<string>('');
  const [role, setRole] = useState<string>('');
  const [hdyhau, setHdyhau] = useState<string>('');
  const [socialPlatform, setSocialPlatform] = useState<string>('');
  const [socialPlatformOther, setSocialPlatformOther] = useState<string>('');
  const [hdyhauOther, setHdyhauOther] = useState<string>('');
  const [problemToSolve, setProblemToSolve] = useState<string>('');
  const [dataUsageConsent, setDataUsageConsent] = useState<string>('');

  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (): Promise<void> => {
    // Validate required fields
    if (!companySize || !role || !hdyhau || !dataUsageConsent) {
      setError('Please complete all required fields');
      return;
    }

    // Validate conditional fields
    if (hdyhau === 'Social' && !socialPlatform) {
      setError('Please select a social platform');
      return;
    }

    if (hdyhau === 'Social' && socialPlatform === 'Other' && !socialPlatformOther.trim()) {
      setError('Please specify which social platform');
      return;
    }

    if (hdyhau === 'Other (Please Specify)' && !hdyhauOther.trim()) {
      setError('Please specify how you heard about us');
      return;
    }

    setError(null);

    try {
      // Compute the final hdyhau value with platform details
      let finalHdyhau = hdyhau;
      if (hdyhau === 'Social' && socialPlatform) {
        if (socialPlatform === 'Other' && socialPlatformOther) {
          finalHdyhau = `Social - ${socialPlatformOther.trim()}`;
        } else {
          finalHdyhau = `Social - ${socialPlatform}`;
        }
      } else if (hdyhau === 'Other (Please Specify)' && hdyhauOther) {
        finalHdyhau = hdyhauOther.trim();
      }

      // Set PostHog person properties
      setUserProperty('company_size', companySize);
      setUserProperty('role', role);
      setUserProperty('hdyhau', finalHdyhau);
      if (problemToSolve.trim()) {
        setUserProperty('problem_to_solve', problemToSolve.trim());
      }

      // Track onboarding survey completion event
      trackEvent('onboarding_survey_completed', {
        company_size: companySize,
        role,
        hdyhau: finalHdyhau,
        problem_to_solve: problemToSolve.trim() || undefined,
      });

      // Save config flags
      await Promise.all([
        updateConfigValue({
          key: 'HAS_COMPLETED_ONBOARDING_SURVEY',
          value: 'true',
        }),
        updateConfigValue({
          key: 'ALLOW_DATA_SHARING_FOR_IMPROVEMENTS',
          value: dataUsageConsent === 'yes' ? 'true' : '',
        }),
      ]);

      // The app will automatically re-render and navigate away
    } catch (err) {
      console.error('Failed to save survey responses:', err);
      setError('Failed to save your responses. Please try again.');
    }
  };

  const showSocialPlatformDropdown = hdyhau === 'Social';
  const showSocialPlatformOtherInput = socialPlatform === 'Other';
  const showHdyhauOtherInput = hdyhau === 'Other (Please Specify)';

  // Form is valid when all required fields are filled
  const isFormValid =
    companySize &&
    role &&
    hdyhau &&
    dataUsageConsent &&
    // If "Social" is selected, social platform must be selected
    (!showSocialPlatformDropdown || socialPlatform) &&
    // If "Social - Other" is selected, socialPlatformOther must be filled
    (!showSocialPlatformOtherInput || socialPlatformOther.trim()) &&
    // If "Other" is selected, hdyhauOther must be filled
    (!showHdyhauOtherInput || hdyhauOther.trim());

  return (
    <FullscreenLayout showSignOut={true}>
      <Flex direction="column" align="center" maxWidth="500px" width="100%" px={6} gap={32}>
        {/* Header with Logo */}
        <Flex direction="column" align="center" gap={16} width="100%">
          <img
            src={grapevinelogo}
            alt="Grapevine Logo"
            style={{ height: '64px', width: 'auto', marginBottom: '16px' }}
          />
          <Flex direction="column" gap={10}>
            <Text fontSize="xxl" textAlign="center" fontWeight="semibold">
              Tell us about yourself
            </Text>
            <Text fontSize="md" textAlign="center">
              Help us tailor Grapevine to your needs
            </Text>
          </Flex>
        </Flex>

        {/* Survey Form */}
        <Flex
          direction="column"
          width="100%"
          gap={20}
          borderRadius={12}
          p={32}
          backgroundColor="primary"
          borderColor="tertiary"
          borderWidth={1}
        >
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

          {/* Company Size */}
          <Select
            label="Company Size"
            options={COMPANY_SIZE_OPTIONS}
            placeholder="Select company size"
            value={companySize}
            onChange={(value) => setCompanySize(value)}
            disabled={isLoading}
          />

          {/* Role */}
          <Select
            label="Role"
            options={ROLE_OPTIONS}
            placeholder="Select your role"
            value={role}
            onChange={(value) => setRole(value)}
            disabled={isLoading}
          />

          {/* How Did You Hear About Us */}
          <Select
            label="How Did You Hear About Us?"
            options={HDYHAU_OPTIONS}
            placeholder="Select an option"
            value={hdyhau}
            onChange={(value) => {
              setHdyhau(value);
              // Reset conditional fields when main selection changes
              setSocialPlatform('');
              setHdyhauOther('');
            }}
            disabled={isLoading}
          />

          {/* Social Platform Sub-dropdown */}
          {showSocialPlatformDropdown && (
            <Select
              label="Which social platform?"
              options={SOCIAL_PLATFORM_OPTIONS}
              placeholder="Select platform"
              value={socialPlatform}
              onChange={(value) => {
                setSocialPlatform(value);
                // Reset social platform other field when platform changes
                setSocialPlatformOther('');
              }}
              disabled={isLoading}
            />
          )}

          {/* Social Platform Other Input */}
          {showSocialPlatformOtherInput && (
            <TextArea
              label="Please specify"
              value={socialPlatformOther}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) =>
                setSocialPlatformOther(e.target.value)
              }
              disabled={isLoading}
              placeholder="Which social platform?"
              style={{ minHeight: '60px' }}
            />
          )}

          {/* HDYHAU Other Input */}
          {showHdyhauOtherInput && (
            <Flex>
              <TextArea
                label="Please specify"
                value={hdyhauOther}
                onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setHdyhauOther(e.target.value)}
                disabled={isLoading}
                placeholder="How did you hear about us?"
                style={{ minHeight: '60px' }}
              />
            </Flex>
          )}

          {/* Problem to Solve */}
          <TextArea
            label="What problem are you hoping Grapevine can solve? (Optional)"
            value={problemToSolve}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setProblemToSolve(e.target.value)}
            disabled={isLoading}
            style={{ minHeight: '50px' }}
          />

          {/* Data Sharing Consent Section */}
          <Flex direction="column" gap={8} mt={8}>
            <Text fontWeight="medium">
              Can Grapevine employees review bot questions and answers to improve the product?
            </Text>
            <Text color="tertiary">
              This helps us improve response quality. We won't train LLMs on your data—it's only
              used to make the product better.
            </Text>
            <div style={{ display: 'contents' }}>
              <RadioGroup
                name="dataConsent"
                value={dataUsageConsent}
                onChange={setDataUsageConsent}
                items={[
                  { value: 'yes', label: 'Yes', disabled: isLoading },
                  { value: 'no', label: 'No', disabled: isLoading },
                ]}
              />
            </div>
          </Flex>

          {/* Submit Button */}
          <Flex mt={4}>
            <Button onClick={handleSubmit} disabled={isLoading || !isFormValid} size="lg" fullWidth>
              {isLoading ? 'Saving...' : 'Continue'}
            </Button>
          </Flex>
        </Flex>
      </Flex>
    </FullscreenLayout>
  );
};

export { OnboardingSurvey };
