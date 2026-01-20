import { GenericMessageEvent } from '@slack/bolt';
import { TenantSlackApp } from './TenantSlackApp';
import { GeneratedAnswer, Message, PermissionAudience } from './types';
import { getAnalyticsTracker } from './services/analyticsTracker';
import { mutatingActionClassifier } from './services/mutatingActionClassifier';
import {
  stripMessageHeader,
  shouldTryToAnswerMessage,
  handleError,
  formatQuestionWithContext,
  getFallbackAnswer,
  downloadSlackFiles,
  getBotResponseFromThread,
  SlackFile,
  validateMessageExistsOrCleanup,
  getTenantStateToAnswerQuestions,
  getConfiguredSourceNames,
  StreamEvent,
} from './common';
import { logger } from './utils/logger';
import { tenantConfigManager } from './config/tenantConfigManager';
import { config, shouldUseProgressBarAndTranslation } from './config';
import { getGrapevineEnv } from '@corporate-context/backend-common';
import { DEFAULT_PHRASES_EN } from './i18n/phrases';
import {
  buildProgressMessage,
  buildProgressBlocks,
  getInitialProgressMessage,
  getInitialProgressBlocks,
  createProgressState,
  ThrottledProgressUpdater,
} from './utils/progressFormatter';
import { getPhrasesForMessage } from './i18n/translatePhrases';
import type { TranslatedPhrases } from './i18n/phrases';

function shouldUseAskAgentRace(): boolean {
  return config.enableAskAgentRaceMode;
}

function stripDisplayedConfidence(answer: string): string {
  if (!answer) {
    return answer;
  }

  return answer.replace(/\n+\s*_Confidence:[\s\S]*$/u, '').trim();
}

function appendDisplayedConfidence(
  answer: string,
  confidence?: number,
  confidenceExplanation?: string
): string {
  if (!answer) {
    return answer;
  }

  if (confidence === undefined || confidence <= 0) {
    return answer;
  }

  const explanation = confidenceExplanation?.trim();
  const confidenceLine = explanation
    ? `_Confidence: ${confidence}% - ${explanation}_`
    : `_Confidence: ${confidence}%_`;

  return `${answer}\n\n${confidenceLine}`;
}

/**
 * Build a Message object from a Slack event, handling file downloads
 */
async function buildMessageFromSlackEvent(
  msg: GenericMessageEvent,
  tenantSlackApp: TenantSlackApp,
  content: string
): Promise<Message> {
  // Download files if present
  const files =
    msg.files && msg.files.length > 0
      ? await downloadSlackFiles(msg.files as SlackFile[], tenantSlackApp.botToken)
      : [];

  // Build the message for backend processing
  return {
    role: 'user' as const,
    content,
    files: files.length > 0 ? files : undefined,
  };
}

/**
 * Handle processing errors with consistent cleanup and formatting
 */
async function handleProcessingError(
  context: string,
  error: unknown,
  tenantSlackApp: TenantSlackApp,
  msg: GenericMessageEvent
): Promise<{ success: boolean; [key: string]: unknown }> {
  await tenantSlackApp.removeProcessingReaction(msg.channel, msg.ts);
  const errorResult = handleError(context, error, { fallbackValue: {} });
  return {
    success: false,
    ...(typeof errorResult === 'object' && errorResult !== null ? errorResult : {}),
  };
}

interface AskAgentRunnersSetup {
  messageText: string;
  fastPromise: Promise<GeneratedAnswer | null> | null;
  /** Lazily creates the non-streaming slow promise. Only call this when you actually need it. */
  runSlow: () => Promise<GeneratedAnswer | null>;
  runSlowStreaming: (onEvent?: (event: StreamEvent) => void) => Promise<GeneratedAnswer | null>;
}

async function startAskAgentRace(
  msg: GenericMessageEvent,
  tenantSlackApp: TenantSlackApp,
  contextMessages: Message[],
  options: {
    previousResponseId?: string;
    channelId?: string;
    permissionAudience?: PermissionAudience;
    linearTeamId?: string;
  } = {},
  useRace: boolean = true
): Promise<AskAgentRunnersSetup> {
  const messageText = stripMessageHeader(msg.text || '');
  const questionText = formatQuestionWithContext(messageText, contextMessages);

  logger.info('Processing question from user', {
    tenantId: tenantSlackApp.tenantId,
    userId: msg.user,
    channelId: msg.channel,
    fileCount: msg.files?.length || 0,
    operation: 'question-processing',
  });

  const backendMessage = await buildMessageFromSlackEvent(msg, tenantSlackApp, questionText);
  const { run, runStreaming } = await tenantSlackApp.createAskAgentRunners(
    backendMessage,
    msg.user,
    {
      previousResponseId: options.previousResponseId,
      channelId: options.channelId,
      permissionAudience: options.permissionAudience,
      nonBillable: !!options.previousResponseId,
      writeTools: options.linearTeamId ? ['linear'] : [],
    }
  );

  const fastPromise = useRace
    ? run('ask_agent_fast', {
        reasoningEffort: 'minimal',
        verbosity: 'low',
      })
    : null;

  // Return functions to lazily start slow calls - only call when you need them
  const runSlow = () => run('ask_agent', {});
  const runSlowStreaming = (onEvent?: (event: StreamEvent) => void) => runStreaming({}, onEvent);

  return { messageText, fastPromise, runSlow, runSlowStreaming };
}

