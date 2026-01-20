/**
 * Tests for Slack text formatting utilities
 */

import {
  formatTextForSlack,
  convertMarkdownToSlack,
  convertSlackToMarkdown,
} from '../utils/textFormatting';

describe('convertMarkdownToSlack', () => {
  describe('headers', () => {
    it('should convert single # header to bold', () => {
      expect(convertMarkdownToSlack('# Header')).toBe('*Header*');
    });

    it('should convert multiple # levels to bold', () => {
      expect(convertMarkdownToSlack('## Header 2')).toBe('*Header 2*');
      expect(convertMarkdownToSlack('### Header 3')).toBe('*Header 3*');
      expect(convertMarkdownToSlack('###### Header 6')).toBe('*Header 6*');
    });

    it('should handle headers with other content', () => {
      const input = `# Main Title
Some content here
## Subtitle`;
      const expected = `*Main Title*
Some content here
*Subtitle*`;
      expect(convertMarkdownToSlack(input)).toBe(expected);
    });
  });

  describe('bold text', () => {
    it('should convert **text** to *text*', () => {
      expect(convertMarkdownToSlack('This is **bold** text')).toBe('This is *bold* text');
    });

    it('should convert __text__ to *text*', () => {
      expect(convertMarkdownToSlack('This is __bold__ text')).toBe('This is *bold* text');
    });

    it('should handle multiple bold sections', () => {
      expect(convertMarkdownToSlack('**First** and **second**')).toBe('*First* and *second*');
    });
  });

  describe('italic text', () => {
    it('should convert *text* to _text_', () => {
      expect(convertMarkdownToSlack('This is *italic* text')).toBe('This is _italic_ text');
    });

    it('should preserve _text_ as _text_', () => {
      expect(convertMarkdownToSlack('This is _italic_ text')).toBe('This is _italic_ text');
    });

    it('should handle bold and italic together', () => {
      expect(convertMarkdownToSlack('**bold** and *italic*')).toBe('*bold* and _italic_');
    });
  });

  describe('strikethrough', () => {
    it('should convert ~~text~~ to ~text~', () => {
      expect(convertMarkdownToSlack('This is ~~deleted~~ text')).toBe('This is ~deleted~ text');
    });
  });

  describe('links', () => {
    it('should convert [text](url) to <url|text>', () => {
      expect(convertMarkdownToSlack('[Google](https://google.com)')).toBe(
        '<https://google.com|Google>'
      );
    });

    it('should handle multiple links', () => {
      const input = 'Check [Google](https://google.com) and [GitHub](https://github.com)';
      const expected = 'Check <https://google.com|Google> and <https://github.com|GitHub>';
      expect(convertMarkdownToSlack(input)).toBe(expected);
    });

    it('should handle Linear-style links', () => {
      const input = '[ABC-123](https://linear.app/workspace/issue/ABC-123)';
      const expected = '<https://linear.app/workspace/issue/ABC-123|ABC-123>';
      expect(convertMarkdownToSlack(input)).toBe(expected);
    });

    it('should handle double-bracketed links', () => {
      const input = '[[1]](https://slack.com/archives/C123)';
      const expected = '<https://slack.com/archives/C123|[1]>';
      expect(convertMarkdownToSlack(input)).toBe(expected);
    });

    it('should handle multiple double-bracketed links', () => {
      const input = 'See [[1]](https://example.com/1) and [[2]](https://example.com/2)';
      const expected = 'See <https://example.com/1|[1]> and <https://example.com/2|[2]>';
      expect(convertMarkdownToSlack(input)).toBe(expected);
    });
  });

  describe('lists', () => {
    it('should convert dash lists to bullet points', () => {
      const input = `- First item
- Second item
- Third item`;
      const expected = `• First item
• Second item
• Third item`;
      expect(convertMarkdownToSlack(input)).toBe(expected);
    });

    it('should convert asterisk lists to bullet points', () => {
      const input = `* First item
* Second item`;
      const expected = `• First item
• Second item`;
      expect(convertMarkdownToSlack(input)).toBe(expected);
    });

    it('should preserve indentation in nested lists', () => {
      const input = `- Level 1
  - Level 2
    - Level 3`;
      const expected = `• Level 1
  • Level 2
    • Level 3`;
      expect(convertMarkdownToSlack(input)).toBe(expected);
    });

    it('should keep numbered lists as-is', () => {
      const input = `1. First
2. Second
3. Third`;
      expect(convertMarkdownToSlack(input)).toBe(input);
    });
  });

  describe('code blocks', () => {
    it('should preserve code blocks with backticks', () => {
      const input = '```javascript\nconst x = 1;\n```';
      expect(convertMarkdownToSlack(input)).toBe(input);
    });

    it('should preserve inline code', () => {
      expect(convertMarkdownToSlack('Use `const` for constants')).toBe('Use `const` for constants');
    });

    it('should not convert formatting inside code blocks', () => {
      const input = '```\n**bold** and *italic*\n```';
      expect(convertMarkdownToSlack(input)).toBe(input);
    });

    it('should not convert formatting inside inline code', () => {
      expect(convertMarkdownToSlack('Use `**bold**` syntax')).toBe('Use `**bold**` syntax');
    });
  });

  describe('blockquotes', () => {
    it('should preserve blockquotes', () => {
      const input = '> This is a quote';
      expect(convertMarkdownToSlack(input)).toBe(input);
    });
  });

  describe('complex combinations', () => {
    it('should handle mixed markdown formatting', () => {
      const input = `# Title

This is **bold** and *italic* text with a [link](https://example.com).

- First item
- Second item with **bold**

\`\`\`
code block
\`\`\``;

      const expected = `*Title*

This is *bold* and _italic_ text with a <https://example.com|link>.

• First item
• Second item with *bold*

\`\`\`
code block
\`\`\``;

      expect(convertMarkdownToSlack(input)).toBe(expected);
    });

    it('should handle real-world Linear ticket example', () => {
      const input = `## Summary
This ticket is about **implementing** a new feature.

Related: [ABC-123](https://linear.app/issue/ABC-123)

Steps:
- Review requirements
- Implement solution
- Test thoroughly`;

      const expected = `*Summary*
This ticket is about *implementing* a new feature.

Related: <https://linear.app/issue/ABC-123|ABC-123>

Steps:
• Review requirements
• Implement solution
• Test thoroughly`;

      expect(convertMarkdownToSlack(input)).toBe(expected);
    });
  });

  describe('edge cases', () => {
    it('should handle empty string', () => {
      expect(convertMarkdownToSlack('')).toBe('');
    });

    it('should handle plain text without markdown', () => {
      const input = 'Just plain text';
      expect(convertMarkdownToSlack(input)).toBe(input);
    });

    it('should handle idempotent conversion for most formats', () => {
      // Note: *text* in markdown (italic) becomes _text_ in Slack
      // So *text* (Slack bold) will be converted to _text_ (Slack italic)
      // This is a known limitation - the function assumes input is markdown, not Slack format
      const input = '_italic_ and ~strikethrough~';
      expect(convertMarkdownToSlack(input)).toBe(input);
    });
  });
});

