/**
 * Eval Capture Controller
 *
 * Captures real documents + Linear state as eval checkpoint files
 * for use with `yarn checkpoints` in exponent-evals.
 */

import { Router, Request, Response } from 'express';
import { logger } from '../utils/logger.js';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { getConfigValue } from '../config/index.js';
import { linearService } from '../services/linear-service.js';

export const evalCaptureRouter = Router();

interface SlackMessage {
  user?: string;
  text: string;
  ts: string;
  bot_id?: string;
  subtype?: string;
  thread_ts?: string;
}

interface SimpleLinearIssue {
  id: string;
  identifier: string;
  title: string;
  description?: string;
  assigneeId?: string;
  assignee?: string;
  priority?: number;
  state?: string;
  createdAt?: string;
}

interface CheckpointFile {
  title: string;
  type: 'slack' | 'github' | 'meeting';
  date: string;
  content: string;
  metadata: Record<string, unknown>;
}

interface TruthFile {
  output: {
    operations: [];
  };
  input: {
    docs: string[];
    linearState: SimpleLinearIssue[];
  };
}

/**
 * Parse Slack message link to extract channel ID, message timestamp, and parent thread ts
 * Link formats:
 *   - Top-level: https://workspace.slack.com/archives/C123456/p1234567890123456
 *   - Thread reply: https://workspace.slack.com/archives/C123456/p1234567890123456?thread_ts=1234567890.123456&cid=C123456
 */
function parseSlackLink(link: string): {
  channelId: string;
  messageTs: string;
  parentThreadTs?: string;
} | null {
  try {
    const url = new URL(link);
    const pathParts = url.pathname.split('/');

    // Find archives index
    const archivesIndex = pathParts.indexOf('archives');
    if (archivesIndex === -1 || archivesIndex + 2 >= pathParts.length) {
      return null;
    }

    const channelId = pathParts[archivesIndex + 1];
    const messageIdRaw = pathParts[archivesIndex + 2];

    if (!channelId || !messageIdRaw) {
      return null;
    }

    // Convert Slack message ID to timestamp
    // Format: p1234567890123456 -> 1234567890.123456
    if (!messageIdRaw.startsWith('p')) {
      return null;
    }

    const numericPart = messageIdRaw.slice(1);
    const messageTs = `${numericPart.slice(0, 10)}.${numericPart.slice(10)}`;

    // Check for thread_ts query param (indicates this is a reply in a thread)
    const parentThreadTs = url.searchParams.get('thread_ts') || undefined;

    return { channelId, messageTs, parentThreadTs };
  } catch {
    return null;
  }
}

/**
 * Parse GitHub PR URL to extract org, repo, and PR number
 * URL format: https://github.com/org/repo/pull/123
 */
function parseGitHubPrUrl(url: string): { org: string; repo: string; prNumber: number } | null {
  try {
    const parsed = new URL(url);
    const pathParts = parsed.pathname.split('/').filter(Boolean);

    if (pathParts.length < 4 || pathParts[2] !== 'pull') {
      return null;
    }

    const org = pathParts[0];
    const repo = pathParts[1];
    const prNumberStr = pathParts[3];

    if (!org || !repo || !prNumberStr) {
      return null;
    }

    const prNumber = parseInt(prNumberStr, 10);
    if (isNaN(prNumber)) {
      return null;
    }

    return { org, repo, prNumber };
  } catch {
    return null;
  }
}

/**
 * Format Slack messages like SingleAgentStrategy expects
 * Format: [ISO_TIMESTAMP] USERNAME: message
 */
function formatSlackMessages(messages: SlackMessage[], userMap: Map<string, string>): string {
  return messages
    .map((msg) => {
      const timestamp = new Date(parseFloat(msg.ts) * 1000).toISOString();
      const username = msg.user ? userMap.get(msg.user) || msg.user : 'unknown';
      return `[${timestamp}] ${username}: ${msg.text}`;
    })
    .join('\n');
}

/**
 * Check if a Slack message is from a human (not a bot)
 * Matches production message filtering logic
 */
