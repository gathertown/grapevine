/**
 * Single-agent strategy for task extraction and resolution
 * Ported from @exponent/task-extraction/src/strategies/SingleAgentStrategy.ts
 *
 * Unlike the two-agent approach, this strategy uses a single agent that:
 * 1. Analyzes the artifact (Slack) AND existing Linear state together
 * 2. Directly outputs Linear operations (CREATE/UPDATE/SKIP)
 *
 * This approach:
 * - Reduces the number of LLM calls (faster, cheaper)
 * - Allows the model to consider context holistically
 * - May produce more coherent decisions
 * - But requires more sophisticated prompting
 */

import type { LinearOperation, SlackDocument, MeetingTranscript, GithubPrDocument } from './types';
import { Agent, run, type Tool } from '@openai/agents';
import { LinearOperationSchema } from './types';
import { createLinearTaskLookupTool, createMockLinearTaskLookupTool } from './mcp/linearTaskLookup';
import { buildSingleAgentMeetingPrompt } from './prompts/meetingTranscriptExtraction';
import { buildSingleAgentGithubPrompt } from './prompts/githubPrExtraction';
import { deduplicateOperations, validateUniqueIssueIds } from './utils/deduplication';
import { mapSlackToLinearId } from './utils/userMapping';
import { getTeamStateInfo, type TeamStateInfo } from './utils/teamStateCache';
import { createLinearTaskSearchProvider } from './search/provider';
import { buildRecentTasksPromptSection } from './search/recentTasks';
import { createLogger } from '@corporate-context/backend-common';
import { buildSingleAgentSlackPrompt } from './prompts/slackMessageExtraction';
const logger = createLogger('exponent-core');

/**
 * Simple representation of a Linear issue for frozen state mode
 */
export interface SimpleLinearIssue {
  id: string;
  title: string;
  description?: string;
  assigneeId?: string;
  assignee?: string;
  priority?: string;
  stateId?: string;
  state?: string; // State name (e.g., "In Progress") - from eval-capture
  [key: string]: unknown;
}

/**
 * Linear context for resolution
 */
export interface LinearContext {
  /** Linear API key (required for live search mode) */
  apiKey: string;

  /** Team name for scoping searches */
  teamName?: string;

  /** Team ID for Linear operations (used in CREATE operations) */
  teamId: string;

  /** Optional override for which Linear search provider to use */
  searchProvider?: 'grapevine' | 'linear-api';

  /** Grapevine configuration when using the Grapevine MCP search provider */
  grapevine?: {
    apiKey: string;
    mcpUrl: string;
    tenantId: string;
  };

  /**
   * Frozen Linear state for reproducible evaluations.
   * When provided, the agent uses this state instead of live search.
   * This enables deterministic testing against a known set of issues.
   */
  existingIssues?: SimpleLinearIssue[];
}

/**
 * Metadata about the source of the tasks
 */
export interface TaskSourceMetadata {
  /** Source type (e.g., 'slack') */
  source: string;

  /** Unique identifier for this source instance */
  sourceId: string;

  /** Optional Slack message link to include in Linear issues */
  slackMessageLink?: string;

  /**
   * Optional formatted diff showing what changed from previous processing
   * Used when reprocessing documents to help agent avoid duplicate task creation
   */
  contentDiff?: string;
}

/**
 * Result returned from strategy.process()
 */
export interface ProcessResult {
  /** Linear operations to apply */
  operations: LinearOperation[];
}

/**
 * Single-agent strategy: combined extraction and resolution
 *
 * Uses one agent to:
 * - Extract actionable tasks from the artifact
 * - Compare them against existing Linear state
 * - Decide on operations (CREATE/UPDATE/SKIP)
 *
 * All in a single LLM invocation.
 */
export class SingleAgentStrategy {
  readonly name = 'single-agent';

