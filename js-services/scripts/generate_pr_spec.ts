#!/usr/bin/env node

/**
 * Generate a test-bot spec for a PR by pulling deployment + test plan comments.
 *
 * Usage:
 *   node scripts/generate_pr_spec.ts --pr https://github.com/org/repo/pull/123 [--out spec.txt] [--copy] [--cursor-agent]
 *
 * Requirements:
 *   - Node 22.18+ (native type stripping; tested on Node 24).
 *   - GITHUB_TOKEN in env with read access to the repo.
 *   - macOS for --copy (uses pbcopy). --cursor-agent requires cursor-agent on PATH.
 */

import fs from 'node:fs';
import process from 'node:process';
import { execSync, execFileSync } from 'node:child_process';

interface Options {
  prUrl: string;
  outPath?: string;
  copy: boolean;
  cursorAgent: boolean;
  cursorAgentStream: boolean;
  cursorAgentForce: boolean;
  cursorAgentApproveMcps: boolean;
  stripMarkdown: boolean;
  printSpec: boolean;
}

interface PullRequest {
  html_url: string;
  title: string;
  body?: string | null;
}

interface Comment {
  body?: string | null;
  user?: { login?: string | null } | null;
}

function buildPreamble(opts: { email: string; password: string }): string {
  return `
You are a professional test bot. You will be given a Linear ticket, a link to a PR that fixes/satisfies the ticket, and a test plan that outlines how to ensure the PR works as expected.

A developer environment has been created for you to test this PR, and the URL to the admin site is provided below. Use this environment for all Grapevine interaction and don't leave it unless given explicit instructions to do so.

Many PRs require authentication to test properly. If you wish to log into the Grapevine admin site, you can do so with the following credentials:

Username: ${opts.email}
Password: ${opts.password}

The admin site also allows you to issue API keys which are useful for testing MCP or other API calls. To generate an API key:

1. Navigate to the admin site and log in.
2. Go to the API Keys page (nav is on the left).
3. Create a new API key. Name it whatever you want, but make sure "Verification Agent" is somewhere in the name.
4. Copy the API key. This key can be used in the header of API requests: \`Authorization: Bearer <GRAPEVINE_API_KEY>\`.
`.trim();
}

function appendExecutionBlock(spec: string): string {
  const block = `
=== EXECUTION MODE ===
You have permission to run commands and HTTP calls. Execute every test case above against the provided environment. Do not stop at review; run the steps and report results. If a step fails, continue with the remaining tests and note the failures. Use the provided dev environment URLs instead of localhost.`;
  return `${spec.trim()}\n\n${block.trim()}\n`;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const githubToken = process.env.GITHUB_TOKEN ?? process.env.GH_TOKEN;
  if (!githubToken) {
    throw new Error('GitHub token required (set GITHUB_TOKEN or GH_TOKEN).');
  }
  // TypeScript now knows githubToken is defined
  const token: string = githubToken;

  const loginEmail = requireEnv('VERIFICATION_LOOP_TEST_USER_EMAIL');
  const loginPassword = requireEnv('VERIFICATION_LOOP_TEST_USER_PASSWORD');

  const { owner, repo, number } = parsePrUrl(options.prUrl);

  // Validate token before attempting to fetch PR
  await validateGitHubToken(token, owner, repo);

  const pr = await fetchPullRequest(owner, repo, number, token);
  const comments = await fetchIssueComments(owner, repo, number, token);

  const preamble = buildPreamble({ email: loginEmail, password: loginPassword });
  const resources = buildResources({
    prUrl: pr.html_url,
    linearUrl: findLinearLink(pr, comments),
    deployment: findDeploymentDetails(comments),
  });
  const rawInstructions = extractTestPlan(comments);
  const instructions = options.stripMarkdown ? stripMarkdown(rawInstructions) : rawInstructions;

  const spec = [
    '=== PREAMBLE ===',
    preamble.trim(),
    '',
    '=== RESOURCES ===',
    resources.trim(),
    '',
    '=== INSTRUCTIONS ===',
    instructions.trim(),
    '',
  ].join('\n');

  const fullSpec =
    options.cursorAgent || options.cursorAgentStream ? appendExecutionBlock(spec) : spec;

  if (options.outPath) {
    fs.writeFileSync(options.outPath, fullSpec, 'utf8');
    console.log(`Spec written to ${options.outPath}`);
  }
  if (options.printSpec) {
    console.log(fullSpec);
  }

  if (options.copy) {
    copyToClipboard(fullSpec);
    console.log('✅ Copied spec to clipboard.');
  }

  if (options.cursorAgent || options.cursorAgentStream) {
    console.log('⚡ Running cursor-agent with the generated spec...');
    runCursorAgent(fullSpec, {
      streamThinking: options.cursorAgentStream,
      force: options.cursorAgentForce,
      approveMcps: options.cursorAgentApproveMcps,
    });
  }
}

