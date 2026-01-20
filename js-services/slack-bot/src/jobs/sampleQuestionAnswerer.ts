/**
 * Sample Question Answerer
 *
 * Processes the highest scoring unanswered sample questions by attempting to generate
 * answers and evaluating their quality. Implements the following flow:
 * 1. Pull highest scoring unanswered question
 * 2. Check if it's worth answering (shouldTryToAnswerMessage)
 * 3. Generate answer (generateAnswerCore or makeBackendRequest)
 * 4. Evaluate answer quality (isGoodAnswerToQuestion)
 * 5. Store good answers or decrement score for poor ones, this gives high-potential questions multiple potential rounds (with the assumption that a bad answer might sometimes be due to not having the right data ingested)
 */

import { SampleQuestionsDAL } from '@corporate-context/backend-common';
import { logger } from '../utils/logger';
import {
  shouldTryToAnswerMessage,
  makeBackendRequest,
  isGoodAnswerToQuestion,
  handleError,
  getConfiguredSourceNames,
} from '../common';
import { PermissionAudience } from '../types';
import { getSlackMessageStorage } from '../services/slackMessageStorage';
import { tenantDbConnectionManager } from '../config/tenantDbConnectionManager';
import { tenantConfigManager } from '../config/tenantConfigManager';
import type { TenantSlackApp } from '../TenantSlackApp';
import { Pool } from 'pg';
import { SampleQuestionWithAnswers } from '@corporate-context/backend-common';

// Constants for confidence scoring
const CONFIDENCE_GOOD_ANSWER_THRESHOLD = 0.7; // Minimum confidence to consider an answer "good"
const CONFIDENCE_DEFAULT_SCORE = 0.75; // Default confidence score for stored answers (slightly above threshold)
const GOOD_QUESTIONS_NEEDED_COUNT = 3;

// Constants for parallel processing
const MAX_SAMPLE_QUESTIONS_TO_ASK_IN_PARALLEL = process.env.ENABLE_SAMPLE_ANSWER_PARALLELIZATION
  ? 5
  : 1; // Maximum number of questions to process simultaneously

// Constants for citation requirements
const REQUIRED_CITATION_SOURCE_COUNT = 2; // Minimum number of unique citations required

export interface SampleQuestionAnswererResult {
  shouldContinue: boolean;
  reason: 'no_questions' | 'good_answer_created' | 'max_answers_reached' | 'processed';
  goodAnswersCount?: number;
}

/**
 * Send a success notification DM to the Slack installer with all generated Q&A pairs
 */
