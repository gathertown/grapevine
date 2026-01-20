import { memo, useCallback, useState } from 'react';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';
import { Flex, Text, Button, Box } from '@gathertown/gather-design-system';
import { useCompletedSourcesCount, useQAOnboarding } from '../../contexts/OnboardingContext';
import { OnboardingStep } from './OnboardingStep';
import { CompanyContextForm } from '../shared';
import { PlanPickerModal } from '../billing/PlanPickerModal';
import { useIntegrations } from '../../contexts/IntegrationsContext';
import { useSourceStats } from '../../hooks/useSourceStats';
import { IntegrationCard } from '../IntegrationCard';
import { useAnsweredQuestions } from '../../hooks/useAnsweredQuestions';
import { CollapsibleExample } from '../CollapsibleExample';
import { IntegrationAlertModal } from '../IntegrationAlertModal';
import { RequestIntegrationForm } from '../RequestIntegrationForm';
import { DevPlatformHomePage } from './DevPlatformHomePage';
import { useDevMode } from '../../hooks/useDevMode';
import { useAllConfig, useSetConfigValue } from '../../api/config';

/**
 * HomePage component - displays onboarding steps based on tenant mode
 * - For QA mode: Shows Slack-focused onboarding with 6 steps
 * - For dev_platform mode: Shows api key based onboarding with 3 steps
 */
const HomePage: FC = memo(() => {
  const isDevMode = useDevMode();
  // If not in dev mode, show QA home page
  if (isDevMode) {
    return <DevPlatformHomePage />;
  }

  // Otherwise render QA-specific home page
  return <QAHomePage />;
});

HomePage.displayName = 'HomePage';

/**
 * QAHomePage component - Slack-focused onboarding for QA tenant mode
 */