interface AskAgentVariantResult {
  variant: 'fast' | 'slow';
  answer?: GeneratedAnswer | null;
  error?: unknown;
}

interface AskAgentRaceResult {
  finalAnswer: GeneratedAnswer | null;
  finalVariant: 'fast' | 'slow' | null;
  preliminaryAnswer: GeneratedAnswer | null;
}

interface ProgressRaceContext {
  tenantSlackApp: TenantSlackApp;
  channel: string;
  threadTs: string;
  phrases: TranslatedPhrases;
}

/**
 * Execute the fast/slow race and handle preliminary responses (OLD behavior - no progress bar)
 */
async function executeAskAgentRace(
  fastPromise: Promise<GeneratedAnswer | null>,
  slowPromise: Promise<GeneratedAnswer | null>,
  context: {
    tenantId: string;
    channelId: string;
    operation: string;
  },
  onPreliminaryAnswer?: (answer: GeneratedAnswer) => Promise<void>
): Promise<AskAgentRaceResult> {
  const wrappedFast: Promise<AskAgentVariantResult> = fastPromise
    .then((answer) => ({ variant: 'fast' as const, answer }))
    .catch((error) => ({ variant: 'fast' as const, error }));

  const wrappedSlow: Promise<AskAgentVariantResult> = slowPromise
    .then((answer) => ({ variant: 'slow' as const, answer }))
    .catch((error) => ({ variant: 'slow' as const, error }));

  // Race to get the first result
  const firstResult = await Promise.race([wrappedFast, wrappedSlow]);

  let fastResult: AskAgentVariantResult | null = null;
  let slowResult: AskAgentVariantResult | null = null;

  // If fast wins, send preliminary response immediately without waiting for slow
  if (firstResult.variant === 'fast') {
    fastResult = firstResult;

    if (fastResult.answer && fastResult.answer.answer && onPreliminaryAnswer) {
      await onPreliminaryAnswer(fastResult.answer);
    }

    if (fastResult.error) {
      logger.error(`[${context.operation}] ask_agent_fast error`, fastResult.error, {
        tenantId: context.tenantId,
        channelId: context.channelId,
        operation: 'ask-agent-fast-error',
      });
    }

    // Now wait for slow result
    slowResult = await wrappedSlow;

    if (slowResult.error) {
      logger.error(`[${context.operation}] ask_agent error`, slowResult.error, {
        tenantId: context.tenantId,
        channelId: context.channelId,
        operation: 'ask-agent-error',
      });
    }
  } else {
    // Slow finished first (unexpected but possible)
    slowResult = firstResult;

    if (slowResult.error) {
      logger.error(`[${context.operation}] ask_agent error`, slowResult.error, {
        tenantId: context.tenantId,
        channelId: context.channelId,
        operation: 'ask-agent-error',
      });
    }

    // Let fast complete in background - don't block on it since slow is already done
    wrappedFast.catch((error) => {
      logger.error(`[${context.operation}] ask_agent_fast error (background)`, error, {
        tenantId: context.tenantId,
        channelId: context.channelId,
        operation: 'ask-agent-fast-error-background',
      });
    });
  }

  // Determine final answer: prefer slow if available, otherwise use fast
  let finalAnswer: GeneratedAnswer | null = null;
  let finalVariant: 'fast' | 'slow' | null = null;

  if (slowResult?.answer && slowResult.answer.answer) {
    finalAnswer = slowResult.answer;
    finalVariant = 'slow';
  } else if (fastResult?.answer && fastResult.answer.answer) {
    finalAnswer = fastResult.answer;
    finalVariant = 'fast';
  }

  const preliminaryAnswer =
    fastResult?.answer && fastResult.answer.answer ? fastResult.answer : null;

  return { finalAnswer, finalVariant, preliminaryAnswer };
}

/**
 * Execute fast/slow race with a progress bar powered by streaming events.
 * - Posts initial progress message
 * - Updates progress as streaming events arrive (throttled to steady cadence)
 * - Appends fast answer under progress bar when it arrives
 * - Returns final answer and progress message timestamp for replacement
 */