export async function sendInstallerSuccessNotification(
  tenantId: string,
  tenantSlackApp: TenantSlackApp
): Promise<void> {
  try {
    // Get the installer user ID and bot name from tenant config
    const [installerUserId, botName] = await Promise.all([
      tenantConfigManager.getSlackInstallerUserId(tenantId),
      tenantConfigManager.getSlackBotName(tenantId),
    ]);

    if (!installerUserId) {
      logger.warn('No Slack installer user ID found - skipping success notification', {
        tenantId,
        operation: 'sample-question-answerer-no-installer-id',
      });
      return;
    }

    // Get all good sample questions with their answers
    const pool = await tenantDbConnectionManager.get(tenantId);
    if (!pool) {
      logger.error('No database connection available for installer notification', {
        tenantId,
        operation: 'sample-question-answerer-installer-notification-db-error',
      });
      return;
    }

    const [goodQuestions, sourceCount] = await Promise.all([
      SampleQuestionsDAL.getSampleQuestionsWithAnswers(pool, GOOD_QUESTIONS_NEEDED_COUNT),
      getSourceCount(pool),
    ]);

    if (goodQuestions.length === 0) {
      logger.warn('No questions with answers found for installer notification', {
        tenantId,
        operation: 'sample-question-answerer-installer-notification-no-questions',
      });
      return;
    }

    // Open DM channel with installer
    const dmChannelResponse = await tenantSlackApp.client.conversations.open({
      users: installerUserId,
    });

    if (!dmChannelResponse.channel?.id) {
      logger.error('Failed to open DM channel with installer', {
        tenantId,
        installerUserId,
        operation: 'sample-question-answerer-installer-dm-failed',
      });
      return;
    }

    const channelId = dmChannelResponse.channel.id;

    // Get workspace domain once for all questions
    let workspaceDomain: string | undefined;
    try {
      const workspaceInfo = await tenantSlackApp.client.team.info();
      workspaceDomain = workspaceInfo.team?.domain;
    } catch (_error) {
      logger.warn('Failed to get workspace domain for question links', {
        tenantId,
        operation: 'sample-question-answerer-workspace-domain-error',
      });
    }

    // Pre-construct all thread messages
    const threadMessages: string[] = [];

    // Build thread messages in advance (goodQuestions already limited to 3)
    for (let i = 0; i < goodQuestions.length; i++) {
      const question = goodQuestions[i];

      // Construct Slack message link if this is from Slack and we have workspace domain
      let questionLink = '';
      if (question.source === 'slack' && question.source_id && workspaceDomain) {
        // Slack source_id format is typically "channel_id:message_ts"
        const channelId = question.metadata.channel_id;
        const messageTs = question.source_id;
        questionLink = `https://${workspaceDomain}.slack.com/archives/${channelId}/p${messageTs.replace('.', '')}`;
      }

      // Parse user references from <@U040B2T929W|@Sam> to <@U040B2T929W>
      const parseUserReferences = (text: string): string => {
        return text.replace(/<@([^|>]+)\|[^>]*>/g, '<@$1>');
      };

      threadMessages.push(`*Question #${i + 1}:*

💬 (<${questionLink}|source>)
${parseUserReferences(question.question_text)
  .split('\n')
  .map((line) => `> ${line}`)
  .join('\n')}

🤖 Grapevine's Answer:
${parseUserReferences(question.answer_text)
  .split('\n')
  .map((line) => `> ${line}`)
  .join('\n')}`);
    }

    // Send main welcome message
    const sourceText =
      sourceCount > 0 ? `${sourceCount} source${sourceCount === 1 ? '' : 's'}` : 'your sources';
    const mainMessage = `Hi <@${installerUserId}>, thanks for setting up Grapevine! ${botName || 'Your bot'} is ready! 🎉

You and your colleagues can ask questions here, or any channels (just tag me), I'll answer with citations from across your sources.

Here's 3 examples of what we can do with ${sourceText} - add more to get better answers! 🧵 👇`;

    const mainMessageResponse = await tenantSlackApp.postMessage({
      channel: channelId,
      text: mainMessage,
    });

    if (!mainMessageResponse.ts) {
      logger.error('Failed to get timestamp from main message', {
        tenantId,
        installerUserId,
        operation: 'sample-question-answerer-main-message-no-ts',
      });
      return;
    }

    // Send all pre-constructed thread messages quickly
    // Send messages sequentially to maintain order
    for (const threadMessage of threadMessages) {
      await tenantSlackApp.postMessage({
        channel: channelId,
        thread_ts: mainMessageResponse.ts,
        text: threadMessage,
      });
    }

    // Save config value to indicate DM was sent
    const configSaved = await tenantConfigManager.setConfigValue(
      'SLACK_INSTALLER_DM_SENT',
      new Date().toISOString(),
      tenantId
    );

    logger.info('Successfully sent installer success notification', {
      tenantId,
      installerUserId,
      botName,
      questionsShown: threadMessages.length,
      configSaved,
      operation: 'sample-question-answerer-installer-notification-sent',
    });
  } catch (error) {
    logger.error('Failed to send installer success notification', error, {
      tenantId,
      operation: 'sample-question-answerer-installer-notification-error',
    });
    // Don't throw error - this is a nice-to-have feature and shouldn't break the main flow
  }
}

/**
 * Process a single sample question - shared logic for both single and parallel processing
 */