function parseArgs(argv: string[]): Options {
  const opts: Options = {
    prUrl: '',
    copy: false,
    cursorAgent: false,
    cursorAgentStream: false,
    cursorAgentForce: false,
    cursorAgentApproveMcps: false,
    stripMarkdown: false,
    printSpec: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--pr') {
      if (i + 1 >= argv.length) {
        throw new Error('--pr requires a URL argument');
      }
      opts.prUrl = argv[i + 1];
      i += 1;
    } else if (arg === '--out') {
      if (i + 1 >= argv.length) {
        throw new Error('--out requires a path argument');
      }
      opts.outPath = argv[i + 1];
      i += 1;
    } else if (arg === '--copy') {
      opts.copy = true;
    } else if (arg === '--cursor-agent') {
      opts.cursorAgent = true;
    } else if (arg === '--strip-markdown') {
      opts.stripMarkdown = true;
    } else if (arg === '--cursor-agent-stream') {
      opts.cursorAgentStream = true;
    } else if (arg === '--cursor-agent-force') {
      opts.cursorAgentForce = true;
    } else if (arg === '--cursor-agent-approve-mcps') {
      opts.cursorAgentApproveMcps = true;
    } else if (arg === '--print-spec') {
      opts.printSpec = true;
    } else if (arg === '--help' || arg === '-h') {
      printHelp();
      process.exit(0);
    }
  }
  if (!opts.prUrl) {
    printHelp();
    throw new Error('Missing required --pr <url>');
  }
  return opts;
}

function printHelp() {
  console.log(`Generate test-bot spec from a GitHub PR

Options:
  --pr <url>          GitHub PR URL (e.g., https://github.com/org/repo/pull/123)
  --out <path>        Write spec to file (optional; otherwise stdout)
  --copy              Copy spec to clipboard (macOS pbcopy)
  --cursor-agent      Run: cursor-agent --print --browser "<spec>" (final responses only)
  --cursor-agent-stream  Stream partial/thinking output: adds --output-format stream-json --stream-partial-output
  --cursor-agent-force   Pass --force to cursor-agent (auto-approve commands)
  --cursor-agent-approve-mcps  Pass --approve-mcps to cursor-agent
  --strip-markdown    Convert instructions to plain text (default: keep markdown)
  --print-spec        Also print the spec to stdout (default: suppress if not writing to file)

Required env vars:
  GITHUB_TOKEN (or GH_TOKEN)
  VERIFICATION_LOOP_TEST_USER_EMAIL
  VERIFICATION_LOOP_TEST_USER_PASSWORD

Example:
  node scripts/generate_pr_spec.ts --pr <url> --copy
`);
}

function parsePrUrl(prUrl: string): { owner: string; repo: string; number: number } {
  const url = new URL(prUrl);
  if (url.hostname !== 'github.com') {
    throw new Error(`Invalid GitHub PR URL: ${prUrl}`);
  }
  const parts = url.pathname.split('/').filter(Boolean); // [org, repo, 'pull', number]
  if (parts.length < 4 || parts[2] !== 'pull') {
    throw new Error(`Invalid PR path: ${url.pathname}`);
  }
  const [owner, repo, , num] = parts;
  if (!owner || !repo || !num) {
    throw new Error(`Invalid PR path: ${url.pathname}`);
  }
  const number = Number(num);
  if (Number.isNaN(number)) throw new Error(`PR number is not numeric: ${num}`);
  return { owner, repo, number };
}

