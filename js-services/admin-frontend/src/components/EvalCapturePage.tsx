import { useState, FC, memo } from 'react';
import {
  Flex,
  Text,
  Button,
  Select,
  Input,
  type SelectOption,
  Icon,
} from '@gathertown/gather-design-system';
import { apiClient } from '../api/client';
import { SectionContainer } from './shared';
import { useLinearTeams } from '../api/linear';

type DocumentType = 'slack' | 'github' | 'meeting';
type OperationAction = 'CREATE' | 'UPDATE' | 'SKIP' | null;

interface CaptureResponse {
  checkpoint: {
    title: string;
    type: string;
    date: string;
    content: string;
    metadata: Record<string, unknown>;
  };
  truth: {
    output: {
      operations: [];
    };
    input: {
      docs: string[];
      linearState: Array<{
        id: string;
        title: string;
        description?: string;
        assigneeId?: string;
        assignee?: string;
        priority?: string;
        stateId?: string;
      }>;
    };
  };
  suggestedFilename: string;
}

const EvalCapturePage: FC = memo(() => {
  const [documentType, setDocumentType] = useState<DocumentType>('slack');
  const [slackLink, setSlackLink] = useState('');
  const [githubPrUrl, setGithubPrUrl] = useState('');
  const [meetingTitle, setMeetingTitle] = useState('');
  const [meetingDate, setMeetingDate] = useState('');
  const [linearTeamId, setLinearTeamId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Operation form state
  const [operationAction, setOperationAction] = useState<OperationAction>(null);
  const [createTitle, setCreateTitle] = useState('');
  const [createDescription, setCreateDescription] = useState('');
  const [createAssigneeId, setCreateAssigneeId] = useState('');
  const [updateIssueId, setUpdateIssueId] = useState('');
  const [updateDescription, setUpdateDescription] = useState('');
  const [skipReason, setSkipReason] = useState('');
  const [skipIssueId, setSkipIssueId] = useState('');
  const [issueIdentifiers, setIssueIdentifiers] = useState('');

  const { data: linearTeams = [], isLoading: teamsLoading } = useLinearTeams();

  const documentTypeOptions: SelectOption[] = [
    { label: 'Slack Thread', value: 'slack' },
    { label: 'GitHub PR', value: 'github' },
    { label: 'Meeting Transcript', value: 'meeting' },
  ];

  const teamOptions: SelectOption[] = linearTeams
    .map((team) => ({
      label: team.name,
      value: team.id,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));

  const operationOptions: SelectOption[] = [
    { label: 'CREATE', value: 'CREATE' },
    { label: 'UPDATE', value: 'UPDATE' },
    { label: 'SKIP', value: 'SKIP' },
  ];

  // Get Linear URL for the selected team
  const selectedTeam = linearTeams.find((t) => t.id === linearTeamId);
  const linearBoardUrl = selectedTeam?.key
    ? `https://linear.app/gather-town/team/${selectedTeam.key}/all`
    : null;

  const isFormValid = (): boolean => {
    if (!linearTeamId) return false;

    switch (documentType) {
      case 'slack':
        return slackLink.trim().length > 0;
      case 'github':
        return githubPrUrl.trim().length > 0;
      case 'meeting':
        return meetingTitle.trim().length > 0 && meetingDate.length > 0;
      default:
        return false;
    }
  };

  const downloadFile = (content: object, filename: string) => {
    const blob = new Blob([JSON.stringify(content, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCapture = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const payload: Record<string, string> = {
        linearTeamId,
        ...(issueIdentifiers.trim() && { issueIdentifiers: issueIdentifiers.trim() }),
      };

      switch (documentType) {
        case 'slack':
          payload.slackLink = slackLink;
          break;
        case 'github':
          payload.githubPrUrl = githubPrUrl;
          break;
        case 'meeting':
          payload.meetingTitle = meetingTitle;
          payload.meetingDate = meetingDate;
          break;
      }

      const response = await apiClient.post<CaptureResponse>('/api/eval/capture', payload);

      // Build operation if action is selected
      if (operationAction) {
        const operation: Record<string, unknown> = {
          action: operationAction,
        };

        if (operationAction === 'CREATE') {
          operation.createData = {
            title: createTitle,
            ...(createDescription && { description: createDescription }),
            ...(createAssigneeId && { assigneeId: createAssigneeId }),
          };
        } else if (operationAction === 'UPDATE') {
          operation.updateData = {
            issueId: updateIssueId,
            ...(updateDescription && { description: updateDescription }),
          };
        } else if (operationAction === 'SKIP') {
          operation.skipData = {
            reason: skipReason,
            ...(skipIssueId && { issueId: skipIssueId }),
          };
        }

        (response.truth.output as { operations: unknown[] }).operations = [operation];
      }

      // Download checkpoint file
      downloadFile(response.checkpoint, `${response.suggestedFilename}.json`);

      // Download truth file
      downloadFile(response.truth, `${response.suggestedFilename}-truth.json`);

      setSuccess(
        `Downloaded checkpoint and truth files. Edit the truth file to specify expected operations, then run: yarn checkpoints --dataset ./your-dataset/`
      );

      // Auto-dismiss success message after 3 seconds
      setTimeout(() => {
        setSuccess(null);
      }, 3000);
    } catch (err) {
      console.error('Failed to capture eval:', err);
      setError(err instanceof Error ? err.message : 'Failed to capture eval. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const renderOperationInputs = () => {
    if (!operationAction) return null;

    switch (operationAction) {
      case 'CREATE':
        return (
          <Flex direction="column" gap={16}>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="medium">
                Title *
              </Text>
              <Input
                value={createTitle}
                onChange={(e) => setCreateTitle(e.target.value)}
                placeholder="Issue title"
              />
            </Flex>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="medium">
                Description
              </Text>
              <Input
                value={createDescription}
                onChange={(e) => setCreateDescription(e.target.value)}
                placeholder="Issue description (optional)"
              />
            </Flex>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="medium">
                Assignee ID
              </Text>
              <Input
                value={createAssigneeId}
                onChange={(e) => setCreateAssigneeId(e.target.value)}
                placeholder="e.g., sarah (optional)"
              />
            </Flex>
          </Flex>
        );
      case 'UPDATE':
        return (
          <Flex direction="column" gap={16}>
            <Flex direction="column" gap={8}>
              <Flex direction="row" align="center" justify="space-between">
                <Text fontSize="sm" fontWeight="medium">
                  Issue ID *
                </Text>
                {linearBoardUrl && (
                  <a
                    href={linearBoardUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: '12px', color: '#6366f1' }}
                  >
                    Open team board in Linear ↗
                  </a>
                )}
              </Flex>
              <Input
                value={updateIssueId}
                onChange={(e) => setUpdateIssueId(e.target.value)}
                placeholder="e.g., ENG-123"
              />
            </Flex>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="medium">
                Description
              </Text>
              <Input
                value={updateDescription}
                onChange={(e) => setUpdateDescription(e.target.value)}
                placeholder="Updated description (optional)"
              />
            </Flex>
          </Flex>
        );
      case 'SKIP':
        return (
          <Flex direction="column" gap={16}>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="medium">
                Reason *
              </Text>
              <Input
                value={skipReason}
                onChange={(e) => setSkipReason(e.target.value)}
                placeholder="Why should this be skipped?"
              />
            </Flex>
            <Flex direction="column" gap={8}>
              <Flex direction="row" align="center" justify="space-between">
                <Text fontSize="sm" fontWeight="medium">
                  Issue ID
                </Text>
                {linearBoardUrl && (
                  <a
                    href={linearBoardUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontSize: '12px', color: '#6366f1' }}
                  >
                    Open team board in Linear ↗
                  </a>
                )}
              </Flex>
              <Input
                value={skipIssueId}
                onChange={(e) => setSkipIssueId(e.target.value)}
                placeholder="e.g., ENG-123 (optional)"
              />
            </Flex>
          </Flex>
        );
      default:
        return null;
    }
  };

  const renderDocumentInputs = () => {
    switch (documentType) {
      case 'slack':
        return (
          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="medium">
              Slack Message Link
            </Text>
            <Input
              value={slackLink}
              onChange={(e) => setSlackLink(e.target.value)}
              placeholder="https://workspace.slack.com/archives/C123/p1234567890123456"
            />
            <Text fontSize="xs" color="tertiary">
              Right-click a message in Slack → Copy link
            </Text>
          </Flex>
        );
      case 'github':
        return (
          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="medium">
              GitHub PR URL
            </Text>
            <Input
              value={githubPrUrl}
              onChange={(e) => setGithubPrUrl(e.target.value)}
              placeholder="https://github.com/org/repo/pull/123"
            />
            <Text fontSize="xs" color="tertiary">
              Copy the URL from your browser when viewing the PR
            </Text>
          </Flex>
        );
      case 'meeting':
        return (
          <Flex direction="column" gap={16}>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="medium">
                Meeting Title
              </Text>
              <Input
                value={meetingTitle}
                onChange={(e) => setMeetingTitle(e.target.value)}
                placeholder="Weekly standup"
              />
              <Text fontSize="xs" color="tertiary">
                Partial match is supported (e.g., "standup" will match "Weekly standup")
              </Text>
            </Flex>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="medium">
                Meeting Date
              </Text>
              <Input
                type="date"
                value={meetingDate}
                onChange={(e) => setMeetingDate(e.target.value)}
              />
            </Flex>
          </Flex>
        );
      default:
        return null;
    }
  };

  return (
    <Flex direction="column" gap={32}>
      <SectionContainer>
        <Flex direction="column" gap={24}>
          <Flex direction="column" gap={8}>
            <Text fontSize="lg" fontWeight="bold" color="primary">
              Capture Eval Test Case
            </Text>
            <Text fontSize="sm" color="tertiary">
              Convert a real document + current Linear state into eval checkpoint files. Use this
              when you spot an incorrect extraction and want to add it to your test suite.
            </Text>
          </Flex>

          {/* Document Type Selection */}
          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="medium">
              Document Type
            </Text>
            <div style={{ maxWidth: '300px' }}>
              <Select
                value={documentType}
                onChange={(value: string) => setDocumentType(value as DocumentType)}
                options={documentTypeOptions}
              />
            </div>
          </Flex>

          {/* Dynamic Document Inputs */}
          {renderDocumentInputs()}

          {/* Linear Team Selection */}
          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="medium">
              Linear Team
            </Text>
            <div style={{ maxWidth: '300px' }}>
              <Select
                value={linearTeamId}
                onChange={(value: string) => setLinearTeamId(value)}
                options={teamOptions}
                placeholder={teamsLoading ? 'Loading teams...' : 'Select a team'}
                disabled={teamsLoading}
              />
            </div>
          </Flex>

          {/* Linear Issue Identifiers (Optional) */}
          <Flex direction="column" gap={8}>
            <Text fontSize="sm" fontWeight="medium">
              Linear Issue Identifiers (Optional)
            </Text>
            <Input
              value={issueIdentifiers}
              onChange={(e) => setIssueIdentifiers(e.target.value)}
              placeholder="ENG-123, ENG-166, PROJ-42"
            />
            <Text fontSize="xs" color="tertiary">
              If not provided, 20 most recent issues from selected team will be included.
            </Text>
          </Flex>

          {/* Operation Form (Optional) */}
          <Flex direction="column" gap={16}>
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="medium">
                Add Operation (Optional)
              </Text>
              <Text fontSize="xs" color="tertiary">
                Pre-fill the truth file with an expected operation
              </Text>
            </Flex>
            <div style={{ maxWidth: '300px' }}>
              <Select
                value={operationAction ?? undefined}
                onChange={(value: string) =>
                  setOperationAction(value ? (value as OperationAction) : null)
                }
                options={operationOptions}
                placeholder="Select action type"
              />
            </div>
            {renderOperationInputs()}
          </Flex>

          {/* Error Message */}
          {error && (
            <Flex
              direction="row"
              align="center"
              gap={8}
              style={{
                padding: '12px',
                backgroundColor: '#FFF4ED',
                borderRadius: '8px',
                border: '1px solid #FFE6D5',
              }}
            >
              <Icon name="exclamationCircle" size="md" color="dangerPrimary" />
              <Text fontSize="sm" color="dangerPrimary">
                {error}
              </Text>
            </Flex>
          )}

          {/* Success Message */}
          {success && (
            <Flex
              direction="column"
              gap={8}
              style={{
                padding: '12px',
                backgroundColor: '#EEFFF3',
                borderRadius: '8px',
                border: '1px solid #B2FFCC',
              }}
            >
              <Flex direction="row" align="center" gap={8}>
                <Icon name="checkCircle" size="md" color="successPrimary" />
                <Text fontSize="sm" color="successPrimary" fontWeight="medium">
                  Files downloaded!
                </Text>
              </Flex>
              <Text fontSize="sm" color="tertiary">
                {success}
              </Text>
            </Flex>
          )}

          {/* Download Button */}
          <Flex>
            <Button
              onClick={handleCapture}
              kind="primary"
              disabled={!isFormValid() || loading}
              loading={loading}
            >
              {loading ? 'Capturing...' : 'Download Checkpoint Files'}
            </Button>
          </Flex>
        </Flex>
      </SectionContainer>

      {/* Instructions Section */}
      <SectionContainer>
        <Flex direction="column" gap={16}>
          <Text fontSize="lg" fontWeight="bold" color="primary">
            How to Use
          </Text>

          <Flex direction="column" gap={12}>
            <Flex direction="column" gap={4}>
              <Text fontSize="sm" fontWeight="medium">
                1. Select document and download
              </Text>
              <Text fontSize="sm" color="tertiary">
                Choose the document type, paste the link or enter details, select the Linear team,
                and click download.
              </Text>
            </Flex>

            <Flex direction="column" gap={4}>
              <Text fontSize="sm" fontWeight="medium">
                2. Edit the truth file
              </Text>
              <Text fontSize="sm" color="tertiary">
                Open the <code>*-truth.json</code> file and fill in the expected operations (CREATE,
                UPDATE, or SKIP).
              </Text>
            </Flex>

            <Flex direction="column" gap={4}>
              <Text fontSize="sm" fontWeight="medium">
                3. Run the eval
              </Text>
              <Text fontSize="sm" color="tertiary">
                Place files in a dataset folder and run: <code>yarn checkpoints --dataset ./</code>
              </Text>
            </Flex>
          </Flex>
        </Flex>
      </SectionContainer>
    </Flex>
  );
});

EvalCapturePage.displayName = 'EvalCapturePage';

export { EvalCapturePage };
