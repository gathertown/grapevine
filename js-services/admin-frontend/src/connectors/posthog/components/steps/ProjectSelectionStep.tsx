import type { FC, ChangeEvent } from 'react';
import { Flex, Text, Button, Checkbox } from '@gathertown/gather-design-system';
import type { PostHogProject } from '../../posthogApi';

interface ProjectSelectionStepProps {
  projects: PostHogProject[];
  selectedProjectIds: Set<number>;
  onToggleProject: (projectId: number) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  isFetchingProjects: boolean;
  error: Error | null;
}

export const ProjectSelectionStep: FC<ProjectSelectionStepProps> = ({
  projects,
  selectedProjectIds,
  onToggleProject,
  onSelectAll,
  onDeselectAll,
  isFetchingProjects,
  error,
}) => {
  if (isFetchingProjects) {
    return (
      <Flex
        direction="column"
        gap={16}
        align="center"
        justify="center"
        style={{ padding: '48px 0' }}
      >
        <Flex
          direction="column"
          gap={8}
          align="center"
          style={{
            padding: '24px',
            backgroundColor: '#e3f2fd',
            borderRadius: '8px',
            border: '1px solid #90caf9',
            textAlign: 'center',
          }}
        >
          <Text fontSize="md" fontWeight="semibold">
            Fetching projects from PostHog...
          </Text>
          <Text fontSize="sm" color="secondary">
            Please wait while we retrieve your available projects.
          </Text>
        </Flex>
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex direction="column" gap={8}>
        <Text color="dangerPrimary" fontWeight="semibold">
          Error: {error.message}
        </Text>
        <Text fontSize="sm" color="secondary">
          Please go back and verify your API key and host are correct.
        </Text>
      </Flex>
    );
  }

  if (projects.length === 0) {
    return (
      <Flex direction="column" gap={8}>
        <Text color="warningPrimary" fontWeight="semibold">
          No projects found
        </Text>
        <Text fontSize="sm" color="secondary">
          No PostHog projects were found with your API key. Please verify your API key has the
          correct scopes and try again.
        </Text>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={16}>
      <Flex direction="column" gap={12}>
        <Flex justify="space-between" align="center">
          <Text fontWeight="semibold">Select Projects to Sync</Text>
          <Flex gap={8}>
            <Button kind="transparent" size="sm" onClick={onSelectAll}>
              Select All
            </Button>
            <Button kind="transparent" size="sm" onClick={onDeselectAll}>
              Deselect All
            </Button>
          </Flex>
        </Flex>
        <Flex
          direction="column"
          gap={8}
          style={{
            maxHeight: '200px',
            overflowY: 'auto',
            padding: '8px',
            border: '1px solid #e0e0e0',
            borderRadius: '4px',
          }}
        >
          {projects.map((project) => (
            <Flex key={project.id} gap={8} align="center">
              <Checkbox
                checked={selectedProjectIds.has(project.id)}
                onChange={(e: ChangeEvent<HTMLInputElement>) => {
                  if (e.target.checked !== selectedProjectIds.has(project.id)) {
                    onToggleProject(project.id);
                  }
                }}
                label={project.name}
              />
            </Flex>
          ))}
        </Flex>
        <Text fontSize="sm" color="secondary">
          {selectedProjectIds.size} of {projects.length} projects selected
        </Text>
      </Flex>
    </Flex>
  );
};
