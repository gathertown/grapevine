/**
 * Types for connector management
 */

export type ConnectorStatus = 'pending' | 'active' | 'error' | 'disconnected';

export enum ConnectorType {
  Slack = 'slack',
  GitHub = 'github',
  GitLab = 'gitlab',
  Linear = 'linear',
  Notion = 'notion',
  GoogleDrive = 'google_drive',
  GoogleEmail = 'google_email',
  HubSpot = 'hubspot',
  Salesforce = 'salesforce',
  Jira = 'jira',
  Confluence = 'confluence',
  Gong = 'gong',
  Gather = 'gather',
  Trello = 'trello',
  Zendesk = 'zendesk',
  Asana = 'asana',
  Intercom = 'intercom',
  Snowflake = 'snowflake',
  Attio = 'attio',
  Fireflies = 'fireflies',
  CustomData = 'custom_data',
  Clickup = 'clickup',
  Pylon = 'pylon',
  Monday = 'monday',
  Pipedrive = 'pipedrive',
  Figma = 'figma',
  PostHog = 'posthog',
  Canva = 'canva',
  Teamwork = 'teamwork',
}

export interface Connector {
  id: string;
  tenant_id: string;
  type: ConnectorType;
  external_id: string;
  external_metadata: Record<string, unknown>;
  status: ConnectorStatus;
  created_at: string;
  updated_at: string;
}

export interface CreateConnectorData {
  tenant_id: string;
  type: ConnectorType;
  external_id: string;
  external_metadata?: Record<string, unknown>;
  status?: ConnectorStatus;
}

export interface UpdateConnectorData {
  status?: ConnectorStatus;
  external_metadata?: Record<string, unknown>;
}
