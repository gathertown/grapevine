import { useEffect, useState, useRef } from 'react';
import type { FC } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import styles from './GitHubRedirect.module.css';
import { connectorConfigQueryKey } from '../api/config';

const GitHubRedirect: FC = () => {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'processing' | 'error'>('processing');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const hasProcessed = useRef(false); // purely to prevent double processing from React StrictMode

  useEffect(() => {
    // Normally this should never run more than once, but React StrictMode in local dev causes it to
    if (hasProcessed.current) return;

    const handleRedirect = async () => {
      hasProcessed.current = true;
      try {
        const installationId = searchParams.get('installation_id');
        const setupAction = searchParams.get('setup_action');

        if (!installationId) {
          setStatus('error');
          setErrorMessage('No installation ID found in callback');
          return;
        }

        // Clean the URL by removing query parameters
        const cleanUrl = new URL(window.location.href);
        cleanUrl.search = '';
        window.history.replaceState({}, '', cleanUrl.toString());

        // Make API call to store installation_id for authenticated tenant
        await apiClient.post('/api/github/installation', {
          installation_id: installationId,
          setup_action: setupAction,
        });

        // Trigger config refresh to update GitHub status
        queryClient.invalidateQueries({ queryKey: connectorConfigQueryKey });

        // Check if this is running in a popup window
        if (window.opener && !window.opener.closed) {
          // Send message to parent window and close popup
          window.opener.postMessage(
            { type: 'GITHUB_AUTH_COMPLETE', installationId },
            window.location.origin
          );
          window.close();
          return;
        }

        // Check for stored return URL
        const returnUrl = localStorage.getItem('github_return_url');

        if (returnUrl) {
          // Clean up localStorage and navigate to stored URL
          localStorage.removeItem('github_return_url');

          // Add query parameter to indicate this is a GitHub callback return
          const urlWithParam = returnUrl.includes('?')
            ? `${returnUrl}&from=github`
            : `${returnUrl}?from=github`;

          navigate(urlWithParam);
        } else {
          navigate('/');
        }
      } catch (error) {
        console.error('Error storing GitHub installation:', error);
        setStatus('error');
        setErrorMessage('Failed to store GitHub installation. Please try again.');
      }
    };

    handleRedirect();
  }, [searchParams, navigate, queryClient]);

  if (status === 'processing') {
    return (
      <div className={styles.configFields}>
        <div className={styles.loadingContainer}>
          <div className={styles.spinner} />
          <h3>Processing GitHub App Installation</h3>
          <p>Configuring your GitHub integration...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.configFields}>
      <div className={styles.errorContainer}>
        <div className={styles.errorIcon}>❌</div>
        <h3>Installation Failed</h3>
        <p>{errorMessage}</p>
        <button className={styles.primaryButton} onClick={() => navigate('/')}>
          Return to Setup
        </button>
      </div>
    </div>
  );
};

export { GitHubRedirect };
