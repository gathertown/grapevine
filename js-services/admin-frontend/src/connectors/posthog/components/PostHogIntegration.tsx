import { useState, useEffect, useMemo, useCallback, type FC, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { BaseIntegration } from '../../../components/integrations/BaseIntegration';
import type { Integration, ConnectionStep } from '../../../types';
import { useAllConfig } from '../../../api/config';
import {
  useConnectPostHog,
  useDisconnectPostHog,
  useFetchPostHogProjects,
  type PostHogProject,
} from '../posthogApi';
import {
  POSTHOG_API_KEY_CONFIG_KEY,
  POSTHOG_HOST_CONFIG_KEY,
  POSTHOG_HOSTS,
  DEFAULT_POSTHOG_HOST,
} from '../posthogConfig';
import { CredentialsStep, ProjectSelectionStep, ConnectedState } from './steps';

interface PostHogConfig {
  [POSTHOG_API_KEY_CONFIG_KEY]?: string;
  [POSTHOG_HOST_CONFIG_KEY]?: string;
}

interface PostHogIntegrationProps {
  integration: Integration;
  isModalOpen: boolean;
  onModalOpenChange: (open: boolean) => void;
  renderInline?: boolean;
  onComplete?: () => void;
}

export const PostHogIntegration: FC<PostHogIntegrationProps> = ({
  integration,
  isModalOpen,
  onModalOpenChange,
  renderInline = false,
  onComplete: onInlineComplete,
}) => {
  const queryClient = useQueryClient();
  const { data: configData } = useAllConfig();
  const config = (configData ?? {}) as PostHogConfig;

  const isConnected = !!config[POSTHOG_API_KEY_CONFIG_KEY];
  const savedHost = config[POSTHOG_HOST_CONFIG_KEY] ?? '';

  // Step state
  const [currentStepIndex, setCurrentStepIndex] = useState(0);

  // Form state
  const [hostOption, setHostOption] = useState<string>(() => {
    if (!savedHost) return DEFAULT_POSTHOG_HOST;
    const matchingOption = POSTHOG_HOSTS.find((h) => h.value === savedHost);
    return matchingOption ? matchingOption.value : 'custom';
  });
  const [customHost, setCustomHost] = useState<string>(() => {
    if (!savedHost) return '';
    const matchingOption = POSTHOG_HOSTS.find((h) => h.value === savedHost);
    return matchingOption ? '' : savedHost;
  });
  const [apiKey, setApiKey] = useState<string>('');
  const [keyVisible, setKeyVisible] = useState(false);

  // Projects state
  const [projects, setProjects] = useState<PostHogProject[]>([]);
  const [selectedProjectIds, setSelectedProjectIds] = useState<Set<number>>(new Set());
  const [projectsFetched, setProjectsFetched] = useState(false);

  // API hooks
  const { mutate: connect, isPending: isConnecting, error: connectError } = useConnectPostHog();
  const {
    mutate: disconnect,
    isPending: isDisconnecting,
    error: disconnectError,
  } = useDisconnectPostHog();
  const {
    mutateAsync: fetchProjects,
    isPending: isFetchingProjects,
    error: projectsError,
  } = useFetchPostHogProjects();

  const effectiveHost = hostOption === 'custom' ? customHost : hostOption;
  const canValidate = apiKey.length > 0 && effectiveHost.length > 0;

  // Reset state when modal closes
  useEffect(() => {
    if (!isModalOpen) {
      setCurrentStepIndex(0);
      setApiKey('');
      setKeyVisible(false);
      setProjects([]);
      setSelectedProjectIds(new Set());
      setProjectsFetched(false);
    }
  }, [isModalOpen]);

  // Fetch projects when entering step 2
  useEffect(() => {
    const fetchProjectsForStep = async () => {
      if (currentStepIndex === 1 && !projectsFetched && canValidate && !isConnected) {
        try {
          const result = await fetchProjects({ apiKey, host: effectiveHost });
          setProjects(result.projects);
          setSelectedProjectIds(new Set(result.projects.map((p) => p.id)));
          setProjectsFetched(true);
        } catch {
          // Error handled by hook
          setProjectsFetched(true);
        }
      }
    };

    fetchProjectsForStep();
  }, [
    currentStepIndex,
    projectsFetched,
    canValidate,
    isConnected,
    apiKey,
    effectiveHost,
    fetchProjects,
  ]);

  // Reset projectsFetched when going back to step 1
  useEffect(() => {
    if (currentStepIndex === 0) {
      setProjectsFetched(false);
    }
  }, [currentStepIndex]);

  const handleConnect = useCallback(() => {
    const projectIds = Array.from(selectedProjectIds);
    connect(
      {
        apiKey,
        host: effectiveHost,
        selectedProjectIds: projectIds.length > 0 ? projectIds : undefined,
      },
      {
        onSuccess: () => {
          queryClient.invalidateQueries({ queryKey: ['config'] });
        },
      }
    );
  }, [connect, apiKey, effectiveHost, selectedProjectIds, queryClient]);

  const handleDisconnect = useCallback(() => {
    disconnect(undefined, {
      onSuccess: () => {
        setApiKey('');
        setProjects([]);
        setSelectedProjectIds(new Set());
        setProjectsFetched(false);
        setCurrentStepIndex(0);
      },
    });
  }, [disconnect]);

  const toggleProjectSelection = useCallback((projectId: number) => {
    setSelectedProjectIds((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(projectId)) {
        newSet.delete(projectId);
      } else {
        newSet.add(projectId);
      }
      return newSet;
    });
  }, []);

  const selectAllProjects = useCallback(() => {
    setSelectedProjectIds(new Set(projects.map((p) => p.id)));
  }, [projects]);

  const deselectAllProjects = useCallback(() => {
    setSelectedProjectIds(new Set());
  }, []);

  const isStepValid = useCallback(
    (stepIndex: number): boolean => {
      switch (stepIndex) {
        case 0:
          return canValidate;
        case 1: {
          // Step 2 is only valid if:
          // - Projects fetched successfully (no error, has projects)
          // - At least one project selected
          // - Not currently fetching
          const hasError = !!(projectsError || connectError);
          const hasProjects = projects.length > 0;
          const hasSelection = selectedProjectIds.size > 0;
          return !isFetchingProjects && !hasError && hasProjects && hasSelection;
        }
        default:
          return true;
      }
    },
    [
      canValidate,
      selectedProjectIds.size,
      projectsError,
      connectError,
      projects.length,
      isFetchingProjects,
    ]
  );

  const handleStepChange = useCallback((newStepIndex: number) => {
    setCurrentStepIndex(newStepIndex);
  }, []);

  const handleComplete = useCallback(async () => {
    if (isConnected) {
      // When connected, just close/complete
      if (renderInline && onInlineComplete) {
        onInlineComplete();
      } else {
        onModalOpenChange(false);
      }
    } else {
      // When not connected, trigger the connect action
      handleConnect();
    }
  }, [isConnected, renderInline, onInlineComplete, onModalOpenChange, handleConnect]);

  const steps: ConnectionStep[] = useMemo(() => {
    if (isConnected) {
      return [
        {
          title: 'Connected',
          content: (
            <ConnectedState
              host={savedHost}
              onDisconnect={handleDisconnect}
              isDisconnecting={isDisconnecting}
              disconnectError={disconnectError}
            />
          ),
        },
      ];
    }

    return [
      {
        title: 'Enter Credentials',
        content: (
          <CredentialsStep
            hostOption={hostOption}
            onHostOptionChange={setHostOption}
            customHost={customHost}
            onCustomHostChange={setCustomHost}
            apiKey={apiKey}
            onApiKeyChange={setApiKey}
            keyVisible={keyVisible}
            onToggleKeyVisible={() => setKeyVisible((prev) => !prev)}
          />
        ),
        requiresInput: true,
        validateInput: () => canValidate,
      },
      {
        title: 'Select Projects',
        content: (
          <ProjectSelectionStep
            projects={projects}
            selectedProjectIds={selectedProjectIds}
            onToggleProject={toggleProjectSelection}
            onSelectAll={selectAllProjects}
            onDeselectAll={deselectAllProjects}
            isFetchingProjects={isFetchingProjects}
            error={projectsError || connectError}
          />
        ),
        requiresInput: true,
        validateInput: () => selectedProjectIds.size > 0,
      },
    ];
  }, [
    isConnected,
    savedHost,
    handleDisconnect,
    isDisconnecting,
    disconnectError,
    hostOption,
    customHost,
    apiKey,
    keyVisible,
    canValidate,
    projects,
    selectedProjectIds,
    toggleProjectSelection,
    selectAllProjects,
    deselectAllProjects,
    isFetchingProjects,
    projectsError,
    connectError,
  ]);

  const renderStepContent = (step: ConnectionStep): ReactNode => {
    if (typeof step.content === 'function') {
      return null;
    }
    return step.content;
  };

  const effectiveStepIndex = isConnected ? 0 : currentStepIndex;
  const shouldHideNavigation = isConnected;

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
      isCompleting={isConnecting}
      renderStepContent={renderStepContent}
      renderInline={renderInline}
      hideNavigation={shouldHideNavigation}
      hideComplete={isConnected}
      isConnected={isConnected}
      completionButtonText={isConnected ? 'Complete' : 'Connect'}
    />
  );
};
