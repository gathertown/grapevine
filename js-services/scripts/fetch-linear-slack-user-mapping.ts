import { LinearClient } from '@linear/sdk';
import { WebClient } from '@slack/web-api';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

interface UserMapping {
  linearId: string;
  linearName: string;
  linearDisplayName: string;
  linearEmail: string;
  slackUserId: string | null;
  slackUserName: string | null;
  slackRealName: string | null;
  slackEmail: string | null;
}

async function main() {
  const linearApiKey = process.env.LINEAR_API_KEY;
  const slackToken = process.env.SLACK_BOT_TOKEN;

  if (!linearApiKey) {
    console.error('Error: LINEAR_API_KEY environment variable is required');
    process.exit(1);
  }

  if (!slackToken) {
    console.error('Error: SLACK_BOT_TOKEN environment variable is required');
    process.exit(1);
  }

  // Initialize clients
  const linearClient = new LinearClient({ apiKey: linearApiKey });
  const slackClient = new WebClient(slackToken);

  console.log('Fetching all Linear users from organization...');

  // Fetch all users from the organization with pagination
  const allUsers = [];
  let hasNextPage = true;
  let endCursor: string | undefined = undefined;

  while (hasNextPage) {
    const users = await linearClient.users({
      after: endCursor,
      first: 100, // Fetch 100 users per page (max allowed)
    });

    allUsers.push(...users.nodes);

    hasNextPage = users.pageInfo.hasNextPage;
    endCursor = users.pageInfo.endCursor ?? undefined;

    console.log(`Fetched ${allUsers.length} users so far...`);
  }

  const linearUsers = allUsers.map((user) => ({
    id: user.id,
    name: user.name,
    displayName: user.displayName,
    email: user.email,
  }));

  console.log(`Found ${linearUsers.length} Linear users`);
  console.log('Fetching Slack users...');

  // Fetch all Slack users
  const slackUsersResponse = await slackClient.users.list({});
  const slackUsers = slackUsersResponse.members || [];

  console.log(`Found ${slackUsers.length} Slack users`);
  console.log('Mapping Linear users to Slack users...');

  // Create mapping
  const userMappings: UserMapping[] = [];

  for (const linearUser of linearUsers) {
    // Try to find matching Slack user by email
    const matchingSlackUser = slackUsers.find(
      (slackUser) => slackUser.profile?.email?.toLowerCase() === linearUser.email?.toLowerCase()
    );

    const mapping: UserMapping = {
      linearId: linearUser.id,
      linearName: linearUser.name,
      linearDisplayName: linearUser.displayName,
      linearEmail: linearUser.email || '',
      slackUserId: matchingSlackUser?.id || null,
      slackUserName: matchingSlackUser?.name || null,
      slackRealName: matchingSlackUser?.real_name || null,
      slackEmail: matchingSlackUser?.profile?.email || null,
    };

    userMappings.push(mapping);

    if (matchingSlackUser) {
      console.log(
        `✓ Mapped: ${linearUser.displayName} (${linearUser.email}) → @${matchingSlackUser.name}`
      );
    } else {
      console.log(`✗ No match: ${linearUser.displayName} (${linearUser.email})`);
    }
  }

  // Generate output
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const outputDir = path.join(process.cwd(), 'data');
  const jsonOutputPath = path.join(outputDir, `linear-slack-user-mapping-${timestamp}.json`);
  const csvOutputPath = path.join(outputDir, `linear-slack-user-mapping-${timestamp}.csv`);
  const tsOutputPath = path.join(outputDir, `linear-slack-user-mapping-${timestamp}.ts`);

  // Ensure output directory exists
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  // Write JSON output
  fs.writeFileSync(jsonOutputPath, JSON.stringify(userMappings, null, 2), 'utf-8');

  // Write CSV output
  const csvLines = [
    'Linear ID,Linear Name,Linear Display Name,Linear Email,Slack User ID,Slack Username,Slack Real Name,Slack Email',
    ...userMappings.map((mapping) =>
      [
        mapping.linearId,
        `"${mapping.linearName}"`,
        `"${mapping.linearDisplayName}"`,
        mapping.linearEmail,
        mapping.slackUserId || '',
        mapping.slackUserName || '',
        `"${mapping.slackRealName || ''}"`,
        mapping.slackEmail || '',
      ].join(',')
    ),
  ];
  fs.writeFileSync(csvOutputPath, csvLines.join('\n'), 'utf-8');

  // Write TypeScript output (ready to copy into primitives)
  const tsContent = `export const linearSlackUserMapping = ${JSON.stringify(userMappings, null, 2)};\n`;
  fs.writeFileSync(tsOutputPath, tsContent, 'utf-8');

  // Print summary
  const mappedCount = userMappings.filter((m) => m.slackUserId !== null).length;
  const unmappedCount = userMappings.length - mappedCount;

  console.log('\n=== Summary ===');
  console.log(`Total Linear users: ${linearUsers.length}`);
  console.log(`Mapped to Slack: ${mappedCount}`);
  console.log(`Not mapped: ${unmappedCount}`);
  console.log(`\nOutputs written to:`);
  console.log(`- ${jsonOutputPath}`);
  console.log(`- ${csvOutputPath}`);
  console.log(`- ${tsOutputPath} (copy this to primitives/linear-slack-user-mapping.ts)`);
}

main().catch((error) => {
  console.error('Error:', error);
  process.exit(1);
});
