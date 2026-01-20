import { ReactNode, useState, useEffect } from 'react';
import { Button, Flex, Text, Input } from '@gathertown/gather-design-system';
import { useDisconnectFigma, useOauthFigma, useFigmaTeams, useSaveFigmaTeams } from '../figmaApi';
import { FigmaConfig } from '../figmaConfig';
import { getSupportContactText } from '../../../constants';

const FigmaOauth = ({ config }: { config: FigmaConfig }) => {
  const isConnected = !!config.FIGMA_ACCESS_TOKEN;
  const userEmail = config.FIGMA_USER_EMAIL;
  const userHandle = config.FIGMA_USER_HANDLE;

  // Prevent layout shift - parent is max-width 800px plus 24px padding on either side
  const containerStyle = { minWidth: '752px' };

  return (
    <Flex direction="column" gap={16} style={containerStyle}>
      {isConnected && (
        <SuccessMessage
          primaryMessage="Figma Account Connected"
          secondaryMessage={
            userEmail
              ? `Connected as ${userHandle || userEmail}. Your design files and comments will be synced.`
              : 'Your Figma account is connected and data will be synced.'
          }
        />
      )}

      <InfoMessage
        primaryMessage={'Data Access'}
        secondaryMessage={
          <>
            Grapevine will sync design files and comments from teams you have access to. File
            contents, component names, and comment threads will be indexed for search.
          </>
        }
      />
      {isConnected ? (
        <>
          <TeamSelection />
          <Disconnect />
        </>
      ) : (
        <Connect />
      )}
    </Flex>
  );
};

const TeamSelection = () => {
  const { data: teamsData, isLoading } = useFigmaTeams();
  const { mutate: saveTeams, isPending: isSaving } = useSaveFigmaTeams();
  const [teamIdInput, setTeamIdInput] = useState('');
  const [teamIds, setTeamIds] = useState<string[]>([]);

  // Initialize local state from fetched data
  useEffect(() => {
    if (teamsData?.team_ids) {
      setTeamIds(teamsData.team_ids);
    }
  }, [teamsData]);

  const handleAddTeam = () => {
    const trimmedId = teamIdInput.trim();
    if (trimmedId && /^\d+$/.test(trimmedId) && !teamIds.includes(trimmedId)) {
      const newTeamIds = [...teamIds, trimmedId];
      setTeamIds(newTeamIds);
      setTeamIdInput('');
      saveTeams(newTeamIds);
    }
  };

  const handleRemoveTeam = (idToRemove: string) => {
    const newTeamIds = teamIds.filter((id) => id !== idToRemove);
    setTeamIds(newTeamIds);
    saveTeams(newTeamIds);
  };

  if (isLoading) {
    return <Text fontSize="sm">Loading team configuration...</Text>;
  }

  return (
    <Flex
      direction="column"
      gap={16}
      style={{
        padding: '16px',
        backgroundColor: '#fafafa',
        borderRadius: '8px',
        border: '1px solid #e5e5e5',
      }}
    >
      <Flex direction="column" gap={4}>
        <Text fontSize="sm" fontWeight="semibold">
          Select Figma Teams to Sync
        </Text>
        <Text fontSize="sm" color="secondary">
          Add the teams you want to sync. All files and comments from these teams will be indexed.
        </Text>
      </Flex>

      {/* How to find team ID instructions */}
      <Flex
        direction="column"
        gap={8}
        style={{
          padding: '12px',
          backgroundColor: '#fff',
          borderRadius: '6px',
          border: '1px solid #e5e5e5',
        }}
      >
        <Text fontSize="sm" fontWeight="medium">
          How to find your Team ID:
        </Text>
        <Flex direction="column" gap={4}>
          <Text fontSize="sm" color="secondary">
            1. Open{' '}
            <a
              href="https://www.figma.com/files"
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#0d99ff', textDecoration: 'underline' }}
            >
              Figma Files
            </a>{' '}
            and click on a team in the left sidebar
          </Text>
          <Text fontSize="sm" color="secondary">
            2. Look at the URL in your browser - it will look like:
          </Text>
          <Flex
            style={{
              padding: '8px 12px',
              backgroundColor: '#f5f5f5',
              borderRadius: '4px',
              fontFamily: 'monospace',
              fontSize: '12px',
              overflowX: 'auto',
            }}
          >
            <span style={{ color: '#666' }}>figma.com/files/team/</span>
            <span style={{ color: '#0d99ff', fontWeight: 600 }}>1234567890123456</span>
            <span style={{ color: '#666' }}>/Team-Name</span>
          </Flex>
          <Text fontSize="sm" color="secondary">
            3. Copy the number after /team/ - that&apos;s your Team ID
          </Text>
        </Flex>
      </Flex>

      {/* Input section */}
      <Flex direction="column" gap={8}>
        <Text fontSize="sm" fontWeight="medium">
          Add Team ID:
        </Text>
        <Flex gap={8} align="center">
          <Input
            placeholder="Paste team ID here (e.g., 1234567890123456)"
            value={teamIdInput}
            onChange={(e) => setTeamIdInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddTeam()}
            style={{ flex: 1 }}
          />
          <Button onClick={handleAddTeam} kind="secondary" size="sm" loading={isSaving}>
            Add Team
          </Button>
        </Flex>
      </Flex>

      {/* Selected teams */}
      {teamIds.length > 0 && (
        <Flex direction="column" gap={8}>
          <Text fontSize="sm" fontWeight="medium">
            Teams to sync ({teamIds.length}):
          </Text>
          <Flex gap={8} flexWrap="wrap">
            {teamIds.map((id) => (
              <Flex
                key={id}
                align="center"
                gap={6}
                style={{
                  padding: '6px 10px',
                  backgroundColor: '#e8f4fd',
                  borderRadius: '4px',
                  border: '1px solid #b8daff',
                }}
              >
                <Text fontSize="sm">{id}</Text>
                <Button
                  onClick={() => handleRemoveTeam(id)}
                  kind="transparent"
                  size="xs"
                  style={{ padding: '2px', minWidth: 'auto' }}
                >
                  ×
                </Button>
              </Flex>
            ))}
          </Flex>
        </Flex>
      )}

      {teamIds.length === 0 && (
        <Flex
          style={{
            padding: '12px',
            backgroundColor: '#fff8e6',
            borderRadius: '6px',
            border: '1px solid #ffe0a3',
          }}
        >
          <Text fontSize="sm" color="secondary">
            ⚠️ No teams selected yet. Add at least one team to start syncing your Figma files.
          </Text>
        </Flex>
      )}
    </Flex>
  );
};

