/**
 * Description enhancer for extracted tasks
 *
 * Takes basic task information and uses ask_agent_fast to generate a more
 * structured, detailed description suitable for coding agents.
 */

import { createLogger } from '@corporate-context/backend-common';
const logger = createLogger('description-enhancer');

export interface EnhancementInput {
  /** Original task title */
  title: string;
  /** Original task description from extraction */
  description: string;
  /** Source content (Slack messages, meeting transcript, etc.) */
  sourceContent: string;
  /** Human-readable source description (e.g., "this Slack conversation", "this meeting transcript") */
  sourceDescription: string;
  /** Optional link to original source */
  sourceLink?: string;
}

export interface EnhancedDescription {
  /** Enhanced description in structured format */
  description: string;
}

export interface AskAgentFastOptions {
  /** The user query */
  query: string;
  /** Optional system prompt override */
  systemPrompt?: string;
}

/**
 * Build the system prompt for ask_agent_fast to enhance task descriptions
 */
function buildSystemPrompt(sourceLink?: string): string {
  return `You are an agent assigned to help add details to Linear tickets to better enable coding agents to implement. You'll be given a title and description of a ticket, and your job is to enrich them with MAXIMUM context from TWO sources:

1. **The provided source content** (the original discussion/conversation that spawned this ticket)
2. **Related content you find via search** (prior discussions, documentation, code, and tickets)

## YOUR TASK

**STEP 1: Search for related context (REQUIRED - DO NOT SKIP)**
You MUST perform searches before writing the description. Do at least 3-5 searches using different keywords extracted from the task. This is critical for providing comprehensive context.

Search queries to try:
- The main feature or component name mentioned in the task
- Technical terms, function names, or file paths mentioned
- The problem being solved or bug being fixed
- Related system or service names
- Key phrases from the discussion

Sources to search (in priority order):
- Slack: Prior discussions about this feature/problem (HIGHEST VALUE - human context and decisions)
- Linear: Previous tickets in the same area (often contains useful context)
- Notion: Documentation about the system
- GitHub: Only search if you need to find specific code references mentioned in discussions (raw code without context is rarely helpful for understanding intent)

DO NOT proceed to Step 2 until you have performed multiple searches. Even if some searches return no results, the search effort is required.

**STEP 2: Analyze Root Cause (CRITICAL)**
If the source content contains error logs, stack traces, or symptoms:

1. **Examine the details carefully** - error messages often contain clues about WHY something is failing, not just WHAT failed
2. **Identify the root cause** - ask "why is this happening?" not just "what error occurred?"
3. **Consider scope** - if this bug exists in one place, could it exist elsewhere?
4. **Search for relevant code** - find where this behavior originates and include specific file paths in Technical Considerations
5. **Propose a concrete fix** - not just "handle the error" but a specific implementation approach that addresses the root cause
6. **Prevention over handling** - if an error can be prevented entirely (not just caught and retried), prefer that approach. For example: proactively refresh tokens before expiry rather than only retrying after 401s.

Include your root cause analysis and proposed approach in the Technical Considerations section. A coding agent should be able to implement from your description without asking clarifying questions.

**STEP 3: Write the enriched description**
Combine what you found from searches with the provided source content to create a comprehensive ticket description.

## Summary
[1-2 sentence overview of what needs to be done]

## Context
[Why this task exists - business/user motivation, background from the discussion]

## Requirements
[What specifically needs to be built/changed/fixed - acceptance criteria mentioned, edge cases discussed]

## Key Discussion Excerpts
[Include quotes from the source content that provide important context. These raw messages help coding agents understand the nuances and intent. Format as blockquotes with attribution if possible.]

Example:
> "We should make sure to handle the edge case where the user hasn't set up their profile yet" - @alice
> "Also need to think about backwards compatibility with the old API" - @bob

## Technical Considerations
[Only include this section if specific technical approaches, technologies, constraints, or things to avoid were mentioned. Otherwise omit this section.]

## Related Context (from search)
[Include relevant information you found via your searches. Prioritize human discussions (Slack, meeting transcripts, Linear comments) over raw code. For each piece of related content, include:
- A link to the source (Slack thread, Linear ticket, Notion page, etc.)
- Key excerpts or summaries of what's relevant
- Why it's relevant to this task

Only include GitHub links if they contain highly relevant PR descriptions, issue discussions, or code that was specifically mentioned in conversations. Avoid including raw code search results that lack human context.

If you didn't find any related content, explicitly state that.]

## References
[Link to source${sourceLink ? `: ${sourceLink}` : ''}]

IMPORTANT RULES:
1. ONLY include information explicitly stated in the source content or found via search - DO NOT invent details
2. BE GENEROUS with excerpts - more raw context is better than less
3. Include specific file paths, function names, or code snippets when they're mentioned or found
4. If technical details weren't discussed, omit the Technical Considerations section entirely
5. For the Requirements section, capture what was actually decided, not hypothetical implementation steps
6. Use markdown formatting (## for headers, - for bullets, > for quotes)
7. When in doubt, include more context rather than less - coding agents benefit from seeing the original discussion

Return ONLY the enhanced description text, starting with "## Summary".`;
}