const QAHomePage: FC = memo(() => {
  const navigate = useNavigate();
  const [isPlanPickerModalOpen, setIsPlanPickerModalOpen] = useState(false);

  const { steps, isInitialized, billingComplete, trialStatus } = useQAOnboarding();
  const [openSlackIntegrationAlertModal, setOpenSlackIntegrationAlertModal] = useState(false);
  const { data: configData } = useAllConfig();
  const { mutateAsync: updateConfigValue } = useSetConfigValue();
  const { connectedIntegrations, availableIntegrations, integrations } = useIntegrations();
  const { data: sourceStats } = useSourceStats({ enabled: isInitialized });
  const { answeredQuestions } = useAnsweredQuestions();
  const completedSourceCount = useCompletedSourcesCount();

  // Handler to mark Slack bot as tested
  const handleMarkSlackBotTested = useCallback(async () => {
    try {
      await updateConfigValue({
        key: 'SLACK_BOT_TESTED',
        value: 'true',
      });
    } catch (error) {
      console.error('Failed to mark Slack bot as tested:', error);
    }
  }, [updateConfigValue]);

  // Don't render until context is initialized
  if (!isInitialized) {
    return null;
  }

  // Find the first uncompleted step for primary button styling
  const getFirstUncompletedStep = (): number | null => {
    if (!steps.step1) return 1;
    if (!steps.step2) return 2; // Upload Recent Slack Export
    if (!steps.step3) return 3; // Set up Integrations
    if (!steps.step4) return 4; // Tell Grapevine about your Company
    if (!steps.step5) return 5; // Test Your Slack Bot
    if (!steps.step6) return 6; // Upload Historical Slack Export (moved from step 5 to 6)

    return null; // All steps completed
  };

  const firstUncompletedStep = getFirstUncompletedStep();
  const botName = configData?.SLACK_BOT_NAME || 'Grapevine';

  const indexedData = Object.values(sourceStats || {}).reduce(
    (sum, source) => sum + source.indexed,
    0
  );
  const totalData = Object.values(sourceStats || {}).reduce(
    (sum, source) => sum + Object.values(source.discovered).reduce((s, count) => s + count, 0),
    0
  );
  const step5WarningText = !steps.step2
    ? 'For better answers, we recommend uploading your last 7 days of Slack data'
    : !steps.step4
      ? 'For better answers, we recommend providing some company context'
      : totalData > 50 && indexedData / totalData < 0.05
        ? 'For better answers, we recommend asking a question in 10 minutes'
        : null;

  const slackIntegration = integrations.find((integration) => integration.id === 'slack');

  const availableIntegrationsWithoutComingSoon = availableIntegrations.filter(
    (integration) => !integration.comingSoon
  );

  return (
    <Flex direction="column" width="100%" gap={4} maxWidth="800px" mx="auto">
      {/* Onboarding Steps */}
      <Flex direction="column" gap={48} pb={64}>
        {/* Step 1: Set up Slack */}
        <OnboardingStep stepNumber={1} isComplete={steps.step1}>
          <Flex direction="column" justify="space-between" gap={16}>
            <Flex
              direction="row"
              gap={24}
              justify="space-between"
              align={steps.step1 ? 'center' : undefined}
            >
              <Flex direction="column" gap={4}>
                <Text fontSize="md" fontWeight="semibold">
                  Set up Slack
                </Text>
                <Text fontSize="sm">
                  Connect Grapevine to Slack so we can start learning about{' '}
                  {configData?.COMPANY_NAME}
                </Text>
              </Flex>
              {!steps.step1 ? (
                <Flex justify="flex-end">
                  <Button
                    kind={firstUncompletedStep === 1 ? 'primary' : 'secondary'}
                    onClick={() => {
                      firstUncompletedStep === 1 && slackIntegration
                        ? setOpenSlackIntegrationAlertModal(true)
                        : navigate('/onboarding/slack');
                    }}
                  >
                    Set up Slack
                  </Button>
                  {slackIntegration ? (
                    <IntegrationAlertModal
                      integration={{ ...slackIntegration, name: 'Slack' }}
                      open={openSlackIntegrationAlertModal}
                      onDismiss={() => setOpenSlackIntegrationAlertModal(false)}
                      onSetup={() => navigate('/onboarding/slack')}
                    />
                  ) : null}
                </Flex>
              ) : (
                <Flex pl={40}>
                  <Text color="successPrimary">Done!</Text>
                </Flex>
              )}
            </Flex>
          </Flex>
        </OnboardingStep>

        {/* Step 2: Upload Recent Slack Export */}
        <OnboardingStep stepNumber={2} isComplete={steps.step2}>
          <Flex direction="column" justify="space-between" gap={16}>
            <Flex direction="row" gap={24} justify="space-between" align="center">
              <Flex direction="column" gap={4}>
                <Text fontSize="md" fontWeight="semibold">
                  Upload 'Last 7 Days' Slack Export
                </Text>
                <Text fontSize="sm">
                  {configData?.SLACK_TEAM_DOMAIN ? (
                    <>
                      Visit your{' '}
                      <a
                        href={`https://${configData.SLACK_TEAM_DOMAIN}.slack.com/services/export`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ textDecoration: 'underline' }}
                      >
                        Slack export page
                      </a>{' '}
                      to start an export, then upload it here once ready.
                    </>
                  ) : (
                    <>
                      Once it's ready, upload your Slack export for the last 7 days here.{' '}
                      <a
                        href="https://slack.com/help/articles/201658943-Export-your-workspace-data"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Not sure how?
                      </a>
                    </>
                  )}
                </Text>
              </Flex>
              {!steps.step2 ? (
                <Flex justify="flex-end">
                  <Button
                    kind={firstUncompletedStep === 2 ? 'primary' : 'secondary'}
                    onClick={() => navigate('/integrations/slack-export')}
                  >
                    Upload Export
                  </Button>
                </Flex>
              ) : (
                <Flex pl={40}>
                  <Text color="successPrimary">Done!</Text>
                </Flex>
              )}
            </Flex>
          </Flex>
        </OnboardingStep>

        {/* Step 3: Set up Integrations */}
        <OnboardingStep stepNumber={3} isComplete={steps.step3}>
          <Flex direction="column" justify="space-between" gap={16}>
            <Flex direction="row" gap={24} justify="space-between" align="center">
              <Flex direction="column" gap={4}>
                <Text fontSize="md" fontWeight="semibold">
                  Set up Integrations
                </Text>
                <Text fontSize="sm">
                  {(() => {
                    const remaining = Math.max(0, 3 - completedSourceCount);
                    return remaining > 0 ? (
                      <>
                        We recommend connecting at least 3 sources to Grapevine...{' '}
                        <b>{remaining} more to go!</b>
                      </>
                    ) : (
                      'Connect your data from various work apps so Grapevine can understand your company'
                    );
                  })()}
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

        {/* Step 4: Tell Grapevine about your Company */}
        <OnboardingStep stepNumber={4} isComplete={steps.step4}>
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

        {/* Step 5: Test Your Slack Bot */}
        <OnboardingStep stepNumber={5} isComplete={steps.step5}>
          <Flex direction="column" gap={24}>
            <Flex direction="column" justify="space-between" gap={8}>
              {step5WarningText ? (
                <Text fontSize="sm" color="warningPrimary">
                  {step5WarningText}
                </Text>
              ) : null}
              <Flex direction="row" gap={24} justify="space-between" align="center">
                <Flex direction="column" gap={4}>
                  <Text fontSize="md" fontWeight="semibold">
                    Ask {botName} some questions!
                  </Text>
                  <Text fontSize="sm">
                    Go to Slack and ask {botName} questions, either by DM'ing it or @ mentioning it
                    in any channel or DM
                  </Text>
                </Flex>
                {!steps.step5 ? (
                  <Flex justify="flex-end">
                    <Button
                      kind={firstUncompletedStep === 5 ? 'primary' : 'secondary'}
                      onClick={handleMarkSlackBotTested}
                    >
                      Mark as Complete
                    </Button>
                  </Flex>
                ) : (
                  <Flex pl={40}>
                    <Text color="successPrimary">Done!</Text>
                  </Flex>
                )}
              </Flex>
            </Flex>

            {answeredQuestions.length > 0 ? (
              <Flex direction="column" gap={8}>
                <Text fontSize="md" fontWeight="semibold">
                  Sample questions to ask
                </Text>
                {answeredQuestions.map((q) => {
                  if (!q.answers[0]?.answer_text) {
                    return null;
                  }
                  return (
                    <CollapsibleExample key={q.id} title={q.question_text}>
                      <span
                        style={{
                          lineClamp: 2,
                          WebkitLineClamp: 2,
                          overflow: 'hidden',
                        }}
                      >
                        {q.answers[0].answer_text}
                      </span>
                    </CollapsibleExample>
                  );
                })}
              </Flex>
            ) : null}
          </Flex>
        </OnboardingStep>

        {/* Step 6: Upload Historical Slack Export */}
        <OnboardingStep stepNumber={6} isComplete={steps.step6}>
          <Flex direction="column" justify="space-between" gap={16}>
            <Flex direction="row" gap={24} justify="space-between" align="center">
              <Flex direction="column" gap={4}>
                <Text fontSize="md" fontWeight="semibold">
                  Upload 'All Time' Slack Export
                </Text>
                <Text fontSize="sm">
                  Once it's ready, upload all your historical Slack data here.{' '}
                  <a
                    href="https://slack.com/help/articles/201658943-Export-your-workspace-data"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Not sure how?
                  </a>
                </Text>
              </Flex>
              {!steps.step6 ? (
                <Flex justify="flex-end">
                  <Button
                    kind={firstUncompletedStep === 6 ? 'primary' : 'secondary'}
                    onClick={() => navigate('/integrations/slack-export')}
                  >
                    Upload Export
                  </Button>
                </Flex>
              ) : (
                <Flex pl={40}>
                  <Text color="successPrimary">Done!</Text>
                </Flex>
              )}
            </Flex>
          </Flex>
        </OnboardingStep>

        <OnboardingStep stepNumber={7} label="BILLING" isComplete={billingComplete}>
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
                  kind={firstUncompletedStep === 7 ? 'primary' : 'secondary'}
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

QAHomePage.displayName = 'QAHomePage';

export { HomePage };
