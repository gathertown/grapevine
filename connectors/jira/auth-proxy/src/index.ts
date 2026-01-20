import { invokeRemote, storage } from '@forge/api';

export const forwardEventToGrapevine = async (event: Record<string, unknown>) => {
  try {
    const signingSecret = await storage.get('JIRA_SIGNING_SECRET') as string | undefined;

    if (!signingSecret || signingSecret.trim() === '') {
      console.log('Skipping event forwarding: No signing secret configured');
      return;
    }

    const backendResponse = await invokeRemote('grapevine-connector', {
      path: `/webhooks/jira`,
      method: 'POST',
      body: JSON.stringify(event),
      headers: {
        'Content-Type': 'application/json',
        'x-jira-signing-secret': signingSecret.trim(),
      },
    });

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();
      throw new Error(`Remote backend error: ${backendResponse.status} ${errorText}`);
    }

    const result = await backendResponse.json();
    console.log('Event processed successfully:', result);
  } catch (error) {
    console.error('Event processing error:', error);
  }
};