async function validateGitHubToken(token: string, owner: string, repo: string): Promise<void> {
  // First, check if token is valid by checking the authenticated user
  const userRes = await fetch('https://api.github.com/user', {
    headers: {
      'User-Agent': 'generate-pr-spec-script',
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
    },
  });

  if (userRes.status === 401) {
    throw new Error(
      'GitHub token is invalid or expired. Please check your GITHUB_TOKEN or GH_TOKEN environment variable.'
    );
  }

  if (!userRes.ok) {
    const body = await safeReadBody(userRes);
    throw new Error(
      `Failed to validate GitHub token: ${userRes.status} ${userRes.statusText} - ${body}`
    );
  }

  // Check if we can access the repository
  const repoRes = await fetch(`https://api.github.com/repos/${owner}/${repo}`, {
    headers: {
      'User-Agent': 'generate-pr-spec-script',
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
    },
  });

  if (repoRes.status === 404) {
    throw new Error(
      `Repository ${owner}/${repo} not found or you don't have access to it. ` +
        `Make sure your token has the 'repo' scope for private repositories.`
    );
  }

  if (!repoRes.ok) {
    const body = await safeReadBody(repoRes);
    throw new Error(
      `Failed to access repository ${owner}/${repo}: ${repoRes.status} ${repoRes.statusText} - ${body}`
    );
  }
}

async function fetchPullRequest(
  owner: string,
  repo: string,
  number: number,
  token: string
): Promise<PullRequest> {
  // Validate token format (should start with ghp_, gho_, or gh_)
  if (!token || token.length < 10) {
    throw new Error(
      `Invalid GitHub token format. Token appears to be missing or too short. ` +
        `Make sure GITHUB_TOKEN or GH_TOKEN is set in your environment.`
    );
  }

  const headers = {
    'User-Agent': 'generate-pr-spec-script',
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github+json',
  };

  // Try the pulls endpoint first (standard for PRs)
  const pullsUrl = `https://api.github.com/repos/${owner}/${repo}/pulls/${number}`;
  let res = await fetch(pullsUrl, { headers });

  // If 404, try the issues endpoint as fallback (PRs are also issues, and this sometimes works better for draft PRs)
  if (res.status === 404) {
    const issuesUrl = `https://api.github.com/repos/${owner}/${repo}/issues/${number}`;
    res = await fetch(issuesUrl, { headers });

    if (res.ok) {
      // Issues endpoint returns issue data, but we need to check if it's actually a PR
      const issueData = (await res.json()) as any;
      if (issueData.pull_request) {
        // It's a PR, but we got it from the issues endpoint
        // Try to get full PR data from the pull_request URL
        const prRes = await fetch(issueData.pull_request.url, { headers });
        if (prRes.ok) {
          const prData = (await prRes.json()) as PullRequest;
          return prData;
        }
        // If that fails, construct a minimal PR object from issue data
        return {
          html_url: issueData.html_url,
          title: issueData.title,
          body: issueData.body,
        };
      }
      // If the issue is not a PR, throw an error
      throw new Error(
        `Issue #${number} exists but is not a pull request. ` +
          `Please verify the PR number is correct.`
      );
    }
  }

  if (!res.ok) {
    const body = await safeReadBody(res);

    if (res.status === 404) {
      // Provide more helpful error message for 404s
      const errorMsg =
        `Failed to fetch PR #${number} from ${owner}/${repo}.\n` +
        `Possible causes:\n` +
        `  1. The PR doesn't exist or has been deleted\n` +
        `  2. The repository is private and your token doesn't have access\n` +
        `  3. The token doesn't have the 'repo' scope (required for private repos)\n` +
        `  4. The token is invalid or expired\n` +
        `  5. The PR might be a draft and requires additional permissions\n\n` +
        `API Response: ${res.status} ${res.statusText} - ${body}\n` +
        `Tried URLs: ${pullsUrl}, https://api.github.com/repos/${owner}/${repo}/issues/${number}`;
      throw new Error(errorMsg);
    }

    throw new Error(`Failed to fetch PR: ${res.status} ${res.statusText} - ${body}`);
  }

  const data = (await res.json()) as PullRequest;
  return data;
}