async function executeAskAgentRaceWithProgress(
  fastPromise: Promise<GeneratedAnswer | null>,
  runSlowStreaming: (onEvent?: (event: StreamEvent) => void) => Promise<GeneratedAnswer | null>,
  progressContext: ProgressRaceContext
): Promise<AskAgentRaceResult & { progressMessageTs?: string }> {
  const { tenantSlackApp, channel, threadTs, phrases } = progressContext;

  // Post initial progress message with blocks
  const progressMessageTs = await tenantSlackApp.postProgressMessage(
    channel,
    threadTs,
    getInitialProgressMessage(phrases),
    getInitialProgressBlocks(phrases)
  );

  // Create throttled progress updater that drains events at steady 2.5s intervals
  const progressUpdater = new ThrottledProgressUpdater(
    createProgressState(phrases),
    async (state) => {
      const currentStep = state.recentSteps[state.recentSteps.length - 1];
      logger.info('[executeAskAgentRaceWithProgress] Progress update', {
        tenantId: tenantSlackApp.tenantId,
        stepCount: state.recentSteps.length,
        currentAction: currentStep?.action,
        operation: 'progress-update',
      });

      if (progressMessageTs) {
        await tenantSlackApp.updateProgressMessage(
          channel,
          progressMessageTs,
          buildProgressMessage(state),
          buildProgressBlocks(state)
        );
      }
    },
    2500 // Update every 2.5 seconds
  );

  // Start the throttled updater
  progressUpdater.start();

  // Handle streaming events by queueing them for throttled processing
  const handleStreamEvent = (event: StreamEvent) => {
    logger.info('[executeAskAgentRaceWithProgress] Progress event queued', {
      tenantId: tenantSlackApp.tenantId,
      eventType: event.type,
      operation: 'progress-event-queued',
    });
    progressUpdater.pushEvent(event);
  };

  // Start the slow streaming with our event handler
  const slowPromise = runSlowStreaming(handleStreamEvent);

  // Wrap promises to track which completes first
  const wrappedFast: Promise<AskAgentVariantResult> = fastPromise
    .then((answer) => ({ variant: 'fast' as const, answer }))
    .catch((error) => ({ variant: 'fast' as const, error }));

  const wrappedSlow: Promise<AskAgentVariantResult> = slowPromise
    .then((answer) => ({ variant: 'slow' as const, answer }))
    .catch((error) => ({ variant: 'slow' as const, error }));

  let fastResult: AskAgentVariantResult | null = null;
  let slowResult: AskAgentVariantResult | null = null;

  // Race to get the first result
  const firstResult = await Promise.race([wrappedFast, wrappedSlow]);

  if (firstResult.variant === 'fast') {
    fastResult = firstResult;

    // If fast answer is available, append it under the progress bar
    if (fastResult.answer && fastResult.answer.answer) {
      progressUpdater.setFastAnswer(fastResult.answer.answer);
    }

    if (fastResult.error) {
      logger.error('[executeAskAgentRaceWithProgress] ask_agent_fast error', fastResult.error, {
        tenantId: tenantSlackApp.tenantId,
        channelId: channel,
        operation: 'ask-agent-fast-error',
      });
    }

    // Wait for slow result
    slowResult = await wrappedSlow;

    if (slowResult.error) {
      logger.error('[executeAskAgentRaceWithProgress] ask_agent error', slowResult.error, {
        tenantId: tenantSlackApp.tenantId,
        channelId: channel,
        operation: 'ask-agent-error',
      });
    }
  } else {
    // Slow finished first
    slowResult = firstResult;

    if (slowResult.error) {
      logger.error('[executeAskAgentRaceWithProgress] ask_agent error', slowResult.error, {
        tenantId: tenantSlackApp.tenantId,
        channelId: channel,
        operation: 'ask-agent-error',
      });
    }

    // Let fast complete in background and log any errors
    wrappedFast.then((result) => {
      if (result.error) {
        logger.error(
          '[executeAskAgentRaceWithProgress] ask_agent_fast error (background)',
          result.error,
          {
            tenantId: tenantSlackApp.tenantId,
            channelId: channel,
            operation: 'ask-agent-fast-error-background',
          }
        );
      }
    });
  }

  // Stop the throttled updater and flush any remaining events
  await progressUpdater.stop();

  // Determine final answer
  let finalAnswer: GeneratedAnswer | null = null;
  let finalVariant: 'fast' | 'slow' | null = null;

  if (slowResult?.answer && slowResult.answer.answer) {
    finalAnswer = slowResult.answer;
    finalVariant = 'slow';
  } else if (fastResult?.answer && fastResult.answer.answer) {
    finalAnswer = fastResult.answer;
    finalVariant = 'fast';
  }

  const preliminaryAnswer =
    fastResult?.answer && fastResult.answer.answer ? fastResult.answer : null;

  return { finalAnswer, finalVariant, preliminaryAnswer, progressMessageTs };
}

/**
 * Process a message that should always respond (DMs, mentions, thread mentions)
 * Handles the complete flow: processing reaction -> generate answer -> validate -> respond -> cleanup
 */