function isHumanMessage(msg: SlackMessage): boolean {
  // Skip bot messages
  if (msg.bot_id) return false;
  // Skip messages with subtypes (except 'bot_message' which we also skip via bot_id)
  if (msg.subtype && msg.subtype.length > 0) return false;
  // Skip empty messages
  if (!msg.text?.trim()) return false;
  return true;
}

/**
 * Fetch Slack thread content matching production input format
 * @param messageTs - The timestamp of the specific linked message
 * @param parentThreadTs - The parent thread ts (from URL query param, if this is a reply)
 */
async function fetchSlackThread(
  tenantId: string,
  channelId: string,
  messageTs: string,
  parentThreadTs?: string
): Promise<{
  content: string;
  title: string;
  metadata: Record<string, unknown>;
  artifactTimestamp: string;
}> {
  const botToken = await getConfigValue('SLACK_BOT_TOKEN', tenantId);
  if (!botToken) {
    throw new Error('Slack bot not configured for this tenant');
  }

  // Use parent thread ts if this is a reply, otherwise use the message ts
  const actualThreadTs = parentThreadTs || messageTs;
  const linkedMessageTs = messageTs;

  // Fetch full thread using the correct parent ts
  const params = new URLSearchParams({
    channel: channelId,
    ts: actualThreadTs,
    inclusive: 'true',
    limit: '1000',
  });

  const response = await fetch(`https://slack.com/api/conversations.replies?${params.toString()}`, {
    headers: {
      Authorization: `Bearer ${botToken}`,
      'Content-Type': 'application/json',
    },
  });

  const data = await response.json();

  if (!data.ok) {
    throw new Error(`Slack API error: ${data.error}`);
  }

  const allMessages: SlackMessage[] = data.messages || [];

  // Step 3: Filter to human messages up to linked timestamp
  const humanMessages = allMessages.filter((msg) => {
    if (!isHumanMessage(msg)) return false;
    if (parseFloat(msg.ts) > parseFloat(linkedMessageTs)) return false;
    return true;
  });

  if (humanMessages.length === 0) {
    throw new Error('No human messages found in thread up to linked message');
  }

  // Step 4: Partition into prior messages and the linked message
  const priorMessages = humanMessages.filter(
    (msg) => parseFloat(msg.ts) < parseFloat(linkedMessageTs)
  );
  const linkedMessage = humanMessages.find((msg) => msg.ts === linkedMessageTs);
  const newMessages = linkedMessage ? [linkedMessage] : [];

  if (newMessages.length === 0) {
    throw new Error('Linked message not found or was filtered out (might be a bot message)');
  }

  // Fetch user info for all unique users
  const userIds = [...new Set(humanMessages.map((m) => m.user).filter(Boolean))];
  const userMap = new Map<string, string>();

  for (const userId of userIds) {
    if (!userId) continue;
    try {
      const userResponse = await fetch(`https://slack.com/api/users.info?user=${userId}`, {
        headers: {
          Authorization: `Bearer ${botToken}`,
          'Content-Type': 'application/json',
        },
      });
      const userData = await userResponse.json();
      if (userData.ok && userData.user) {
        userMap.set(
          userId,
          userData.user.profile?.display_name || userData.user.real_name || userData.user.name
        );
      }
    } catch {
      // Ignore user fetch errors
    }
  }

  // Step 5: Format with section headers matching production message formatting
  const sections: string[] = [];
  if (priorMessages.length > 0) {
    sections.push(
      '=== Earlier conversation (context, already processed) ===',
      formatSlackMessages(priorMessages, userMap)
    );
  }
  if (newMessages.length > 0) {
    if (sections.length > 0) {
      sections.push('');
    }
    sections.push(
      '=== New messages since last pass (process these) ===',
      formatSlackMessages(newMessages, userMap)
    );
  }
  const content = sections.join('\n');

  const firstMessage = humanMessages[0];
  const title = firstMessage?.text?.slice(0, 100) || 'Slack thread';

  // Use the linked message timestamp as the artifact timestamp
  const artifactTimestamp = new Date(parseFloat(linkedMessageTs) * 1000).toISOString();

  return {
    content,
    title,
    metadata: {
      channel: channelId,
      threadTs: actualThreadTs,
      messageCount: humanMessages.length,
      priorMessageCount: priorMessages.length,
      newMessageCount: newMessages.length,
      participants: [...userMap.values()],
    },
    artifactTimestamp,
  };
}