describe('formatTextForSlack', () => {
  it('should convert simple dash lists to bullet points', () => {
    const input = `Here are the steps:
- First step
- Second step
- Third step`;

    const expected = `Here are the steps:
• First step
• Second step
• Third step`;

    expect(formatTextForSlack(input)).toBe(expected);
  });

  it('should preserve indentation for nested lists', () => {
    const input = `Main list:
- First item
  - Nested item
  - Another nested item
- Second item`;

    const expected = `Main list:
• First item
  • Nested item
  • Another nested item
• Second item`;

    expect(formatTextForSlack(input)).toBe(expected);
  });

  it('should handle mixed content with lists', () => {
    const input = `Here's some info:

This is a paragraph.

- First point
- Second point

More text here.`;

    const expected = `Here's some info:

This is a paragraph.

• First point
• Second point

More text here.`;

    expect(formatTextForSlack(input)).toBe(expected);
  });

  it('should handle empty input', () => {
    expect(formatTextForSlack('')).toBe('');
  });

  it('should not affect text without dash lists', () => {
    const input = `This is just regular text.
No lists here.
Just plain content.`;

    expect(formatTextForSlack(input)).toBe(input);
  });

  it('should handle multiple levels of indentation', () => {
    const input = `Complex list:
- Level 1
  - Level 2
    - Level 3
      - Level 4
- Back to level 1`;

    const expected = `Complex list:
• Level 1
  • Level 2
    • Level 3
      • Level 4
• Back to level 1`;

    expect(formatTextForSlack(input)).toBe(expected);
  });
});

