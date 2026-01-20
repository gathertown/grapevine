import { Flex } from '@gathertown/gather-design-system';
import { CopyButton } from './CopyButton';

interface CodeBlockProps {
  code: string;
}

const CodeBlock = ({ code }: CodeBlockProps) => (
  <Flex
    direction="column"
    gap={8}
    p={12}
    style={{
      backgroundColor: '#f5f5f5',
      borderRadius: '8px',
      border: '1px solid #e0e0e0',
      position: 'relative',
      width: '100%',
      maxWidth: '100%',
      minWidth: 0,
      overflow: 'auto',
      boxSizing: 'border-box',
    }}
  >
    <Flex position="absolute" top="8px" right="8px">
      <CopyButton textToCopy={code} />
    </Flex>
    <pre
      style={{
        margin: 0,
        fontFamily: 'monospace',
        fontSize: '12px',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        overflowWrap: 'break-word',
      }}
    >
      <code>{code}</code>
    </pre>
  </Flex>
);

export { CodeBlock };