async function processSingleSampleQuestion(
  pool: Pool,
  tenantId: string,
  question: SampleQuestionWithAnswers
): Promise<{ success: boolean; reason: string; goodAnswersCount?: number }> {
  logger.info('Processing sample question', {
    tenantId,
    questionId: question.id,
    questionText: question.question_text.substring(0, 100),
    currentScore: question.score,
    operation: 'sample-question-answerer-start',
  });

  // Get configured sources for the tenant
  const storage = getSlackMessageStorage();
  const stats = await storage.getSourcesStats(tenantId);
  const configuredSources = getConfiguredSourceNames(stats);

  // Step 1: Check if this question is worth answering
  const { shouldAnswer, reasoning } = await shouldTryToAnswerMessage(
    question.question_text,
    configuredSources
  );

  if (!shouldAnswer) {
    logger.info('Question failed shouldTryToAnswerMessage check - deleting', {
      tenantId,
      questionId: question.id,
      questionText: question.question_text.substring(0, 100),
      reasoning,
      operation: 'sample-question-answerer-delete-bad-question',
    });

    const deleted = await SampleQuestionsDAL.deleteSampleQuestion(pool, question.id);
    if (!deleted) {
      logger.warn('Failed to delete bad question', {
        tenantId,
        questionId: question.id,
        operation: 'sample-question-answerer-delete-failed',
      });
    }
    return { success: false, reason: 'shouldTryToAnswerMessage check failed' };
  }

  // Step 2: Generate answer using backend request
  logger.info('Generating answer for sample question', {
    tenantId,
    questionId: question.id,
    operation: 'sample-question-answerer-generating',
  });

  const result = await makeBackendRequest(
    tenantId,
    question.question_text,
    undefined, // no user email for sample questions
    undefined, // no files
    undefined, // no previous response id
    PermissionAudience.Tenant, // sample questions use public audience policy
    true // sample questions are non-billable
  );

  if (!result || !result.answer) {
    logger.warn('Failed to generate answer - decrementing score', {
      tenantId,
      questionId: question.id,
      currentScore: question.score,
      operation: 'sample-question-answerer-no-answer',
    });

    await decrementScoreOrDelete(pool, question, tenantId);
    return { success: false, reason: 'failed to generate answer' };
  }

  // Step 3: Check if answer has enough citations
  if (!hasEnoughCitations(result.answer)) {
    logger.info('Answer lacks sufficient citations - decrementing score', {
      tenantId,
      questionId: question.id,
      citationCount: countUniqueCitations(result.answer),
      requiredCitations: REQUIRED_CITATION_SOURCE_COUNT,
      operation: 'sample-question-answerer-insufficient-citations',
    });

    await decrementScoreOrDelete(pool, question, tenantId);
    return { success: false, reason: 'insufficient citations' };
  }

  // Step 4: Evaluate answer quality
  logger.info('Evaluating answer quality', {
    tenantId,
    questionId: question.id,
    answerLength: result.answer.length,
    citationCount: countUniqueCitations(result.answer),
    operation: 'sample-question-answerer-evaluating',
  });

  // TODO: ideally we'd use confidence score (similar to proactivity) instead of this old logic
  // See AIVP-613 for context
  const isGoodAnswer = await isGoodAnswerToQuestion(question.question_text, result.answer);

  if (isGoodAnswer) {
    // Step 4a: Store good answer
    logger.info('Answer quality approved - storing sample answer', {
      tenantId,
      questionId: question.id,
      answerLength: result.answer.length,
      operation: 'sample-question-answerer-storing-answer',
    });

    const stored = await SampleQuestionsDAL.storeSampleAnswer(
      pool,
      question.id,
      result.answer,
      CONFIDENCE_DEFAULT_SCORE,
      { response_id: result.response_id } // store response_id in source_documents
    );

    if (stored) {
      logger.info('Successfully stored sample answer', {
        tenantId,
        questionId: question.id,
        operation: 'sample-question-answerer-success',
      });

      return { success: true, reason: 'good answer stored' };
    } else {
      logger.error('Failed to store sample answer', {
        tenantId,
        questionId: question.id,
        operation: 'sample-question-answerer-store-failed',
      });
      return { success: false, reason: 'failed to store answer' };
    }
  } else {
    // Step 4b: Decrement score for poor answer
    logger.info('Answer quality rejected - decrementing score', {
      tenantId,
      questionId: question.id,
      currentScore: question.score,
      answer: result.answer.substring(0, 256),
      answerLength: result.answer.length,
      operation: 'sample-question-answerer-poor-answer',
    });

    await decrementScoreOrDelete(pool, question, tenantId);
    return { success: false, reason: 'poor answer quality' };
  }
}

