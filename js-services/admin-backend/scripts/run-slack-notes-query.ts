#!/usr/bin/env tsx
/**
 * Script to run MCP queries for each tenant with connected integrations
 * and update their "Slack Notes" field in Notion CRM
 *
 * Usage:
 *   tsx scripts/run-slack-notes-query.ts
 *   tsx scripts/run-slack-notes-query.ts --tenant-ids abc123def456,xyz789
 *   tsx scripts/run-slack-notes-query.ts --tenant-ids abc123def456
 *
 * Template placeholders:
 *   {{tenantId}} - Replaced with the tenant's ID
 *   {{tenantName}} - Replaced with the tenant's organization name
 */

import jwt from 'jsonwebtoken';
import axios from 'axios';
import {
  getNotionClient,
  getNotionDataSourceId,
  isNotionCrmEnabled,
} from '../src/clients/notion.js';
import { logger } from '../src/utils/logger.js';

// ============================================================================
// CONFIGURATION
// ============================================================================

// Gather's internal tenant ID (update this to Gather's actual tenant ID)
const GATHER_TENANT_ID = '878f6fb522b441d1';

// Query to run for each tenant (you can iterate on this)
// Available placeholders: {{tenantId}}, {{tenantName}}
const QUERY_TEMPLATE =
  '\
  Collect all notes we have on the customer {{tenantName}} (tenant ID: {{tenantId}}). \
  We are interested only in notes related to Grapevine, not GatherV1 or GatherV2. \
  Try to be as comprehensive as you can, linking to any message in Slack where there is \
  a new insight about this customer or a piece of feedback from them. \
  A few sources to check: \
    - #customer-notes-grapevine \
    - the Slack Connect channel for this customer (which you need to discover). \
    - spreadsheet survey results available in google drive that may contain responses from the customer \
    - data available in hubspot for this company. if available, make sure to carry over usage information.\
  \
  DO NOT use the "Grapevine CRM" Notion database as a source. That is where you put your output, and you will pollute your \
  context if you use it \
  \
  IMPORTANT: Be exhaustive. Read the entire slack connect channel. Read every customer note related to the customer. Read the survey. Check hubspot. \
  IMPORTANT: Format your response as a bulleted list with the date (if available) and summary of each insight or feedback. \
  IMPORTANT: Order your final output by date in order of earliest to latest feedback \
';

// Concurrency limit (number of queries to run in parallel)
const CONCURRENCY_LIMIT = 15;

// ============================================================================
// COMMAND-LINE ARGUMENTS
// ============================================================================

function parseArgs(): { tenantIds?: string[] } {
  const args = process.argv.slice(2);
  const result: { tenantIds?: string[] } = {};

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--tenant-ids' && args[i + 1]) {
      result.tenantIds = args[i + 1].split(',').map((id) => id.trim());
      i++; // Skip the next argument
    }
  }

  return result;
}

// ============================================================================
// JWT GENERATION (copied from slack-bot)
// ============================================================================

interface JWTPayload {
  iss?: string;
  aud?: string;
  sub?: string;
  tenant_id: string;
  email?: string;
  permission_audience?: string;
  nonBillable?: boolean;
  exp?: number;
  iat?: number;
}

function generateInternalJWT(
  tenantId: string,
  email?: string,
  expiresIn: string = '1h',
  permissionAudience?: string,
  nonBillable: boolean = true // Set to true for non-billable internal queries
): string {
  const now = Math.floor(Date.now() / 1000);

  const payload: JWTPayload = {
    tenant_id: tenantId,
    iat: now,
  };

  if (nonBillable) {
    payload.nonBillable = true;
  }

  if (email) {
    payload.email = email;
  }

  if (permissionAudience) {
    payload.permission_audience = permissionAudience;
  }

  // Add issuer if configured
  const issuer = process.env.INTERNAL_JWT_ISSUER;
  if (issuer) {
    payload.iss = issuer;
  }

  // Add audience if configured
  const audience = process.env.INTERNAL_JWT_AUDIENCE;
  if (audience) {
    payload.aud = audience;
  }

  const privateKey = process.env.INTERNAL_JWT_PRIVATE_KEY;
  if (!privateKey) {
    throw new Error('JWT signing configuration missing: INTERNAL_JWT_PRIVATE_KEY is required');
  }

  return jwt.sign(payload, privateKey, {
    expiresIn,
    algorithm: 'RS256',
  });
}

// ============================================================================
// MCP CLIENT
// ============================================================================

interface MCPResponse {
  jsonrpc: string;
  id: string;
  result?: {
    content?: Array<{
      type: string;
      text: string;
    }>;
  };
}