  async process(
    input: SlackDocument | MeetingTranscript | GithubPrDocument,
    linearContext: LinearContext,
    metadata: TaskSourceMetadata
  ): Promise<ProcessResult> {
    logger.info(`Processing ${metadata.source} artifact`, {
      strategy: this.name,
      source: metadata.source,
      sourceId: metadata.sourceId,
    });

    // If existingIssues is provided, use frozen state mode (no live search)
    if (linearContext.existingIssues !== undefined) {
      logger.debug('Using frozen state mode (prompt injection)', {
        strategy: this.name,
        existingIssuesCount: linearContext.existingIssues.length,
      });
      const operations = await this.processWithFrozenState(
        input,
        linearContext.existingIssues,
        metadata,
        linearContext
      );
      return { operations };
    }

    // Otherwise use live search mode
    const operations = await this.processWithMcp(input, linearContext, metadata);
    return { operations };
  }

  /**
   * Process artifact with Linear search access via configurable provider
   */
  private async processWithMcp(
    input: SlackDocument | MeetingTranscript | GithubPrDocument,
    linearContext: LinearContext,
    metadata: TaskSourceMetadata
  ): Promise<LinearOperation[]> {
    const teamName = linearContext.teamName;

    const providerName = linearContext.searchProvider ?? 'linear-api';

    if (!teamName && providerName === 'grapevine') {
      throw new Error(
        'Linear team name is required for the Grapevine search provider. Provide teamName in LinearContext when using Grapevine.'
      );
    }

    const apiKey = linearContext.apiKey;

    if (!apiKey) {
      throw new Error('Linear API key is required');
    }

    if (!linearContext.teamId) {
      throw new Error('Linear team ID is required in LinearContext');
    }

    const provider = await createLinearTaskSearchProvider({
      provider: providerName,
      teamName: teamName ?? '',
      teamId: linearContext.teamId,
      linearApiKey: apiKey,
      grapevineApiKey: linearContext.grapevine?.apiKey,
      grapevineMcpUrl: linearContext.grapevine?.mcpUrl,
    });

    logger.debug('Using search provider for Linear task search', {
      strategy: this.name,
      provider: provider.name,
    });

    const linearTaskLookupTool = createLinearTaskLookupTool({
      provider,
      teamName,
    });

    try {
      logger.debug('Starting agent execution', {
        strategy: this.name,
      });
      const operations = await this.runSingleAgent(input, metadata, linearContext, [
        linearTaskLookupTool,
      ]);
      logger.info('Agent execution complete', {
        strategy: this.name,
        operationsCount: operations.length,
      });
      return operations;
    } finally {
      logger.debug('Closing search provider connection', {
        strategy: this.name,
        provider: provider.name,
      });
      await provider.close();
      logger.debug('Search provider connection closed', {
        strategy: this.name,
        provider: provider.name,
      });
    }
  }

  /**
   * Process artifact with frozen Linear state (no live search)
   * Uses a mock linear_task_lookup tool that returns the frozen state,
   * so the agent uses the same prompt and tool-based flow as production.
   */
  private async processWithFrozenState(
    input: SlackDocument | MeetingTranscript | GithubPrDocument,
    linearState: SimpleLinearIssue[],
    metadata: TaskSourceMetadata,
    linearContext: LinearContext
  ): Promise<LinearOperation[]> {
    logger.debug('Using frozen Linear state with mock tool', {
      strategy: this.name,
      issueCount: linearState.length,
    });

    // Create mock tool that returns frozen state
    const mockTool = createMockLinearTaskLookupTool(linearState);

    // Pass skipLiveApis=true to avoid fetching recent tasks from live Linear API
    const operations = await this.runSingleAgent(
      input,
      metadata,
      linearContext,
      [mockTool],
      true // skipLiveApis
    );

    logger.info('Generated operations from frozen state', {
      strategy: this.name,
      operationsCount: operations.length,
    });

    return operations;
  }

