import { useState, useEffect, useMemo, useCallback, type FC, type ReactNode } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { BaseIntegration } from '../../../components/integrations/BaseIntegration';
import type { Integration, ConnectionStep } from '../../../types';
import { useAllConfig } from '../../../api/config';
import { useDisconnectSnowflake, useOauthSnowflake, useSnowflakeStatus } from '../snowflakeApi';
import {
  SetupRoleStep,
  RetrieveCredentialsStep,
  CustomEndpointsStep,
  ConnectStep,
  ConnectedState,
  OAuthPendingState,
  parseCredentialsJson,
  type CredentialsValidationState,
} from './steps';

interface SnowflakeIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

interface SnowflakeStepInputs {
  accountIdentifier: string;
  clientId: string;
  clientSecret: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  credentialsJson: string;
}

export const SnowflakeIntegration: FC<SnowflakeIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const { data: _configData } = useAllConfig();
  const { data: status, isLoading: isStatusLoading } = useSnowflakeStatus();

  const oauthErrorMessage = searchParams.get('oauth-error');
  const oauthSuccess = searchParams.get('oauth-success') === 'true';

  // Track if we're waiting for OAuth completion
  const [isOAuthPending, setIsOAuthPending] = useState(oauthSuccess);

  const isConnected = status?.connected ?? false;
  const savedAccountIdentifier = status?.accountIdentifier ?? '';

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [stepInputs, setStepInputs] = useState<SnowflakeStepInputs>({
    accountIdentifier: savedAccountIdentifier || '',
    clientId: '',
    clientSecret: '',
    authorizationEndpoint: '',
    tokenEndpoint: '',
    credentialsJson: '',
  });
  const [credentialsValidation, setCredentialsValidation] = useState<CredentialsValidationState>({
    isValid: false,
    error: null,
  });

  const {
    mutate: disconnectSnowflake,
    isPending: isDisconnecting,
    error: disconnectError,
  } = useDisconnectSnowflake();

  const {
    mutate: connectSnowflake,
    isPending: isConnecting,
    isSuccess: isConnectSuccess,
    error: connectError,
  } = useOauthSnowflake();

  const isLoading = isConnecting || isConnectSuccess;

  // Initialize account identifier from saved value
  useEffect(() => {
    if (savedAccountIdentifier && !stepInputs.accountIdentifier) {
      setStepInputs((prev) => ({
        ...prev,
        accountIdentifier: savedAccountIdentifier,
      }));
    }
  }, [savedAccountIdentifier, stepInputs.accountIdentifier]);

  // Handle OAuth success - invalidate queries and wait for status update
  useEffect(() => {
    if (oauthSuccess) {
      setIsOAuthPending(true);
      // Invalidate status to refetch
      queryClient.invalidateQueries({ queryKey: ['snowflake', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['config'] });
      // Clear URL params
      navigate('/integrations/snowflake', { replace: true });
    }
    if (oauthErrorMessage) {
      navigate('/integrations/snowflake', { replace: true });
    }
  }, [oauthSuccess, oauthErrorMessage, navigate, queryClient]);

  // Clear OAuth pending state once connected
  useEffect(() => {
    if (isConnected && isOAuthPending) {
      setIsOAuthPending(false);
    }
  }, [isConnected, isOAuthPending]);

  const redirectUri = `${window.location.origin}/api/snowflake/oauth/callback`;

  const roleSetupSql = `-- Step 1: Create a role with query permissions
CREATE ROLE IF NOT EXISTS GRAPEVINE_QUERY_ROLE;

-- Step 2: Grant database and schema usage
GRANT USAGE ON DATABASE <database_name> TO ROLE GRAPEVINE_QUERY_ROLE;
GRANT USAGE ON SCHEMA <database>.<schema> TO ROLE GRAPEVINE_QUERY_ROLE;

-- Step 3: Grant select permissions on tables you want to query
GRANT SELECT ON TABLE <database>.<schema>.<table> TO ROLE GRAPEVINE_QUERY_ROLE;

-- Step 4: Grant Cortex AI permissions (required for natural language queries)
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE GRAPEVINE_QUERY_ROLE;

-- Step 5: Assign the role to your user
GRANT ROLE GRAPEVINE_QUERY_ROLE TO USER <user_name>;`;

  const securityIntegrationSql = `-- Create OAuth Security Integration (requires ACCOUNTADMIN role)
CREATE SECURITY INTEGRATION GRAPEVINE_OAUTH_INTEGRATION
  TYPE = OAUTH
  ENABLED = TRUE
  OAUTH_CLIENT = CUSTOM
  OAUTH_CLIENT_TYPE = 'CONFIDENTIAL'
  OAUTH_REDIRECT_URI = '${redirectUri}'
  OAUTH_ISSUE_REFRESH_TOKENS = TRUE
  OAUTH_REFRESH_TOKEN_VALIDITY = 7776000;`;

  const retrieveCredentialsSql = `-- Retrieve OAuth Client ID and Secret
SELECT SYSTEM$SHOW_OAUTH_CLIENT_SECRETS('GRAPEVINE_OAUTH_INTEGRATION');`;

  const retrieveEndpointsSql = `-- Retrieve OAuth Endpoints (for Private Link or custom vanity URLs)
DESC SECURITY INTEGRATION GRAPEVINE_OAUTH_INTEGRATION;`;

  const handleCredentialsJsonChange = (value: string) => {
    setStepInputs((prev) => ({ ...prev, credentialsJson: value }));

    if (!value.trim()) {
      setCredentialsValidation({ isValid: false, error: null });
      return;
    }

    const parsed = parseCredentialsJson(value);
    if (parsed) {
      setStepInputs((prev) => ({
        ...prev,
        clientId: parsed.clientId,
        clientSecret: parsed.clientSecret,
      }));
      setCredentialsValidation({ isValid: true, error: null });
    } else {
      setCredentialsValidation({
        isValid: false,
        error: 'Invalid JSON format. Expected OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET fields.',
      });
    }
  };

  const handleConnect = useCallback(() => {
    connectSnowflake({
      accountIdentifier: stepInputs.accountIdentifier.trim(),
      clientId: stepInputs.clientId.trim(),
      clientSecret: stepInputs.clientSecret.trim(),
      authorizationEndpoint: stepInputs.authorizationEndpoint.trim() || undefined,
      tokenEndpoint: stepInputs.tokenEndpoint.trim() || undefined,
    });
  }, [connectSnowflake, stepInputs]);

  const isStepValid = (stepIndex: number): boolean => {
    switch (stepIndex) {
      case 0:
        return stepInputs.accountIdentifier.trim().length > 0;
      case 1:
        return credentialsValidation.isValid;
      case 2:
        return true;
      case 3:
        if (isConnected) return true;
        return (
          stepInputs.accountIdentifier.trim().length > 0 &&
          stepInputs.clientId.trim().length > 0 &&
          stepInputs.clientSecret.trim().length > 0
        );
      default:
        return true;
    }
  };

  const handleStepChange = (newStepIndex: number) => {
    setCurrentStepIndex(newStepIndex);
  };

  const handleComplete = async () => {
    if (renderInline && onInlineComplete) {
      onInlineComplete();
    } else {
      onModalOpenChange(false);
    }
  };

  const steps: ConnectionStep[] = useMemo(() => {
    // Show pending state while waiting for OAuth to complete
    if (isOAuthPending || isStatusLoading) {
      return [
        {
          title: 'Connecting',
          content: <OAuthPendingState />,
        },
      ];
    }

    if (isConnected) {
      return [
        {
          title: 'Connected',
          content: (
            <ConnectedState
              accountIdentifier={savedAccountIdentifier}
              onDisconnect={() => disconnectSnowflake()}
              isDisconnecting={isDisconnecting}
              disconnectError={disconnectError}
            />
          ),
        },
      ];
    }

    return [
      {
        title: 'Setup Role & Integration',
        content: (
          <SetupRoleStep
            roleSetupSql={roleSetupSql}
            securityIntegrationSql={securityIntegrationSql}
            accountIdentifier={stepInputs.accountIdentifier}
            onAccountIdentifierChange={(value) =>
              setStepInputs((prev) => ({ ...prev, accountIdentifier: value }))
            }
          />
        ),
        requiresInput: true,
        validateInput: () => stepInputs.accountIdentifier.trim().length > 0,
      },
      {
        title: 'Retrieve Credentials',
        content: (
          <RetrieveCredentialsStep
            retrieveCredentialsSql={retrieveCredentialsSql}
            credentialsJson={stepInputs.credentialsJson}
            onCredentialsJsonChange={handleCredentialsJsonChange}
            credentialsValidation={credentialsValidation}
          />
        ),
        requiresInput: true,
        validateInput: () => credentialsValidation.isValid,
      },
      {
        title: 'Custom Endpoints (Optional)',
        content: (
          <CustomEndpointsStep
            retrieveEndpointsSql={retrieveEndpointsSql}
            authorizationEndpoint={stepInputs.authorizationEndpoint}
            tokenEndpoint={stepInputs.tokenEndpoint}
            onAuthorizationEndpointChange={(value) =>
              setStepInputs((prev) => ({ ...prev, authorizationEndpoint: value }))
            }
            onTokenEndpointChange={(value) =>
              setStepInputs((prev) => ({ ...prev, tokenEndpoint: value }))
            }
          />
        ),
      },
      {
        title: 'Connect',
        content: (
          <ConnectStep
            onConnect={handleConnect}
            isLoading={isLoading}
            error={connectError}
            oauthErrorMessage={oauthErrorMessage}
          />
        ),
      },
    ];
  }, [
    isOAuthPending,
    isStatusLoading,
    isConnected,
    savedAccountIdentifier,
    isDisconnecting,
    disconnectError,
    roleSetupSql,
    securityIntegrationSql,
    retrieveCredentialsSql,
    retrieveEndpointsSql,
    stepInputs,
    credentialsValidation,
    isLoading,
    connectError,
    oauthErrorMessage,
    disconnectSnowflake,
    handleConnect,
  ]);

  const renderStepContent = (step: ConnectionStep): ReactNode => {
    if (typeof step.content === 'function') {
      return null;
    }
    return step.content;
  };

  // When connected or pending, always show step 0
  const effectiveStepIndex =
    isConnected || isOAuthPending || isStatusLoading ? 0 : currentStepIndex;

  // Hide navigation when connected, pending, or loading
  const shouldHideNavigation = isConnected || isOAuthPending || isStatusLoading;

  return (
    <BaseIntegration
      integration={integration}
      steps={steps}
      isModalOpen={isModalOpen}
      onModalOpenChange={onModalOpenChange}
      currentStepIndex={effectiveStepIndex}
      onStepChange={handleStepChange}
      isStepValid={isStepValid}
      onComplete={handleComplete}
      renderStepContent={renderStepContent}
      renderInline={renderInline}
      hideNavigation={shouldHideNavigation}
      hideComplete={!isConnected}
    />
  );
};
