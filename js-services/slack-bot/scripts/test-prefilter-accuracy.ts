#!/usr/bin/env node
/**
 * Test Proactive Prefilter Accuracy
 *
 * Tests the shouldTryToAnswerMessage prefilter against a set of predefined
 * questions to measure accuracy and consistency. Each test case runs multiple
 * times (default: 3) to measure stability.
 *
 * Usage:
 *   npx tsx scripts/test-prefilter-accuracy.ts [--attempts=N]
 *
 * Options:
 *   --attempts=N    Number of times to run each test (default: 3)
 *
 * Environment:
 *   OPENAI_API_KEY  Required for OpenAI API access
 */

import { shouldTryToAnswerMessage, ShouldAnswerResponse } from '../src/common';

// Track results for each test across all attempts
interface TestResult {
  testName: string;
  expectedValue: boolean;
  attempts: number;
  passed: number;
  failed: number;
  results: boolean[]; // actual results from each attempt
  failures: Array<{ attemptNumber: number; reasoning: string }>; // reasoning for failed attempts
  runtimes: number[]; // runtime in milliseconds for each attempt
}

interface TestCase {
  name: string;
  question: string;
  expected: boolean;
  sources?: string[];
}

// Define all test cases
const testCases: TestCase[] = [
  // Should answer TRUE (work-related questions)
  {
    name: 'technical configuration question',
    question: 'How do I configure the auth settings in our app?',
    expected: true,
  },
  {
    name: 'company policy question',
    question: "What's our PTO policy?",
    expected: true,
  },
  {
    name: 'documentation location question',
    question: 'Where can I find the Q3 roadmap?',
    expected: true,
  },
  {
    name: 'ownership/responsibility question',
    question: 'Who owns the payments integration?',
    expected: true,
  },
  {
    name: 'process/procedure question',
    question: 'How do we handle customer refunds?',
    expected: true,
  },
  {
    name: 'feature flag question',
    question: 'What feature flags are enabled for dark mode?',
    expected: true,
  },
  {
    name: 'infrastructure question',
    question: 'Can someone explain how our CI/CD pipeline works?',
    expected: true,
  },

  // Should answer FALSE (non-work questions)
  {
    name: 'casual greeting/check-in',
    question: "Hey, how's everyone doing today?",
    expected: false,
  },
  {
    name: 'personal question',
    question: 'What should I cook for dinner?',
    expected: false,
  },
  {
    name: 'external/general knowledge question',
    question: "What's the weather like over there today?",
    expected: false,
  },
  {
    name: 'social chatter',
    question: "lol that's hilarious",
    expected: false,
  },
  {
    name: 'greeting',
    question: 'Good morning team!',
    expected: false,
  },
  {
    name: 'opinion-seeking from specific person',
    question: '@john what do you think about this approach?',
    expected: false,
  },
  {
    name: 'command/request',
    question: 'Can you grab coffee?',
    expected: false,
  },

  // Real-world examples
  {
    name: 'complex customer question',
    question:
      'Can anyone help with these questions from a customer? ' +
      'Has questions on meeting memo functionality to see if it can feasibly replace otter.ai. ' +
      'Thank you for that detail. Since you brought up replacing otter I do have a few questions pertaining to that. ' +
      'Can it record when I cannot actually attend a meeting? ' +
      'For folks I am meeting with that do not want to come on to the gather platform as a guest can I record the meeting if I am hosting through Google meet? ' +
      'My clients are in the trades and are not always willing to adopt tech. ' +
      'A flaw I have found with the otter platform is that if I am using a headset and am trying to record an impromptu call it will only record my voice so I have to keep the call throw Google Voice on my phone on speaker. Would that be an issue with gather?',
    expected: true,
    sources: ['github', 'slack'],
  },
  {
    name: 'Gather code question',
    question: 'What is the escape hatch to create a v1 space? Dave do you know',
    expected: true,
    sources: ['github_code', 'notion', 'slack'],
  },
  {
    name: 'feature question',
    question:
      'Via Deepr: We want to ask if it is possible that guests in Gather are being able to write chats. At the moment we have a freelancer in the space for only today and he cant write with us',
    expected: true,
    sources: ['github', 'notion', 'slack'],
  },
  {
    name: 'technical question',
    question:
      'do you think we could make some kind of redirect ? I can also update the URL in the V1 repo I guess',
    expected: true,
    sources: ['github'],
  },
  {
    name: 'meeting status',
    // from Aterlo
    question: `is standup ongoing rn? gather isn't working`,
    expected: false,
    sources: ['github', 'slack', 'notion'],
  },
  {
    name: 'Reddy product decision',
    question:
      `1. Dispute feedback - we'll add a button to the right of acknowledge for disputing. We should ship with both.` +
      `It's good to know that we need to close the loop on dashboard and then reporting for each data point we add. Should we` +
      `go ahead and add to the dashboard the ability to view calls with acknowledged and disputed feedback? do you think they` +
      `need a view to zip through all feedback without going in call by call?`,
    expected: false,
    sources: ['github', 'slack', 'notion'],
  },
  {
    name: 'plausible that we could have this info',
    // from Sensay.
    question: 'when / where are we announcing full list of winners?',
    expected: true,
    sources: ['slack', 'google_drive'],
  },
  {
    name: 'request to change process',
    question: 'Can we remove the on call message? I think nobody is filling it since weeks anymore',
    expected: false,
    sources: ['slack', 'notion', 'google_drive'],
  },
  {
    name: 'should question',
    question:
      `for the case where someone asks a question but then it doesn’t have context in earlier in ` +
      `the thread, should we consider sending a message that additionally says, “hey I only have ` +
      `context from the message you send and any thread contents above, so in the future tag me ` +
      `as a follow-up as a thread to that message”`,
    expected: false,
    sources: ['slack', 'github_code', 'notion'],
  },
];

