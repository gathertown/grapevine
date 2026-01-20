import { type CSSProperties } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';

const markdownComponents: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
};

interface MarkdownRendererProps {
  children: string;
  style?: CSSProperties;
}

export const MarkdownRenderer = ({ children, style }: MarkdownRendererProps) => {
  return (
    <div style={style}>
      <ReactMarkdown components={markdownComponents}>{children}</ReactMarkdown>
    </div>
  );
};
