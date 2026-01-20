/**
 * Test for user reference parsing functionality
 * Converts <@U040B2T929W|@Sam> format to <@U040B2T929W>
 */

describe('parseUserReferences', () => {
  const parseUserReferences = (text: string): string => {
    return text.replace(/<@([^|>]+)\|[^>]*>/g, '<@$1>');
  };

  test('should parse single user reference', () => {
    const input = 'Hey <@U040B2T929W|@Sam>, can you help?';
    const expected = 'Hey <@U040B2T929W>, can you help?';
    expect(parseUserReferences(input)).toBe(expected);
  });

  test('should parse multiple user references', () => {
    const input = '<@U040B2T929W|@Sam> and <@U123456789|@John> are working on this';
    const expected = '<@U040B2T929W> and <@U123456789> are working on this';
    expect(parseUserReferences(input)).toBe(expected);
  });

  test('should handle text with no user references', () => {
    const input = 'This is just regular text';
    const expected = 'This is just regular text';
    expect(parseUserReferences(input)).toBe(expected);
  });

  test('should handle empty string', () => {
    const input = '';
    const expected = '';
    expect(parseUserReferences(input)).toBe(expected);
  });

  test('should handle multiline text with user references', () => {
    const input =
      'Question from <@U040B2T929W|@Sam>:\nWhat is the status?\nCC: <@U123456789|@John>';
    const expected = 'Question from <@U040B2T929W>:\nWhat is the status?\nCC: <@U123456789>';
    expect(parseUserReferences(input)).toBe(expected);
  });

  test('should preserve other Slack formatting', () => {
    const input =
      'Hey <@U040B2T929W|@Sam>, check out <https://example.com|this link> and *bold text*';
    const expected =
      'Hey <@U040B2T929W>, check out <https://example.com|this link> and *bold text*';
    expect(parseUserReferences(input)).toBe(expected);
  });
});
