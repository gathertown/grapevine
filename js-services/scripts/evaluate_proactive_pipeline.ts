#!/usr/bin/env ts-node --project ../slack-bot/tsconfig.json

/**
 * Evaluate the complete proactive response pipeline (processChannelQuestion)
 *
 * This script tests the bot's ability to:
 * 1. Classify which messages should receive a proactive response (shouldTryToAnswerMessage)
 * 2. Generate high-quality answers using the backend MCP server
 * 3. Apply confidence thresholds to filter low-quality responses
 *
 * The script mocks Slack API calls (getUserEmail, getUserName, getChannelName) to avoid
 * requiring valid Slack credentials or making real API calls during evaluation.
 *
 * Usage:
 *   ts-node scripts/evaluate_proactive_pipeline.ts --tenant-id <id> [options]
 *
 * Options:
 *   --rate-limit SEC   Seconds between API calls (default: 1.0)
 *   --tenant-id ID     Tenant ID to use (required)
 *
 * Requirements:
 *   - Backend MCP server must be running and accessible
 *   - OpenAI API access for answer quality evaluation
 *   - AWS SSM access for tenant credentials (can be invalid/expired - mocked methods handle this)
 */

import { GenericMessageEvent } from '@slack/bolt';
import { getOpenAI } from '../slack-bot/src/clients';
import {
  shouldTryToAnswerMessage,
  stripMessageHeader,
  getConfiguredSourceNames,
  getTenantStateToAnswerQuestions,
  makeBackendRequest,
} from '../slack-bot/src/common';
import { PermissionAudience } from '../slack-bot/src/types';
import { tenantConfigManager } from '../slack-bot/src/config/tenantConfigManager';
import { logger } from '../slack-bot/src/utils/logger';
import { getGrapevineEnv } from '@corporate-context/backend-common';

interface TestCase {
  // Test identification
  description: string;
  category: string; // e.g., "technical", "small-talk", "product-decision"

  // Input
  text: string;

  // Expected behavior
  expectedShouldAnswer: boolean;

  // Answer quality validation (only if expectedShouldAnswer = true)
  requiredFacts?: string[]; // Factual claims that must be present (validated by LLM)

  // Optional mock Slack metadata (for avoiding real API calls)
  userId?: string; // Default: "U_TEST_USER"
  userName?: string; // Default: "Test User"
  userEmail?: string; // Default: "testuser@example.com"
  channelId?: string; // Default: "C_TEST_CHANNEL"
  channelName?: string; // Default: "test-channel"
}

interface EvaluationResult {
  // Test case info
  description: string;
  category: string;
  text: string;

  // Classification results
  expectedShouldAnswer: boolean;
  actualDidAnswer: boolean;
  classificationCorrect: boolean;

  // Answer quality (only if both expected and actual answered)
  generatedAnswer?: string;
  answerConfidence?: number;
  requiredFactsPresent?: boolean;
  missingFacts?: string;
  factCheckReasoning?: string;
  answerQualityPass?: boolean;

  // Filter tracking (where the answer was rejected if not answered)
  filterStage?: 'prefilter' | 'backend_failure' | 'confidence_threshold';
  confidenceThreshold?: number;

  // Overall
  overallPass: boolean;
  failureReason?: string;
  error?: string;
  evaluated_at: string;
}

interface Options {
  rateLimit: number;
  tenantId?: string;
}

