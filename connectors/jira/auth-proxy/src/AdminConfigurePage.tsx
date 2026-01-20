import React, { useState, useEffect } from 'react';

import ForgeReconciler, {
  Form,
  Button,
  Textfield,
  Label,
  Text,
  SectionMessage,
  Spinner,
  Link
} from '@forge/react';
import { invoke } from '@forge/bridge';

const AdminConfigurePage = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);
  const [currentSecret, setCurrentSecret] = useState('');
  const [savedSecret, setSavedSecret] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://app.getgrapevine.ai');

  useEffect(() => {
    loadExistingSecret();
  }, []);

  const onSubmit = async () => {
    setIsLoading(true);
    setMessage(null);

    try {
      const response = await invoke('saveSecret', { secret: currentSecret }) as any;

      if (response.success) {
        setSavedSecret(currentSecret);
      } else {
        setMessage({ type: 'error', text: response.error || 'Failed to save configuration' });
      }
    } catch (error) {
      console.error('Error saving secret:', error);
      setMessage({ type: 'error', text: 'An unexpected error occurred' });
    } finally {
      setIsLoading(false);
    }
  };

  const loadExistingSecret = async () => {
    setIsLoading(true);
    setMessage(null);

    try {
      const response = await invoke('getSecret') as any;

      if (response.success && response.secret) {
        setCurrentSecret(response.secret);
        setSavedSecret(response.secret);
      }
      if (response.baseUrl) {
        setBaseUrl(response.baseUrl);
      }
    } catch (error) {
      console.error('Error loading secret:', error);
      setMessage({ type: 'error', text: 'Failed to load existing signing secret' });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <React.Fragment>
      <Text>
        Finish configuring Grapevine
      </Text>

      {message && (
        <SectionMessage appearance={message.type === 'success' ? 'information' : 'error'}>
          <Text>{message.text}</Text>
        </SectionMessage>
      )}

      {isLoading ? (
        <Spinner />
      ) : (
        <Form onSubmit={onSubmit}>
          <Label labelFor="secret-input">Signing Secret</Label>
          <Textfield
            id="secret-input"
            placeholder="0000000000-000000000000000000000000000000000000000000000000"
            value={currentSecret}
            onChange={(e) => setCurrentSecret(e.target.value)}
          />
          <Button
            type="submit"
            appearance="primary"
            isDisabled={!currentSecret?.trim()}
          >
            Save
          </Button>
        </Form>
      )}

      {savedSecret && !isLoading && (
        <Text>
          Configuration complete! You can now <Link href={`${baseUrl}/integrations/jira`} openNewTab>return to Grapevine</Link>.
        </Text>
      )}
    </React.Fragment>
  );
};

ForgeReconciler.render(
  <React.StrictMode>
    <AdminConfigurePage />
  </React.StrictMode>
);
