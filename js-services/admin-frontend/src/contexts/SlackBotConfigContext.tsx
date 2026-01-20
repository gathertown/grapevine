import { createContext, useContext, useMemo, memo } from 'react';
import type { FC, ReactNode } from 'react';
import { isSlackBotConfigured } from '../utils/validation';
import type { SlackBotConfigContextType } from '../types';
import { useAllConfig } from '../api/config';

const SlackBotConfigContext = createContext<SlackBotConfigContextType | null>(null);

interface SlackBotConfigProviderProps {
  children: ReactNode;
}

export const SlackBotConfigProvider: FC<SlackBotConfigProviderProps> = memo(({ children }) => {
  const { data: configData, isLoading } = useAllConfig();

  const contextValue = useMemo((): SlackBotConfigContextType => {
    const signingSecret = configData?.SLACK_SIGNING_SECRET || '';
    const botToken = configData?.SLACK_BOT_TOKEN || '';
    const botName = configData?.SLACK_BOT_NAME || '';
    const proactivitySetting = configData?.SLACK_BOT_QA_ALL_CHANNELS || '';
    const excludedChannels = configData?.SLACK_BOT_QA_DISALLOWED_CHANNELS || '';

    const hasSigningSecret = /^[a-fA-F0-9]{32}$/.test(signingSecret.trim());
    const hasBotToken = botToken.trim().startsWith('xoxb-') && botToken.trim().length > 10;
    const hasBotName = Boolean(botName.trim());
    const proactivityEnabled = proactivitySetting.toLowerCase() === 'true';
    const isConfigured = !!configData && isSlackBotConfigured(configData);

    return {
      isConfigured,
      hasBotToken,
      hasSigningSecret,
      isLoading,
      botTokenPreview: hasBotToken ? `${botToken.substring(0, 8)}...` : '',
      signingSecretPreview: hasSigningSecret ? `${signingSecret.substring(0, 8)}...` : '',
      // Bot configuration
      botName,
      hasBotName,
      proactivityEnabled,
      excludedChannels,
    };
  }, [configData, isLoading]);

  return (
    <SlackBotConfigContext.Provider value={contextValue}>{children}</SlackBotConfigContext.Provider>
  );
});

SlackBotConfigProvider.displayName = 'SlackBotConfigProvider';

export const useSlackBotConfig = (): SlackBotConfigContextType => {
  const context = useContext(SlackBotConfigContext);
  if (!context) {
    throw new Error('useSlackBotConfig must be used within a SlackBotConfigProvider');
  }
  return context;
};

export { SlackBotConfigContext };