// Inline test cases for evaluation
// Note: All Slack metadata fields (userId, userName, userEmail, channelId, channelName) are optional.
// If not specified, defaults will be used (U_TEST_USER, Test User, testuser@example.com, etc.)
const TEST_CASES: TestCase[] = [
  // SHOULD ANSWER - Technical Questions
  {
    description: 'Infrastructure question, check iaac repo',
    category: 'technical',
    text: 'have we deployed an sfuga t1 ng in ap-south-1-a?',
    expectedShouldAnswer: true,
    requiredFacts: [
      'yes we have deployed an sfuga T1 node group in ap-south-1-a. Should mention t1 node group (ng) by name.',
    ],
    // Optional: specify custom user/channel context for this test
    userId: 'U02DF8N2RK4', // actual user id, it's part of the prompt
    userName: 'Achilleas Triantafyllou',
    userEmail: 'achilleas@gather.town',
    channelId: 'C01PZGY62UD', // actual channel id, it's part of the prompt
    channelName: 'mon-infra-prod-critical',
  },
  // SHOULD ANSWER - Product Feature Questions
  {
    description: 'Product: details on Hubspot connector',
    category: 'product-features',
    text: `Where can I find details about the Hubspot connector? What information can it access, how do permissions work, what types of questions would people ask once they've added it?`,
    expectedShouldAnswer: true,
    requiredFacts: [
      'mentions hubspot Notion doc https://www.notion.so/HubSpot-246bc7eac3d180598847d9ca817e3e49#269bc7eac3d180c08852ed42d2bf3706',
      'Can access Contacts, Companies, Deals, Tickets, Notes and activities, Custom properties',
      'Users can only see via Grapevine what they can see in Hubspot',
    ],
    userId: 'U03NRBX8QH2',
    userName: 'Morgan Smith',
    userEmail: 'morgan@gather.town',
    channelId: 'C08UFM8FRNE',
    channelName: 'ai-grapevine',
  },
  {
    description: 'Audio volume settings',
    category: 'product-features',
    text: 'What nearby audio settings are available in Gather V2? Was there a volume level for the user to use?',
    expectedShouldAnswer: true,
    // TODO confirm this was true as of September Slack upload
    requiredFacts: [
      'There is no overall ambient volume control',
      'Users can use busy mode',
      'Users can lock their desks to prevent audio leak',
      'Users can use private offices',
    ],
    userId: 'Uasdf',
    userName: 'Carina',
    userEmail: 'carina@gather.town',
    channelId: 'C01898BH6D7',
    channelName: 'team-cx-support',
  },
  {
    description: 'How to create a v1 space',
    category: 'product-features',
    text: '<@U03PCMY5GEL> how does a user create a v1 space then if they really wanted to',
    expectedShouldAnswer: true,
    requiredFacts: ['We can send them the URL https://app.gather.town/get-started'],
    userId: 'U02S5GN2DQD',
    userName: 'Evangeline Chen',
    userEmail: 'evangeline@gather.town',
    channelId: 'C09FD19DMEY',
    channelName: 'inc-648-2025-09-15-can-no-longer-create-spaces-in-v1',
  },
  {
    description: 'Customer feature questions',
    category: 'product-features',
    text: `Hi Guys

2 questions

1. The proximity conversations how can we reduce the distance?  In the work desk you can hear everything 
2. Can I add spotify to my own office desk area?
`,
    expectedShouldAnswer: true,
    requiredFacts: [
      'The distance cannot be adjusted',
      'Can use busy status to stop hearing ambient conversations',
      'Can use walled desks as a permanent change',
    ],
  },

  // SHOULD ANSWER - Company/Process Questions
  {
    description: 'Process documentation question',
    category: 'company-process',
    text: 'What is our code review process?',
    expectedShouldAnswer: true,
    requiredFacts: [
      'Describes the steps or workflow for code reviews',
      'Mentions tools, people, or procedures involved',
    ],
  },
  {
    description: 'Team information question',
    category: 'company-info',
    text: 'Who is on the Grapevine Core team?',
    expectedShouldAnswer: true,
    requiredFacts: [
      'Victor Zhou, David Orr, Kumail Jaffer, Johnny Dimond, Andy Lui, Bryan Phelps, Chandler Roth, Jordan Maduro',
    ],
  },
  {
    description: 'How do we merge in v1',
    category: 'company-process',
    text: `<@U02S5GN2DQD> I can't remember, we merge directly to main in Gather V1 right ?`,
    expectedShouldAnswer: true,
    requiredFacts: [
      `Yes merge directly to main in Gather v1`,
      `use the script gather merge:main, don't click the 'merge' button in Github`,
    ],
  },
  {
    description: 'Task status check',
    category: 'task-state',
    text: '"<@U02S5GN2DQD> (or anyone here who knows) just following up on the Limiting the Number of Calendars to Import effort (to reduce bcce model count). Are you guys picking this up this week?"',
    expectedShouldAnswer: true,
    requiredFacts: ['not yet'],
  },

  // SHOULD NOT ANSWER - Product/Strategy Decisions
  {
    description: 'Product decision question',
    category: 'product-decision',
    text: 'Should we build feature X or feature Y next?',
    expectedShouldAnswer: false,
  },
  {
    description: 'Strategic direction question',
    category: 'product-decision',
    text: 'What should our pricing strategy be for enterprise customers?',
    expectedShouldAnswer: false,
  },
  {
    description: 'Subjective opinion request',
    category: 'opinion',
    text: 'Do you think React or Vue is better for our use case?',
    expectedShouldAnswer: false,
  },

  // SHOULD NOT ANSWER - Small Talk/Social
  {
    description: 'Casual greeting',
    category: 'small-talk',
    text: 'Hey everyone! How was your weekend?',
    expectedShouldAnswer: false,
  },
  {
    description: 'Social conversation',
    category: 'small-talk',
    text: "Anyone want to grab lunch today? I'm thinking tacos",
    expectedShouldAnswer: false,
  },
  {
    description: 'Personal opinion seeking',
    category: 'small-talk',
    text: "What's your favorite coffee shop near the office?",
    expectedShouldAnswer: false,
  },

  // SHOULD NOT ANSWER - External/Unrelated
  {
    description: 'External news question',
    category: 'external',
    text: 'Did anyone see the latest news about ChatGPT-5?',
    expectedShouldAnswer: false,
  },
  {
    description: 'Personal non-work question',
    category: 'external',
    text: 'Does anyone know a good dentist in SF?',
    expectedShouldAnswer: false,
  },

  // SHOULD NOT ANSWER - Commands/Statements
  {
    description: 'Command or instruction',
    category: 'command',
    text: 'Please review my PR when you get a chance',
    expectedShouldAnswer: false,
  },
  {
    description: 'Announcement',
    category: 'statement',
    text: 'Deployed the new feature to production!',
    expectedShouldAnswer: false,
  },

  // ========
  {
    description: 'V2 Create flow survey step',
    category: 'product-flows',
    text: 'Is the Create flow for V2 still supposed to have the survey?',
    expectedShouldAnswer: true,
    requiredFacts: ['Create flow still includes a survey step', 'After survey → create path'],
    userId: 'U01SJ6L8JNS',
    userName: 'Ashley Kalley',
    userEmail: '',
    channelId: 'C03L6HPGDMF',
    channelName: 'sales-and-success',
  },
  {
    description: 'Docker on Windows guidance',
    category: 'dev-environment',
    text: 'Are there any known issues and workarounds internally with installing docker on Windows?',
    expectedShouldAnswer: true,
    requiredFacts: [
      'Officially unsupported on WSL/Windows',
      'Mirror WSL networking',
      'Force SFU to TCP if A/V fails',
    ],
    userId: 'U01GFAMFY31',
    userName: 'Daud',
    userEmail: '',
    channelId: 'C097Q1G59EF',
    channelName: 'army-of-design-agents',
  },
  {
    description: 'Who can manage Admin Users',
    category: 'admin-permissions',
    text: 'Who has ManageAdminUsers permissions currently?',
    expectedShouldAnswer: true,
    requiredFacts: ['Anyone with Admin role', 'View via Admin dashboard → Admin Users'],
    userId: 'U01GFAMFY31',
    userName: 'Daud',
    userEmail: '',
    channelId: 'C097Q1G59EF',
    channelName: 'army-of-design-agents',
  },
  {
    description: 'Bug reporting path (Grapevine)',
    category: 'support-process',
    text: 'Where to report bugs / who to tag (for Grapevine)?',
    expectedShouldAnswer: true,
    requiredFacts: ['Post issues in #ai-grapevine', 'Tag @current-oncall-grapevine when urgent'],
    userId: 'U01GFAMFY31',
    userName: 'Daud',
    userEmail: '',
    channelId: 'C08UFM8FRNE',
    channelName: 'ai-grapevine',
  },
  {
    description: 'Subprocessors list',
    category: 'security-legal',
    text: 'Where can I find our list of subprocessors to share with a user?',
    expectedShouldAnswer: true,
    requiredFacts: ['See public DPA page at https://www.gather.town/dpa'],
    userId: 'U01SJ6L8JNS',
    userName: 'Ashley Kalley',
    userEmail: '',
    channelId: 'C01898BH6D7',
    channelName: 'team-cx-support',
  },
  {
    description: 'Unknown log user id',
    category: 'observability',
    text: 'Why do we see logs with the user id IfYouSeeThisLetGSV2TeamKnow?',
    expectedShouldAnswer: true,
    requiredFacts: [
      'Used for system actions like when the http server connects to the logic (game) server',
    ],
    userId: 'U025PUZ532N',
    userName: 'Dave Orr',
    userEmail: 'david@gather.town',
    channelId: 'C094APZQ4G3',
    channelName: 'C094APZQ4G3',
  },
  {
    description: 'New Relic log filters',
    category: 'observability',
    text: 'How do I filter server logs in New Relic based on environment (staging, prod)?',
    expectedShouldAnswer: true,
    requiredFacts: ["Use a `WHERE env='staging'` (or 'prod') clause"],
    userId: 'U0571JA1FFD',
    userName: 'Steven Yau',
    userEmail: '',
    channelId: 'C09HVLTEJS1',
    channelName: 'team-gather-core',
  },
  {
    description: 'Help docs for linking 1.0 and 2.0',
    category: 'help-docs',
    text: 'Do we have any help articles out in the wild right now on linking a 1.0 space to 2.0?',
    expectedShouldAnswer: true,
    requiredFacts: ['Yes this site: https://gathertown.notion.site/link-1-0'],
    userId: 'U07RTGM16KH',
    userName: 'Teresa',
    userEmail: '',
    channelId: 'C09HV0R8V7V',
    channelName: 'inc-662-2025-09-30-confusion-and-incorrect-links-for-upcoming-renewal',
  },
  {
    description: 'Capacity increase with locked pricing',
    category: 'billing',
    text: 'How can the customers increase their capacity maintaining their locked pricing?',
    expectedShouldAnswer: true,
    requiredFacts: ['Apply the Legacy Annual code', 'Use monthly code 7Monthly if promised [32]'],
    userId: 'U061C3TDCCC',
    userName: 'Carina',
    userEmail: '',
    channelId: 'C01898BH6D7',
    channelName: 'team-cx-support',
  },
  {
    description: 'Instrumentation sanity check',
    category: 'metrics',
    text: 'Just confirming, were there any event-firing issues last week?',
    expectedShouldAnswer: true,
    requiredFacts: [
      'Pose the instrumentation question [C01K5HZQ0BY_2025-10-06|"were there any event-firing issues last week?"]',
      'Corrected totals context: 84 is accurate total [34]',
    ],
    userId: 'U040B2T929W',
    userName: 'Sam',
    userEmail: '',
    channelId: 'C01K5HZQ0BY',
    channelName: 'metrics',
  },
  {
    description: 'Find v1 staging/hotfix doc',
    category: 'eng-process',
    text: 'Can you find the notion doc that talks about the 1.0 staging hotfixes and git branches?',
    expectedShouldAnswer: true,
    requiredFacts: [
      'Adopting TBD/CD in 2023 https://www.notion.so/gathertown/Adopting-TBD-CD-in-2023-1109bbce99964dbea3c138ee9ebb42f2',
    ],
    userId: 'U08A8EV0CLT',
    userName: 'austin (gather)',
    userEmail: '',
    channelId: 'C09HVLTEJS1',
    channelName: 'C09HVLTEJS1',
  },
  {
    description: 'Catalog items not visible',
    category: 'content-pipeline',
    text: `Can someone help me figure out why these aren\'t showing in app yet? They synced hours ago
https://github.com/gathertown/gather-catalog-items/actions/runs/18533636355
Successfully synced catalog items to staging :ship:`,
    expectedShouldAnswer: true,
    requiredFacts: [
      'Verify via admin dashboard /dashboard/catalog-items',
      'Logic Server loads catalog on start, server may need to be restarted',
    ],
    userId: 'U01GFAMFY31',
    userName: 'Daud',
    userEmail: '',
    channelId: 'C09HVLTEJS1',
    channelName: 'team-gather-core',
  },
];

