#!/usr/bin/env node
/**
 * Test Proactive Post-filter Accuracy
 *
 * Tests the isGoodAnswerToQuestion post-filter against a set of predefined
 * question-answer pairs to measure accuracy and consistency. Each test case runs
 * multiple times (default: 3) to measure stability.
 *
 * Usage:
 *   npx tsx scripts/test-postfilter-accuracy.ts [--attempts=N]
 *
 * Options:
 *   --attempts=N    Number of times to run each test (default: 3)
 *
 * Environment:
 *   OPENAI_API_KEY  Required for OpenAI API access
 */

import { isGoodAnswerToQuestion } from '../src/common';

// Track results for each test across all attempts
interface TestResult {
  testName: string;
  expectedValue: boolean;
  attempts: number;
  passed: number;
  failed: number;
  results: boolean[]; // actual results from each attempt
  runtimes: number[]; // runtime in milliseconds for each attempt
}

interface TestCase {
  name: string;
  question: string;
  answer: string;
  expected: boolean;
}

// Define all test cases
const testCases: TestCase[] = [
  // Should answer TRUE (high-quality answers that should be posted)
  {
    name: 'direct answer with specific info',
    question: 'How do I configure the auth settings in our app?',
    answer: `To configure auth settings in the app, you need to:

1. Navigate to the \`config/auth.ts\` file
2. Set the \`AUTH_PROVIDER\` environment variable to either 'oauth' or 'saml'
3. For OAuth, configure these settings:
   - \`OAUTH_CLIENT_ID\`: Your OAuth client ID
   - \`OAUTH_CLIENT_SECRET\`: Your OAuth client secret
   - \`OAUTH_REDIRECT_URI\`: The callback URL for your app

4. For SAML, configure:
   - \`SAML_ENTITY_ID\`: Your SAML entity ID
   - \`SAML_SSO_URL\`: The SSO endpoint URL
   - \`SAML_CERT\`: The certificate for signature verification

The config file includes detailed comments explaining each option.`,
    expected: true,
  },
  {
    name: 'concrete procedure with steps',
    question: 'How do we handle customer refunds?',
    answer: `Our customer refund process follows these steps:

1. Customer submits refund request via the support portal
2. Support team reviews the request within 24 hours
3. If approved, refund is processed through the original payment method:
   - Credit card refunds: 3-5 business days
   - PayPal refunds: 1-2 business days
   - Wire transfers: 5-7 business days
4. Customer receives automated email confirmation once processed

For urgent cases, contact the billing team directly at billing@company.com.`,
    expected: true,
  },
  {
    name: 'specific ownership info',
    question: 'Who owns the payments integration?',
    answer:
      'The payments integration is owned by the Platform team. The primary maintainers are Sarah Chen (@sarah) and Mike Rodriguez (@mike). For questions about the Stripe integration specifically, reach out to Sarah. For PayPal-related issues, Mike is your go-to person.',
    expected: true,
  },
  {
    name: 'detailed technical explanation',
    question: 'Can someone explain how our CI/CD pipeline works?',
    answer: `Our CI/CD pipeline runs on GitHub Actions and follows this flow:

1. **On Pull Request**: Runs linting, type checking, and unit tests
2. **On Merge to main**:
   - Builds Docker images for all services
   - Pushes to ECR with commit SHA tags
   - Runs integration tests against staging
3. **On Tag Push** (e.g., v1.2.3):
   - Deploys to production using Kubernetes
   - Applies database migrations automatically
   - Runs smoke tests post-deployment

The full pipeline configuration is in \`.github/workflows/ci.yml\`. Deployment is handled by ArgoCD.`,
    expected: true,
  },
  {
    name: 'answer with helpful examples',
    question: "What's our PTO policy?",
    answer: `Our PTO policy provides:

- **Unlimited PTO** for all full-time employees
- Encouraged minimum of 15 days per year
- Major holidays are company-wide closures (not counted against PTO)
- Submit PTO requests via BambooHR at least 2 weeks in advance
- Blackout dates: December 1-15 for engineering (release window)

Examples of common PTO patterns:
- Extended vacation: 2+ weeks requires manager approval
- Sick days: No advance notice needed, just notify your manager
- Mental health days: Treat the same as sick days

See the full policy in the Employee Handbook on Notion.`,
    expected: true,
  },

  // Should answer FALSE (low-quality answers that should NOT be posted)
  {
    name: 'deflection to other sources',
    question: 'How do I configure the auth settings in our app?',
    answer:
      "I don't have access to the specific auth configuration documentation for your app. You should check the engineering documentation or ask the platform team directly.",
    expected: false,
  },
  {
    name: 'suggests asking others',
    question: 'Who owns the payments integration?',
    answer:
      "I couldn't find definitive information about ownership of the payments integration. Your best bet would be to ask in the #engineering channel or check with your team lead.",
    expected: false,
  },
  {
    name: 'vague non-answer',
    question: "What's our PTO policy?",
    answer:
      'PTO policies vary by company and role. You should consult your employee handbook or reach out to HR for specific details about your benefits.',
    expected: false,
  },
  {
    name: 'disclaimer undermining confidence',
    question: 'How do we handle customer refunds?',
    answer:
      "While I found some information about refunds, I'm not entirely confident in the accuracy of this process. I'd recommend checking with the support team or customer success manager to get the authoritative answer on our refund procedures.",
    expected: false,
  },
  {
    name: 'no relevant info found',
    question: 'Can someone explain how our CI/CD pipeline works?',
    answer:
      "I wasn't able to find detailed documentation about your CI/CD pipeline setup. This type of infrastructure information might be in confluence or internal docs that I don't have access to.",
    expected: false,
  },
  {
    name: 'clearly incomplete answer',
    question: 'How do I set up the development environment?',
    answer: `To set up the dev environment:

1. Install Node.js 18+
2. Clone the repository
3. Run npm install
4. Configure your

[The answer appears to be cut off here]`,
    expected: false,
  },
  {
    name: 'multiple caveats and disclaimers',
    question: 'Where can I find the Q3 roadmap?',
    answer:
      "Based on limited information I found, the roadmap might be in Notion, but I'm not certain which workspace or page. You should probably ask the product team directly, or check the #product-updates channel. Note that I don't have full access to your Notion workspace so there may be more recent updates I'm missing.",
    expected: false,
  },

  // Real-world edge cases
  {
    name: 'good answer with minor caveat',
    question: 'What feature flags are enabled for dark mode?',
    answer:
      'The dark mode feature is controlled by the `enable_dark_mode` flag in Statsig. Currently enabled for 50% of users in production. You can override it locally by adding `?dark_mode=true` to the URL. Note: some components may not be fully styled yet - track progress in issue #342.',
    expected: true,
  },
  {
    name: 'partial info but actionable',
    question: 'How do I access the staging database?',
    answer:
      'Staging database access requires VPN connection. Connect to the engineering VPN, then use these credentials from 1Password (vault: Engineering). The connection string format is in the deploy docs. If you need write access, submit a request via the #infrastructure channel.',
    expected: true,
  },
  {
    name: 'honest limitation but with helpful info',
    question: 'What was decided in the last architecture review?',
    answer:
      "I don't have access to the most recent architecture review meeting notes, but I can see the previous review (2 weeks ago) decided to move forward with PostgreSQL over MongoDB for the new service. For the latest decisions, check the #architecture channel or the meeting notes in Notion.",
    expected: false,
  },
  {
    name: 'generic advice without specifics',
    question: 'How should I structure my pull requests?',
    answer:
      'Good pull requests should have clear descriptions, be reasonably sized, include tests, and follow coding standards. Make sure to address review comments promptly and keep your branch up to date with main.',
    expected: false,
  },
];

