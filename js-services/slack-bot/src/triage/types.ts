/**
 * Type definitions for triage workflow
 * Ported from @exponent/task-extraction
 */

import { z } from 'zod';
import type { FileAttachment } from '../types';

/**
 * Linear ticket information extracted from Slack attachments
 */
export interface LinearTicketInfo {
  /** Linear ticket ID (e.g., "DES-123") */
  ticketId: string;

  /** Linear ticket URL */
  ticketUrl?: string;

  /** Full ticket description from Linear API */
  description?: string;

  /** Ticket title */
  title?: string;
}

/**
 * Slack document input
 */
export interface SlackDocument {
  /** Unique document identifier (e.g., channel_date) */
  documentId?: string;

  /** Slack channel name or ID */
  channel?: string;

  /** Document date (ISO 8601) */
  date?: string;

  /** List of participants in the conversation */
  participants?: string[];

  /** Formatted Slack messages and threads */
  content: string;

  /** File attachments from Slack messages */
  files?: FileAttachment[];

  /** Linear ticket information (if Linear Asks bot is present) */
  linearTicketInfo?: LinearTicketInfo;
}

/**
 * Action to take for a Linear issue
 */
export enum TaskAction {
  CREATE = 'CREATE',
  UPDATE = 'UPDATE',
  SKIP = 'SKIP',
  REQUEST_CLARIFICATION = 'REQUEST_CLARIFICATION',
}

/**
 * Zod schema for Linear operation
 */
export const LinearOperationSchema = z
  .object({
    /** Action type */
    action: z.nativeEnum(TaskAction),

    /** Confidence level (0-100) in this decision */
    confidence: z.number().min(0).max(100),

    /** Agent's reasoning for this action */
    reasoning: z.string(),

    /** For CREATE operations - full issue creation data */
    createData: z
      .object({
        title: z.string(),
        description: z.string(),
        teamId: z.string().nullish(),
        assigneeId: z.string().nullish(),
        priority: z.coerce
          .number()
          .min(1)
          .max(4)
          .nullish()
          .transform((val) => (val === 0 ? null : val)),
        dueDate: z.string().nullish(),
        state: z.enum(['todo', 'in_progress', 'in_review', 'done', 'canceled']).nullish(),
        stateId: z.string().nullish(),
      })
      .passthrough()
      .nullish(),

    /** For UPDATE operations - issue ID and fields to update
     *
     * Two use cases:
     * 1. General updates: Set title, description, assigneeId, priority, etc.
     * 2. Duplicate append: Set documentId, duplicateDescription, descriptionAppend to append new context to a duplicate
     */
    updateData: z
      .object({
        issueId: z.string(),
        title: z.string().nullish(),
        description: z.string().nullish(),
        assigneeId: z.string().nullish(),
        priority: z.coerce
          .number()
          .min(1)
          .max(4)
          .nullish()
          .transform((val) => (val === 0 ? null : val)),
        dueDate: z.string().nullish(),
        stateId: z.string().nullish(),
        state: z.enum(['todo', 'in_progress', 'in_review', 'done', 'canceled']).nullish(),
        // For duplicate-append use case:
        documentId: z.string().optional(), // Grapevine document_id (e.g., "issue_{uuid}") for get_document calls
        reason: z.string().optional(), // Why we're updating (e.g., "Adding new context to duplicate")
        relatedTickets: z
          .array(
            z.object({
              ticketId: z.string(),
              title: z.string(),
              confidence: z.number(),
              reason: z.string(),
            })
          )
          .optional(),
        duplicateDescription: z.string().optional(), // Full description from duplicate ticket (for reference)
        descriptionAppend: z.string().optional(), // New context to append (empty string = nothing new)
      })
      .nullish(),

    /** For SKIP operations - reason for skipping (too vague, insufficient info, etc.)
     *
     * Note: issueId should be null for SKIP operations (use UPDATE for duplicates)
     * If you have a duplicate with high confidence (≥ 0.9), use UPDATE action instead
     */
    skipData: z
      .object({
        issueId: z.string().nullish(), // Should be null for true SKIP operations
        title: z.string().optional(), // Optional for "no actionable content" cases
        reason: z.string(),
        relatedTickets: z
          .array(
            z.object({
              ticketId: z.string(),
              title: z.string(),
              confidence: z.number(),
              reason: z.string(),
            })
          )
          .optional(),
      })
      .nullish(),

    /** For REQUEST_CLARIFICATION operations - questions to ask the user */
    clarificationData: z
      .object({
        message: z.string(),
      })
      .nullish(),
  })
  .refine(
    (data) => {
      // Ensure the correct data field exists based on action
      if (data.action === TaskAction.CREATE) {
        return data.createData != null;
      }
      if (data.action === TaskAction.UPDATE) {
        return data.updateData != null;
      }
      if (data.action === TaskAction.SKIP) {
        return data.skipData != null;
      }
      if (data.action === TaskAction.REQUEST_CLARIFICATION) {
        return data.clarificationData != null;
      }
      return true;
    },
    (data) => ({
      message: `${data.action} operations must have ${
        data.action === TaskAction.CREATE
          ? 'createData'
          : data.action === TaskAction.UPDATE
            ? 'updateData'
            : data.action === TaskAction.SKIP
              ? 'skipData'
              : 'clarificationData'
      } field`,
      path: [
        data.action === TaskAction.CREATE
          ? 'createData'
          : data.action === TaskAction.UPDATE
            ? 'updateData'
            : data.action === TaskAction.SKIP
              ? 'skipData'
              : 'clarificationData',
      ],
    })
  );