const Disconnect = () => {
  const {
    mutate: disconnectFigma,
    isPending: isDisconnectPending,
    error: disconnectError,
  } = useDisconnectFigma();

  return (
    <Flex direction="column" gap={12}>
      <Button
        onClick={() => disconnectFigma()}
        loading={isDisconnectPending}
        kind="danger"
        size="sm"
        style={{ alignSelf: 'start' }}
      >
        Disconnect
      </Button>
      {disconnectError && <ErrorComponent error={disconnectError} />}
    </Flex>
  );
};

const Connect = () => {
  const { mutate: handleConnect, isPending, isSuccess, error } = useOauthFigma();

  return (
    <Flex direction="column" gap={12}>
      <Button
        onClick={() => handleConnect()}
        kind="primary"
        size="sm"
        loading={isPending || isSuccess}
        style={{ alignSelf: 'start' }}
      >
        Connect
      </Button>
      {error && <ErrorComponent error={error} />}
    </Flex>
  );
};

const ErrorComponent = ({ error }: { error: Error }) => (
  <Flex direction="column" gap={8}>
    <Text color="dangerPrimary" fontWeight="semibold">
      Error Connecting Figma: {error.message}
    </Text>
    <Text fontSize="sm" color="secondary">
      {getSupportContactText()}
    </Text>
  </Flex>
);

const InfoMessage = ({
  primaryMessage,
  secondaryMessage,
}: {
  primaryMessage: ReactNode;
  secondaryMessage: ReactNode;
}) => (
  <Flex
    direction="column"
    gap={8}
    style={{
      padding: '12px',
      backgroundColor: '#f0f9ff',
      borderRadius: '8px',
      border: '1px solid #bae6fd',
    }}
  >
    <Text fontSize="sm" color="primary" fontWeight="semibold">
      {primaryMessage}
    </Text>
    <Text fontSize="sm" color="secondary">
      {secondaryMessage}
    </Text>
  </Flex>
);

const SuccessMessage = ({
  primaryMessage,
  secondaryMessage,
}: {
  primaryMessage: ReactNode;
  secondaryMessage: ReactNode;
}) => (
  <Flex
    direction="column"
    gap={8}
    style={{
      padding: '12px',
      backgroundColor: '#d4edda',
      borderRadius: '8px',
      border: '1px solid #c3e6cb',
    }}
  >
    <Text fontSize="sm" color="successPrimary" fontWeight="semibold">
      {primaryMessage}
    </Text>
    <Text fontSize="sm" color="secondary">
      {secondaryMessage}
    </Text>
  </Flex>
);

export { FigmaOauth };