function parseArgs(): Options {
  const args = process.argv.slice(2);

  const options: Options = {
    rateLimit: 1.0,
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--rate-limit':
        options.rateLimit = parseFloat(args[++i] ?? '');
        break;
      case '--tenant-id':
        options.tenantId = args[++i];
        break;
      default:
        console.error(`Unknown option: ${args[i]}`);
        process.exit(1);
    }
  }

  if (!options.tenantId) {
    console.error('Error: --tenant-id is required');
    console.error(
      'Usage: ts-node evaluate_proactive_pipeline.ts --tenant-id <id> [--rate-limit 1.0]'
    );
    process.exit(1);
  }

  return options;
}

/**
 * Use LLM to check if required factual claims are present in the generated answer
 * @returns Which claims passed/failed and reasoning
 */
async function checkFactClaims(
  generatedAnswer: string,
  requiredClaims: string[],
  question: string
): Promise<{ allPresent: boolean; missingClaims: string[]; reasoning: string }> {
  try {
    const response = await getOpenAI().chat.completions.create({
      model: 'gpt-4o',
      response_format: { type: 'json_object' },
      messages: [
        {
          role: 'system',
          content: `You are evaluating whether an AI-generated answer contains required factual information.

Your task:
1. Check if the generated answer supports or implies each required factual claim
2. A claim is "present" if the answer either directly states it or clearly implies it
3. Be somewhat lenient - answers don't need exact wording, just the core information
4. Identify which claims are missing or not supported by the answer

CRITICAL: Return ONLY raw JSON. Do NOT wrap your response in markdown code blocks or backticks.

Respond with a JSON object in this exact format:
{
  "claimsPassed": ["claim 1", "claim 2"],
  "claimsFailed": ["claim 3"],
  "reasoning": "<brief explanation of what passed/failed>"
}`,
        },
        {
          role: 'user',
          content: `Question: ${question}

Required Claims:
${requiredClaims.map((c, i) => `${i + 1}. ${c}`).join('\n')}

Generated Answer: ${generatedAnswer}`,
        },
      ],
      temperature: 0.1,
      max_tokens: 500,
    });

    let content = response.choices[0]?.message.content?.trim();
    if (!content) {
      return {
        allPresent: false,
        missingClaims: requiredClaims,
        reasoning: 'Empty response from LLM fact checker',
      };
    }

    // Strip markdown code blocks if present (defensive fallback)
    content = content.replace(/^```(?:json)?\s*\n?/i, '').replace(/\n?```\s*$/i, '');

    const parsed = JSON.parse(content);
    if (
      !Array.isArray(parsed.claimsPassed) ||
      !Array.isArray(parsed.claimsFailed) ||
      typeof parsed.reasoning !== 'string'
    ) {
      return {
        allPresent: false,
        missingClaims: requiredClaims,
        reasoning: 'Invalid response format from LLM fact checker',
      };
    }

    return {
      allPresent: parsed.claimsFailed.length === 0,
      missingClaims: parsed.claimsFailed,
      reasoning: parsed.reasoning,
    };
  } catch (error) {
    console.error('Error checking fact claims:', error);
    return {
      allPresent: false,
      missingClaims: requiredClaims,
      reasoning: `Error during fact checking: ${error}`,
    };
  }
}

