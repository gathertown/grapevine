import { SLACK_NAME_CHAR_LIMIT } from './constants';

export interface FieldValidator {
  validate: (value: string) => boolean;
  transform?: (value: string) => string;
  errorMessage: string;
}

export const fieldValidators = {
  companyName: {
    validate: (value: string): boolean => value.trim().length > 0,
    transform: (value: string): string => value.trim(),
    errorMessage: 'Company name is required',
  },

  companyDomain: {
    validate: (value: string): boolean => {
      const trimmed = value.trim();
      return trimmed.length > 0 && trimmed.includes('.');
    },
    transform: (value: string): string => value.trim(),
    errorMessage: 'Please enter a valid domain (e.g., example.com)',
  },

  // Slack-specific validators
  slackBotName: {
    validate: (value: string): boolean => {
      const trimmed = value.trim();
      if (trimmed.length === 0 || trimmed.length > SLACK_NAME_CHAR_LIMIT) {
        return false;
      }
      // Allow alphanumeric, spaces, hyphens, underscores, and periods
      return /^[a-zA-Z0-9\s\-_.]+$/.test(trimmed);
    },
    transform: (value: string): string => value.trim(),
    errorMessage: `Bot name is required, must be ${SLACK_NAME_CHAR_LIMIT} characters or less, and contain only letters, numbers, spaces, hyphens, underscores, and periods`,
  },

  slackSigningSecret: {
    validate: (value: string): boolean => /^[a-fA-F0-9]{32}$/.test(value.trim()),
    transform: (value: string): string => value.trim(),
    errorMessage: 'Please enter a valid 32-character hex signing secret',
  },

  slackBotToken: {
    validate: (value: string): boolean => {
      const trimmed = value.trim();
      return trimmed.startsWith('xoxb-') && trimmed.length > 10;
    },
    transform: (value: string): string => value.trim(),
    errorMessage: 'Please enter a valid bot user OAuth token (starts with "xoxb-")',
  },

  proactiveAnswering: {
    validate: (value: string): boolean => value === 'true' || value === 'false',
    transform: (value: string): string => value.trim(),
    errorMessage: 'Please select Yes or No',
  },
  slackClientId: {
    validate: (value: string): boolean => {
      // Client IDs are typically numeric strings in format: XXXXXXXXX.XXXXXXXXX
      return /^\d+\.\d+$/.test(value.trim());
    },
    transform: (value: string): string => value.trim(),
    errorMessage: 'Please enter a valid Slack Client ID (format: XXXXXXXXX.XXXXXXXXX)',
  },

  slackClientSecret: {
    validate: (value: string): boolean => {
      // Client secrets are alphanumeric strings, typically 32+ characters
      const trimmed = value.trim();
      return /^[a-zA-Z0-9]+$/.test(trimmed) && trimmed.length >= 32;
    },
    transform: (value: string): string => value.trim(),
    errorMessage: 'Please enter a valid Slack Client Secret (32+ alphanumeric characters)',
  },
};