/**
 * Process a single sample question for a tenant
 */
export async function processSampleQuestionAnswerer(
  tenantId: string
): Promise<SampleQuestionAnswererResult> {
  logger.info(`Processing sample question answerer for tenant: ${tenantId}`);

  try {
    // Check if installer DM was already sent - if so, stop processing
    const installerDmSent = await tenantConfigManager.getConfigValue(
      'SLACK_INSTALLER_DM_SENT',
      tenantId
    );

    if (installerDmSent) {
      logger.info('Installer DM already sent - skipping sample question processing', {
        tenantId,
        dmSentAt: installerDmSent,
        operation: 'sample-question-answerer-already-completed',
      });
      return { shouldContinue: false, reason: 'processed' };
    }

    const pool = await tenantDbConnectionManager.get(tenantId);
    if (!pool) {
      logger.error('No database connection available for tenant', {
        tenantId,
        operation: 'sample-question-answerer-db-error',
      });
      return { shouldContinue: false, reason: 'processed' };
    }

    // First check if we already have enough good answers (>= 5)
    const goodAnswersCount = await getGoodAnswersCount(pool);
    if (goodAnswersCount >= 5) {
      logger.info('Already have sufficient good answers - stopping', {
        tenantId,
        goodAnswersCount,
        operation: 'sample-question-answerer-sufficient-answers',
      });

      return { shouldContinue: false, reason: 'max_answers_reached', goodAnswersCount };
    }

    // Step 1: Get the highest scoring unanswered questions for parallel processing
    const questions = await SampleQuestionsDAL.getSampleQuestions(pool, {
      answered: false,
      limit: MAX_SAMPLE_QUESTIONS_TO_ASK_IN_PARALLEL,
    });

    if (questions.length === 0) {
      // If there are no unanswered questions, we should continue, because
      // new questions may be added later
      logger.info('No unanswered sample questions found', {
        tenantId,
        operation: 'sample-question-answerer-no-questions',
      });
      return { shouldContinue: true, reason: 'no_questions' };
    }

    logger.info(`Processing ${questions.length} sample questions in parallel`, {
      tenantId,
      questionCount: questions.length,
      maxParallel: MAX_SAMPLE_QUESTIONS_TO_ASK_IN_PARALLEL,
      operation: 'sample-question-answerer-parallel-start',
    });

    // Step 2: Process all questions in parallel
    const results = await Promise.all(
      questions.map((question) => processSingleSampleQuestion(pool, tenantId, question))
    );

    // Step 3: Count successful results
    const successfulResults = results.filter(
      (result: { success: boolean; reason: string; goodAnswersCount?: number }) => result.success
    );
    const goodAnswersCreated = successfulResults.length;

    logger.info('Parallel question processing completed', {
      tenantId,
      totalProcessed: questions.length,
      successful: goodAnswersCreated,
      failed: questions.length - goodAnswersCreated,
      operation: 'sample-question-answerer-parallel-completed',
    });

    // Step 4: Check if we now have enough good answers after processing batch
    const updatedGoodAnswersCount = await getGoodAnswersCount(pool);
    if (updatedGoodAnswersCount >= GOOD_QUESTIONS_NEEDED_COUNT) {
      logger.info('Reached target number of good answers after parallel processing', {
        tenantId,
        goodAnswersCount: updatedGoodAnswersCount,
        operation: 'sample-question-answerer-target-reached',
      });

      return {
        shouldContinue: false,
        reason: 'max_answers_reached',
        goodAnswersCount: updatedGoodAnswersCount,
      };
    }

    // Continue processing if we haven't reached the target
    if (goodAnswersCreated > 0) {
      return {
        shouldContinue: true,
        reason: 'good_answer_created',
        goodAnswersCount: updatedGoodAnswersCount,
      };
    } else {
      return { shouldContinue: true, reason: 'processed' };
    }
  } catch (error) {
    handleError('processSampleQuestionAnswerer', error, {
      level: 'error',
      tenantId,
      operation: 'sample-question-answerer-error',
    });
    return { shouldContinue: true, reason: 'processed' };
  }
}