function sleep(seconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, seconds * 1000));
}

/**
 * Create a mock GenericMessageEvent from test case
 */
function createMockMessageEvent(testCase: TestCase, index: number): GenericMessageEvent {
  // Generate a unique timestamp for each test case
  const baseTimestamp = Date.now() / 1000;
  const timestamp = (baseTimestamp + index).toFixed(6);

  return {
    type: 'message',
    subtype: undefined,
    channel: testCase.channelId || 'C_TEST_CHANNEL',
    user: testCase.userId || 'U_TEST_USER',
    text: testCase.text,
    ts: timestamp,
    event_ts: timestamp,
    channel_type: 'channel',
  } as GenericMessageEvent;
}

/**
 * Evaluation-only version of processChannelQuestion that doesn't require Slack credentials
 * or post messages to Slack. Only generates and returns the answer for quality evaluation.
 */
async function evaluateChannelQuestion(
  msg: GenericMessageEvent,
  tenantId: string,
  userEmail: string,
  userName: string,
  channelName: string
): Promise<{
  success: boolean;
  answer?: string;
  confidence?: number;
  filterStage?: 'prefilter' | 'backend_failure' | 'confidence_threshold';
  confidenceThreshold?: number;
}> {
  try {
    // Get tenant state to determine configured sources
    const { stats } = await getTenantStateToAnswerQuestions(tenantId);
    const configuredSources = getConfiguredSourceNames(stats);

    // Strip message header and check if we should answer
    const messageText = stripMessageHeader(msg.text || '');
    const { shouldAnswer: shouldAnswerProactively, reasoning } = await shouldTryToAnswerMessage(
      messageText,
      configuredSources
    );

    const env = getGrapevineEnv();
    const logReasoning = env === 'staging' || env === 'local';
    logger.info(
      `Proactive pre-filter decision: ${shouldAnswerProactively}${logReasoning ? ` reasoning: ${reasoning}` : ''}`,
      { sources: configuredSources }
    );

    if (!shouldAnswerProactively) {
      return { success: false, filterStage: 'prefilter' };
    }

    // Build the user prompt with context
    let userPrompt = `The user asking this question is: ${userName} (${userEmail}).\n\n${messageText}`;

    // Add channel context
    userPrompt = `You are in SLACK CHANNEL:${channelName} (${msg.channel}). Utilize the channel and its contents as context to answering the query.

IMPORTANT: If you retrieve Slack messages from this channel during your search, do NOT use the current thread/conversation you are responding in as evidence for your answer. The user's question was asked IN this thread, so using the thread content to answer would be circular and confusing.

CRITICAL: Do NOT cite your own previous responses as evidence. All factual claims must be supported by citations to actual source documents (GitHub, Slack messages from other threads/channels, Notion, etc.), never by your own prior answers. Your previous responses may contain reasoning and conclusions, but those must have been based on underlying evidence - cite that underlying evidence directly.

${userPrompt}`;

    // Add confidence prompt
    userPrompt = `
IMPORTANT: Include a confidence level from 0% to 100% with your answer and explain why.
Use the following format and place it at the very end of your answer, on the last line:
<confidence><level>100</level><why>This is the explanation for the given confidence level</why></confidence>
Make sure not to include any other tags with the confidence level!

${userPrompt}`;

    // Make backend request
    const response = await makeBackendRequest(
      tenantId,
      userPrompt,
      userEmail,
      [], // No files in evaluation
      undefined, // No previous response ID
      PermissionAudience.Tenant,
      false // Billable
    );

    if (!response) {
      return { success: false, filterStage: 'backend_failure' };
    }

    let answer = response.answer;

    // Extract confidence level from answer
    let confidence: number | undefined;
    confidence = 0;
    const confidenceMatch = answer.match(
      /<confidence>\s*<level>(\d+)<\/level>\s*<why>([\s\S]*?)<\/why>\s*<\/confidence>/
    );
    if (confidenceMatch) {
      const parsedConfidence = parseInt(confidenceMatch[1], 10);
      confidence = isNaN(parsedConfidence) ? 0 : Math.min(Math.max(parsedConfidence, 0), 100);

      // Remove confidence tags from answer
      answer = answer.replace(
        /<confidence>\s*<level>\d+<\/level>\s*<why>[\s\S]*?<\/why>\s*<\/confidence>\s*/g,
        ''
      );
    }

    // Apply quality gate for proactive responses
    const confidenceThreshold = await tenantConfigManager.getQaConfidenceThreshold(tenantId);

    if ((confidence ?? 0) < confidenceThreshold) {
      logger.info('Answer filtered by quality gate for proactive response', {
        tenantId,
        userId: msg.user,
        channelId: msg.channel,
        messageTs: msg.ts,
        questionLength: messageText.length,
        confidenceThreshold,
        answerConfidence: confidence,
        operation: 'proactive-answer-filtered',
      });
      return {
        success: false,
        answer,
        confidence,
        filterStage: 'confidence_threshold',
        confidenceThreshold,
      };
    }

    logger.info('Answer passed quality gate for proactive response', {
      tenantId,
      userId: msg.user,
      channelId: msg.channel,
      messageTs: msg.ts,
      questionLength: messageText.length,
      answerLength: answer.length,
      confidenceThreshold,
      answerConfidence: confidence,
      operation: 'proactive-answer-approved',
    });

    return { success: true, answer, confidence };
  } catch (error) {
    logger.error(
      'Error in evaluateChannelQuestion',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId,
        operation: 'evaluate-channel-question-error',
      }
    );
    return { success: false };
  }
}

