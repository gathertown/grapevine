/* eslint-disable @gathertown/require-memo */

import React from 'react';

import * as styles from './TokenDisplay.css';

interface TokenDisplayProps {
  label: string;
  tokenGroup: Record<string, string | number>;
  renderExample: (value: string | number) => React.ReactNode;
}

export const TokenDisplay: React.FC<TokenDisplayProps> = ({ label, tokenGroup, renderExample }) => (
  <div>
    <div className={styles.tokenGrid}>
      <div className={styles.tokenHeader}>
        <div>Token</div>
        <div>Example</div>
        <div>Value</div>
      </div>

      {Object.entries(tokenGroup).map(([key, value]) => (
        <div key={key} className={styles.tokenRow}>
          <div>
            <code className={styles.tokenCode}>
              {isNaN(Number.parseInt(key)) ? `${label}.${key}` : `${label}[${key}]`}
            </code>
          </div>
          <div>{renderExample(value)}</div>
          <div className={styles.tokenValue}>{value}</div>
        </div>
      ))}
    </div>
  </div>
);
