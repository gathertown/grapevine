import type { BaseEventProperties } from './base-types';

// Constant array of all requestable integrations (grouped by functionality)
export const REQUESTABLE_INTEGRATIONS = [
  'Fireflies',
  // Other
  'Zapier',
] as const;

// Type derived from the array above - single source of truth
export type RequestableIntegrationSource = (typeof REQUESTABLE_INTEGRATIONS)[number];

// Central schema for all analytics events shared between frontend and backend
// Add new events here with their specific property types
export interface AnalyticsEventSchema {
  integration_requested: BaseEventProperties & {
    requested_integrations: (RequestableIntegrationSource | string)[];
    freeform_requested_integration?: string;
  };
  admin_invitation_sent: BaseEventProperties & {
    invitation_email_hash: string;
    organization_id?: string;
  };
  admin_invitation_failed: BaseEventProperties & {
    invitation_email_hash: string;
    organization_id?: string;
    error_type: string;
    error_message?: string;
  };
  admin_invitation_revoked: BaseEventProperties & {
    invitation_email_hash: string;
    organization_id?: string;
    invitation_id?: string;
  };
  help_button_clicked: BaseEventProperties & {
    location: string;
  };
  help_email_clicked: BaseEventProperties;
  help_book_call_clicked: BaseEventProperties;
  company_context_updated: BaseEventProperties & {
    context_length: number;
    is_initial_setup?: boolean;
  };
  organization_name_updated: BaseEventProperties & {
    name_length: number;
  };
  data_sharing_toggled: BaseEventProperties & {
    enabled: boolean;
  };
  external_guest_setting_changed: BaseEventProperties & {
    skip_external_guests: boolean;
  };
  skip_mentions_by_non_members_changed: BaseEventProperties & {
    skip_mentions_by_non_members: boolean;
  };
  answer_proactively_setting_changed: BaseEventProperties & {
    proactively_enabled: boolean;
  };
  proactive_channels_allowlist_updated: BaseEventProperties & {
    channels: string[];
    channel_count: number;
  };
  proactive_channels_blocklist_updated: BaseEventProperties & {
    channels: string[];
    channel_count: number;
  };
  proactive_confidence_threshold_changed: BaseEventProperties & {
    confidence_threshold: number;
  };
  slack_question_answered: BaseEventProperties & {
    response_ts: string;
    channel_name: string;
    channel_id: string;
    is_dm: boolean;
    is_thread: boolean;
    slack_user_id: string;
    is_proactive: boolean;
    confidence?: number;
    response_variant: 'preliminary' | 'final';
  };
  slack_user_reaction_added: BaseEventProperties & {
    reaction: string;
    normalized_reaction: string;
    response_ts: string;
    channel_name: string;
    channel_id: string;
    user_id: string;
  };
  slack_user_feedback_button: BaseEventProperties & {
    feedback_type: 'positive' | 'negative';
    response_ts: string;
    channel_name: string;
    channel_id: string;
    user_id: string;
  };
  organization_created: BaseEventProperties & {
    organization_id: string;
    organization_name: string;
  };
  onboarding_survey_completed: BaseEventProperties & {
    company_size: string;
    role: string;
    hdyhau: string;
    problem_to_solve?: string;
  };
  slackbot_setup_complete: BaseEventProperties & {
    bot_name?: string;
    setup_duration_seconds?: number;
  };
  slackbot_disconnected: BaseEventProperties;
  integration_setup_started: BaseEventProperties & {
    integration_type: string;
    total_steps: number;
  };
  integration_step_completed: BaseEventProperties & {
    integration_type: string;
    step_number: number;
    step_title: string;
    total_steps: number;
  };
  integration_configured: BaseEventProperties & {
    integration_type: string;
    setup_duration_seconds: number;
    total_steps: number;
  };
  slack_export_success: BaseEventProperties & {
    file_name: string;
    file_size_mb: number;
    upload_duration_seconds: number;
  };
  slack_question_fallback: BaseEventProperties & {
    channel_name: string;
    channel_id: string;
    is_dm: boolean;
    is_thread: boolean;
    slack_user_id: string;
    fallback_reason: 'insufficient_data' | 'processing' | 'no_answer_generated' | 'error';
    fallback_message?: string;
  };
  slack_welcome_message_sent: BaseEventProperties & {
    installer_user_id: string;
  };
  slack_proactive_prefilter: BaseEventProperties & {
    channel_id: string;
    channel_name: string;
    slack_user_id: string;
  };
  slack_triage_delete_ticket: BaseEventProperties & {
    channel_id: string;
    channel_name: string;
    user_id: string;
    message_ts: string;
    linear_issue_id: string;
    linear_issue_url: string;
    action_result: 'success' | 'error';
  };
  slack_triage_undo_update: BaseEventProperties & {
    channel_id: string;
    channel_name: string;
    user_id: string;
    message_ts: string;
    linear_issue_id: string;
    linear_issue_url: string;
    action_result: 'success' | 'error';
  };
  slack_triage_feedback_button: BaseEventProperties & {
    feedback_type: 'positive' | 'negative';
    response_ts: string;
    channel_id: string;
    user_id: string;
    action_type: string;
    action_status: 'executed' | 'suggested';
  };
  slack_triage_decision_made: BaseEventProperties & {
    channel_id: string;
    channel_name: string;
    message_ts: string;
    linear_team_id: string;
    action: 'CREATE' | 'UPDATE' | 'SKIP' | 'REQUEST_CLARIFICATION';
    linear_issue_id?: string;
    linear_issue_url?: string;
    linear_issue_title?: string;
  };
  integration_alert_modal_viewed: BaseEventProperties & {
    integration_name: string;
    integration_type: string;
    is_coming_soon: boolean;
  };
  integration_alert_modal_setup_clicked: BaseEventProperties & {
    integration_name: string;
    integration_type: string;
    is_coming_soon: boolean;
  };
  triage_bot_page_viewed: BaseEventProperties & {
    has_linear_write_access: boolean;
  };
  triage_bot_enabled: BaseEventProperties;
  triage_bot_mappings_saved: BaseEventProperties & {
    mapping_count: number;
  };
  triage_bot_disconnected: BaseEventProperties;
  triage_bot_proactive_mode_toggled: BaseEventProperties & {
    enabled: boolean;
  };
  // Example of how to add events:
  // 'page_viewed': BaseEventProperties & {
  //   page_name: string;
  //   referrer?: string;
  //   path?: string;
  // };
  // 'element_clicked': BaseEventProperties & {
  //   element_name: string;
  //   element_type?: 'button' | 'link' | 'icon';
  //   page?: string;
  //   section?: string;
  // };
  // 'form_submitted': BaseEventProperties & {
  //   form_name: string;
  //   form_type?: 'onboarding' | 'configuration' | 'settings';
  //   success?: boolean;
  //   error_message?: string;
  // };
  // 'data_source_configured': BaseEventProperties & {
  //   source_type: 'github' | 'slack' | 'notion' | 'linear' | 'google_drive' | 'hubspot';
  //   success: boolean;
  //   configuration_method?: 'manual' | 'oauth' | 'api_key';
  //   error_type?: string;
  // };
  // 'onboarding_step_completed': BaseEventProperties & {
  //   step_name: string;
  //   step_number: number;
  //   total_steps: number;
  //   time_spent_seconds?: number;
  // };
  // 'error_occurred': BaseEventProperties & {
  //   error_type: string;
  //   error_message?: string;
  //   component?: string;
  //   stack_trace?: string;
  // };
  // 'user_signed_in': BaseEventProperties & {
  //   method?: 'workos' | 'oauth' | 'email';
  //   organization_id?: string;
  // };
  // 'user_signed_out': BaseEventProperties & {
  //   session_duration_seconds?: number;
  // };
  // 'api_request_completed': BaseEventProperties & {
  //   endpoint: string;
  //   method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  //   status_code: number;
  //   duration_ms: number;
  //   success: boolean;
  // };
  // 'search_performed': BaseEventProperties & {
  //   search_type: 'keyword' | 'semantic';
  //   query: string;
  //   results_count: number;
  //   duration_ms: number;
  // };
}

// Extract event names as union type
export type AnalyticsEventName = keyof AnalyticsEventSchema;

// Extract properties for specific event
export type AnalyticsEventProperties<T extends AnalyticsEventName> = AnalyticsEventSchema[T];
