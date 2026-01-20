import { memo, useState } from 'react';
import type { FC } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Flex, Text, Button, Box } from '@gathertown/gather-design-system';
import { OnboardingStep } from './OnboardingStep';
import { CompanyContextForm } from '../shared';
import { PlanPickerModal } from '../billing/PlanPickerModal';
import { useIntegrations } from '../../contexts/IntegrationsContext';
import { IntegrationCard } from '../IntegrationCard';
import { RequestIntegrationForm } from '../RequestIntegrationForm';
import { useDevOnboarding } from '../../contexts/OnboardingContext';
import { DOCS_URL } from '../../constants';

const DevPlatformHomePage: FC = memo(() => {
  const navigate = useNavigate();
  const [isPlanPickerModalOpen, setIsPlanPickerModalOpen] = useState(false);

  const { steps, isInitialized, billingComplete, trialStatus } = useDevOnboarding();
  const { connectedIntegrations, availableIntegrations } = useIntegrations();

  // Don't render until context is initialized
  if (!isInitialized) {
    return null;
  }

  // Find the first uncompleted step for primary button styling
  const getFirstUncompletedStep = (): number | null => {
    if (!steps.step1) return 1;
    if (!steps.step2) return 2;
    if (!steps.step3) return 3;
    if (!billingComplete) return 4;
    return null; // All steps completed
  };

  const firstUncompletedStep = getFirstUncompletedStep();

  const availableIntegrationsWithoutComingSoon = availableIntegrations.filter(
    (integration) => !integration.comingSoon
  );

  return (
    <Flex direction="column" width="100%" gap={4} maxWidth="800px" mx="auto">
      {/* Onboarding Steps */}
      <Flex direction="column" gap={48} pb={64}>
        {/* Welcome Section */}
        <Flex direction="column" gap={16}>
          <Text fontSize="xl" fontWeight="semibold">
            Welcome to Grapevine
          </Text>
          <Text fontSize="md">
            Get started by connecting your data sources and setting up the MCP server for Claude
            Desktop integration.
          </Text>
        </Flex>

        {/* Step 1: Set up Integrations */}
        <OnboardingStep stepNumber={1} isComplete={steps.step1}>
          <Flex direction="column" justify="space-between" gap={16}>
            <Flex direction="row" gap={24} justify="space-between" align="center">
              <Flex direction="column" gap={4}>
                <Text fontSize="md" fontWeight="semibold">
                  Connect Data Sources
                </Text>
                <Text fontSize="sm">
                  {steps.step1
                    ? 'Connect your work apps so Grapevine can understand your company'
                    : 'We recommend connecting at least 1 source to get started'}
                </Text>
              </Flex>
            </Flex>
            <Flex direction="column" gap={16}>
              {connectedIntegrations.length > 0 ? (
                <Flex direction="column" gap={4}>
                  <Text color="successPrimary" fontSize="xs">
                    Connected
                  </Text>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(142px, 1fr))',
                      gap: '12px',
                    }}
                  >
                    {connectedIntegrations.map((integration) => {
                      return (
                        <IntegrationCard key={integration.id} integrationId={integration.id} />
                      );
                    })}
                  </div>
                </Flex>
              ) : null}

              {availableIntegrationsWithoutComingSoon.length > 0 ? (
                <Flex direction="column" gap={4}>
                  <Text color="tertiary" fontSize="xs">
                    Available
                  </Text>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(142px, 1fr))',
                      gap: '12px',
                    }}
                  >
                    {availableIntegrationsWithoutComingSoon.map((integration) => {
                      return (
                        <IntegrationCard key={integration.id} integrationId={integration.id} />
                      );
                    })}
                  </div>
                </Flex>
              ) : null}
            </Flex>
          </Flex>
          <Box mt={16} width="100%">
            <RequestIntegrationForm />
          </Box>
        </OnboardingStep>

        {/* Step 2: Tell Grapevine about your Company */}
        <OnboardingStep stepNumber={2} isComplete={steps.step2}>
          <Flex direction="column" pb={16} gap={8}>
            <Text fontSize="md" fontWeight="semibold">
              Tell Grapevine about your Company
            </Text>
            <Text fontSize="sm">
              This context goes straight into the agent's prompt, so the more context you add, the
              better your answers. To help you get started, we created a short draft from your
              company site.
            </Text>
          </Flex>
          <CompanyContextForm minLength={10} />
        </OnboardingStep>

        {/* Step 3: Install MCP Server */}
        <OnboardingStep stepNumber={3} isComplete={steps.step3}>
          <Flex direction="column" gap={24}>
            <Flex direction="column" justify="space-between" gap={8}>
              <Flex direction="row" gap={24} justify="space-between" align="center">
                <Flex direction="column" gap={4}>
                  <Text fontSize="md" fontWeight="semibold">
                    Generate an API Key and make a call
                  </Text>
                  <Text fontSize="sm">
                    Create an API key in the <Link to="/api-keys">API Keys section</Link>
                  </Text>
                  <Text fontSize="xs" color="tertiary">
                    Once you have your API key, you can use it to make requests to the Grapevine
                    API.
                    {DOCS_URL && (
                      <>
                        {' '}
                        See{' '}
                        <a
                          href={`${DOCS_URL}/features/rest-api`}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ textDecoration: 'underline' }}
                        >
                          API Documentation
                        </a>{' '}
                        for more details.
                      </>
                    )}
                  </Text>
                </Flex>
              </Flex>
            </Flex>
          </Flex>
        </OnboardingStep>

        {/* Step 4: Billing */}
        <OnboardingStep stepNumber={4} label="BILLING" isComplete={billingComplete}>
          <Flex direction="column" justify="space-between" gap={16}>
            <Flex direction="row" gap={24} justify="space-between" align="center">
              <Flex direction="column" gap={4}>
                <Text fontSize="md" fontWeight="semibold">
                  Choose a Plan
                </Text>
                {billingComplete ? (
                  <Text>You're all set! </Text>
                ) : (
                  <Text fontSize="sm">Select the plan that best fits your team's needs</Text>
                )}
              </Flex>
              <Flex justify="flex-end">
                <Button
                  kind={firstUncompletedStep === 4 ? 'primary' : 'secondary'}
                  onClick={() =>
                    billingComplete ? navigate('/billing') : setIsPlanPickerModalOpen(true)
                  }
                >
                  {billingComplete ? 'Manage billing' : 'Choose a plan'}
                </Button>
              </Flex>
            </Flex>
          </Flex>
        </OnboardingStep>
      </Flex>

      {/* Plan Picker Modal */}
      <PlanPickerModal
        open={isPlanPickerModalOpen}
        onOpenChange={setIsPlanPickerModalOpen}
        trialStatus={trialStatus}
      />
    </Flex>
  );
});

DevPlatformHomePage.displayName = 'DevPlatformHomePage';

export { DevPlatformHomePage };