  /**
   * Run the single agent that does extraction + resolution
   *
   * @param skipLiveApis - When true, skip fetching recent tasks (used for frozen state evals)
   */
  private async runSingleAgent(
    input: SlackDocument | MeetingTranscript | GithubPrDocument,
    metadata: TaskSourceMetadata,
    linearContext: LinearContext,
    tools?: Tool<unknown>[],
    skipLiveApis = false
  ): Promise<LinearOperation[]> {
    // Get teamId from context
    const teamId = linearContext.teamId;
    if (!teamId) {
      throw new Error('LINEAR_TEAM_ID is required. Set it in LinearContext.');
    }

    let teamStateInfo: TeamStateInfo | undefined;
    if (linearContext.apiKey && !skipLiveApis) {
      try {
        teamStateInfo = await getTeamStateInfo(linearContext.apiKey, teamId);
      } catch (error) {
        logger.warn('Failed to fetch team state info', {
          strategy: this.name,
          teamId,
          error,
        });
      }
    }

    // Only fetch recent tasks for live search mode (not frozen state evals)
    let recentTasksSection: string | null = null;
    if (linearContext.apiKey && !skipLiveApis) {
      recentTasksSection = await buildRecentTasksPromptSection({
        apiKey: linearContext.apiKey,
        teamId,
        limit: 20,
      });
    }

    // Determine artifact type and build appropriate prompt
    let artifactType: 'meeting' | 'slack' | 'github';
    let systemPrompt: string;
    let userPrompt: string;

    if ('prNumber' in input || 'repository' in input) {
      artifactType = 'github';
      systemPrompt = buildSingleAgentGithubPrompt();

      // Build GitHub PR user prompt
      const github = input as GithubPrDocument;
      userPrompt = `
Document ID: ${github.repository ?? 'github'}-pr-${github.prNumber ?? Date.now()}

Repository: ${github.repository ?? 'Unknown Repository'}
PR Number: ${github.prNumber ?? 'Unknown'}
Title: ${github.title ?? 'Untitled PR'}
Author: ${github.author ?? 'Unknown'}
Date: ${github.date ?? new Date().toISOString()}

** BEGIN GITHUB PR **
${github.content}
** END GITHUB PR **
${metadata.contentDiff ? `\n\n${metadata.contentDiff}` : ''}
`;
    } else if ('attendees' in input || metadata.source === 'gather') {
      artifactType = 'meeting';
      systemPrompt = buildSingleAgentMeetingPrompt(teamId);

      // Build meeting user prompt
      const meeting = input as MeetingTranscript;
      userPrompt = `
Document ID: meeting-${meeting.date || Date.now()}

Meeting Title: ${meeting.title || 'Unknown'}
Date: ${meeting.date || 'Unknown'}
Attendees: ${meeting.attendees?.join(', ') || 'Unknown'}

** BEGIN MEETING TRANSCRIPT **
${meeting.content}
** END MEETING TRANSCRIPT **
${metadata.contentDiff ? `\n\n${metadata.contentDiff}` : ''}
`;
    } else {
      artifactType = 'slack';
      systemPrompt = buildSingleAgentSlackPrompt(teamId);

      // Build Slack user prompt
      const slack = input as SlackDocument;
      userPrompt = `
Document ID: ${slack.documentId || `slack-${Date.now()}`}

Channel: ${slack.channel || 'Unknown'}
Date: ${slack.date || 'Unknown'}
Participants: ${slack.participants?.join(', ') || 'Unknown'}${
        metadata.slackMessageLink
          ? `
Slack Message Link: ${metadata.slackMessageLink}`
          : ''
      }

** BEGIN SLACK CONVERSATION **
${slack.content}
** END SLACK CONVERSATION **
`;
    }

    logger.debug('Loading prompt', {
      strategy: this.name,
      artifactType,
    });

    if (recentTasksSection) {
      userPrompt += `

${recentTasksSection}
`;
    }

    // Add tool-based instructions (used for both live search and frozen state with mock tool)
    userPrompt += `

INSTRUCTIONS:
1. Extract actionable tasks from the input above
2. Use linear_task_lookup to find existing Linear tasks that might be related
   - This tool is already scoped to Linear tasks only
   - Use a max of two keywords in your search query, and never use quotes
   - Over-searching is better than being too specific and not finding any results
3. Compare your extracted tasks against the search results
4. Decide whether to CREATE, UPDATE, SKIP, or REQUEST_CLARIFICATION for each task
5. Return a JSON array of operations

CRITICAL:
- DO NOT write code or describe your search plan
- ACTUALLY CALL linear_task_lookup with relevant queries
- Try different search terms if needed (task title keywords, assignee names, etc.)
- Compare tasks based on the search results you received
- If searches return no matching tasks, CREATE new tasks for actionable items
- If you find NO actionable tasks in the document (e.g., casual conversation, holiday reminders, no work commitments), return a single SKIP operation explaining why:
  { "action": "SKIP", "skipData": { "reason": "Brief explanation" }, "confidence": 95, "reasoning": "Detailed reasoning" }
- After searching and analyzing, return ONLY valid JSON with your decisions
`;

    // Create agent
    const agent = new Agent({
      name: 'Single Agent Task Processor',
      instructions: systemPrompt,
      model: process.env.TASK_EXTRACTION_MODEL || 'gpt-5',
      tools,
    });

    // Run agent
    const result = await run(agent, userPrompt, {
      maxTurns: 25,
    });

    // Parse response
    const finalOutput = result.finalOutput;
    if (!finalOutput || typeof finalOutput !== 'string') {
      throw new Error('Agent did not return a valid response');
    }

    // Debug: log raw LLM output
    logger.info('Raw agent response:', {
      strategy: this.name,
      responseLength: finalOutput.length,
      responsePreview: finalOutput.substring(0, 500),
      fullResponse: finalOutput,
    });

    // Strip markdown code fences if present
    let content = finalOutput;
    if (content.includes('```json')) {
      const parts = content.split('```json');
      if (parts[1]) {
        const innerParts = parts[1].split('```');
        if (innerParts[0]) {
          content = innerParts[0].trim();
        }
      }
    } else if (content.includes('```')) {
      const parts = content.split('```');
      if (parts[1]) {
        const innerParts = parts[1].split('```');
        if (innerParts[0]) {
          content = innerParts[0].trim();
        }
      }
    }

    // Parse JSON
    let parsed;
    try {
      parsed = JSON.parse(content);
    } catch (error) {
      // Log at debug level since rawOutput contains PII (agent responses)
      logger.debug('Failed to parse JSON from agent response', {
        strategy: this.name,
        error: error instanceof Error ? error.message : error,
        rawOutput: finalOutput,
      });
      throw new Error(`Failed to parse JSON: ${error instanceof Error ? error.message : error}`);
    }

    // Handle both array and object responses
    const operations: LinearOperation[] = [];
    const operationsArray = Array.isArray(parsed) ? parsed : parsed.operations || [parsed];

    for (const op of operationsArray) {
      // Clean up empty objects
      if (op.updateData && Object.keys(op.updateData).length === 0) {
        delete op.updateData;
      }
      if (op.skipData && Object.keys(op.skipData).length === 0) {
        delete op.skipData;
      }
      if (op.createData && Object.keys(op.createData).length === 0) {
        delete op.createData;
      }

      // Validate schema
      try {
        const validated = LinearOperationSchema.parse(op);
        operations.push(validated);
      } catch (error) {
        // Log at debug level since operation contains PII
        logger.debug('Schema validation error for operation', {
          strategy: this.name,
          operation: op,
          error,
        });
        // Don't throw - just skip invalid operations
        logger.warn('Skipping invalid operation', {
          strategy: this.name,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    // ALWAYS deduplicate operations as a hard safety net
    // This ensures we never return multiple operations for the same issue ID
    const validation = validateUniqueIssueIds(operations);

    if (!validation.isValid) {
      logger.warn('Detected duplicate operations', {
        strategy: this.name,
        duplicateCount: validation.duplicateCount,
        duplicateIssueIds: validation.duplicateIssueIds,
      });
      logger.debug('Applying automatic deduplication', {
        strategy: this.name,
      });
    }

    // UNCONDITIONALLY deduplicate - even if validation passes, apply deduplication
    // This protects against any edge cases or bugs in the validation logic
    const deduplicatedOperations = deduplicateOperations(operations);

    if (!validation.isValid) {
      logger.debug('Deduplication complete', {
        strategy: this.name,
        before: operations.length,
        after: deduplicatedOperations.length,
      });
    }

    // Map Slack user identifiers to Linear user IDs
    const mappedOperations = this.mapAssigneeIds(deduplicatedOperations, metadata.source);

    // Convert state strings to Linear state UUIDs
    const finalOperations = this.convertStatesToUUIDs(mappedOperations, teamId, teamStateInfo);

    return finalOperations;
  }

  /**
   * Convert state strings to Linear state UUIDs
   *
   * This post-processing step converts standardized state strings
   * ("todo", "in_progress", "done", "canceled") to Linear state UUIDs
   * based on the team state mapping.
   */
  private convertStatesToUUIDs(
    operations: LinearOperation[],
    teamId: string,
    stateInfo: TeamStateInfo | undefined
  ): LinearOperation[] {
    if (!stateInfo) {
      logger.warn('No state mapping available for team. State fields will be removed', {
        strategy: this.name,
        teamId,
      });
      return this.stripStateFields(operations);
    }

    return operations.map((op) => {
      if (op.action === 'CREATE' && op.createData?.state) {
        const stateString = op.createData.state;
        const stateId =
          stateInfo.stateIdsByKey[stateString as keyof TeamStateInfo['stateIdsByKey']];
        if (stateId) {
          logger.debug('Mapped state to Linear state ID', {
            strategy: this.name,
            stateString,
            stateId,
          });
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          const { state, ...rest } = op.createData;
          return {
            ...op,
            createData: {
              ...rest,
              stateId,
            },
          };
        }

        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { state, ...rest } = op.createData;
        return {
          ...op,
          createData: rest,
        };
      }

      if (op.action === 'UPDATE' && op.updateData?.state) {
        const stateString = op.updateData.state;
        const stateId =
          stateInfo.stateIdsByKey[stateString as keyof TeamStateInfo['stateIdsByKey']];
        if (stateId) {
          logger.debug('Mapped state to Linear state ID', {
            strategy: this.name,
            stateString,
            stateId,
          });
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          const { state, ...rest } = op.updateData;
          return {
            ...op,
            updateData: {
              ...rest,
              stateId,
            },
          };
        }

        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { state, ...rest } = op.updateData;
        return {
          ...op,
          updateData: rest,
        };
      }

      return op;
    });
  }

  private stripStateFields(operations: LinearOperation[]): LinearOperation[] {
    return operations.map((op) => {
      const newOp = { ...op };
      if (op.action === 'CREATE' && op.createData?.state) {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { state, ...rest } = op.createData;
        newOp.createData = rest;
      }
      if (op.action === 'UPDATE' && op.updateData?.state) {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { state, ...rest } = op.updateData;
        newOp.updateData = rest;
      }
      return newOp;
    });
  }

  /**
   * Map Slack user identifiers to Linear user IDs in assigneeId fields
   *
   * This post-processing step allows the LLM to use natural language names
   * (e.g., "Kumail", "kumail", "Kumail Jaffer") in the assigneeId field,
   * which we then map to the correct Linear user UUID.
   */
  private mapAssigneeIds(operations: LinearOperation[], source: string): LinearOperation[] {
    // Only map for Slack sources
    const shouldMap = source === 'slack';
    if (!shouldMap) {
      return operations;
    }

    return operations.map((op) => {
      if (op.action === 'CREATE' && op.createData?.assigneeId) {
        const linearId = mapSlackToLinearId(op.createData.assigneeId);
        if (linearId) {
          logger.debug('Mapped assignee to Linear ID', {
            strategy: this.name,
            slackId: op.createData.assigneeId,
            linearId,
          });
          return {
            ...op,
            createData: {
              ...op.createData,
              assigneeId: linearId,
            },
          };
        } else {
          logger.warn('Could not map assignee to Linear ID - setting to null', {
            strategy: this.name,
          });
          logger.debug('Assignee mapping details', {
            strategy: this.name,
            slackId: op.createData.assigneeId,
          });
          return {
            ...op,
            createData: {
              ...op.createData,
              assigneeId: null,
            },
          };
        }
      } else if (op.action === 'UPDATE' && op.updateData?.assigneeId) {
        const linearId = mapSlackToLinearId(op.updateData.assigneeId);
        if (linearId) {
          logger.debug('Mapped assignee to Linear ID', {
            strategy: this.name,
            slackId: op.updateData.assigneeId,
            linearId,
          });
          return {
            ...op,
            updateData: {
              ...op.updateData,
              assigneeId: linearId,
            },
          };
        } else {
          logger.warn('Could not map assignee to Linear ID - keeping original', {
            strategy: this.name,
          });
          logger.debug('Assignee mapping details', {
            strategy: this.name,
            slackId: op.updateData.assigneeId,
          });
        }
      }
      return op;
    });
  }
}
