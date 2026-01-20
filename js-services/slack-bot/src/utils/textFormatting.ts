/**
 * Text formatting utilities for Slack messages
 */

/**
 * Comprehensive markdown to Slack mrkdwn converter
 *
 * Converts standard markdown formatting to Slack's mrkdwn format:
 * - Headers (# Header) → Bold text (*Header*)
 * - Bold (**text** or __text__) → *text*
 * - Italic (*text* or _text_) → _text_
 * - Strikethrough (~~text~~) → ~text~
 * - Links ([text](url)) → <url|text>
 * - Lists (- item or * item) → • item
 * - Code blocks and inline code preserved
 * - Blockquotes preserved
 *
 * @param text - Markdown formatted text
 * @returns Slack mrkdwn formatted text
 */
export function convertMarkdownToSlack(text: string): string {
  if (!text) return text;

  // Step 1: Protect code blocks and inline code from transformation
  const codeBlocks: string[] = [];
  const inlineCodes: string[] = [];

  // Protect code blocks (``` or ~~~)
  let result = text.replace(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/g, (match) => {
    const index = codeBlocks.push(match) - 1;
    return `__CODE_BLOCK_${index}__`;
  });

  // Protect inline code
  result = result.replace(/(`[^`]+?`)/g, (match) => {
    const index = inlineCodes.push(match) - 1;
    return `__INLINE_CODE_${index}__`;
  });

  // Step 2: Convert bold markdown using placeholders to avoid conflicts with italic
  // Store bold text temporarily to prevent italic conversion from affecting it
  // Use a unique marker that won't conflict with markdown or be matched by our regex patterns
  const boldTexts: string[] = [];

  // Convert **text** to placeholders
  result = result.replace(/\*\*(.+?)\*\*/g, (_, content) => {
    const index = boldTexts.push(content) - 1;
    return `⚡BOLD_${index}⚡`;
  });

  // Convert __text__ to placeholders (but not ___text___ which would be caught by the previous regex)
  result = result.replace(/(?<!_)__([^_]+?)__(?!_)/g, (_, content) => {
    const index = boldTexts.push(content) - 1;
    return `⚡BOLD_${index}⚡`;
  });

  // Step 3: Convert headers to bold (also using placeholders)
  result = result.replace(/^#{1,6}\s+(.+)$/gm, (_, content) => {
    const index = boldTexts.push(content) - 1;
    return `⚡BOLD_${index}⚡`;
  });

  // Step 4: Convert italic markdown to Slack format (now safe from bold conflicts)
  // Convert *text* to _text_ (single asterisk italic)
  result = result.replace(/\*(.+?)\*/g, '_$1_');
  // _text_ is already correct for Slack, keep it as is

  // Step 5: Convert strikethrough
  // Convert ~~text~~ to ~text~
  result = result.replace(/~~(.+?)~~/g, '~$1~');

  // Step 6: Convert links
  // Convert [text](url) to <url|text>
  // Also handle [[text]](url) format (double brackets, preserving inner brackets)
  result = result.replace(/\[(\[?[^\]]+\]?)\]\(([^)]+)\)/g, '<$2|$1>');

  // Step 7: Convert lists
  // Convert dash-based bullet lists to Slack bullet points
  result = result.replace(/^(\s*)-\s+(.+)$/gm, '$1• $2');

  // Convert asterisk lists (after italic conversion to avoid conflicts)
  result = result.replace(/^(\s*)_\s+(.+)_$/gm, '$1• $2');

  // Handle any remaining asterisk lists that weren't caught
  result = result.replace(/^(\s*)\*\s+(.+)$/gm, '$1• $2');

  // Numbered lists are kept as-is (Slack doesn't have special formatting)

  // Step 8: Blockquotes are already correct (> text), no conversion needed

  // Step 9: Restore bold text with Slack formatting
  result = result.replace(/⚡BOLD_(\d+)⚡/g, (_, index) => {
    return `*${boldTexts[parseInt(index)]}*`;
  });

  // Step 10: Restore protected code
  result = result.replace(/__CODE_BLOCK_(\d+)__/g, (_, index) => {
    return codeBlocks[parseInt(index)];
  });

  result = result.replace(/__INLINE_CODE_(\d+)__/g, (_, index) => {
    return inlineCodes[parseInt(index)];
  });

  return result;
}

/**
 * Convert Slack mrkdwn back to standard markdown
 *
 * Reverses the transformations from convertMarkdownToSlack:
 * - Bold (*text*) → **text**
 * - Italic (_text_) → *text*
 * - Strikethrough (~text~) → ~~text~~
 * - Links (<url|text>) → [text](url)
 * - Bullets (• item) → - item
 * - Code blocks and inline code preserved
 *
 * @param text - Slack mrkdwn formatted text
 * @returns Standard markdown formatted text
 */
export function convertSlackToMarkdown(text: string): string {
  if (!text) return text;

  // Step 1: Protect code blocks and inline code from transformation
  const codeBlocks: string[] = [];
  const inlineCodes: string[] = [];

  // Protect code blocks (``` or ~~~)
  let result = text.replace(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/g, (match) => {
    const index = codeBlocks.push(match) - 1;
    return `⚡CODE⚡BLOCK⚡${index}⚡`;
  });

  // Protect inline code
  result = result.replace(/(`[^`]+?`)/g, (match) => {
    const index = inlineCodes.push(match) - 1;
    return `⚡INLINE⚡CODE⚡${index}⚡`;
  });

  // Step 2: Convert links
  // Convert <url|text> to [text](url)
  // Also handle plain URLs <url> (convert to [url](url))
  result = result.replace(/<([^|>]+)\|([^>]+)>/g, '[$2]($1)');
  result = result.replace(/<([^>]+)>/g, '[$1]($1)');

  // Step 3: Convert strikethrough
  // Convert ~text~ to ~~text~~
  result = result.replace(/~([^~]+)~/g, '~~$1~~');

  // Step 4: Convert bold and italic using placeholders to avoid conflicts
  // First, protect Slack bold (*text*) as placeholders
  const boldTexts: string[] = [];
  result = result.replace(/\*([^*]+)\*/g, (_, content) => {
    const index = boldTexts.push(content) - 1;
    return `⚡BOLD${index}⚡`;
  });

  // Step 5: Convert italic to markdown
  // Convert _text_ to *text* (now safe from bold conflicts)
  result = result.replace(/_([^_]+)_/g, '*$1*');

  // Step 6: Restore bold as markdown **text**
  result = result.replace(/⚡BOLD(\d+)⚡/g, (_, index) => {
    return `**${boldTexts[parseInt(index)]}**`;
  });

  // Step 7: Convert bullet points
  // Convert • to -
  result = result.replace(/^(\s*)•\s+(.+)$/gm, '$1- $2');

  // Step 8: Restore protected code
  result = result.replace(/⚡CODE⚡BLOCK⚡(\d+)⚡/g, (_, index) => {
    return codeBlocks[parseInt(index)];
  });

  result = result.replace(/⚡INLINE⚡CODE⚡(\d+)⚡/g, (_, index) => {
    return inlineCodes[parseInt(index)];
  });

  return result;
}

/**
 * Format text for optimal Slack display
 * Converts dash-based bullet lists to proper Slack bullet points
 * @param text - The text to format
 * @returns Formatted text with proper Slack bullet points
 */
export function formatTextForSlack(text: string): string {
  if (!text) return text;

  // Convert dash-based bullet lists to Slack bullet points
  // Match lines that start with optional whitespace, dash, space, then content
  const bulletPointRegex = /^(\s*)-\s+(.+)$/gm;

  // Replace with Unicode bullet character
  return text.replace(bulletPointRegex, '$1• $2');
}
