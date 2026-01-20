/**
 * Shared styles for Custom Data components
 */

// Status badge color schemes
export const STATUS_STYLES = {
  enabled: {
    backgroundColor: '#e8f5e9',
    borderColor: '#4caf50',
    textColor: '#2e7d32',
  },
  disabled: {
    backgroundColor: '#f5f5f5',
    borderColor: '#ccc',
    textColor: '#666',
  },
} as const;

// Code block styles
export const CODE_BLOCK_STYLES = {
  inline: {
    backgroundColor: '#f8f9fa',
    border: '1px solid #dee2e6',
    borderRadius: '4px',
    padding: '4px 8px',
    fontSize: '11px',
    fontFamily: "'SF Mono', Monaco, 'Courier New', monospace",
    color: '#6366f1',
  },
  block: {
    display: 'inline-block' as const,
    backgroundColor: '#f0f4ff',
    border: '1px solid #c7d2fe',
    borderRadius: '6px',
    padding: '8px 12px',
    fontSize: '13px',
    fontFamily: "'SF Mono', Monaco, 'Courier New', monospace",
    color: '#4338ca',
  },
  dark: {
    backgroundColor: '#1e1e1e',
    color: '#d4d4d4',
    padding: '16px',
    borderRadius: '8px',
    overflow: 'auto' as const,
    fontSize: '13px',
    fontFamily: "'SF Mono', Monaco, 'Courier New', monospace",
    lineHeight: 1.5,
  },
} as const;