/**
 * Evaluate a single test case through the complete pipeline with multi-level validation
 */
async function evaluateTestCase(
  testCase: TestCase,
  index: number,
  tenantId: string,
  userIdToEmail: Map<string, string>,
  userIdToName: Map<string, string>,
  channelIdToName: Map<string, string>
): Promise<Omit<EvaluationResult, 'evaluated_at'>> {
  const result: Omit<EvaluationResult, 'evaluated_at'> = {
    description: testCase.description,
    category: testCase.category,
    text: testCase.text,
    expectedShouldAnswer: testCase.expectedShouldAnswer,
    actualDidAnswer: false,
    classificationCorrect: false,
    overallPass: false,
  };

  try {
    // Create a mock message event
    const mockEvent = createMockMessageEvent(testCase, index);

    // Get user and channel context from test case
    const userId = testCase.userId || 'U_TEST_USER';
    const userEmail = userIdToEmail.get(userId) || `${userId}@example.com`;
    const userName = userIdToName.get(userId) || `User_${userId}`;
    const channelName = channelIdToName.get(mockEvent.channel) || `channel_${mockEvent.channel}`;

    // Run the evaluation version of processChannelQuestion (no Slack credentials needed)
    const response = await evaluateChannelQuestion(
      mockEvent,
      tenantId,
      userEmail,
      userName,
      channelName
    );

    result.actualDidAnswer = response.success;
    result.generatedAnswer = response.answer;
    result.answerConfidence = response.confidence;
    result.filterStage = response.filterStage;
    result.confidenceThreshold = response.confidenceThreshold;

    // Check if classification was correct
    result.classificationCorrect =
      (testCase.expectedShouldAnswer && response.success) ||
      (!testCase.expectedShouldAnswer && !response.success);

    // If bot shouldn't have answered, we're done
    if (!testCase.expectedShouldAnswer) {
      result.overallPass = result.classificationCorrect;
      if (!result.overallPass) {
        result.failureReason = 'False positive - answered when it should not have';
      }
      return result;
    }

    // If bot should have answered but didn't, it's a failure
    if (testCase.expectedShouldAnswer && !response.success) {
      result.overallPass = false;
      result.failureReason = 'False negative - did not answer when it should have';
      return result;
    }

    // Bot answered correctly, now validate answer quality
    let qualityChecks: Array<{ name: string; passed: boolean }> = [];

    // Check required facts with LLM
    if (testCase.requiredFacts && testCase.requiredFacts.length > 0) {
      const { allPresent, missingClaims, reasoning } = await checkFactClaims(
        result.generatedAnswer!,
        testCase.requiredFacts,
        testCase.text
      );
      result.requiredFactsPresent = allPresent;
      result.missingFacts = missingClaims.length > 0 ? missingClaims.join(', ') : undefined;
      result.factCheckReasoning = reasoning;
      qualityChecks.push({
        name: 'required_facts',
        passed: allPresent,
      });
    }

    // Determine if answer quality passes
    result.answerQualityPass = qualityChecks.length === 0 || qualityChecks.every((c) => c.passed);

    // Overall pass if classification correct AND answer quality passes
    result.overallPass = result.classificationCorrect && result.answerQualityPass;

    if (!result.overallPass) {
      const failedChecks = qualityChecks.filter((c) => !c.passed).map((c) => c.name);
      if (failedChecks.length > 0) {
        result.failureReason = `Answer quality failed: ${failedChecks.join(', ')}`;
      }
    }
  } catch (error) {
    result.error = error instanceof Error ? error.message : String(error);
    result.overallPass = false;
    result.failureReason = 'Error during evaluation';
  }

  return result;
}

