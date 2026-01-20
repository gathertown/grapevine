/**
 * Triage Agent Strategy for Slack message triage
 * Ported from @exponent/task-extraction
 *
 * This strategy uses Grapevine's ask_agent tool to:
 * 1. Make a single comprehensive call to ask_agent with the Slack conversation
 * 2. Ask agent analyzes, searches for related tickets, and returns structured JSON
 * 3. Convert the JSON response into Linear operations
 */

import { Agent, run, tool, type Tool } from '@openai/agents';
import { z } from 'zod';
import { jsonrepair } from 'jsonrepair';
import {
  SlackDocument,
  ProcessResult,
  TriageAnalysis,
  TriageAnalysisSchema,
  LinearOperation,
  TaskAction,
  AskAgentMetrics,
} from './types';
import { logger } from '../utils/logger';
import { TenantSlackApp } from '../TenantSlackApp';
import { callGetDocumentViaMCP } from '../common';

/**
 * Configuration for triage agent
 */
interface TriageAgentConfig {
  model: string;
}

const DEFAULT_CONFIG: TriageAgentConfig = {
  model: process.env.TASK_EXTRACTION_MODEL || 'gpt-5',
};

/**
 * Repair common JSON issues before parsing
 */
function repairJson(jsonStr: string): string {
  try {
    return jsonrepair(jsonStr);
  } catch {
    // If jsonrepair fails, return original string
    return jsonStr;
  }
}

/**
 * Triage Agent Strategy
 *
 * Uses Grapevine's ask_agent tool to triage Slack messages
 * and determine appropriate Linear operations.
 */
export class TriageAgentStrategy {
  readonly name = 'triage-agent';
  private config: TriageAgentConfig;
  private askAgentMetrics?: AskAgentMetrics;