/**
 * Fetch document from database by metadata
 */
async function fetchDocumentFromDb(
  db: import('pg').Pool,
  source: string,
  metadataConditions: Record<string, unknown>
): Promise<{ content: string; title: string; metadata: Record<string, unknown> } | null> {
  // Build query conditions
  const conditions: string[] = [`source = $1`];
  const values: unknown[] = [source];
  let paramIndex = 2;

  for (const [key, value] of Object.entries(metadataConditions)) {
    if (typeof value === 'number') {
      conditions.push(`(metadata->>'${key}')::int = $${paramIndex}`);
    } else {
      conditions.push(`metadata->>'${key}' ILIKE $${paramIndex}`);
    }
    values.push(value);
    paramIndex++;
  }

  const query = `
    SELECT id, source, content, metadata, source_created_at
    FROM documents
    WHERE ${conditions.join(' AND ')}
    ORDER BY source_created_at DESC
    LIMIT 1
  `;

  const result = await db.query(query, values);

  if (result.rows.length === 0) {
    return null;
  }

  const row = result.rows[0];
  return {
    content: row.content,
    title: row.metadata?.title || row.metadata?.calendar_event_title || `${source} document`,
    metadata: row.metadata,
  };
}

/**
 * Fetch 20 most recent Linear issues for a team, created before a given timestamp
 * @param beforeTimestamp - ISO timestamp; only return issues created before this time
 */