async function callMCPAskAgent(
  tenantId: string,
  query: string
): Promise<{ answer: string; response_id?: string } | null> {
  const backendUrl = process.env.MCP_BASE_URL;
  if (!backendUrl || backendUrl === 'undefined') {
    throw new Error('MCP_BASE_URL environment variable is required');
  }

  const bearerToken = generateInternalJWT(tenantId);

  const payload = {
    jsonrpc: '2.0',
    id: '1',
    method: 'tools/call',
    params: {
      name: 'ask_agent',
      arguments: {
        query,
        files: [],
        previous_response_id: null,
        output_format: 'slack',
      },
    },
  };

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream',
    Authorization: `Bearer ${bearerToken}`,
  };

  try {
    const response = await axios.post<string>(`${backendUrl}/`, payload, {
      headers,
      responseType: 'text',
      timeout: 120000, // 2 minute timeout
    });

    // Parse SSE response to extract JSON
    let jsonResponse: MCPResponse | null = null;
    const responseText =
      typeof response.data === 'string' ? response.data : JSON.stringify(response.data);

    // Extract JSON from SSE data field
    const lines = responseText.split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const jsonStr = line.slice(6);
          jsonResponse = JSON.parse(jsonStr);
          break;
        } catch (e) {
          // Continue to next line
        }
      }
    }

    if (!jsonResponse?.result?.content?.[0]?.text) {
      logger.warn('No valid response from MCP', { tenantId });
      return null;
    }

    // Parse the text content which contains the actual answer
    const answerData = JSON.parse(jsonResponse.result.content[0].text);
    return { answer: answerData.answer || '', response_id: answerData.response_id };
  } catch (error) {
    logger.error('Failed to call MCP ask_agent', error, { tenantId, query });
    return null;
  }
}

// ============================================================================
// NOTION CRM OPERATIONS
// ============================================================================

interface TenantRecord {
  pageId: string;
  tenantId: string;
  orgName: string;
  connectedIntegrations: string[];
}

async function getAllTenantsWithIntegrations(filterTenantIds?: string[]): Promise<TenantRecord[]> {
  const client = getNotionClient();
  const dataSourceId = await getNotionDataSourceId();

  if (!client || !dataSourceId) {
    throw new Error('Notion client or data source ID not available');
  }

  if (filterTenantIds && filterTenantIds.length > 0) {
    logger.info(`Querying Notion CRM for specific tenants: ${filterTenantIds.join(', ')}`);
  } else {
    logger.info('Querying Notion CRM for all tenants with connected integrations');
  }

  const tenants: TenantRecord[] = [];
  let hasMore = true;
  let startCursor: string | undefined;

  while (hasMore) {
    const response = await client.dataSources.query({
      data_source_id: dataSourceId,
      start_cursor: startCursor,
      page_size: 100,
    });

    for (const page of response.results) {
      if (!('properties' in page)) continue;

      // Extract tenant ID from title
      const titleProp = page.properties['Tenant ID'];
      const tenantId = titleProp && titleProp.type === 'title' && titleProp.title[0]?.text?.content;

      if (!tenantId) continue;

      // Filter by tenant IDs if specified
      if (filterTenantIds && filterTenantIds.length > 0 && !filterTenantIds.includes(tenantId)) {
        continue;
      }

      // Extract organization name
      const orgNameProp = page.properties['Organization Name'];
      const orgName =
        orgNameProp && orgNameProp.type === 'rich_text' && orgNameProp.rich_text[0]?.text?.content;

      // Extract connected integrations
      const integrationsProp = page.properties['Connected Integrations'];
      const connectedIntegrations: string[] = [];
      if (integrationsProp && integrationsProp.type === 'multi_select') {
        connectedIntegrations.push(...integrationsProp.multi_select.map((item) => item.name));
      }

      // Only include tenants with at least one connected integration
      if (connectedIntegrations.length > 0) {
        tenants.push({
          pageId: page.id,
          tenantId,
          orgName: orgName || tenantId,
          connectedIntegrations,
        });
      }
    }

    hasMore = response.has_more;
    startCursor = response.next_cursor || undefined;
  }

  logger.info(`Found ${tenants.length} tenants with connected integrations`);
  return tenants;
}

/**
 * Convert Slack/Markdown citations to Notion rich text format
 * Handles both Slack format: <url|text> and Markdown format: [text](url)
 */
function convertToNotionRichText(
  text: string
): Array<{ type: string; text: { content: string; link?: { url: string } } }> {
  const richTextBlocks: Array<{ type: string; text: { content: string; link?: { url: string } } }> =
    [];

  // Combined regex to match both Slack <url|text> and Markdown [text](url) formats
  const linkRegex = /<([^|>]+)\|([^>]+)>|\[([^\]]+)\]\(([^)]+)\)/g;

  let lastIndex = 0;
  let match;

  while ((match = linkRegex.exec(text)) !== null) {
    // Add text before the link
    if (match.index > lastIndex) {
      const beforeText = text.slice(lastIndex, match.index);
      if (beforeText) {
        richTextBlocks.push({
          type: 'text',
          text: { content: beforeText },
        });
      }
    }

    // Determine which format matched
    const isSlackFormat = match[1] !== undefined;
    const url = isSlackFormat ? match[1] : match[4];
    const linkText = isSlackFormat ? match[2] : match[3];

    // Add the link
    richTextBlocks.push({
      type: 'text',
      text: {
        content: linkText,
        link: { url },
      },
    });

    lastIndex = linkRegex.lastIndex;
  }

  // Add remaining text after last link
  if (lastIndex < text.length) {
    const remainingText = text.slice(lastIndex);
    if (remainingText) {
      richTextBlocks.push({
        type: 'text',
        text: { content: remainingText },
      });
    }
  }

  // If no links were found, return the whole text as a single block
  if (richTextBlocks.length === 0) {
    richTextBlocks.push({
      type: 'text',
      text: { content: text },
    });
  }

  return richTextBlocks;
}

