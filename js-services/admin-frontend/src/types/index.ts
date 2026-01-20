// Common type definitions for the frontend application

import React from 'react';
import { ConfigData } from '../api/config';

export interface User {
  id: string;
  email: string;
  firstName?: string;
  lastName?: string;
  organizationId?: string;
  tenantId?: string;
  role?: string;
  permissions?: string[];
  createdAt?: string;
  updatedAt?: string;
}

export interface Organization {
  id: string;
  name: string;
  domain?: string;
  createdAt: string;
  updatedAt: string;
}

export interface CompanyData {
  companyName: string;
}

export interface IconGenerationState {
  isGenerating: boolean;
  generatedIcon: string | null;
  originalIcon: string | null;
  error: string | null;
}

export interface CompletedSteps {
  step1: boolean;
  step2: boolean;
  step3: boolean;
  step4: boolean;
}

export interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  user: User | null;
  organization?: string | null;
  organizationId?: string | null;
  hasOrganization: boolean;
  organizationData?: Organization | null;
  accessToken?: string | null;
  tenantStatus: 'provisioned' | 'pending' | 'error' | null;
  tenantError: string | null;
  isProvisioningComplete: boolean;
  signIn: () => Promise<void>;
  signUp: () => Promise<void>;
  signOut: () => Promise<void>;
  switchToOrganization: (organizationId: string) => Promise<void>;
  getAccessToken: () => Promise<string | null>;
}

export interface InitializingProps {
  error?: string | null;
  message?: string;
  onSignOut?: () => void;
  onRetry?: () => void;
}

export interface SlackExportInfo {
  id: string;
  filename: string;
  uploadedAt: string;
  size: number;
  location?: string;
}

export interface SlackUploadStatus {
  uploading: boolean;
  completed: boolean;
  progress: number;
  filename: string | null;
  error: string | null;
  xhr: XMLHttpRequest | null;
}

export interface UploadContextType {
  uploadStatus: 'idle' | 'uploading' | 'success' | 'error';
  uploadProgress: number;
  uploadError: string | null;
  uploadedFileUrl: string | null;
  resetUpload: () => void;
  slackUploadStatus: SlackUploadStatus;
  slackExports: SlackExportInfo[];
  elapsedTime: number;
  handleSlackUpload: (file: File) => void;
  resetSlackUpload: () => void;
  fetchSlackExports: () => Promise<void>;
}

export interface Integration {
  id: string;
  name: string;
  Icon: (props: { size?: number }) => React.ReactNode;
  state: 'available' | 'connected';
  contentCount?: string;
  rgb: string;
  accessItems: string[];
  comingSoon?: boolean;
  oauth?: boolean;
}

export interface ConnectionStep {
  title: string;
  content:
    | React.ReactNode
    | ((props: {
        inputValue: string;
        onInputChange: (value: string) => void;
        hasError: boolean;
        webhookUrls?: {
          GITHUB: string;
          SLACK: string;
          NOTION: string;
          LINEAR: string;
          GATHER: string;
        };
        onCopyWebhookUrl?: () => void;
        onListenForToken?: () => void;
        isListening?: boolean;
        webhookSecret?: string;
        onCopySecret?: () => void;
        slackBotConfigured?: boolean;
        // Google Drive specific props
        clientId?: string;
        onCopyClientId?: () => void;
        hasClientIdCopied?: boolean;
        onCopyScopesUrl?: () => void;
        hasScopesCopied?: boolean;
        // Slack upload specific props
        slackUploadStatus?: SlackUploadStatus;
        resetSlackUpload?: () => void;
        elapsedTime?: number;
        slackExports?: SlackExportInfo[];
        onFileChange?: (file: File | null) => void;
        // Link click tracking props
        linkClickStates?: Record<string, boolean>;
        onLinkClick?: (linkKey: string) => void;
        // Salesforce specific props
        configData?: ConfigData;
        // Notion setup nonce props
        nonceError?: string | null;
      }) => React.ReactNode);
  completed?: boolean;
  validateInput?: (
    value: string,
    inputValue?: string,
    hasError?: boolean,
    linkClickStates?: Record<string, boolean>,
    hasClientIdCopied?: boolean | string | null,
    hasScopesCopied?: boolean
  ) => boolean;
  requiresInput?: boolean;
  requiresLinkClick?: boolean;
}

export interface SlackBotConfigContextType {
  isConfigured: boolean;
  hasBotToken: boolean;
  hasSigningSecret: boolean;
  isLoading: boolean;
  botTokenPreview: string;
  signingSecretPreview: string;
  // Bot configuration
  botName: string;
  hasBotName: boolean;
  proactivityEnabled: boolean;
  excludedChannels: string;
}

export interface IntegrationsContextType {
  integrations: Integration[];
  connectedIntegrations: Integration[];
  availableIntegrations: Integration[];
  hasConnectedIntegrations: boolean;
  completedDataSourcesCount: number;
  completedSteps: CompletedSteps;
  isInitialized: boolean;
}

export interface TrialStatus {
  isInTrial: boolean;
  trialStartDate: string;
  trialEndDate: string;
  daysRemaining: number;
  hasSubscription: boolean;
}

export interface SubscriptionStatus {
  hasActiveSubscription: boolean;
  subscriptionId: string | null;
  status: string | null;
  currentPeriodStart: string | null;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
  plan: string | null;
  trialStart: string | null;
  trialEnd: string | null;
}

export interface BillingStatusResponse {
  tenantId: string;
  billingMode: 'gather_managed' | 'grapevine_managed';
  trial: TrialStatus;
  subscription: SubscriptionStatus;
  billingRequired: boolean;
  enableBillingUsageUI: boolean;
}

export interface CreateSubscriptionResponse {
  url: string;
}

export interface BillingHealthResponse {
  status: 'ok';
}

export interface PortalSessionResponse {
  url: string;
}

export interface BillingUsageResponse {
  tenantId: string;
  requestsUsed: number;
  requestsAvailable: number;
  tier: string;
  isTrial: boolean;
  isGatherManaged: boolean;
  billingCycleAnchor?: string;
  trialStartAt?: string;
}

export interface ProductLimits {
  maxRequests?: number;
}

export interface BillingProduct {
  id: string;
  stripePriceId: string;
  price: number;
  currency: string;
  interval: 'month' | 'year';
  limits: ProductLimits;
}

export interface ProductsResponse {
  products: BillingProduct[];
}

// Webhook subscription types
export interface WebhookSubscription {
  id: string;
  url: string;
  secret?: string; // Only returned on creation
  active: boolean;
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface CreateWebhookRequest {
  url: string;
}

export interface UpdateWebhookRequest {
  url?: string;
  active?: boolean;
}

export interface WebhookSubscriptionsResponse {
  subscriptions: WebhookSubscription[];
  count: number;
}

export interface GongWorkspace {
  id: string;
  name: string;
}

export interface GongWorkspaceSettings {
  selectedWorkspaces: string[] | 'none' | undefined;
}