async function fetchLinearIssues(
  tenantId: string,
  teamId: string,
  beforeTimestamp?: string
): Promise<SimpleLinearIssue[]> {
  const accessToken = await linearService.getValidAccessToken(tenantId);
  if (!accessToken) {
    throw new Error('Linear not connected for this tenant');
  }

  // Build query conditionally - only include filter when beforeTimestamp is provided
  // Linear doesn't accept null values in filters
  const filterClause = beforeTimestamp ? ', filter: { createdAt: { lte: $before } }' : '';
  const variableDecl = beforeTimestamp
    ? '$teamId: String!, $before: DateTimeOrDuration!'
    : '$teamId: String!';

  const query = `
    query(${variableDecl}) {
      team(id: $teamId) {
        issues(
          first: 20,
          orderBy: createdAt${filterClause}
        ) {
          nodes {
            id
            identifier
            title
            description
            assignee {
              id
              name
            }
            priority
            state {
              name
            }
            createdAt
          }
        }
      }
    }
  `;

  const variables: Record<string, string> = { teamId };
  if (beforeTimestamp) {
    variables.before = beforeTimestamp;
  }

  const response = await fetch('https://api.linear.app/graphql', {
    method: 'POST',
    headers: {
      Authorization: accessToken,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      variables,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Linear API error: ${response.status} - ${errorText}`);
  }

  const data = await response.json();

  // Check for GraphQL errors
  if (data.errors && data.errors.length > 0) {
    logger.error('Linear GraphQL errors', { errors: data.errors });
    throw new Error(
      `Linear GraphQL error: ${data.errors.map((e: { message: string }) => e.message).join(', ')}`
    );
  }

  const issues = data?.data?.team?.issues?.nodes || [];

  return issues.map(
    (issue: {
      id: string;
      identifier: string;
      title: string;
      description?: string;
      assignee?: { id: string; name: string };
      priority?: number;
      state?: { name: string };
      createdAt?: string;
    }) => ({
      id: issue.id,
      identifier: issue.identifier,
      title: issue.title,
      description: issue.description,
      assigneeId: issue.assignee?.id,
      assignee: issue.assignee?.name,
      priority: issue.priority,
      state: issue.state?.name,
      createdAt: issue.createdAt,
    })
  );
}

/**
 * Fetch a single Linear issue by identifier
 */
async function fetchSingleLinearIssue(
  accessToken: string,
  identifier: string
): Promise<SimpleLinearIssue | null> {
  const query = `
    query IssueByIdentifier($id: String!) {
      issue(id: $id) {
        id
        identifier
        title
        description
        assignee {
          id
          name
        }
        priority
        state {
          name
        }
        createdAt
      }
    }
  `;

  const trimmedId = identifier.trim();
  logger.info('Fetching Linear issue by identifier', { identifier: trimmedId });

  const response = await fetch('https://api.linear.app/graphql', {
    method: 'POST',
    headers: {
      Authorization: accessToken,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query,
      variables: { id: trimmedId },
    }),
  });

  if (!response.ok) {
    throw new Error(`Linear API error: ${response.status}`);
  }

  const data = await response.json();
  logger.info('Linear API response', {
    identifier: trimmedId,
    data: JSON.stringify(data),
  });

  const issue = data?.data?.issue;
  if (!issue) {
    return null;
  }

  return {
    id: issue.id,
    identifier: issue.identifier,
    title: issue.title,
    description: issue.description,
    assigneeId: issue.assignee?.id,
    assignee: issue.assignee?.name,
    priority: issue.priority,
    state: issue.state?.name,
    createdAt: issue.createdAt,
  };
}

/**
 * Fetch specific Linear issues by identifier (parallel)
 */
async function fetchLinearIssuesByIdentifier(
  tenantId: string,
  identifiers: string[]
): Promise<SimpleLinearIssue[]> {
  const accessToken = await linearService.getValidAccessToken(tenantId);
  if (!accessToken) {
    throw new Error('Linear not connected for this tenant');
  }

  const results = await Promise.all(
    identifiers.map((identifier) => fetchSingleLinearIssue(accessToken, identifier))
  );

  return results.filter((issue): issue is SimpleLinearIssue => issue !== null);
}

/**
 * Generate suggested filename based on document type and artifact date
 */
function generateFilename(type: string, title: string, artifactTimestamp?: string): string {
  // Use artifact timestamp if provided, otherwise fall back to current time
  const timestamp = artifactTimestamp ? new Date(artifactTimestamp) : new Date();

  // Use local time instead of UTC for human-readable filenames
  const year = timestamp.getFullYear();
  const month = String(timestamp.getMonth() + 1).padStart(2, '0');
  const day = String(timestamp.getDate()).padStart(2, '0');
  const hours = String(timestamp.getHours()).padStart(2, '0');
  const minutes = String(timestamp.getMinutes()).padStart(2, '0');
  const seconds = String(timestamp.getSeconds()).padStart(2, '0');

  const dateStr = `${year}-${month}-${day}`;
  const timeStr = `${hours}-${minutes}-${seconds}`;

  // Sanitize title for filename
  const sanitizedTitle = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .slice(0, 30)
    .replace(/-+$/, '');

  return `${dateStr}_${timeStr}_${type}-${sanitizedTitle}`;
}

/**
 * POST /api/eval/capture
 * Capture a document + Linear state as eval checkpoint files
 */
evalCaptureRouter.post('/capture', requireAdmin, async (req: Request, res: Response) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for user' });
  }

  const { slackLink, githubPrUrl, meetingTitle, meetingDate, linearTeamId, issueIdentifiers } =
    req.body;

  if (!linearTeamId) {
    return res.status(400).json({ error: 'linearTeamId is required' });
  }

  // Validate exactly one document type is provided
  const hasSlack = !!slackLink;
  const hasGithub = !!githubPrUrl;
  const hasMeeting = !!meetingTitle && !!meetingDate;
  const typeCount = [hasSlack, hasGithub, hasMeeting].filter(Boolean).length;

  if (typeCount !== 1) {
    return res.status(400).json({
      error:
        'Exactly one document type must be provided (slackLink, githubPrUrl, or meetingTitle+meetingDate)',
    });
  }

  try {
    let checkpoint: CheckpointFile;
    let docType: 'slack' | 'github' | 'meeting';
    let artifactTimestamp: string | undefined;

    // Fetch document based on type
    if (hasSlack) {
      const parsed = parseSlackLink(slackLink);
      if (!parsed) {
        return res.status(400).json({
          error:
            'Invalid Slack link format. Expected: https://workspace.slack.com/archives/CHANNEL/pTIMESTAMP',
        });
      }

      const result = await fetchSlackThread(
        tenantId,
        parsed.channelId,
        parsed.messageTs,
        parsed.parentThreadTs
      );

      docType = 'slack';
      artifactTimestamp = result.artifactTimestamp;
      checkpoint = {
        title: result.title,
        type: 'slack',
        date: new Date().toISOString().slice(0, 10),
        content: result.content,
        metadata: result.metadata,
      };
    } else if (hasGithub) {
      const parsed = parseGitHubPrUrl(githubPrUrl);
      if (!parsed) {
        return res.status(400).json({
          error: 'Invalid GitHub PR URL format. Expected: https://github.com/org/repo/pull/123',
        });
      }

      if (!req.db) {
        return res.status(500).json({ error: 'Database not available' });
      }

      const doc = await fetchDocumentFromDb(req.db, 'github', {
        organization: parsed.org,
        repository: parsed.repo,
        pr_number: parsed.prNumber,
      });

      if (!doc) {
        return res.status(404).json({
          error: `GitHub PR not found: ${parsed.org}/${parsed.repo}#${parsed.prNumber}`,
        });
      }

      docType = 'github';
      // Use PR created_at or source_created_at from metadata if available
      artifactTimestamp =
        (doc.metadata as { created_at?: string; source_created_at?: string })?.created_at ||
        (doc.metadata as { source_created_at?: string })?.source_created_at ||
        new Date().toISOString();
      checkpoint = {
        title: doc.title,
        type: 'github',
        date: new Date().toISOString().slice(0, 10),
        content: doc.content,
        metadata: doc.metadata,
      };
    } else {
      // Meeting
      if (!req.db) {
        return res.status(500).json({ error: 'Database not available' });
      }

      // Query by title (fuzzy) and date
      const query = `
        SELECT id, source, content, metadata, source_created_at
        FROM documents
        WHERE source IN ('gather', 'gong')
          AND (metadata->>'calendar_event_title' ILIKE $1
               OR metadata->>'title' ILIKE $1)
          AND source_created_at >= $2::date
          AND source_created_at < ($2::date + interval '1 day')
        ORDER BY source_created_at DESC
        LIMIT 1
      `;

      const result = await req.db.query(query, [`%${meetingTitle}%`, meetingDate]);

      if (result.rows.length === 0) {
        return res.status(404).json({
          error: `Meeting not found with title containing "${meetingTitle}" on ${meetingDate}`,
        });
      }

      const row = result.rows[0];
      docType = 'meeting';
      // Use source_created_at for meeting timestamp
      artifactTimestamp = row.source_created_at
        ? new Date(row.source_created_at).toISOString()
        : new Date(`${meetingDate}T23:59:59Z`).toISOString();
      checkpoint = {
        title: row.metadata?.calendar_event_title || row.metadata?.title || meetingTitle,
        type: 'meeting',
        date: meetingDate,
        content: row.content,
        metadata: row.metadata,
      };
    }

    // Fetch Linear issues - use specific identifiers if provided, otherwise fetch 20 most recent
    // Filter by artifact timestamp to get issues that existed at the time of the artifact
    let linearIssues: SimpleLinearIssue[];
    if (issueIdentifiers && typeof issueIdentifiers === 'string' && issueIdentifiers.trim()) {
      const identifiers = issueIdentifiers
        .split(',')
        .map((s: string) => s.trim())
        .filter(Boolean);
      linearIssues = await fetchLinearIssuesByIdentifier(tenantId, identifiers);
    } else {
      linearIssues = await fetchLinearIssues(tenantId, linearTeamId, artifactTimestamp);
    }

    // Build truth file with empty operations
    // Important results first, linearState last (it's large)
    const suggestedFilename = generateFilename(docType, checkpoint.title, artifactTimestamp);
    const truth: TruthFile = {
      output: {
        operations: [],
      },
      input: {
        docs: [`${suggestedFilename}.json`],
        linearState: linearIssues,
      },
    };

    logger.info('Eval capture successful', {
      tenantId,
      docType,
      linearIssueCount: linearIssues.length,
      operation: 'eval-capture',
    });

    return res.json({
      checkpoint,
      truth,
      suggestedFilename,
    });
  } catch (error) {
    logger.error('Eval capture failed', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId,
      operation: 'eval-capture-error',
    });

    return res.status(500).json({
      error: error instanceof Error ? error.message : 'Failed to capture eval',
    });
  }
});
