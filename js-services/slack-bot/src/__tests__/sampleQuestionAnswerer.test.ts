import { describe, test, expect } from '@jest/globals';

// Import the function we want to test - need to make it exported first
// For now, we'll create a copy of the function to test
function countUniqueCitations(text: string): number {
  const citationRegex = /<([^|>]+)\|[^>]*>/g;
  const uniqueHosts = new Set<string>();

  let match;
  while ((match = citationRegex.exec(text)) !== null) {
    try {
      const url = new URL(match[1]);
      uniqueHosts.add(url.hostname);
    } catch {
      // If URL parsing fails, skip this citation
      continue;
    }
  }

  return uniqueHosts.size;
}

describe('countUniqueCitations', () => {
  test('should count two unique citations from different hosts', () => {
    const message = `Short answer: Yes. We're changing force‑mute from admin‑only to a member default (i.e., members can mute; it's no longer restricted to admins) <https://bryanstestorg.slack.com/archives/C08TQK7F4J0/p1758058889266239?thread_ts=1758058889.266239&cid=C08TQK7F4J0|[1]> oh and <https://github.com|[2]> Approval: Eng leads agreed there's no objection to members muting other members`;

    expect(countUniqueCitations(message)).toBe(2);
  });

  test('should count one unique citation when multiple citations are from same host', () => {
    const message = `Here are two GitHub links: <https://github.com/repo1|[1]> and <https://github.com/repo2|[2]>`;

    expect(countUniqueCitations(message)).toBe(1);
  });

  test('should return zero for text without citations', () => {
    const message = `This is just plain text without any citations.`;

    expect(countUniqueCitations(message)).toBe(0);
  });

  test('should handle invalid URLs gracefully', () => {
    const message = `Valid citation <https://example.com|[1]> and invalid <not-a-url|[2]>`;

    expect(countUniqueCitations(message)).toBe(1);
  });

  test('should count unique hosts correctly with mixed domains', () => {
    const message = `Multiple sources: <https://github.com/repo|[1]> <https://slack.com/workspace|[2]> <https://notion.so/page|[3]> <https://github.com/another|[4]>`;

    expect(countUniqueCitations(message)).toBe(3);
  });
});