/**
 * Decrement question score by 1.0, or delete if score would be <= 0
 */
async function decrementScoreOrDelete(
  pool: import('pg').Pool,
  question: { id: string; score: number; question_text: string },
  tenantId: string
): Promise<void> {
  const newScore = question.score - 1.0;

  if (newScore <= 0) {
    logger.info('Score would be <= 0 - deleting question', {
      tenantId,
      questionId: question.id,
      currentScore: question.score,
      newScore,
      operation: 'sample-question-answerer-delete-low-score',
    });

    const deleted = await SampleQuestionsDAL.deleteSampleQuestion(pool, question.id);
    if (!deleted) {
      logger.warn('Failed to delete low-score question', {
        tenantId,
        questionId: question.id,
        operation: 'sample-question-answerer-delete-failed',
      });
    }
  } else {
    logger.info('Decrementing question score', {
      tenantId,
      questionId: question.id,
      currentScore: question.score,
      newScore,
      operation: 'sample-question-answerer-decrement-score',
    });

    const updated = await SampleQuestionsDAL.updateSampleQuestionScore(pool, question.id, newScore);
    if (!updated) {
      logger.warn('Failed to update question score', {
        tenantId,
        questionId: question.id,
        newScore,
        operation: 'sample-question-answerer-update-failed',
      });
    }
  }
}

/**
 * Get the count of good sample answers (answers with confidence >= 0.7)
 */
async function getGoodAnswersCount(pool: import('pg').Pool): Promise<number> {
  try {
    const result = await pool.query(
      'SELECT COUNT(*) as count FROM sample_answers WHERE confidence_score >= $1',
      [CONFIDENCE_GOOD_ANSWER_THRESHOLD]
    );
    return parseInt(result.rows[0].count) || 0;
  } catch (error) {
    logger.error('Error getting good answers count', {
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    return 0;
  }
}

/**
 * Get the count of distinct sources from the documents table
 */
async function getSourceCount(pool: import('pg').Pool): Promise<number> {
  try {
    const result = await pool.query('SELECT COUNT(DISTINCT source) as count FROM documents');
    return parseInt(result.rows[0].count) || 0;
  } catch (error) {
    logger.error('Error getting source count', {
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    return 0;
  }
}

/**
 * Count unique citation sources (hosts) in Slack format <url|name>
 */
function countUniqueCitations(text: string): number {
  const citationRegex = /<([^|>]+)\|[^>]*>/g;
  const uniqueHosts = new Set<string>();

  let match;
  while ((match = citationRegex.exec(text)) !== null) {
    try {
      const url = new URL(match[1]);
      uniqueHosts.add(url.hostname);
    } catch {
      // If URL parsing fails, skip this citation
      continue;
    }
  }

  logger.info(
    `Counted unique citation hosts: ${Array.from(uniqueHosts).join('|')} (${uniqueHosts.size} total)`,
    {
      operation: 'count-unique-citations',
    }
  );

  return uniqueHosts.size;
}

/**
 * Check if answer has enough unique citations
 */
function hasEnoughCitations(answer: string): boolean {
  return countUniqueCitations(answer) >= REQUIRED_CITATION_SOURCE_COUNT;
}