async function runTest(
  testCase: TestCase,
  attemptNumber: number,
  totalAttempts: number
): Promise<{ response: ShouldAnswerResponse; runtime: number }> {
  process.stdout.write(
    `\r[${attemptNumber}/${totalAttempts}] Testing: ${testCase.name.padEnd(40)} `
  );

  const startTime = Date.now();
  const response = await shouldTryToAnswerMessage(testCase.question, testCase.sources);
  const runtime = Date.now() - startTime;

  return { response, runtime };
}

function recordResult(
  results: TestResult[],
  testName: string,
  expected: boolean,
  actual: boolean,
  attemptNumber: number,
  reasoning: string,
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
      failures: [],
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
    result.failures.push({ attemptNumber, reasoning });
  }
}

function printTestResult(result: TestResult): void {
  // Clear progress line
  process.stdout.write('\r' + ' '.repeat(80) + '\r');

  const icon = result.passed === result.attempts ? '✅' : '❌';
  const percentage = Math.round((result.passed / result.attempts) * 100);
  const dots = result.results.map((r) => (r === result.expectedValue ? '✓' : '✗')).join(' ');
  const expectedLabel = result.expectedValue ? 'ANSWER' : 'SKIP';

  console.log(
    `${icon} ${result.testName.padEnd(40)} ${result.passed}/${result.attempts} (${percentage.toString().padStart(3)}%) [${expectedLabel}] ${dots}`
  );

  // Print failure reasoning if any failures occurred
  if (result.failures.length > 0) {
    result.failures.forEach((failure) => {
      console.log(`   └─ Attempt ${failure.attemptNumber}: ${failure.reasoning}`);
    });
  }
}

function printSummary(results: TestResult[]): void {
  console.log('\n\n' + '='.repeat(60));
  console.log('Proactive Prefilter Accuracy Results');
  console.log('='.repeat(60) + '\n');

  // Group by expected value
  const shouldAnswerTrue = results.filter((r) => r.expectedValue === true);
  const shouldAnswerFalse = results.filter((r) => r.expectedValue === false);

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

      // Print failure reasoning if any failures occurred
      if (result.failures.length > 0) {
        result.failures.forEach((failure) => {
          console.log(`    Attempt ${failure.attemptNumber}: ${failure.reasoning}`);
        });
      }
    });

    const subtotalPercentage = Math.round((totalPassed / totalAttempts) * 100);
    console.log(`Subtotal: ${totalPassed}/${totalAttempts} (${subtotalPercentage}%)\n`);
  };

  printGroup('Should Answer TRUE', shouldAnswerTrue);
  printGroup('Should Answer FALSE', shouldAnswerFalse);

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
  console.log(`Average Runtime: ${avgRuntime.toFixed(0)}ms per response`);
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
    console.error('Run with: OPENAI_API_KEY=sk-... npx tsx scripts/test-prefilter-accuracy.ts');
    process.exit(1);
  }

  console.log('🔍 Testing Proactive Prefilter Accuracy');
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
      failures: [],
      runtimes: [],
    };
    testResults.push(testResult);

    for (let i = 1; i <= attempts; i++) {
      currentTest++;
      const { response, runtime } = await runTest(testCase, currentTest, totalTests);
      recordResult(
        testResults,
        testCase.name,
        testCase.expected,
        response.shouldAnswer,
        i,
        response.reasoning,
        runtime
      );
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
    console.log(`✅ Prefilter passed (${overallPercentage}% >= ${threshold}% threshold)`);
    process.exit(0);
  } else {
    console.log(`❌ Prefilter failed (${overallPercentage}% < ${threshold}% threshold)`);
    process.exit(1);
  }
}

// Run the script
main().catch((error) => {
  console.error('❌ Fatal error:', error);
  process.exit(1);
});