async function runTest(
  testCase: TestCase,
  attemptNumber: number,
  totalAttempts: number
): Promise<{ result: boolean; runtime: number }> {
  process.stdout.write(
    `\r[${attemptNumber}/${totalAttempts}] Testing: ${testCase.name.padEnd(40)} `
  );

  const startTime = Date.now();
  const result = await isGoodAnswerToQuestion(testCase.question, testCase.answer);
  const runtime = Date.now() - startTime;

  return { result, runtime };
}

function recordResult(
  results: TestResult[],
  testName: string,
  expected: boolean,
  actual: boolean,
  runtime: number
): void {
  let result = results.find((r) => r.testName === testName);
  if (!result) {
    result = {
      testName,
      expectedValue: expected,
      attempts: 0,
      passed: 0,
      failed: 0,
      results: [],
      runtimes: [],
    };
    results.push(result);
  }

  result.attempts++;
  result.results.push(actual);
  result.runtimes.push(runtime);
  if (actual === expected) {
    result.passed++;
  } else {
    result.failed++;
  }
}

function printTestResult(result: TestResult): void {
  // Clear progress line
  process.stdout.write('\r' + ' '.repeat(80) + '\r');

  const icon = result.passed === result.attempts ? '✅' : '❌';
  const percentage = Math.round((result.passed / result.attempts) * 100);
  const dots = result.results.map((r) => (r === result.expectedValue ? '✓' : '✗')).join(' ');
  const expectedLabel = result.expectedValue ? 'GOOD' : 'BAD';

  console.log(
    `${icon} ${result.testName.padEnd(40)} ${result.passed}/${result.attempts} (${percentage.toString().padStart(3)}%) [${expectedLabel}] ${dots}`
  );
}

