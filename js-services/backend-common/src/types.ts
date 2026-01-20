/**
 * Common types shared across services
 */
import { z } from 'zod';

/**
 * External sources that can be ingested for backfill notifications.
 * This should be kept in sync with the Python ExternalSource enum!
 */
export const ExternalSourceSchema = z.enum([
  'slack',
  'github',
  'linear',
  'notion',
  'google_drive',
  'google_email',
  'salesforce',
  'hubspot',
  'jira',
  'custom_data',
  'gong',
  'gather',
  'zendesk',
  'trello',
  'asana',
  'attio',
  'intercom',
  'fireflies',
  'gitlab',
  'pylon',
  'monday',
  'pipedrive',
  'clickup',
  'figma',
  'posthog',
  'canva',
  'teamwork',
]);

export type ExternalSource = z.infer<typeof ExternalSourceSchema>;
