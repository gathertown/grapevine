import { FC, useEffect, useState } from 'react';
import { InitializingProps } from '../types';
import { FullscreenLayout } from './shared/FullscreenLayout';
import styles from './Initializing.module.css';

const PROVISIONING_MESSAGES = [
  'Setting up your workspace...',
  'Configuring databases...',
  'Initializing search indices...',
  'Preparing connectors...',
  'Configuring services...',
  'Finalizing setup...',
  'Almost ready...',
];

const Initializing: FC<InitializingProps> = ({ error, message, onSignOut, onRetry }) => {
  const [currentMessageIndex, setCurrentMessageIndex] = useState(0);

  useEffect(() => {
    if (!message) {
      const interval = setInterval(() => {
        setCurrentMessageIndex((prevIndex) => (prevIndex + 1) % PROVISIONING_MESSAGES.length);
      }, 1000);

      return () => clearInterval(interval);
    }
  }, [message]);

  if (error) {
    return (
      <FullscreenLayout showSignOut={!!onSignOut}>
        <div className={styles.initializingContent}>
          <div className={styles.errorIcon}>⚠️</div>
          <h2>Initialization Failed</h2>
          <p className={styles.errorMessage}>{error}</p>
          <div className={styles.buttonGroup}>
            {onRetry && (
              <button onClick={onRetry} className={`${styles.button} ${styles.retryButton}`}>
                Retry
              </button>
            )}
            {/* Sign Out button now handled by FullscreenLayout */}
          </div>
        </div>
      </FullscreenLayout>
    );
  }

  const displayMessage = message || PROVISIONING_MESSAGES[currentMessageIndex];

  return (
    <FullscreenLayout showSignOut={!!onSignOut}>
      <div className={styles.initializingContent}>
        <div className={styles.initializingSpinner}></div>
        <h2>Initializing...</h2>
        <p>{displayMessage}</p>
        {/* Sign Out button now handled by FullscreenLayout */}
      </div>
    </FullscreenLayout>
  );
};

export { Initializing };