async function fetchIssueComments(
  owner: string,
  repo: string,
  number: number,
  token: string
): Promise<Comment[]> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${number}/comments?per_page=100`,
    {
      headers: {
        'User-Agent': 'generate-pr-spec-script',
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
      },
    }
  );
  if (!res.ok) {
    const body = await safeReadBody(res);
    throw new Error(`Failed to fetch comments: ${res.status} ${res.statusText} - ${body}`);
  }
  const data = (await res.json()) as Comment[];
  return data;
}

function findLinearLink(pr: PullRequest, comments: Comment[]): string | undefined {
  const linearPattern = /https?:\/\/linear\.app\/[^\s)]+/i;
  const fromPr = pr.body?.match(linearPattern)?.[0];
  if (fromPr) return fromPr;
  for (const comment of comments) {
    const match = comment.body?.match(linearPattern)?.[0];
    if (match) return match;
  }
  return undefined;
}

function findDeploymentDetails(comments: Comment[]) {
  const deploymentComment = comments.find(
    (c) =>
      (c.user?.login ?? '').includes('github-actions') &&
      (c.body ?? '').toLowerCase().includes('deployment status')
  );
  const body = deploymentComment?.body ?? '';
  return {
    adminUi: matchUrl(body, /Admin UI:\s*(https?:\/\/\S+)/i),
    adminApi: matchUrl(body, /Admin Backend API:\s*(https?:\/\/\S+)/i),
    mcp: matchUrl(body, /MCP API:\s*(https?:\/\/\S+)/i),
  };
}

function matchUrl(text: string, pattern: RegExp): string | undefined {
  const match = text.match(pattern);
  return match ? match[1] : undefined;
}

function extractTestPlan(comments: Comment[]): string {
  const testPlanComment =
    comments.find(
      (c) =>
        (c.user?.login ?? '').includes('github-actions') &&
        (c.body ?? '').toLowerCase().includes('generated test plan')
    ) ?? comments.find((c) => (c.body ?? '').toLowerCase().includes('generated test plan'));

  if (!testPlanComment?.body) {
    throw new Error('Could not find a "Generated Test Plan" comment on the PR.');
  }
  // Strip the leading title line if present.
  const lines = testPlanComment.body.split('\n');
  const trimmedLines = lines[0]?.toLowerCase().includes('generated test plan')
    ? lines.slice(1).join('\n')
    : testPlanComment.body;
  return trimmedLines.trim();
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env var ${name}.`);
  }
  return value;
}

async function safeReadBody(res: Response): Promise<string> {
  try {
    const text = await res.text();
    if (!text) return '<empty>';
    return text.slice(0, 500);
  } catch {
    return '<unreadable>';
  }
}

function buildResources({
  prUrl,
  linearUrl,
  deployment,
}: {
  prUrl: string;
  linearUrl?: string;
  deployment: { adminUi?: string; adminApi?: string; mcp?: string };
}): string {
  return [
    `Linear Ticket: ${linearUrl ?? 'TODO: add Linear ticket link'}`,
    `Github PR: ${prUrl}`,
    `Developer Environment Admin UI: ${deployment.adminUi ?? 'TODO: admin site URL'}`,
    `Developer Environment Admin Backend API: ${deployment.adminApi ?? 'TODO: admin API URL'}`,
    `Developer Environment MCP Server: ${deployment.mcp ?? 'TODO: MCP server URL'}`,
    '',
    'If links in the instructions mention localhost:8000, use the developer environment URLs instead.',
  ].join('\n');
}

function copyToClipboard(text: string) {
  try {
    execSync('pbcopy', { input: text });
  } catch (err) {
    console.warn('Clipboard copy failed (pbcopy not available).');
  }
}

function runCursorAgent(
  prompt: string,
  opts: { streamThinking: boolean; force: boolean; approveMcps: boolean }
) {
  const baseArgs = ['--print', '--browser'];
  if (opts.force) baseArgs.push('--force');
  if (opts.approveMcps) baseArgs.push('--approve-mcps');
  const args = opts.streamThinking
    ? [...baseArgs, '--output-format', 'stream-json', '--stream-partial-output', prompt]
    : [...baseArgs, prompt];
  try {
    execFileSync('cursor-agent', args, { stdio: 'inherit' });
  } catch (err) {
    console.warn('Failed to run cursor-agent. Is it installed and on PATH?');
  }
}

function stripMarkdown(input: string): string {
  return (
    input
      // Remove fenced code blocks (keep contents)
      .replace(/```+/g, '')
      // Inline code
      .replace(/`([^`]+)`/g, '$1')
      // Images ![alt](url) -> alt
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
      // Links [text](url) -> text
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      // Headings
      .replace(/^#{1,6}\s+/gm, '')
      // Bold/italic
      .replace(/\*\*(.+?)\*\*/g, '$1')
      .replace(/\*(.+?)\*/g, '$1')
      .replace(/__(.+?)__/g, '$1')
      // Bullet/ordered list markers
      .replace(/^\s*[-*+]\s+/gm, '')
      .replace(/^\s*\d+\.\s+/gm, '')
      // Collapse multiple blank lines
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  );
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