async function processAlwaysRespondMessage(
  msg: GenericMessageEvent,
  tenantSlackApp: TenantSlackApp,
  contextType: 'dm' | 'thread-mention' | 'channel-mention',
  contextMessages: Message[] = [],
  previousResponseId?: string,
  threadTs?: string,
  permissionAudience?: PermissionAudience,
  linearTeamId?: string
): Promise<{ success: boolean; answer?: string; response?: unknown }> {
  const messageText = stripMessageHeader(msg.text || '');

  try {
    // Show eyes reaction FIRST so users know bot is active immediately
    await tenantSlackApp.addProcessingReaction(msg.channel, msg.ts);

    // Start phrases translation in parallel - we'll await it when needed for UI
    const phrasesPromise = getPhrasesForMessage(tenantSlackApp.tenantId, messageText);

    // Classify if the message involves mutating actions (can run in parallel with phrases)
    const hasMutatingAction = await mutatingActionClassifier.detectsMutatingAction(
      messageText,
      contextMessages
    );

    logger.info('Mutating action classification result', {
      hasMutatingAction,
      linearTeamId: !!linearTeamId,
      contextMessageCount: contextMessages.length,
    });

    // Determine write tools based on context
    // Enable Linear tools if we have a team ID, or if it's a mutating action (best effort)
    const writeTools: string[] = linearTeamId || hasMutatingAction ? ['linear'] : [];
    const hasWriteTools = writeTools.length > 0;

    const finalThreadTs = contextType === 'dm' ? msg.ts : threadTs || msg.ts;
    const isDM = contextType === 'dm';

    const { state } = await getTenantStateToAnswerQuestions(tenantSlackApp.tenantId);

    if (['insufficient-data', 'processing'].includes(state)) {
      // Need phrases for the message - await here
      const { phrases } = await phrasesPromise;
      const message =
        state === 'processing'
          ? phrases.processingState
          : phrases.noSourcesSetup.replace('{dashboardUrl}', config.frontendUrl);

      await tenantSlackApp.sendResponse(
        msg.channel,
        msg.ts,
        message,
        msg.text || '',
        msg.user,
        finalThreadTs,
        isDM,
        undefined,
        false,
        undefined,
        {
          skipAnalytics: true,
          skipFeedback: true,
          skipMirroring: true,
        }
      );

      const analyticsTracker = getAnalyticsTracker();
      const channelName = await tenantSlackApp.getChannelName(msg.channel);
      const isThread = !!(contextType !== 'dm' && finalThreadTs && finalThreadTs !== msg.ts);
      await analyticsTracker.trackQuestionFallback(
        tenantSlackApp.tenantId,
        msg.channel,
        channelName,
        isDM,
        isThread,
        msg.user,
        state as 'insufficient_data' | 'processing',
        message
      );

      return { success: true, answer: message, response: null };
    }

    const channelIdForPrompt = contextType === 'dm' ? undefined : msg.channel;

    // If write tools are enabled, always use ask_agent_fast directly (no race)
    // We don't race when write tools are enabled because write actions (create/update tickets)
    // should only be executed once. Racing would cause both fast and slow agents to take the
    // same action, resulting in duplicate tickets or duplicate status changes.
    if (hasWriteTools) {
      const messageText = stripMessageHeader(msg.text || '');
      let questionText = formatQuestionWithContext(messageText, contextMessages);

      // Append Linear team ID to the question so the agent knows which team to use
      if (linearTeamId) {
        questionText += `\n\n[System note: For Linear ticket operations, use team_id: ${linearTeamId}]`;
      }

      const backendMessage = await buildMessageFromSlackEvent(msg, tenantSlackApp, questionText);

      const { run } = await tenantSlackApp.createAskAgentRunners(backendMessage, msg.user, {
        previousResponseId,
        channelId: channelIdForPrompt,
        permissionAudience,
        nonBillable: !!previousResponseId,
        writeTools: ['linear'],
      });

      const answerData = await run('ask_agent_fast', {
        reasoningEffort: 'minimal',
        verbosity: 'low',
      });

      if (answerData) {
        const answer = stripDisplayedConfidence(answerData.answer);
        const answerToDisplay = appendDisplayedConfidence(
          answer,
          answerData.confidence,
          answerData.confidenceExplanation
        );

        await tenantSlackApp.sendResponse(
          msg.channel,
          msg.ts,
          answerToDisplay,
          msg.text || '',
          msg.user,
          finalThreadTs,
          isDM,
          answerData.responseId,
          false,
          answerData.confidence
        );

        return { success: true, answer: answerToDisplay, response: answerData };
      }

      return { success: false };
    }

    const useRace = shouldUseAskAgentRace();
    const useProgressBar = shouldUseProgressBarAndTranslation();

    const { fastPromise, runSlow, runSlowStreaming } = await startAskAgentRace(
      msg,
      tenantSlackApp,
      contextMessages,
      {
        previousResponseId,
        channelId: channelIdForPrompt,
        permissionAudience,
        linearTeamId,
      },
      useRace
    );

    let preliminaryMessageTs: string | undefined;
    let preliminaryAnswerData: GeneratedAnswer | null = null;
    let finalAnswerData: GeneratedAnswer | null = null;

    if (useRace && fastPromise) {
      if (useProgressBar) {
        // NEW: Use progress bar race execution with translation (staging/local only)
        const { phrases, detectedLanguage } = await phrasesPromise;
        logger.info('Using phrases for language', {
          detectedLanguage,
          tenantId: tenantSlackApp.tenantId,
          operation: 'question-processing',
        });

        const raceResult = await executeAskAgentRaceWithProgress(fastPromise, runSlowStreaming, {
          tenantSlackApp,
          channel: msg.channel,
          threadTs: finalThreadTs,
          phrases,
        });

        finalAnswerData = raceResult.finalAnswer;
        preliminaryAnswerData = raceResult.preliminaryAnswer;
        preliminaryMessageTs = raceResult.progressMessageTs;
      } else {
        // OLD: Use simple race without progress bar (production default)
        const raceResult = await executeAskAgentRace(
          fastPromise,
          runSlow(),
          {
            tenantId: tenantSlackApp.tenantId,
            channelId: msg.channel,
            operation: 'processAlwaysRespondMessage',
          },
          async (answer) => {
            preliminaryMessageTs = await tenantSlackApp.sendResponse(
              msg.channel,
              msg.ts,
              answer.answer,
              msg.text || '',
              msg.user,
              finalThreadTs,
              isDM,
              answer.responseId,
              false,
              answer.confidence,
              {
                isPreliminary: true,
                deferReactionCleanup: true,
              }
            );
          }
        );

        finalAnswerData = raceResult.finalAnswer;
        preliminaryAnswerData = raceResult.preliminaryAnswer;
      }

      if (!finalAnswerData) {
        // For fallback, use translated phrases only if progress bar mode, else use English
        const fallbackPhrases = useProgressBar
          ? (await phrasesPromise).phrases
          : DEFAULT_PHRASES_EN;

        logger.warn(`${contextType}: No answer generated, using fallback message`, {
          tenantId: tenantSlackApp.tenantId,
          userId: msg.user,
          channelId: msg.channel,
          messageTs: msg.ts,
          threadTs,
          operation: `${contextType}-fallback`,
        });

        const fallbackMessage = getFallbackAnswer(fallbackPhrases);

        await tenantSlackApp.sendResponse(
          msg.channel,
          msg.ts,
          fallbackMessage,
          msg.text || '',
          msg.user,
          finalThreadTs,
          isDM,
          undefined,
          false,
          undefined,
          {
            replaceMessageTs: preliminaryMessageTs,
            skipAnalytics: true,
            skipFeedback: true,
            skipMirroring: true,
          }
        );

        const analyticsTracker = getAnalyticsTracker();
        const channelName = await tenantSlackApp.getChannelName(msg.channel);
        const isThread = !!(contextType !== 'dm' && finalThreadTs && finalThreadTs !== msg.ts);
        await analyticsTracker.trackQuestionFallback(
          tenantSlackApp.tenantId,
          msg.channel,
          channelName,
          isDM,
          isThread,
          msg.user,
          'no_answer_generated',
          fallbackMessage
        );

        return { success: true, answer: fallbackMessage, response: null };
      }
    } else {
      // No race mode - just run slow streaming without progress bar
      const slowResult = await runSlowStreaming();
      if (slowResult && slowResult.answer) {
        finalAnswerData = slowResult;
      }

      if (!finalAnswerData) {
        // Need phrases for fallback message
        const fallbackPhrases = useProgressBar
          ? (await phrasesPromise).phrases
          : DEFAULT_PHRASES_EN;

        logger.warn(`${contextType}: No answer generated, using fallback message`, {
          tenantId: tenantSlackApp.tenantId,
          userId: msg.user,
          channelId: msg.channel,
          messageTs: msg.ts,
          threadTs,
          operation: `${contextType}-fallback`,
        });

        const fallbackMessage = getFallbackAnswer(fallbackPhrases);

        await tenantSlackApp.sendResponse(
          msg.channel,
          msg.ts,
          fallbackMessage,
          msg.text || '',
          msg.user,
          finalThreadTs,
          isDM,
          undefined,
          false,
          undefined,
          {
            replaceMessageTs: preliminaryMessageTs,
            skipAnalytics: true,
            skipFeedback: true,
            skipMirroring: true,
          }
        );

        const analyticsTracker = getAnalyticsTracker();
        const channelName = await tenantSlackApp.getChannelName(msg.channel);
        const isThread = !!(contextType !== 'dm' && finalThreadTs && finalThreadTs !== msg.ts);
        await analyticsTracker.trackQuestionFallback(
          tenantSlackApp.tenantId,
          msg.channel,
          channelName,
          isDM,
          isThread,
          msg.user,
          'no_answer_generated',
          fallbackMessage
        );

        return { success: true, answer: fallbackMessage, response: null };
      }
    }

    const messageExists = await validateMessageExistsOrCleanup(
      tenantSlackApp,
      msg,
      contextType,
      threadTs
    );

    if (!messageExists) {
      return { success: false };
    }

    let replaceMessageTs: string | undefined;
    let responseBody = finalAnswerData.answer;
    let finalConfidence = finalAnswerData.confidence;
    let finalConfidenceExplanation = finalAnswerData.confidenceExplanation;
    let judgmentApplied = false;

    if (useRace && preliminaryMessageTs && preliminaryAnswerData && preliminaryAnswerData.answer) {
      const fastBody = stripDisplayedConfidence(preliminaryAnswerData.answer);
      const slowBody = stripDisplayedConfidence(finalAnswerData.answer);
      const judgment = await tenantSlackApp.judgeFastVsSlowAnswer(
        msg.channel,
        finalThreadTs,
        msg.ts,
        fastBody,
        preliminaryAnswerData.confidence,
        slowBody,
        finalConfidence,
        finalConfidenceExplanation,
        finalAnswerData.responseId,
        msg.user,
        permissionAudience
      );

      finalConfidence = judgment.confidence ?? finalConfidence;
      finalConfidenceExplanation = judgment.confidenceExplanation ?? finalConfidenceExplanation;

      if (judgment.action === 'no_update') {
        const finalNoUpdateAnswer = appendDisplayedConfidence(
          judgment.finalAnswer,
          finalConfidence,
          finalConfidenceExplanation
        );
        await tenantSlackApp.sendResponse(
          msg.channel,
          msg.ts,
          finalNoUpdateAnswer,
          msg.text || '',
          msg.user,
          finalThreadTs,
          isDM,
          finalAnswerData.responseId,
          false,
          finalConfidence,
          {
            replaceMessageTs: preliminaryMessageTs,
          }
        );
        return { success: true, answer: finalNoUpdateAnswer, response: null };
      }

      responseBody = judgment.finalAnswer;
      replaceMessageTs = preliminaryMessageTs;
      judgmentApplied = true;
    }

    let responseText = judgmentApplied
      ? appendDisplayedConfidence(responseBody, finalConfidence, finalConfidenceExplanation)
      : finalAnswerData.answer;

    // Always check thread for new messages before posting (even if judgment was applied)
    // This catches messages posted in the gap between judgment and sending the response
    if (!isDM) {
      responseText = await tenantSlackApp.checkThreadForExistingAnswers(
        msg.channel,
        finalThreadTs,
        msg.ts,
        responseText,
        finalConfidence,
        finalConfidenceExplanation,
        finalAnswerData.responseId,
        msg.user,
        permissionAudience
      );
    }

    // Determine if we should replace the preliminary message
    // If preliminaryMessageTs exists, we sent a fast message in race mode and should always replace it
    // (unless judgment already handled it, which sets replaceMessageTs above)
    if (!replaceMessageTs && preliminaryMessageTs) {
      // preliminaryMessageTs only exists in race mode, so we always replace the fast message
      replaceMessageTs = preliminaryMessageTs;
    }

    await tenantSlackApp.sendResponse(
      msg.channel,
      msg.ts,
      responseText,
      msg.text || '',
      msg.user,
      finalThreadTs,
      isDM,
      finalAnswerData.responseId,
      false,
      finalConfidence,
      {
        replaceMessageTs,
      }
    );

    return { success: true, answer: responseText, response: null };
  } catch (error) {
    return handleProcessingError(
      `process${contextType
        .split('-')
        .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
        .join('')}`,
      error,
      tenantSlackApp,
      msg
    );
  }
}