/**
 * Build the user query containing the task data
 */
function buildUserQuery(input: EnhancementInput): string {
  return `Please enrich this Linear ticket with additional context:

Source: ${input.sourceDescription}
Title: ${input.title}
Description: ${input.description}

Source content:
${input.sourceContent}`;
}

/**
 * Enhance a task description using ask_agent_fast
 *
 * @param input - Task information and source content
 * @param askAgentFast - Function to call ask_agent_fast tool (accepts options with query and optional systemPrompt)
 * @returns Enhanced description
 */
export async function enhanceTaskDescription(
  input: EnhancementInput,
  askAgentFast: (options: AskAgentFastOptions) => Promise<{ answer: string }>
): Promise<EnhancedDescription> {
  try {
    logger.info('Enhancing task description', {
      title: input.title,
    });

    const systemPrompt = buildSystemPrompt(input.sourceLink);
    const query = buildUserQuery(input);
    const result = await askAgentFast({ query, systemPrompt });

    // Ensure the result starts with our expected format
    let enhancedDescription = result.answer.trim();

    // If ask_agent_fast added extra preamble, try to extract just the formatted content
    if (!enhancedDescription.startsWith('## Summary')) {
      const summaryIndex = enhancedDescription.indexOf('## Summary');
      if (summaryIndex !== -1) {
        enhancedDescription = enhancedDescription.substring(summaryIndex);
      }
    }

    logger.info('Successfully enhanced task description', {
      title: input.title,
      originalLength: input.description.length,
      enhancedLength: enhancedDescription.length,
    });

    return {
      description: enhancedDescription,
    };
  } catch (error) {
    logger.error('Failed to enhance task description, using original', {
      title: input.title,
      error: error instanceof Error ? error.message : String(error),
    });

    // Fallback to original description if enhancement fails
    return {
      description: input.description,
    };
  }
}

/**
 * Enhance CREATE operations in-place by improving their descriptions
 *
 * @param operations - Array of Linear operations
 * @param sourceContent - Original source content (Slack messages, meeting transcript, etc.)
 * @param sourceDescription - Human-readable description of the source
 * @param askAgentFast - Function to call ask_agent_fast (accepts options with query and optional systemPrompt)
 * @param sourceLink - Optional link to original source
 * @returns Same array with enhanced descriptions for CREATE operations
 */
export async function enhanceOperations(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  operations: Array<any>,
  sourceContent: string,
  sourceDescription: string,
  askAgentFast: (options: AskAgentFastOptions) => Promise<{ answer: string }>,
  sourceLink?: string
): Promise<void> {
  const createOps = operations.filter(
    (op) => op.action === 'CREATE' && op.createData?.title && op.createData?.description
  );

  if (createOps.length === 0) {
    logger.info('No CREATE operations to enhance');
    return;
  }

  logger.info(`Enhancing ${createOps.length} CREATE operation(s)`, {
    sourceDescription,
    operations: createOps.length,
  });

  // Enhance all CREATE operations in parallel
  await Promise.all(
    createOps.map(async (op) => {
      if (!op.createData) return;

      const enhanced = await enhanceTaskDescription(
        {
          title: op.createData.title,
          description: op.createData.description,
          sourceContent,
          sourceDescription,
          sourceLink,
        },
        askAgentFast
      );

      // Update the operation in-place
      op.createData.description = enhanced.description;
    })
  );

  logger.info(`Enhanced ${createOps.length} CREATE operation(s)`);
}