function printSummary(results: TestResult[]): void {
  console.log('\n\n' + '='.repeat(60));
  console.log('Proactive Post-filter Accuracy Results');
  console.log('='.repeat(60) + '\n');

  // Group by expected value
  const shouldBeGood = results.filter((r) => r.expectedValue === true);
  const shouldBeBad = results.filter((r) => r.expectedValue === false);

  const printGroup = (title: string, groupResults: TestResult[]) => {
    const totalAttempts = groupResults.reduce((sum, r) => sum + r.attempts, 0);
    const totalPassed = groupResults.reduce((sum, r) => sum + r.passed, 0);

    console.log(`${title} (${groupResults.length} tests, ${totalAttempts} attempts):`);
    console.log('-'.repeat(60));

    groupResults.forEach((result) => {
      const icon = result.passed === result.attempts ? '✓' : '✗';
      const percentage = Math.round((result.passed / result.attempts) * 100);
      const dots = result.results.map((r) => (r === result.expectedValue ? '✓' : '✗')).join('');

      console.log(
        `${icon} ${result.testName.padEnd(38)} ${result.passed}/${result.attempts} (${percentage.toString().padStart(3)}%) ${dots}`
      );
    });

    const subtotalPercentage = Math.round((totalPassed / totalAttempts) * 100);
    console.log(`Subtotal: ${totalPassed}/${totalAttempts} (${subtotalPercentage}%)\n`);
  };

  printGroup('High-Quality Answers (should pass filter)', shouldBeGood);
  printGroup('Low-Quality Answers (should be filtered)', shouldBeBad);

  // Overall statistics
  const totalAttempts = results.reduce((sum, r) => sum + r.attempts, 0);
  const totalPassed = results.reduce((sum, r) => sum + r.passed, 0);
  const overallPercentage = Math.round((totalPassed / totalAttempts) * 100);

  // Calculate runtime statistics
  const allRuntimes = results.flatMap((r) => r.runtimes);
  const totalRuntime = allRuntimes.reduce((sum, rt) => sum + rt, 0);
  const avgRuntime = totalRuntime / allRuntimes.length;

  console.log('='.repeat(60));
  console.log(`Overall Score: ${totalPassed}/${totalAttempts} (${overallPercentage}%)`);
  console.log(`Total Runtime: ${(totalRuntime / 1000).toFixed(2)}s`);
  console.log(`Average Runtime: ${avgRuntime.toFixed(0)}ms per evaluation`);
  console.log('='.repeat(60) + '\n');
}

async function main() {
  // Parse command line arguments
  const args = process.argv.slice(2);
  let attempts = 3;

  for (const arg of args) {
    if (arg.startsWith('--attempts=')) {
      const value = parseInt(arg.split('=')[1], 10);
      if (!isNaN(value) && value > 0) {
        attempts = value;
      }
    }
  }

  // Check for OpenAI API key
  if (!process.env.OPENAI_API_KEY) {
    console.error('❌ Error: OPENAI_API_KEY environment variable is required');
    console.error('Run with: OPENAI_API_KEY=sk-... npx tsx scripts/test-postfilter-accuracy.ts');
    process.exit(1);
  }

  console.log('🔍 Testing Proactive Post-filter Accuracy');
  console.log(
    `Running ${testCases.length} test cases × ${attempts} attempts = ${testCases.length * attempts} total tests\n`
  );

  const testResults: TestResult[] = [];
  let currentTest = 0;
  const totalTests = testCases.length * attempts;

  // Run all tests
  for (const testCase of testCases) {
    const testResult: TestResult = {
      testName: testCase.name,
      expectedValue: testCase.expected,
      attempts: 0,
      passed: 0,
      failed: 0,
      results: [],
      runtimes: [],
    };
    testResults.push(testResult);

    for (let i = 1; i <= attempts; i++) {
      currentTest++;
      const { result, runtime } = await runTest(testCase, currentTest, totalTests);
      recordResult(testResults, testCase.name, testCase.expected, result, runtime);
    }

    // Print result for this test case immediately after all attempts complete
    printTestResult(testResult);
  }

  console.log(); // Empty line before summary

  // Print summary
  printSummary(testResults);

  // Exit with appropriate code
  const totalAttempts = testResults.reduce((sum, r) => sum + r.attempts, 0);
  const totalPassed = testResults.reduce((sum, r) => sum + r.passed, 0);
  const overallPercentage = Math.round((totalPassed / totalAttempts) * 100);

  // Exit code 0 if >= 80% pass rate, 1 otherwise
  const threshold = 80;
  if (overallPercentage >= threshold) {
    console.log(`✅ Post-filter passed (${overallPercentage}% >= ${threshold}% threshold)`);
    process.exit(0);
  } else {
    console.log(`❌ Post-filter failed (${overallPercentage}% < ${threshold}% threshold)`);
    process.exit(1);
  }
}

// Run the script
main().catch((error) => {
  console.error('❌ Fatal error:', error);
  process.exit(1);
});