/**
 * A Linear operation to be executed
 */
export type LinearOperation = z.infer<typeof LinearOperationSchema>;

/**
 * Zod schema for related ticket in triage analysis
 */
export const RelatedTicketSchema = z.object({
  /** Linear ticket ID or identifier */
  ticketId: z.string(),
  /** Ticket title */
  title: z.string(),
  /** Full Linear URL (optional) */
  url: z.string().optional(),
  /** Confidence score (0-1) */
  confidence: z.number().min(0).max(1),
  /** Reason for relation */
  reasoning: z.string(),
});

/**
 * Zod schema for triage analysis response
 */
export const TriageAnalysisSchema = z.object({
  /** Understanding of the issue */
  issueSummary: z.string(),
  /** Severity assessment */
  severity: z.enum(['low', 'medium', 'high', 'critical']).optional(),
  /** Related Linear tickets found */
  relatedTickets: z.array(RelatedTicketSchema),
  /** The Linear operation to perform (create or skip) */
  operation: LinearOperationSchema,
});

/**
 * Structured response schema for triage analysis
 */
export type TriageAnalysis = z.infer<typeof TriageAnalysisSchema>;

/**
 * Linear context for triage
 */
export interface LinearContext {
  /** Linear API key */
  apiKey: string;

  /** Team ID for Linear operations */
  teamId: string;

  /** Grapevine configuration */
  grapevine: {
    apiKey: string;
    mcpUrl: string;
    tenantId: string;
  };

  /** Optional label ID to add to created tickets */
  labelId?: string;
}

/**
 * Snapshot of a Linear issue before executing an operation
 */
export interface LinearIssueSnapshot {
  stateId?: string | null;
  assigneeId?: string | null;
  priority?: number | null;
  dueDate?: string | null;
  title?: string | null;
  description?: string | null;
  [key: string]: unknown;
}

/**
 * Result of executing a Linear operation
 */
export interface ExecutionResult {
  /** The operation that was executed */
  operation: LinearOperation;

  /** Whether execution succeeded */
  success: boolean;

  /** Linear issue ID (created or updated) */
  linearIssueId?: string;

  /** Linear issue identifier (e.g., "DES-2885") */
  linearIssueIdentifier?: string;

  /** Direct link to the Linear issue */
  linearIssueUrl?: string;

  /** Human-readable Linear issue title */
  linearIssueTitle?: string;

  /** Snapshot of the issue before executing the operation (when available) */
  previousIssueSnapshot?: LinearIssueSnapshot;

  /** Whether the description was updated (for UPDATE operations with descriptionAppend) */
  descriptionUpdated?: boolean;

  /** Error message if failed */
  error?: string;
}

/**
 * Summary of batch operation execution
 */
export interface ExecutionSummary {
  /** Total operations attempted */
  totalOperations: number;

  /** Number of successful executions */
  successful: number;

  /** Number of failed executions */
  failed: number;

  /** Individual results */
  results: ExecutionResult[];
}

/**
 * Metrics captured from ask_agent tool execution
 */
export interface AskAgentMetrics {
  /** Length of the answer field extracted from ask_agent response */
  answerLength: number;
  /** Preview of the answer (first 200 characters) */
  answerPreview: string;
  /** Length of the original response before optimization */
  originalResponseLength: number;
  /** Compression ratio as percentage (answerLength / originalResponseLength * 100) */
  compressionRatio: number;
}

/**
 * Result from strategy.process()
 */
export interface ProcessResult {
  /** Linear operations to apply */
  operations: LinearOperation[];
  /** Triage analysis details */
  triageAnalysis?: TriageAnalysis;
  /** Metrics from ask_agent tool execution (triage agent only) */
  askAgentMetrics?: AskAgentMetrics;
}
