/**
 * Slack block builder utility functions
 */

import type { KnownBlock, RichTextElement, RichTextBlockElement } from '@slack/types';
import { convertMarkdownToSlack } from './textFormatting';

/**
 * Rich text text element with style
 */
export interface RichTextTextElement {
  type: 'text';
  text: string;
  style?: {
    bold?: boolean;
    italic?: boolean;
    strike?: boolean;
    code?: boolean;
  };
}

/**
 * Rich text link element with style
 */
export interface RichTextLinkElement {
  type: 'link';
  url: string;
  text?: string;
  style?: {
    bold?: boolean;
    italic?: boolean;
    strike?: boolean;
    code?: boolean;
  };
}

/**
 * Rich text section containing elements
 */
export interface RichTextSection {
  type: 'rich_text_section';
  elements: RichTextElement[];
}

/**
 * Rich text list (bullet or ordered)
 */
export interface RichTextList {
  type: 'rich_text_list';
  style: 'bullet' | 'ordered';
  elements: RichTextSection[];
  indent?: number;
  offset?: number;
  border?: 0 | 1;
}

/**
 * Build a Slack section block with markdown text
 * @param text - Markdown text to display
 * @returns Slack section block
 */
export function buildSectionBlock(text: string): KnownBlock {
  return {
    type: 'section',
    text: {
      type: 'mrkdwn',
      text: convertMarkdownToSlack(text),
    },
  };
}

/**
 * Build a Slack divider block
 * @returns Slack divider block
 */
export function buildDividerBlock(): KnownBlock {
  return {
    type: 'divider',
  };
}

/**
 * Create a rich text element for plain text
 * @param text - Text content
 * @param style - Optional styling (bold, italic, strike, code)
 * @returns Rich text text element
 */
export function richTextText(
  text: string,
  style?: { bold?: boolean; italic?: boolean; strike?: boolean; code?: boolean }
): RichTextTextElement {
  const element: RichTextTextElement = {
    type: 'text',
    text: convertMarkdownToSlack(text),
  };
  if (style && Object.keys(style).length > 0) {
    element.style = style;
  }
  return element;
}

/**
 * Create a rich text element for a link
 * @param url - Link URL
 * @param text - Optional link text (defaults to URL)
 * @param style - Optional styling (bold, italic, strike, code)
 * @returns Rich text link element
 */
export function richTextLink(
  url: string,
  text?: string,
  style?: { bold?: boolean; italic?: boolean; strike?: boolean; code?: boolean }
): RichTextLinkElement {
  const element: RichTextLinkElement = {
    type: 'link',
    url,
  };
  if (text) {
    element.text = text;
  }
  if (style && Object.keys(style).length > 0) {
    element.style = style;
  }
  return element;
}

/**
 * Create a rich text section with elements
 * @param elements - Array of rich text elements (text, links, etc.)
 * @returns Rich text section
 */
export function richTextSection(elements: RichTextElement[]): RichTextSection {
  return {
    type: 'rich_text_section',
    elements,
  };
}

/**
 * Create a rich text list (bullet or ordered)
 * @param items - Array of rich text sections (each representing a list item)
 * @param style - List style: 'bullet' or 'ordered' (default: 'bullet')
 * @param options - Optional list configuration (indent, offset, border)
 * @returns Rich text list
 */
export function richTextList(
  items: RichTextSection[],
  style: 'bullet' | 'ordered' = 'bullet',
  options?: { indent?: number; offset?: number; border?: 0 | 1 }
): RichTextList {
  const list: RichTextList = {
    type: 'rich_text_list',
    style,
    elements: items,
  };
  if (options?.indent !== undefined) {
    list.indent = options.indent;
  }
  if (options?.offset !== undefined) {
    list.offset = options.offset;
  }
  if (options?.border !== undefined) {
    list.border = options.border;
  }
  return list;
}

/**
 * Build a complete rich text block
 * @param elements - Array of rich text block elements (sections, lists, preformatted, quotes)
 * @returns Slack rich text block
 */
export function buildRichTextBlock(elements: RichTextBlockElement[]): KnownBlock {
  return {
    type: 'rich_text',
    elements,
  };
}