async function updateSlackNotes(pageId: string, notes: string): Promise<boolean> {
  const client = getNotionClient();
  if (!client) {
    throw new Error('Notion client not available');
  }

  try {
    // Convert markdown/slack citations to Notion rich text format
    const richTextBlocks = convertToNotionRichText(notes);

    await client.pages.update({
      page_id: pageId,
      properties: {
        'Slack Notes': {
          rich_text: richTextBlocks,
        },
      },
    });

    return true;
  } catch (error) {
    logger.error('Failed to update Slack Notes', error, { pageId });
    return false;
  }
}

// ============================================================================
// PARALLEL PROCESSING
// ============================================================================

async function processTenant(tenant: TenantRecord, queryTemplate: string): Promise<void> {
  logger.info(`Processing tenant: ${tenant.orgName} (${tenant.tenantId})`);

  try {
    // Replace template placeholders with tenant data
    const customQuery = queryTemplate
      .replace(/\{\{tenantId\}\}/g, tenant.tenantId)
      .replace(/\{\{tenantName\}\}/g, tenant.orgName);

    logger.info(`Query: ${customQuery}`);

    // Call MCP with Gather's tenant ID to query about this specific tenant
    const result = await callMCPAskAgent(GATHER_TENANT_ID, customQuery);

    if (!result || !result.answer) {
      logger.warn(`No answer received for tenant ${tenant.tenantId}`);
      return;
    }

    logger.info(`Received answer for ${tenant.orgName}: ${result.answer.slice(0, 100)}...`);

    // Update Notion CRM with the answer
    const success = await updateSlackNotes(tenant.pageId, result.answer);

    if (success) {
      logger.info(`✅ Updated Slack Notes for ${tenant.orgName}`);
    } else {
      logger.warn(`❌ Failed to update Slack Notes for ${tenant.orgName}`);
    }
  } catch (error) {
    logger.error(`Failed to process tenant ${tenant.orgName}`, error);
  }
}

async function processTenantsInBatches(
  tenants: TenantRecord[],
  query: string,
  concurrency: number
): Promise<void> {
  logger.info(`Processing ${tenants.length} tenants with concurrency=${concurrency}`);

  for (let i = 0; i < tenants.length; i += concurrency) {
    const batch = tenants.slice(i, i + concurrency);
    logger.info(
      `Processing batch ${Math.floor(i / concurrency) + 1}/${Math.ceil(tenants.length / concurrency)}`
    );

    await Promise.all(batch.map((tenant) => processTenant(tenant, query)));

    // Small delay between batches to avoid rate limits
    if (i + concurrency < tenants.length) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

// ============================================================================
// MAIN
// ============================================================================

async function main() {
  logger.info('Starting Slack Notes Query Script');

  // Parse command-line arguments
  const args = parseArgs();

  if (args.tenantIds && args.tenantIds.length > 0) {
    logger.info(`Filtering to specific tenant IDs: ${args.tenantIds.join(', ')}`);
  }

  // Validate environment
  if (!isNotionCrmEnabled()) {
    throw new Error('Notion CRM is not enabled. Set NOTION_API_KEY and NOTION_DATA_SOURCE_ID');
  }

  if (!process.env.MCP_BASE_URL) {
    throw new Error('MCP_BASE_URL environment variable is required');
  }

  if (!process.env.INTERNAL_JWT_PRIVATE_KEY) {
    throw new Error('INTERNAL_JWT_PRIVATE_KEY environment variable is required');
  }

  if (GATHER_TENANT_ID === 'YOUR_GATHER_TENANT_ID_HERE') {
    throw new Error('Please update GATHER_TENANT_ID in the script');
  }

  // Get tenants with connected integrations (optionally filtered)
  const tenants = await getAllTenantsWithIntegrations(args.tenantIds);

  if (tenants.length === 0) {
    logger.info('No tenants with connected integrations found');
    return;
  }

  logger.info(`Found ${tenants.length} tenants to process`);
  logger.info(`Query template: ${QUERY_TEMPLATE}`);

  // Process tenants in parallel batches
  await processTenantsInBatches(tenants, QUERY_TEMPLATE, CONCURRENCY_LIMIT);

  logger.info('✅ Script completed successfully');
}

// Run the script
main().catch((error) => {
  logger.error('Script failed', error);
  process.exit(1);
});