/**
 * Generate answer for messages that should always be answered (DMs, mentions)
 */
/**
 * Generate answer for regular channel questions (with shouldAnswer check)
 *
 * Returns a `null` answer if the question shouldn't be answered or failed to be answered.
 */
/**
 * Process a direct message (always responds)
 */
export async function processDirectMessage(
  msg: GenericMessageEvent,
  tenantSlackApp: TenantSlackApp
): Promise<{ success: boolean; answer?: string; response?: unknown }> {
  return processAlwaysRespondMessage(
    msg,
    tenantSlackApp,
    'dm',
    [],
    undefined,
    undefined,
    PermissionAudience.Private
  );
}

/**
 * Process DM thread response or @ mention in channel thread (always responds)
 * Adds context from the rest of the thread
 */
export async function processDMThreadOrChannelThreadMention(
  msg: GenericMessageEvent,
  tenantSlackApp: TenantSlackApp,
  linearTeamId?: string
): Promise<{ success: boolean; answer?: string; response?: unknown }> {
  // Get thread context (all messages)
  const { messages: contextMessages, messageElements } = await tenantSlackApp.getThreadContext(
    msg.channel,
    msg.thread_ts as string
  );

  const previousResponseId = await getBotResponseFromThread(
    messageElements,
    tenantSlackApp.botId,
    tenantSlackApp.tenantId
  );

  return processAlwaysRespondMessage(
    msg,
    tenantSlackApp,
    'thread-mention',
    contextMessages,
    previousResponseId ?? undefined,
    msg.thread_ts,
    PermissionAudience.Tenant,
    linearTeamId
  );
}