async function main() {
  const options = parseArgs();

  console.log('='.repeat(80));
  console.log('Proactive Pipeline Evaluation');
  console.log('='.repeat(80));
  console.log(`Test cases: ${TEST_CASES.length}`);
  console.log(`Tenant ID: ${options.tenantId}`);
  console.log(`Rate limit: ${options.rateLimit}s between tests`);
  console.log('='.repeat(80));
  console.log();

  // Build lookup maps from test case metadata for user/channel context
  const userIdToEmail = new Map<string, string>();
  const userIdToName = new Map<string, string>();
  const channelIdToName = new Map<string, string>();

  TEST_CASES.forEach((testCase) => {
    const userId = testCase.userId || 'U_TEST_USER';
    const userName = testCase.userName || 'Test User';
    const userEmail = testCase.userEmail || 'testuser@example.com';
    const channelId = testCase.channelId || 'C_TEST_CHANNEL';
    const channelName = testCase.channelName || 'test-channel';

    userIdToEmail.set(userId, userEmail);
    userIdToName.set(userId, userName);
    channelIdToName.set(channelId, channelName);
  });

  console.log('✓ User and channel context prepared (no Slack credentials needed)\n');

  const results: EvaluationResult[] = [];

  // Evaluate each test case
  for (let i = 0; i < TEST_CASES.length; i++) {
    const testCase = TEST_CASES[i]!;

    const truncatedText =
      testCase.text.length > 80 ? testCase.text.slice(0, 80) + '...' : testCase.text;
    console.log(`[${i + 1}/${TEST_CASES.length}] ${testCase.description}`);
    console.log(`  Category: ${testCase.category}`);
    console.log(`  Text: "${truncatedText}"`);
    console.log(
      `  Expected: ${testCase.expectedShouldAnswer ? 'SHOULD ANSWER' : 'SHOULD NOT ANSWER'}`
    );

    const result = await evaluateTestCase(
      testCase,
      i,
      options.tenantId!,
      userIdToEmail,
      userIdToName,
      channelIdToName
    );
    const evaluation: EvaluationResult = {
      ...result,
      evaluated_at: new Date().toISOString(),
    };

    results.push(evaluation);

    // Display result
    if (evaluation.overallPass) {
      console.log(`  ✓ PASS`);
    } else {
      console.log(`  ✗ FAIL: ${evaluation.failureReason}`);
    }

    if (evaluation.actualDidAnswer) {
      console.log(`  Actual: ANSWERED`);
      if (evaluation.generatedAnswer) {
        const truncatedAnswer =
          evaluation.generatedAnswer.length > 100
            ? evaluation.generatedAnswer.slice(0, 100) + '...'
            : evaluation.generatedAnswer;
        console.log(`  Answer: "${truncatedAnswer}"`);
      }
      if (evaluation.factCheckReasoning) {
        console.log(`  Fact Check: ${evaluation.factCheckReasoning}`);
      }
    } else {
      console.log(`  Actual: DID NOT ANSWER`);
    }

    console.log();

    // Rate limit
    if (i < TEST_CASES.length - 1) {
      await sleep(options.rateLimit);
    }
  }

  // Calculate metrics
  console.log('='.repeat(80));
  console.log('EVALUATION SUMMARY');
  console.log('='.repeat(80));

  const overallPassCount = results.filter((r) => r.overallPass).length;
  const overallPassRate = ((overallPassCount / results.length) * 100).toFixed(1);

  console.log(`\nOverall: ${overallPassCount}/${results.length} passed (${overallPassRate}%)\n`);

  // Classification metrics (confusion matrix)
  const truePositives = results.filter((r) => r.expectedShouldAnswer && r.actualDidAnswer).length;
  const trueNegatives = results.filter((r) => !r.expectedShouldAnswer && !r.actualDidAnswer).length;
  const falsePositives = results.filter((r) => !r.expectedShouldAnswer && r.actualDidAnswer).length;
  const falseNegatives = results.filter((r) => r.expectedShouldAnswer && !r.actualDidAnswer).length;

  console.log('Classification Metrics:');
  console.log(`  True Positives:  ${truePositives} (correctly answered)`);
  console.log(`  True Negatives:  ${trueNegatives} (correctly declined)`);
  console.log(`  False Positives: ${falsePositives} (incorrectly answered)`);
  console.log(`  False Negatives: ${falseNegatives} (incorrectly declined)`);

  const precision =
    truePositives + falsePositives > 0
      ? ((truePositives / (truePositives + falsePositives)) * 100).toFixed(1)
      : 'N/A';
  const recall =
    truePositives + falseNegatives > 0
      ? ((truePositives / (truePositives + falseNegatives)) * 100).toFixed(1)
      : 'N/A';
  const f1 =
    precision !== 'N/A' && recall !== 'N/A'
      ? (
          (2 * (parseFloat(precision) * parseFloat(recall))) /
          (parseFloat(precision) + parseFloat(recall))
        ).toFixed(1)
      : 'N/A';

  console.log(`  Precision: ${precision}%`);
  console.log(`  Recall: ${recall}%`);
  console.log(`  F1 Score: ${f1}%`);

  // Answer quality metrics (for true positives)
  const tpResults = results.filter((r) => r.expectedShouldAnswer && r.actualDidAnswer);
  if (tpResults.length > 0) {
    const qualityPassed = tpResults.filter((r) => r.answerQualityPass).length;
    const qualityRate = ((qualityPassed / tpResults.length) * 100).toFixed(1);

    console.log(`\nAnswer Quality (for ${tpResults.length} answered cases):`);
    console.log(`  Quality Pass Rate: ${qualityPassed}/${tpResults.length} (${qualityRate}%)`);

    const withRequiredFacts = tpResults.filter((r) => r.requiredFactsPresent !== undefined);
    if (withRequiredFacts.length > 0) {
      const factsPassed = withRequiredFacts.filter((r) => r.requiredFactsPresent).length;
      console.log(
        `  Required Facts: ${factsPassed}/${withRequiredFacts.length} (${((factsPassed / withRequiredFacts.length) * 100).toFixed(1)}%)`
      );
    }
  }

  // By-category breakdown
  const categories = Array.from(new Set(results.map((r) => r.category)));
  if (categories.length > 1) {
    console.log('\nBy Category:');
    for (const category of categories.sort()) {
      const categoryResults = results.filter((r) => r.category === category);
      const passed = categoryResults.filter((r) => r.overallPass).length;
      const passRate = ((passed / categoryResults.length) * 100).toFixed(1);
      console.log(`  ${category}: ${passed}/${categoryResults.length} (${passRate}%)`);
    }
  }

  // Failed cases
  const failures = results.filter((r) => !r.overallPass);
  if (failures.length > 0) {
    console.log('\nFailed Cases:');
    for (const failure of failures) {
      console.log(`  ✗ ${failure.description}`);
      console.log(`    Reason: ${failure.failureReason || failure.error || 'Unknown'}`);

      // Show where it was filtered (if applicable)
      if (failure.filterStage) {
        console.log(`    Filter Stage: ${failure.filterStage}`);
        if (
          failure.filterStage === 'confidence_threshold' &&
          failure.answerConfidence !== undefined
        ) {
          console.log(
            `    Confidence: ${failure.answerConfidence}% (threshold: ${failure.confidenceThreshold}%)`
          );
        }
      }

      // Show generated answer if available (helps debug false positives and quality issues)
      if (failure.generatedAnswer) {
        const truncated =
          failure.generatedAnswer.length > 200
            ? failure.generatedAnswer.slice(0, 200) + '...'
            : failure.generatedAnswer;
        console.log(`    Generated Answer: "${truncated}"`);
      }

      if (failure.missingFacts) {
        console.log(`    Missing facts: ${failure.missingFacts}`);
      }
      if (failure.factCheckReasoning) {
        console.log(`    Reasoning: ${failure.factCheckReasoning}`);
      }
    }
  }

  console.log('\n' + '='.repeat(80));
  console.log('Evaluation Complete');
  console.log('='.repeat(80));
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
