import type { ReactNode } from 'react';
import { Badge } from '@gathertown/gather-design-system';
import { HomePageSubtitle } from '../components/HomePageSubtitle';

interface RouteConfig {
  title: string;
  subtitle?: string | ReactNode;
}

export const routeConfig: Record<string, RouteConfig> = {
  '/': {
    title: 'Welcome to Grapevine!',
    subtitle: <HomePageSubtitle />,
  },
  '/stats': {
    title: 'Bot Q&A statistics',
    subtitle: 'View all questions answered by the bot and user reactions',
  },
  '/integrations': {
    title: 'Integrations',
    subtitle: (
      <Badge color="accent" text="We highly recommend at least 3 for Grapevine to be effective" />
    ),
  },
  '/slackbot': {
    title: 'SlackBot',
    subtitle:
      'Set up a SlackBot that continuously learns and is easily accessible from any channel',
  },
  '/apps/triage': {
    title: 'Triage',
    subtitle: 'Automatically create and update Linear issues from Slack bug reports',
  },
  '/billing': {
    title: 'Billing',
    subtitle: 'Manage your subscription and payment methods',
  },
  '/api-keys': {
    title: 'API Keys',
    subtitle: 'Create and manage API keys for programmatic access',
  },
  '/organization-settings': {
    title: 'General settings',
    subtitle: 'Configure organization preferences and settings',
  },
  '/invite': {
    title: 'Invite admins',
    subtitle: 'Add team members as administrators for your Grapevine workspace',
  },
  '/github-redirect': {
    title: 'GitHub setup',
    subtitle: 'Setting up your GitHub integration',
  },
  '/prototype/sample-questions': {
    title: 'Sample Questions',
    subtitle: 'View answered questions and top unanswered questions from your data sources',
  },
  '/webhooks': {
    title: 'Webhook Subscriptions',
    subtitle: 'Manage webhook subscriptions for document change notifications',
  },
  '/apps/ask-grapevine': {
    title: 'Slackbot',
    subtitle: 'View slackbot settings and stats',
  },
  '/eval-capture': {
    title: 'Exponent Eval Capture',
    subtitle: 'Capture real documents + Linear state as eval test cases',
  },
  '/apps/reviewer': {
    title: 'Reviewer',
    subtitle: 'View feedback on Grapevine PR review comments',
  },
};

export const getRouteConfig = (pathname: string): RouteConfig | null => {
  return routeConfig[pathname] || null;
};