/**
 * Process a non-thread @mention in a channel (always respond like a DM)
 */
export async function processChannelMention(
  msg: GenericMessageEvent,
  tenantSlackApp: TenantSlackApp,
  linearTeamId?: string
): Promise<{ success: boolean; answer?: string; response?: unknown }> {
  return processAlwaysRespondMessage(
    msg,
    tenantSlackApp,
    'channel-mention',
    [],
    undefined,
    undefined,
    PermissionAudience.Tenant,
    linearTeamId
  );
}

/**
 * Process a channel question (selective response based on AI confidence)
 *
 * KEY BEHAVIORAL DIFFERENCES from direct messages and mentions:
 *
 * 1. SELECTIVE RESPONSE: Only responds if AI classifier determines it's a technical question
 *    the bot can answer confidently. Uses shouldTryToAnswerMessage() for classification.
 *
 * 2. SILENT FAILURE: If no answer can be generated or question isn't suitable, silently
 *    returns success=false without sending any response to avoid channel noise.
 *
 * 3. NO PROCESSING REACTION: Doesn't show "thinking" emoji since user didn't directly
 *    address the bot and we might not respond at all.
 *
 * 4. NO FALLBACK MESSAGE: Never sends "I don't know" responses - either provides a
 *    confident answer or stays silent.
 *
 * This contrasts with processDirectMessage() and processDMThreadOrChannelThreadMention() which ALWAYS
 * respond (with fallback if needed) because the user directly addressed the bot.
 *
 * Note: Silently ignores messages from guest/external users without sending any notifications
 */