  constructor(config?: Partial<TriageAgentConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Process a Slack document and return Linear operations
   */
  async process(
    input: SlackDocument,
    userId: string,
    tenantSlackApp: TenantSlackApp
  ): Promise<ProcessResult> {
    logger.info('Processing Slack message for triage', {
      strategy: this.name,
    });

    return await this.processWithGrapevine(input, userId, tenantSlackApp);
  }

  /**
   * Process with Grapevine's ask_agent tool
   */
  private async processWithGrapevine(
    input: SlackDocument,
    userId: string,
    tenantSlackApp: TenantSlackApp
  ): Promise<ProcessResult> {
    // Create ask_agent tool that uses makeBackendRequest
    const askAgentTool = tool({
      name: 'ask_agent',
      description:
        'Triage questions and content through Grapevine. Must return complete JSON structure with triage analysis.',
      parameters: z.object({
        query: z
          .string()
          .describe('Comprehensive query requesting full triage analysis with JSON response'),
      }),
      execute: async (args: { query: string }) => {
        const { run } = await tenantSlackApp.createTriageRunners(
          { role: 'user', content: args.query, files: input.files },
          userId,
          {
            nonBillable: true,
          }
        );

        const response = await run('ask_agent', { outputFormat: 'markdown' });

        // Extract metrics from the response
        if (response) {
          const answer = response.answer || '';
          const originalResponse = JSON.stringify(response);

          this.askAgentMetrics = {
            answerLength: answer.length,
            answerPreview: answer.substring(0, 200),
            originalResponseLength: originalResponse.length,
            compressionRatio: (answer.length / originalResponse.length) * 100,
          };
        }

        return response?.answer;
      },
    });

    // Create get_document tool for fetching duplicate ticket descriptions
    const getDocumentTool = tool({
      name: 'get_document',
      description:
        'Fetch full document content by document_id from Grapevine. Use this to retrieve duplicate ticket descriptions.',
      parameters: z.object({
        document_id: z
          .string()
          .describe(
            'The document_id to fetch (e.g., "issue_d0cede8a-292c-43d8-9d62-d30b1a533c44")'
          ),
      }),
      execute: async (args: { document_id: string }) => {
        // Check if tenant app has callGetDocument method (eval mode with API key)
        // Otherwise use callGetDocumentViaMCP (production with JWT)
        const response =
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          typeof (tenantSlackApp as any).callGetDocument === 'function'
            ? // eslint-disable-next-line @typescript-eslint/no-explicit-any
              await (tenantSlackApp as any).callGetDocument(args.document_id)
            : await callGetDocumentViaMCP(tenantSlackApp.tenantId, args.document_id);

        logger.info('get_document tool response', {
          document_id: args.document_id,
          hasContent: !!response?.content,
        });
        return response?.content;
      },
    });

    logger.info('Starting triage agent execution', {
      strategy: this.name,
    });
    const result = await this.runTriageAgent(input, [askAgentTool, getDocumentTool]);
    logger.info('Triage agent execution complete', {
      strategy: this.name,
      operationsCount: result.operations.length,
    });
    return result;
  }

  /**
   * Run the triage agent
   */
  private async runTriageAgent(
    input: SlackDocument,
    tools?: Tool<unknown>[]
  ): Promise<ProcessResult> {
    // Build prompts
    const systemPrompt = this.buildTriageSystemPrompt();
    const userPrompt = this.buildUserPrompt(input);

    // Create agent
    const agent = new Agent({
      name: 'Triage Agent Task Processor',
      instructions: systemPrompt,
      model: this.config.model,
      tools,
    });

    // Run agent
    try {
      const result = await run(agent, userPrompt, {
        maxTurns: 3,
      });

      // Parse response
      const finalOutput = result.finalOutput;
      if (!finalOutput || typeof finalOutput !== 'string') {
        throw new Error('Triage agent did not return a valid response');
      }

      // Parse JSON with validation
      let parsed;
      try {
        // Strip markdown code blocks if present
        let content = finalOutput;
        if (content.includes('```json')) {
          content = content.split('```json')[1].split('```')[0].trim();
        } else if (content.includes('```')) {
          content = content.split('```')[1].split('```')[0].trim();
        }

        // Repair common JSON issues
        content = repairJson(content);
        parsed = JSON.parse(content);
      } catch (error) {
        logger.error('Failed to parse JSON from triage agent response', {
          strategy: this.name,
          error: error instanceof Error ? error.message : error,
        });
        throw new Error(`Failed to parse JSON: ${error instanceof Error ? error.message : error}`);
      }

      // Validate against Zod schema
      let triageAnalysis: TriageAnalysis;
      try {
        triageAnalysis = TriageAnalysisSchema.parse(parsed);
      } catch (error) {
        logger.error('Schema validation error for triage analysis', {
          strategy: this.name,
          error:
            error instanceof z.ZodError
              ? error.errors.map((e) => `${e.path.join('.')}: ${e.message}`)
              : error instanceof Error
                ? error.message
                : String(error),
        });
        throw new Error(
          `Schema validation failed: ${
            error instanceof z.ZodError
              ? error.errors.map((e) => `${e.path.join('.')}: ${e.message}`).join(', ')
              : error instanceof Error
                ? error.message
                : error
          }`
        );
      }

      const operations: LinearOperation[] = [];

      logger.info('Triage analysis complete', {
        strategy: this.name,
        relatedTicketsCount: triageAnalysis.relatedTickets?.length || 0,
        operationAction: triageAnalysis.operation.action,
      });

      switch (triageAnalysis.operation.action) {
        case TaskAction.CREATE:
          operations.push(triageAnalysis.operation);
          break;
        case TaskAction.UPDATE:
          operations.push(triageAnalysis.operation);
          break;
        case TaskAction.SKIP:
          operations.push(triageAnalysis.operation);
          break;
        default:
          logger.error('Unknown operation action', {
            strategy: this.name,
            action: triageAnalysis.operation.action,
          });
          throw new Error(`Unhandled operation action: ${triageAnalysis.operation.action}`);
      }

      return { operations, triageAnalysis, askAgentMetrics: this.askAgentMetrics };
    } catch (error) {
      logger.error('[runTriageAgent] Agent run failed:', {
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : 'No stack',
      });
      throw error;
    }
  }

  /**
   * Build the system prompt for the triage agent
   */
  private buildTriageSystemPrompt(): string {
    return `You are a triage agent that analyzes incoming Slack messages and determines appropriate Linear operations.

# Workflow

Your workflow has 3 steps:

1. **Call ask_agent ONCE with a comprehensive query**

   Query structure (keep concise to preserve tokens):
   \`\`\`
   Analyze this Slack conversation and provide complete triage analysis:

   [IF USER PROMPT MENTIONS EXISTING LINEAR TICKET, INCLUDE THAT INFO HERE - ticket ID, title, URL, and description]

   [SLACK CONVERSATION]

   Tasks:
   1. Explain the issue
      - IMPORTANT: If an existing Linear ticket is mentioned above, it will contain extra details that explains the issue
   2. Judge if this report is actionable (see criteria below)
   3. Search for related Linear tickets (return document_id format "issue_{uuid}" AND issue_id format "DES-892")
   4. Construct what a Linear ticket would contain: title and description

   ACTIONABLE CRITERIA:
   - Has clear description of what's wrong OR what's requested
   - Provides enough context to understand the issue
   - NOT just "something doesn't work" without details
   If report is too vague, set isActionable=false and explain why in insufficientReason.

   TITLE: Clear and actionable. Example: "OAuth fails with 'invalid_scope' error"

   DESCRIPTION: Use markdown headers (##) for sections: ## Summary, ## Root Cause, ## Reproduction Steps (bugs only), ## Current Behavior (bugs only), ## Expected Behavior, ## Related Context (3-5 items with markdown links).

   ROOT CAUSE ANALYSIS:
   - Take a pass at identifying the likely root cause of the issue
   - ONLY include high-confidence probable root causes - do NOT hallucinate or speculate
   - Examples of good root causes: "When users connect Google Calendar but deny some of the required OAuth permissions (specifically the "invasive third calendar permission" for calendar.acls.readonly), the backend's OAuth validation in googleOAuth.ts redirects to /calendar/google/error. However, this frontend route didn't exist, causing a 404 error."
   - Examples to AVOID: "Probably the database is down", "Maybe a memory leak" (too speculative)

   Return response as JSON matching this EXACT structure:
   {
     "issueSummary": "1-2 sentence overview of what user reported",
     "severity": "low|medium|high|critical",
     "isActionable": true or false,
     "insufficientReason": "why report lacks details (only if isActionable=false)",
     "relatedTickets": [
       {
         "ticketId": "DES-123",
         "documentId": "issue_uuid-here",
         "title": "ticket title",
         "url": "https://linear.app/... (optional)",
         "confidence": 0.0-1.0,
         "reasoning": "why this ticket is related"
       }
     ],
     "constructedTicket": {
       "title": "Clear, actionable title",
       "description": "Full description with Summary, Root Cause, Reproduction Steps, Current Behavior, Expected Behavior, Related Context sections"
     }
   }
   \`\`\`

2. **YOU (triage agent) apply mechanical decision rule**

   MANDATORY DECISION RULE (apply mechanically, no exceptions):

   - IF user prompt mentioned existing Linear ticket AND ask_agent found it in relatedTickets: ACTION = UPDATE (use that ticket)
   - ELSE IF highest relatedTickets[].confidence ≥ 0.9: ACTION = UPDATE
   - ELSE IF isActionable = false: ACTION = SKIP
   - ELSE: ACTION = CREATE

   Example: highest confidence = 0.92 → 0.92 ≥ 0.9 = TRUE → UPDATE
   Example with existing ticket: user prompt says "DES-123" → ask_agent finds DES-123 in search → UPDATE DES-123

3. **YOU (triage agent) construct and return complete TriageAnalysis JSON**

   **If UPDATE**:
   a. Call get_document(documentId) to fetch existing ticket description
   b. Use ask_agent's constructedTicket.description as the "full CREATE description"
   c. Compare constructedTicket.description against existing description from get_document
   d. Extract ONLY new information not already present:
      - New user quotes/feedback
      - New behavioral details
      - New related tickets/context links
   e. Format delta in descriptionAppend using structured sections:
      - ### New User Feedback (only if new quotes/feedback)
      - ### Additional Details (only if new reproduction steps/behaviors)
      - ### Related Context (always include new related tickets as markdown links)
   f. Return complete TriageAnalysis JSON:
      {
        "issueSummary": "<from ask_agent response>",
        "relatedTickets": "<from ask_agent response>",
        "operation": {
          "action": "UPDATE",
          "confidence": <your confidence 0-100>,
          "reasoning": "<your reasoning>",
          "updateData": {
            "issueId": "string (e.g., DES-123)",
            "documentId": "string (e.g., issue_uuid-format)",
            "descriptionAppend": <from ask_agent response>
          }
        }
      }

   **If SKIP**:
   Return complete TriageAnalysis JSON:
   {
     "issueSummary": "<from ask_agent response>",
     "relatedTickets": "<from ask_agent response>",
     "operation": {
       "action": "SKIP",
       "confidence": <your confidence 0-100>,
       "reasoning": "<your reasoning>",
       "skipData": {
         "issueId": null,
         "title": "<from constructedTicket>",
         "reason": "<from insufficientReason>"
       }
     }
   }

   **If CREATE**:
   Return complete TriageAnalysis JSON:
   {
     "issueSummary": "<from ask_agent response>",
     "relatedTickets": "<from ask_agent response>",
     "operation": {
       "action": "CREATE",
       "confidence": <your confidence 0-100>,
       "reasoning": "<your reasoning>",
       "createData": {
         "title": "<from constructedTicket>",
         "description": "<from constructedTicket>"
       }
     }
   }

# ask_agent Response Schema

ask_agent MUST return this EXACT JSON structure (no operation field):

\`\`\`json
{
  "issueSummary": "string (1-2 sentences)",
  "severity": "low" | "medium" | "high" | "critical",
  "isActionable": true | false,
  "insufficientReason": "string (only if isActionable=false, otherwise omit)",
  "relatedTickets": [
    {
      "ticketId": "string (e.g., DES-123)",
      "documentId": "string (e.g., issue_uuid-format)",
      "title": "string",
      "url": "string (optional)",
      "confidence": number (0.0-1.0),
      "reasoning": "string"
    }
  ],
  "constructedTicket": {
    "title": "string (clear and actionable)",
    "description": "string (with Summary, Root Cause, Reproduction Steps, etc. sections)"
  }
}
\`\`\`

CRITICAL JSON REQUIREMENTS:
- Valid, parseable JSON with no syntax errors
- NO trailing commas
- ALL required fields present
- Proper comma separation between properties
- Strings properly quoted and escaped
- Numbers are numbers (not strings): confidence is 0.85, not "0.85"

# Examples of ask_agent Responses

Example 1 - Actionable new issue (low confidence related tickets):
\`\`\`json
{
  "issueSummary": "User cannot connect their Google Calendar to Gather, authentication flow returns a 404 error",
  "severity": "high",
  "isActionable": true,
  "relatedTickets": [
    {
      "ticketId": "DES-456",
      "documentId": "issue_abc123-uuid",
      "title": "Calendar sync failing for Outlook users",
      "url": "https://linear.app/gather-town/issue/DES-456/calendar-sync-failing-for-outlook-users",
      "confidence": 0.65,
      "reasoning": "Similar calendar integration issue but affects different provider"
    }
  ],
  "constructedTicket": {
    "title": "Google Calendar connection fails with 404 error",
    "description": "## Summary\\n\\nUser reported that when attempting to connect their Google Calendar to Gather, the authentication flow fails with a 404 error. This prevents them from syncing their calendar events.\\n\\n## Root Cause\\n\\nWhen users connect Google Calendar but deny some of the required OAuth permissions (specifically the "invasive third calendar permission" for calendar.acls.readonly), the backend's OAuth validation in googleOAuth.ts redirects to /calendar/google/error. However, this frontend route didn't exist, causing a 404 error.\\n\\n## Reproduction Steps\\n\\n1. Navigate to Calendar settings\\n2. Click 'Connect Google Calendar'\\n3. Complete OAuth flow with at least a single scope unchecked.\\n4. Observe 404 error on redirect\\n\\n## Current Behavior\\n\\nAuthentication flow returns a 404 error during OAuth redirect. User is unable to complete calendar connection.\\n\\n## Expected Behavior\\n\\nUser should be redirected back to Gather after OAuth authentication and their Google Calendar should be successfully connected.\\n\\n## Related Context\\n\\n- [DES-456](https://linear.app/gather-town/issue/DES-456): Calendar sync failing for Outlook users - similar calendar integration issue but affects different provider"
  }
}
\`\`\`

YOU (triage agent) would then:
- Check highest confidence: 0.65 < 0.9 → not UPDATE
- Check isActionable: true → not SKIP
- Decision: CREATE with constructedTicket data

Example 2 - High confidence duplicate (≥0.9):
\`\`\`json
{
  "issueSummary": "User experiencing audio quality issues during screen sharing on Chrome 120, macOS Sonoma",
  "severity": "medium",
  "isActionable": true,
  "relatedTickets": [
    {
      "ticketId": "DES-892",
      "documentId": "issue_d0cede8a-292c-43d8-9d62-d30b1a533c44",
      "title": "Audio degradation when screen sharing enabled",
      "url": "https://linear.app/gather-town/issue/DES-892/audio-degradation-when-screen-sharing",
      "confidence": 0.95,
      "reasoning": "Exact same issue - audio quality drops during screen share, multiple users affected"
    },
    {
      "ticketId": "DES-456",
      "documentId": "issue_other-uuid",
      "title": "Screen share performance degradation",
      "url": "https://linear.app/gather-town/issue/DES-456/screen-share-performance",
      "confidence": 0.72,
      "reasoning": "Related to screen sharing but focuses on video performance rather than audio"
    }
  ],
  "constructedTicket": {
    "title": "Audio degradation when screen sharing enabled",
    "description": "## Summary\\n\\nUser experiencing audio quality issues during screen sharing. Audio cuts out every 3-5 seconds with consistent choppy pattern.\\n\\n## Root Cause\\n\\nLikely bandwidth or CPU resource contention - screen sharing video stream may be prioritized over audio stream, causing periodic audio packet drops. The consistent 3-5 second pattern suggests a buffering or bandwidth allocation issue.\\n\\n## Reproduction Steps\\n\\n1. Start screen sharing in a Gather meeting\\n2. Speak while sharing screen\\n3. Observe audio cutting out regularly\\n\\n## Current Behavior\\n\\nAudio becomes choppy and cuts out every 3-5 seconds during screen sharing sessions.\\n\\n## Expected Behavior\\n\\nAudio should remain clear and consistent during screen sharing.\\n\\n## Related Context\\n\\n- [DES-456](https://linear.app/gather-town/issue/DES-456): Screen share performance degradation - related screen sharing issue affecting video"
  }
}
\`\`\`

YOU (triage agent) would then:
- Check highest confidence: 0.95 ≥ 0.9 → UPDATE
- Call get_document("issue_d0cede8a-292c-43d8-9d62-d30b1a533c44") → returns existing description
- Compare constructedTicket.description vs existing description
- Extract new details: "Chrome 120, macOS Sonoma", "cuts out every 3-5 seconds", "consistent pattern"
- Return UPDATE operation with descriptionAppend containing new info

Example 2b - Existing ticket mentioned in user prompt:
\`\`\`json
{
  "issueSummary": "User reports additional context for existing ticket DES-892: issue also occurs on Firefox and Safari",
  "severity": "medium",
  "isActionable": true,
  "relatedTickets": [
    {
      "ticketId": "DES-892",
      "documentId": "issue_d0cede8a-292c-43d8-9d62-d30b1a533c44",
      "title": "Audio degradation when screen sharing enabled",
      "url": "https://linear.app/gather-town/issue/DES-892/audio-degradation-when-screen-sharing",
      "confidence": 1.0,
      "reasoning": "This is the exact ticket mentioned in the user prompt - user is providing additional context for this existing ticket"
    }
  ],
  "constructedTicket": {
    "title": "Audio degradation when screen sharing enabled",
    "description": "## Summary\\n\\nUser experiencing audio quality issues during screen sharing across multiple browsers.\\n\\n## Additional Details\\n\\n- Issue confirmed on Firefox and Safari in addition to Chrome\\n- Affects all major browsers"
  }
}
\`\`\`

YOU (triage agent) would then:
- User prompt mentioned existing ticket DES-892 → ask_agent found it with confidence 1.0 → UPDATE
- Call get_document("issue_d0cede8a-292c-43d8-9d62-d30b1a533c44") → returns existing description
- Compare constructedTicket.description vs existing description
- Extract new details: "Firefox and Safari confirmation"
- Return UPDATE operation with descriptionAppend containing new browser info

Example 3 - Not actionable (too vague):
\`\`\`json
{
  "issueSummary": "User mentioned something isn't working",
  "severity": "low",
  "isActionable": false,
  "insufficientReason": "User said 'something isn't working' without specifying which feature, error messages, or reproduction steps. Cannot create meaningful ticket without these details.",
  "relatedTickets": [],
  "constructedTicket": {
    "title": "User reported an issue",
    "description": "## Summary\\n\\nUser mentioned that something isn't working but did not provide details.\\n\\n## Expected Behavior\\n\\nNeed clarification on which feature, error messages, and reproduction steps."
  }
}
\`\`\`

YOU (triage agent) would then:
- Check isActionable: false → SKIP
- Return SKIP operation with insufficientReason

Example 4 - Related tickets but not duplicates (moderate confidence):
\`\`\`json
{
  "issueSummary": "Automated fatal error report with no user message",
  "severity": "low",
  "isActionable": false,
  "insufficientReason": "Automated error report without user context, stack trace, or reproduction steps. Related issues exist but none are clear duplicates.",
  "relatedTickets": [
    {
      "ticketId": "PDCT-856",
      "documentId": "issue_another-uuid",
      "title": "Unable to type a message after sending error report",
      "url": "https://linear.app/gather-town/issue/PDCT-856/unable-to-type-message",
      "confidence": 0.8,
      "reasoning": "Possibly related to why user message is missing, but not a clear duplicate"
    },
    {
      "ticketId": "PDCT-1010",
      "documentId": "issue_yet-another-uuid",
      "title": "Auto-send grapes when sending bug report for fatal error",
      "url": "https://linear.app/gather-town/issue/PDCT-1010/auto-send-grapes",
      "confidence": 0.55,
      "reasoning": "Related to fatal error reporting flow improvements"
    }
  ],
  "constructedTicket": {
    "title": "Automated fatal error report with no user message",
    "description": "## Summary\\n\\nAutomated fatal error report without actionable details.\\n\\n## Expected Behavior\\n\\nNeed stack trace or user reproduction steps to be actionable."
  }
}
\`\`\`

YOU (triage agent) would then:
- Check highest confidence: 0.8 < 0.9 → not UPDATE
- Check isActionable: false → SKIP
- Return SKIP operation with insufficientReason

# UPDATE Formatting Requirements

When creating UPDATE operations, follow these formatting rules for descriptionAppend:

1. **Use structured sections with markdown headings (###)**
   - ### New User Feedback - Include user quotes and feedback not in existing description
   - ### Additional Details - Include new reproduction steps, behaviors, or impact details
   - ### Related Context - ALWAYS include related tickets as markdown links

2. **Only append sections containing NEW information**
   - Compare constructedTicket.description against duplicateDescription from get_document
   - If a section has no new content, omit that section entirely

3. **Format Related Context as markdown links**
   - Use format: [TICKET-ID](url): Brief description
   - Include all related tickets found during triage (not just the duplicate)

4. **Example of well-formatted descriptionAppend:**
   \`\`\`
   ### New User Feedback

   - "Notification too hard to find when missed"
   - Thread "Highlighted" styling too similar to regular text

   ### Additional Details

   - Impact: Users miss important messages after returning
   - Suggested fix: Stronger contrast for missed notification indicators

   ### Related Context

   - [DES-1262](https://linear.app/...): Missed in meeting chat - related discoverability issue
   - [GCO-258](https://linear.app/...): Chat notification sound issues - related notification problem
   \`\`\`

# Role Boundaries

- **ask_agent tool**: Searches for related tickets, judges actionability, constructs ticket data
- **YOU (triage agent)**: Apply mechanical decision rule, call get_document for UPDATE, extract delta, return complete TriageAnalysis JSON

# Important Guidelines

- Call ask_agent ONCE with the Slack conversation
- Apply decision rule mechanically: confidence ≥0.9 → UPDATE, !isActionable → SKIP, else → CREATE
- For UPDATE: compare constructedTicket.description vs get_document result to extract delta
- Preserve all links exactly as provided - do not infer or modify URLs
- **CRITICAL**: Your final response MUST be complete TriageAnalysis JSON with ALL fields:
  * issueSummary (from ask_agent)
  * relatedTickets (from ask_agent)
  * operation (constructed by you with action, confidence, reasoning, and appropriate data field)`;
  }

  /**
   * Build the user prompt with Slack conversation
   */
  private buildUserPrompt(input: SlackDocument): string {
    // If there's a Linear ticket already created, include its contents for triage
    if (input.linearTicketInfo) {
      return `
** LINEAR TICKET ALREADY EXISTS **
Ticket ID: ${input.linearTicketInfo.ticketId}
Ticket URL: ${input.linearTicketInfo.ticketUrl || 'N/A'}
Title: ${input.linearTicketInfo.title || 'N/A'}

** EXISTING TICKET DESCRIPTION **
${input.linearTicketInfo.description || 'No description available'}

** SLACK CONVERSATION ABOUT THIS TICKET **
${input.content}

** TASK **
A Linear ticket (${input.linearTicketInfo.ticketId}) was already created for this conversation. Analyze the Slack conversation to determine if:
1. New information should be added to the existing ticket (UPDATE action)
2. The conversation is about a different issue and needs a new ticket (CREATE action)
3. No action is needed (SKIP action)

Focus on extracting any new context, user feedback, or additional details from the Slack conversation that aren't already in the ticket description.
`;
    }

    // Normal triage flow without pre-existing ticket
    return `
** BEGIN SLACK CONVERSATION **
${input.content}
** END SLACK CONVERSATION **
`;
  }
}
