import { memo, useState, useEffect, ChangeEvent } from 'react';
import type { FC } from 'react';
import { Flex, Text, Button, Box, TextArea } from '@gathertown/gather-design-system';
import { CollapsibleExample } from '../CollapsibleExample';
import { useTrackEvent } from '../../hooks/useTrackEvent';
import { useAuth } from '../../hooks/useAuth';
import { useAllConfig, useSetConfigValue } from '../../api/config';

interface CompanyContextFormProps {
  minLength?: number;
  validationMessage?: string;
  inSettingsPage?: boolean;
}

const CompanyContextForm: FC<CompanyContextFormProps> = memo(
  ({ minLength = 10, validationMessage: _validationMessage, inSettingsPage = false }) => {
    const { data: configData } = useAllConfig();
    const { mutateAsync: updateConfigValue, isPending: isSaving } = useSetConfigValue();
    const { trackEvent } = useTrackEvent();
    const { user } = useAuth();
    const [companyContext, setCompanyContext] = useState<string>(configData?.COMPANY_CONTEXT || '');
    const [saveStatus, setSaveStatus] = useState<null | 'saved' | 'error'>(null);

    // Initialize with existing value when config data changes
    useEffect(() => {
      setCompanyContext(configData?.COMPANY_CONTEXT || '');
    }, [configData?.COMPANY_CONTEXT]);

    // Form validation
    const isCompanyContextValid = companyContext.trim().length >= minLength;
    const hasChanges = companyContext.trim() !== (configData?.COMPANY_CONTEXT || '');

    // Conditional styling based on context
    const textStyles = inSettingsPage
      ? { fontSize: 'md' as const, color: 'tertiary' as const }
      : { fontSize: 'sm' as const };

    // Event handler
    const handleCompanyContextChange = (e: ChangeEvent<HTMLTextAreaElement>): void => {
      setCompanyContext(e.target.value);
    };

    // Save company context
    const handleSaveCompanyContext = async (): Promise<void> => {
      if (!isCompanyContextValid || isSaving) return;

      setSaveStatus(null);

      try {
        await updateConfigValue({
          key: 'COMPANY_CONTEXT',
          value: companyContext.trim(),
        });

        setSaveStatus('saved');

        // Track company context update
        const isInitial = configData?.COMPANY_CONTEXT === undefined;
        trackEvent('company_context_updated', {
          user_id: user?.id,
          context_length: companyContext.trim().length,
          is_initial_setup: isInitial,
        });

        setTimeout(() => setSaveStatus(null), 3000);
      } catch (error) {
        console.error('Error saving company context:', error);
        setSaveStatus('error');
        setTimeout(() => setSaveStatus(null), 3000);
      }
    };

    return (
      <Flex direction="column" gap={16}>
        {/* Description */}
        <Text fontSize={textStyles.fontSize} color={textStyles.color}>
          We recommend adding{' '}
          <b>details about your company, team structure, projects, tech stack,</b> and any other
          relevant information.
        </Text>

        {/* Example */}
        <CollapsibleExample title="View Example">
          {`Gather is a startup that builds a product that combines a 2D video-game-like interface with live video chat, enabling people who are next to each other to talk with each other. The main use-case is virtual offices for remote teams, where people have meetings and adhoc conversations at each other's virtual desks.

Key technical details:
- Tech stack: TypeScript (primary language), React (frontend), MobX (state management), Node.js (backend)
- Product evolution: The company rewrote their product into "v2" (aka "Work 2.0") starting mid-2024, with the rest of the company transitioning to v2 around end of 2024. This is a forked codebase from v1 with almost all code rewritten, containing only small remnants of earlier v1 code and patterns. Any information from before summer 2024 is likely outdated (referencing v1). Unless otherwise specified, assume questions are about v2.
- Database: PostgreSQL (current v2), previously CockroachDB in v1
- Repositories: "gather-town" (v1/legacy), "gather-town-v2" (current)
- Backend architecture: Includes a realtime sync engine (game server/"GS"), HTTP server, and in-house video system based on SFU (Selective Forwarding Unit) architecture

**V1 vs. V2**: When referencing code, architecture, or technical decisions, provide context about whether it relates to v1 (legacy) or v2 (current) systems. Note that v1 information is likely outdated.`}
        </CollapsibleExample>

        {/* Textarea with proper GDS styling */}
        <Box position="relative">
          <TextArea
            value={companyContext}
            onChange={handleCompanyContextChange}
            placeholder="Describe your company, team structure, key projects, tech stack, and any other relevant context that will help your Slack bot provide better responses..."
            style={{
              minHeight: '300px',
            }}
            onFocus={(e) => {
              e.target.style.borderColor = '#6366F1';
            }}
            onBlur={(e) => {
              e.target.style.borderColor = '#D1D5DB';
            }}
          />

          {/* Character count - only show when below minimum */}
          {companyContext.length < minLength && (
            <Box
              position="absolute"
              style={{
                bottom: '8px',
                right: '12px',
                backgroundColor: '#FFFFFF',
                padding: '0 4px',
                color: '#6B7280',
              }}
            >
              <Text fontSize="xs">
                {companyContext.length} characters (minimum {minLength})
              </Text>
            </Box>
          )}
        </Box>

        {/* Save Button */}
        <Flex justify="flex-end">
          <Button
            kind="primary"
            onClick={handleSaveCompanyContext}
            disabled={!isCompanyContextValid || !hasChanges || isSaving}
          >
            {saveStatus === 'saved'
              ? 'Saved!'
              : saveStatus === 'error'
                ? 'Error - Try Again'
                : isSaving
                  ? 'Saving...'
                  : 'Save'}
          </Button>
        </Flex>
      </Flex>
    );
  }
);

CompanyContextForm.displayName = 'CompanyContextForm';

export { CompanyContextForm };