export async function processChannelQuestion(
  msg: GenericMessageEvent,
  tenantSlackApp: TenantSlackApp
): Promise<{ success: boolean; answer?: string; response?: unknown }> {
  try {
    const { stats } = await getTenantStateToAnswerQuestions(tenantSlackApp.tenantId);
    const configuredSources = getConfiguredSourceNames(stats);

    const messageText = stripMessageHeader(msg.text || '');

    const { shouldAnswer: shouldAnswerProactively, reasoning } = await shouldTryToAnswerMessage(
      messageText,
      configuredSources
    );

    const env = getGrapevineEnv();
    const logReasoning = env === 'staging' || env === 'local';
    logger.info(
      `Proactive pre-filter decision: ${shouldAnswerProactively}${
        logReasoning ? ` reasoning: ${reasoning}` : ''
      }`,
      { sources: configuredSources }
    );

    if (!shouldAnswerProactively) {
      return { success: false };
    }

    const analyticsTracker = getAnalyticsTracker();
    const channelName = await tenantSlackApp.getChannelName(msg.channel);
    await analyticsTracker.trackProactivePreFilter(
      tenantSlackApp.tenantId,
      msg.channel,
      channelName,
      msg.user
    );

    const useRace = shouldUseAskAgentRace();
    // Fetch threshold early so we can check it before posting fast response
    const confidenceThreshold = await tenantConfigManager.getQaConfidenceThreshold(
      tenantSlackApp.tenantId
    );

    const { fastPromise, runSlow } = await startAskAgentRace(
      msg,
      tenantSlackApp,
      [],
      {
        channelId: msg.channel,
        permissionAudience: PermissionAudience.Tenant,
      },
      useRace
    );

    let preliminaryMessageTs: string | undefined;
    let preliminaryAnswerData: GeneratedAnswer | null = null;
    let finalAnswerData: GeneratedAnswer | null = null;
    let finalVariant: 'fast' | 'slow' | null = null;

    if (useRace && fastPromise) {
      // For proactive responses, always use simple race without progress bar.
      // We don't want to show progress then delete it if the answer doesn't meet threshold.
      const raceResult = await executeAskAgentRace(
        fastPromise,
        runSlow(),
        {
          tenantId: tenantSlackApp.tenantId,
          channelId: msg.channel,
          operation: 'processChannelQuestion',
        },
        async (answer) => {
          // Only post if above confidence threshold
          const fastConfidence = answer.confidence ?? 0;
          if (fastConfidence >= confidenceThreshold) {
            preliminaryMessageTs = await tenantSlackApp.sendResponse(
              msg.channel,
              msg.ts,
              answer.answer,
              msg.text || '',
              msg.user,
              msg.ts,
              false,
              answer.responseId,
              true,
              answer.confidence,
              {
                isPreliminary: true,
              }
            );
          }
        }
      );

      finalAnswerData = raceResult.finalAnswer;
      finalVariant = raceResult.finalVariant;
      preliminaryAnswerData = raceResult.preliminaryAnswer;
    } else {
      // No race mode - just run slow without progress bar
      const slowResult = await runSlow();
      if (slowResult && slowResult.answer) {
        finalAnswerData = slowResult;
        finalVariant = 'slow';
      }
    }

    const initialConfidence = finalAnswerData?.confidence ?? 0;

    if (!finalAnswerData || initialConfidence < confidenceThreshold) {
      logger.info('Answer filtered by quality gate for proactive response', {
        tenantId: tenantSlackApp.tenantId,
        userId: msg.user,
        channelId: msg.channel,
        messageTs: msg.ts,
        questionLength: messageText.length,
        confidenceThreshold,
        answerConfidence: finalAnswerData?.confidence,
        operation: 'proactive-answer-filtered',
      });

      if (preliminaryMessageTs) {
        try {
          await tenantSlackApp.client.chat.delete({
            channel: msg.channel,
            ts: preliminaryMessageTs,
          });
        } catch (deleteError) {
          logger.warn('Failed to delete preliminary message after quality filter', {
            tenantId: tenantSlackApp.tenantId,
            channelId: msg.channel,
            preliminaryMessageTs,
            error: deleteError instanceof Error ? deleteError.message : String(deleteError),
            operation: 'preliminary-delete-failed',
          });
        }
      }

      return { success: false };
    }

    const messageExists = await tenantSlackApp.checkMessageExists(msg.channel, msg.ts);
    if (!messageExists) {
      if (preliminaryMessageTs) {
        try {
          await tenantSlackApp.client.chat.delete({
            channel: msg.channel,
            ts: preliminaryMessageTs,
          });
        } catch {
          // Intentionally ignore delete failure if message already gone
        }
      }
      return { success: false };
    }

    let replaceMessageTs: string | undefined;
    let responseBody = finalAnswerData.answer;
    let finalConfidence = finalAnswerData.confidence;
    let finalConfidenceExplanation = finalAnswerData.confidenceExplanation;
    let judgmentApplied = false;

    if (useRace && preliminaryMessageTs && preliminaryAnswerData && preliminaryAnswerData.answer) {
      const fastBody = stripDisplayedConfidence(preliminaryAnswerData.answer);
      const slowBody = stripDisplayedConfidence(finalAnswerData.answer);
      const judgment = await tenantSlackApp.judgeFastVsSlowAnswer(
        msg.channel,
        msg.ts,
        msg.ts,
        fastBody,
        preliminaryAnswerData.confidence,
        slowBody,
        finalConfidence,
        finalConfidenceExplanation,
        finalAnswerData.responseId,
        msg.user,
        PermissionAudience.Tenant
      );

      finalConfidence = judgment.confidence ?? finalConfidence;
      finalConfidenceExplanation = judgment.confidenceExplanation ?? finalConfidenceExplanation;

      if (judgment.action === 'no_update') {
        const finalNoUpdateAnswer = appendDisplayedConfidence(
          judgment.finalAnswer,
          finalConfidence,
          finalConfidenceExplanation
        );
        await tenantSlackApp.sendResponse(
          msg.channel,
          msg.ts,
          finalNoUpdateAnswer,
          msg.text || '',
          msg.user,
          msg.ts,
          false,
          finalAnswerData.responseId,
          true,
          finalConfidence,
          {
            replaceMessageTs: preliminaryMessageTs,
          }
        );
        return { success: true, answer: finalNoUpdateAnswer, response: null };
      }

      responseBody = judgment.finalAnswer;
      replaceMessageTs = preliminaryMessageTs;
      judgmentApplied = true;
    }

    let responseText = judgmentApplied
      ? appendDisplayedConfidence(responseBody, finalConfidence, finalConfidenceExplanation)
      : finalAnswerData.answer;

    // Always check thread for new messages before posting (even if judgment was applied)
    // This catches messages posted in the gap between judgment and sending the response
    responseText = await tenantSlackApp.checkThreadForExistingAnswers(
      msg.channel,
      msg.ts,
      msg.ts,
      responseText,
      finalConfidence,
      finalConfidenceExplanation,
      finalAnswerData.responseId,
      msg.user,
      PermissionAudience.Tenant
    );

    const finalBehavior = config.finalAnswerBehavior;
    if (!replaceMessageTs && preliminaryMessageTs) {
      if (judgmentApplied) {
        replaceMessageTs = preliminaryMessageTs;
      } else if (finalVariant === 'fast') {
        replaceMessageTs = preliminaryMessageTs;
      } else if (finalBehavior === 'replace') {
        replaceMessageTs = preliminaryMessageTs;
      }
    }

    await tenantSlackApp.sendResponse(
      msg.channel,
      msg.ts,
      responseText,
      msg.text || '',
      msg.user,
      msg.ts,
      false,
      finalAnswerData.responseId,
      true,
      finalConfidence,
      {
        replaceMessageTs,
      }
    );

    return { success: true, answer: responseText, response: null };
  } catch (error) {
    const errorResult = handleError('processChannelQuestion', error, { fallbackValue: {} });
    return {
      success: false,
      ...(typeof errorResult === 'object' && errorResult !== null ? errorResult : {}),
    };
  }
}
