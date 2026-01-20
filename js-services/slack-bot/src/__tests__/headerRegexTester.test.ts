import { describe, test, expect } from '@jest/globals';
import { stripMessageHeader } from '../common';

describe('Header Regex Tester', () => {
  // Use the shared function from common.ts

  const testCases = [
    {
      name: 'standard format',
      input:
        ':postbox: *Original message from User Name* • <https://slack.com/archives/C123/p123|View original> :postbox:\n\nThis is the actual message content.',
      expected: 'This is the actual message content.',
    },
    {
      name: 'bot message format',
      input:
        ':postbox: *Original message from Bot Name* :robot_face: • <https://slack.com/archives/C123/p123|View original> :postbox:\n\nThis is a bot message content.',
      expected: 'This is a bot message content.',
    },
    {
      name: 'multiline header',
      input:
        ':postbox: *Original message from User Name*\n• <https://slack.com/archives/C123/p123|View original> :postbox:\n\nThis is a message\nwith multiple lines.',
      expected: 'This is a message\nwith multiple lines.',
    },
    {
      name: 'irregular spacing',
      input: ':postbox: *Message with irregular spacing*   :postbox:  \n\nActual content here.',
      expected: 'Actual content here.',
    },
    {
      name: 'content with colons',
      input:
        ':postbox: *Original message* :postbox:\n\nThis message contains: colons: in the: content.',
      expected: 'This message contains: colons: in the: content.',
    },
    {
      name: 'emoji in content',
      input:
        ':postbox: *Original message* :postbox:\n\nThis message has emoji :smile: :+1: in content.',
      expected: 'This message has emoji :smile: :+1: in content.',
    },
    {
      name: 'no header',
      input: 'This message does not have a header at all.',
      expected: 'This message does not have a header at all.',
    },
    {
      name: 'partial header',
      input: ':postbox: *Incomplete header\n\nThis message has a partial header.',
      expected: ':postbox: *Incomplete header\n\nThis message has a partial header.',
    },
    {
      name: 'header emoji in content',
      input:
        ':postbox: *Original message* :postbox:\n\nThis message mentions the :postbox: emoji in content.',
      expected: 'This message mentions the :postbox: emoji in content.',
    },
    {
      name: 'multiple newlines after header',
      input:
        ':postbox: *Original message* :postbox:\n\n\n\nThis message has extra newlines after header.',
      expected: 'This message has extra newlines after header.',
    },
  ];

  testCases.forEach((tc) => {
    test(`should handle ${tc.name} correctly`, () => {
      const result = stripMessageHeader(tc.input);
      expect(result).toBe(tc.expected);
    });
  });

  // Test the original use case mentioned by the user
  test('should properly strip the header including "postbox:" emoji', () => {
    const mirroredMessage = {
      text: ':postbox: *Original message from User Name* • <https://slack.com/archives/C123/p123|View original> :postbox:\n\nThis is the message content.',
    };

    const result = stripMessageHeader(mirroredMessage.text);

    // Verify emoji is completely removed
    expect(result).not.toContain(':postbox:');
    expect(result).not.toContain('postbox:');
    expect(result).toBe('This is the message content.');
  });
});