describe('convertSlackToMarkdown', () => {
  describe('bold text', () => {
    it('should convert *text* to **text**', () => {
      expect(convertSlackToMarkdown('This is *bold* text')).toBe('This is **bold** text');
    });

    it('should handle multiple bold sections', () => {
      expect(convertSlackToMarkdown('*First* and *second*')).toBe('**First** and **second**');
    });
  });

  describe('italic text', () => {
    it('should convert _text_ to *text*', () => {
      expect(convertSlackToMarkdown('This is _italic_ text')).toBe('This is *italic* text');
    });

    it('should handle multiple italic sections', () => {
      expect(convertSlackToMarkdown('_First_ and _second_')).toBe('*First* and *second*');
    });
  });

  describe('bold and italic together', () => {
    it('should handle bold and italic correctly', () => {
      expect(convertSlackToMarkdown('*bold* and _italic_')).toBe('**bold** and *italic*');
    });

    it('should handle multiple mixed formatting', () => {
      expect(convertSlackToMarkdown('*bold1* _italic1_ *bold2* _italic2_')).toBe(
        '**bold1** *italic1* **bold2** *italic2*'
      );
    });
  });

  describe('strikethrough', () => {
    it('should convert ~text~ to ~~text~~', () => {
      expect(convertSlackToMarkdown('This is ~deleted~ text')).toBe('This is ~~deleted~~ text');
    });

    it('should handle multiple strikethrough sections', () => {
      expect(convertSlackToMarkdown('~First~ and ~second~')).toBe('~~First~~ and ~~second~~');
    });
  });

  describe('links', () => {
    it('should convert <url|text> to [text](url)', () => {
      expect(convertSlackToMarkdown('<https://google.com|Google>')).toBe(
        '[Google](https://google.com)'
      );
    });

    it('should handle multiple links', () => {
      const input = 'Check <https://google.com|Google> and <https://github.com|GitHub>';
      const expected = 'Check [Google](https://google.com) and [GitHub](https://github.com)';
      expect(convertSlackToMarkdown(input)).toBe(expected);
    });

    it('should handle plain URLs', () => {
      expect(convertSlackToMarkdown('<https://google.com>')).toBe(
        '[https://google.com](https://google.com)'
      );
    });

    it('should handle Linear-style links', () => {
      const input = '<https://linear.app/workspace/issue/ABC-123|ABC-123>';
      const expected = '[ABC-123](https://linear.app/workspace/issue/ABC-123)';
      expect(convertSlackToMarkdown(input)).toBe(expected);
    });

    it('should handle bracketed link text', () => {
      const input = '<https://slack.com/archives/C123|[1]>';
      const expected = '[[1]](https://slack.com/archives/C123)';
      expect(convertSlackToMarkdown(input)).toBe(expected);
    });
  });

  describe('lists', () => {
    it('should convert bullet points to dash lists', () => {
      const input = `• First item
• Second item
• Third item`;
      const expected = `- First item
- Second item
- Third item`;
      expect(convertSlackToMarkdown(input)).toBe(expected);
    });

    it('should preserve indentation in nested lists', () => {
      const input = `• Level 1
  • Level 2
    • Level 3`;
      const expected = `- Level 1
  - Level 2
    - Level 3`;
      expect(convertSlackToMarkdown(input)).toBe(expected);
    });
  });

  describe('code blocks', () => {
    it('should preserve code blocks with backticks', () => {
      const input = '```javascript\nconst x = 1;\n```';
      expect(convertSlackToMarkdown(input)).toBe(input);
    });

    it('should preserve inline code', () => {
      expect(convertSlackToMarkdown('Use `const` for constants')).toBe('Use `const` for constants');
    });

    it('should not convert formatting inside code blocks', () => {
      const input = '```\n*bold* and _italic_\n```';
      expect(convertSlackToMarkdown(input)).toBe(input);
    });

    it('should not convert formatting inside inline code', () => {
      expect(convertSlackToMarkdown('Use `*bold*` syntax')).toBe('Use `*bold*` syntax');
    });
  });

  describe('complex combinations', () => {
    it('should handle mixed Slack formatting', () => {
      const input = `*Title*

This is *bold* and _italic_ text with a <https://example.com|link>.

• First item
• Second item with *bold*

\`\`\`
code block
\`\`\``;

      const expected = `**Title**

This is **bold** and *italic* text with a [link](https://example.com).

- First item
- Second item with **bold**

\`\`\`
code block
\`\`\``;

      expect(convertSlackToMarkdown(input)).toBe(expected);
    });

    it('should handle real-world Linear context example', () => {
      const input = `*Summary*
This ticket is about *implementing* a new feature.

Related: <https://linear.app/issue/ABC-123|ABC-123>

Steps:
• Review requirements
• Implement solution
• Test thoroughly`;

      const expected = `**Summary**
This ticket is about **implementing** a new feature.

Related: [ABC-123](https://linear.app/issue/ABC-123)

Steps:
- Review requirements
- Implement solution
- Test thoroughly`;

      expect(convertSlackToMarkdown(input)).toBe(expected);
    });
  });

  describe('edge cases', () => {
    it('should handle empty string', () => {
      expect(convertSlackToMarkdown('')).toBe('');
    });

    it('should handle plain text without Slack formatting', () => {
      const input = 'Just plain text';
      expect(convertSlackToMarkdown(input)).toBe(input);
    });
  });

  describe('round-trip conversion', () => {
    it('should round-trip markdown → Slack → markdown for simple cases', () => {
      const original = 'This is **bold** and *italic* text';
      const slack = convertMarkdownToSlack(original);
      const backToMarkdown = convertSlackToMarkdown(slack);
      expect(backToMarkdown).toBe(original);
    });

    it('should round-trip for links', () => {
      const original = 'Check [Google](https://google.com) for info';
      const slack = convertMarkdownToSlack(original);
      const backToMarkdown = convertSlackToMarkdown(slack);
      expect(backToMarkdown).toBe(original);
    });

    it('should round-trip for lists', () => {
      const original = `- First item
- Second item
- Third item`;
      const slack = convertMarkdownToSlack(original);
      const backToMarkdown = convertSlackToMarkdown(slack);
      expect(backToMarkdown).toBe(original);
    });

    it('should round-trip for complex formatting', () => {
      const original = `This is **bold** and *italic* with [link](https://example.com).

- First item
- Second item

Some ~~deleted~~ text.`;
      const slack = convertMarkdownToSlack(original);
      const backToMarkdown = convertSlackToMarkdown(slack);
      expect(backToMarkdown).toBe(original);
    });
  });
});
