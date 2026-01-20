import { BackendAnalyticsService, getAnalyticsService } from '@corporate-context/backend-common';
import { logger } from '../utils/logger';

/**
 * Slack bot-specific analytics tracking service
 */
class SlackBotAnalyticsTracker {
  private analyticsService: BackendAnalyticsService;

  constructor() {
    this.analyticsService = getAnalyticsService();
  }

  /**
   * Track when the bot answers a question
   */
  async trackQuestionAnswered(
    tenantId: string,
    responseTs: string,
    channelId: string,
    channelName: string,
    isDM: boolean,
    isThread: boolean,
    slackUserId: string,
    isProactive: boolean,
    confidence?: number,
    responseVariant: 'preliminary' | 'final' = 'final'
  ): Promise<void> {
    try {
      await this.analyticsService.trackEvent('slack_question_answered', {
        tenant_id: tenantId,
        response_ts: responseTs,
        channel_name: channelName,
        channel_id: channelId,
        is_dm: isDM,
        is_thread: isThread,
        slack_user_id: slackUserId,
        is_proactive: isProactive,
        confidence,
        response_variant: responseVariant,
      });

      logger.debug('Tracked question answered event', {
        tenantId,
        responseTs,
        channelId,
        channelName,
        isDM,
        isThread,
        slackUserId,
        isProactive,
        confidence,
        responseVariant,
        operation: 'analytics-question-answered',
      });
    } catch (error) {
      logger.error(
        'Error tracking question answered event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          responseTs,
          channelId,
          operation: 'analytics-question-answered-error',
        }
      );
    }
  }

  /**
   * Track when the bot sends a fallback response instead of answering
   */
  async trackQuestionFallback(
    tenantId: string,
    channelId: string,
    channelName: string,
    isDM: boolean,
    isThread: boolean,
    slackUserId: string,
    fallbackReason: 'insufficient_data' | 'processing' | 'no_answer_generated' | 'error',
    fallbackMessage?: string
  ): Promise<void> {
    try {
      await this.analyticsService.trackEvent('slack_question_fallback', {
        tenant_id: tenantId,
        channel_name: channelName,
        channel_id: channelId,
        is_dm: isDM,
        is_thread: isThread,
        slack_user_id: slackUserId,
        fallback_reason: fallbackReason,
        fallback_message: fallbackMessage,
      });

      logger.debug('Tracked question fallback event', {
        tenantId,
        channelId,
        channelName,
        isDM,
        isThread,
        slackUserId,
        fallbackReason,
        operation: 'analytics-question-fallback',
      });
    } catch (error) {
      logger.error(
        'Error tracking question fallback event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          channelId,
          fallbackReason,
          operation: 'analytics-question-fallback-error',
        }
      );
    }
  }

  /**
   * Track when a user reacts to a bot response
   */
  async trackUserReaction(
    tenantId: string,
    reaction: string,
    responseTs: string,
    channelId: string,
    channelName: string,
    userId: string
  ): Promise<void> {
    try {
      const normalizedReaction = reaction.split('::')[0];

      await this.analyticsService.trackEvent('slack_user_reaction_added', {
        tenant_id: tenantId,
        reaction,
        normalized_reaction: normalizedReaction,
        response_ts: responseTs,
        channel_name: channelName,
        channel_id: channelId,
        user_id: userId,
      });

      logger.debug('Tracked user reaction event', {
        tenantId,
        reaction,
        responseTs,
        channelId,
        channelName,
        userId,
        operation: 'analytics-user-reaction',
      });
    } catch (error) {
      logger.error(
        'Error tracking user reaction event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          reaction,
          responseTs,
          channelId,
          userId,
          operation: 'analytics-user-reaction-error',
        }
      );
    }
  }

  /**
   * Track when a user provides feedback via interactive buttons
   */
  async trackUserFeedback(
    tenantId: string,
    feedbackType: 'positive' | 'negative',
    responseTs: string,
    channelId: string,
    channelName: string,
    userId: string
  ): Promise<void> {
    try {
      await this.analyticsService.trackEvent('slack_user_feedback_button', {
        tenant_id: tenantId,
        feedback_type: feedbackType,
        response_ts: responseTs,
        channel_name: channelName,
        channel_id: channelId,
        user_id: userId,
      });

      logger.debug('Tracked user feedback event', {
        tenantId,
        feedbackType,
        responseTs,
        channelId,
        channelName,
        userId,
        operation: 'analytics-user-feedback',
      });
    } catch (error) {
      logger.error(
        'Error tracking user feedback event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          feedbackType,
          responseTs,
          channelId,
          userId,
          operation: 'analytics-user-feedback-error',
        }
      );
    }
  }

  /**
   * Track when a welcome message is sent to a user
   */
  async trackWelcomeMessageSent(tenantId: string, installerUserId: string): Promise<void> {
    try {
      await this.analyticsService.trackEvent('slack_welcome_message_sent', {
        tenant_id: tenantId,
        installer_user_id: installerUserId,
      });

      logger.debug('Tracked welcome message sent event', {
        tenantId,
        installerUserId,
        operation: 'analytics-welcome-message-sent',
      });
    } catch (error) {
      logger.error(
        'Error tracking welcome message sent event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          installerUserId,
          operation: 'analytics-welcome-message-sent-error',
        }
      );
    }
  }

  /**
   * Track when a message passes the proactive pre-filter
   */
  async trackProactivePreFilter(
    tenantId: string,
    channelId: string,
    channelName: string,
    slackUserId: string
  ): Promise<void> {
    try {
      await this.analyticsService.trackEvent('slack_proactive_prefilter', {
        tenant_id: tenantId,
        channel_id: channelId,
        channel_name: channelName,
        slack_user_id: slackUserId,
      });

      logger.debug('Tracked proactive pre-filter event', {
        tenantId,
        channelId,
        channelName,
        slackUserId,
        operation: 'analytics-proactive-prefilter',
      });
    } catch (error) {
      logger.error(
        'Error tracking proactive pre-filter event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          channelId,
          operation: 'analytics-proactive-prefilter-error',
        }
      );
    }
  }

  /**
   * Track when a user deletes a triage ticket via button
   */
  async trackTriageDeleteTicket(
    tenantId: string,
    channelId: string,
    channelName: string,
    userId: string,
    messageTs: string,
    linearIssueId: string,
    linearIssueUrl: string,
    actionResult: 'success' | 'error'
  ): Promise<void> {
    try {
      await this.analyticsService.trackEvent('slack_triage_delete_ticket', {
        tenant_id: tenantId,
        channel_id: channelId,
        channel_name: channelName,
        user_id: userId,
        message_ts: messageTs,
        linear_issue_id: linearIssueId,
        linear_issue_url: linearIssueUrl,
        action_result: actionResult,
      });

      logger.debug('Tracked triage delete ticket event', {
        tenantId,
        channelId,
        channelName,
        userId,
        messageTs,
        linearIssueId,
        linearIssueUrl,
        actionResult,
        operation: 'analytics-triage-delete-ticket',
      });
    } catch (error) {
      logger.error(
        'Error tracking triage delete ticket event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          channelId,
          userId,
          messageTs,
          linearIssueId,
          operation: 'analytics-triage-delete-ticket-error',
        }
      );
    }
  }

  /**
   * Track when a user undoes a triage update via button
   */
  async trackTriageUndoUpdate(
    tenantId: string,
    channelId: string,
    channelName: string,
    userId: string,
    messageTs: string,
    linearIssueId: string,
    linearIssueUrl: string,
    actionResult: 'success' | 'error'
  ): Promise<void> {
    try {
      await this.analyticsService.trackEvent('slack_triage_undo_update', {
        tenant_id: tenantId,
        channel_id: channelId,
        channel_name: channelName,
        user_id: userId,
        message_ts: messageTs,
        linear_issue_id: linearIssueId,
        linear_issue_url: linearIssueUrl,
        action_result: actionResult,
      });

      logger.debug('Tracked triage undo update event', {
        tenantId,
        channelId,
        channelName,
        userId,
        messageTs,
        linearIssueId,
        linearIssueUrl,
        actionResult,
        operation: 'analytics-triage-undo-update',
      });
    } catch (error) {
      logger.error(
        'Error tracking triage undo update event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          channelId,
          userId,
          messageTs,
          linearIssueId,
          operation: 'analytics-triage-undo-update-error',
        }
      );
    }
  }

  /**
   * Track when a user provides feedback on triage bot via interactive buttons
   * Only sends to Amplitude (not PostHog)
   */
  async trackTriageFeedback(
    tenantId: string,
    feedbackType: 'positive' | 'negative',
    responseTs: string,
    channelId: string,
    userId: string,
    actionType: string,
    actionStatus: 'executed' | 'suggested'
  ): Promise<void> {
    try {
      await this.analyticsService.trackEventAmplitudeOnly('slack_triage_feedback_button', {
        tenant_id: tenantId,
        feedback_type: feedbackType,
        response_ts: responseTs,
        channel_id: channelId,
        user_id: userId,
        action_type: actionType,
        action_status: actionStatus,
      });

      logger.debug('Tracked triage feedback event (Amplitude only)', {
        tenantId,
        feedbackType,
        responseTs,
        channelId,
        userId,
        actionType,
        actionStatus,
        operation: 'analytics-triage-feedback',
      });
    } catch (error) {
      logger.error(
        'Error tracking triage feedback event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          feedbackType,
          responseTs,
          channelId,
          userId,
          actionType,
          actionStatus,
          operation: 'analytics-triage-feedback-error',
        }
      );
    }
  }

  /**
   * Track when a triage decision is successfully made
   */
  async trackTriageDecisionMade(
    tenantId: string,
    channelId: string,
    channelName: string,
    messageTs: string,
    linearTeamId: string,
    action: 'CREATE' | 'UPDATE' | 'SKIP' | 'REQUEST_CLARIFICATION',
    linearIssueId?: string,
    linearIssueUrl?: string,
    linearIssueTitle?: string
  ): Promise<void> {
    try {
      await this.analyticsService.trackEvent('slack_triage_decision_made', {
        tenant_id: tenantId,
        channel_id: channelId,
        channel_name: channelName,
        message_ts: messageTs,
        linear_team_id: linearTeamId,
        action,
        linear_issue_id: linearIssueId,
        linear_issue_url: linearIssueUrl,
        linear_issue_title: linearIssueTitle,
      });

      logger.debug('Tracked triage decision made event', {
        tenantId,
        channelId,
        channelName,
        messageTs,
        linearTeamId,
        action,
        linearIssueId,
        linearIssueUrl,
        operation: 'analytics-triage-decision-made',
      });
    } catch (error) {
      logger.error(
        'Error tracking triage decision made event',
        error instanceof Error ? error : new Error(String(error)),
        {
          tenantId,
          channelId,
          messageTs,
          action,
          operation: 'analytics-triage-decision-made-error',
        }
      );
    }
  }

  /**
   * Flush pending events (useful for graceful shutdown)
   */
  async flush(): Promise<void> {
    try {
      await this.analyticsService.flush();
    } catch (error) {
      logger.error(
        'Error flushing analytics events',
        error instanceof Error ? error : new Error(String(error)),
        {
          operation: 'analytics-flush-error',
        }
      );
    }
  }
}

// Singleton instance for the Slack bot
let analyticsTracker: SlackBotAnalyticsTracker | null = null;

/**
 * Get the singleton analytics tracker instance
 */
export function getAnalyticsTracker(): SlackBotAnalyticsTracker {
  if (!analyticsTracker) {
    analyticsTracker = new SlackBotAnalyticsTracker();
  }
  return analyticsTracker;
}
