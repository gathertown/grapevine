import { storage, invokeRemote, webTrigger } from '@forge/api';
import Resolver from '@forge/resolver';

interface GetSecretResponse {
  success: boolean;
  secret?: string;
  baseUrl?: string;
  error?: string;
}

interface SaveSigningSecretRequest {
  secret: string;
}

interface SaveSecretResponse {
  success: boolean;
  message?: string;
  error?: string;
}

const resolver = new Resolver();

resolver.define('getSecret', async (): Promise<GetSecretResponse> => {
  try {
    const secret = await storage.get('CONFLUENCE_SIGNING_SECRET');
    const baseUrl = process.env.GRAPEVINE_URL || 'https://app.getgrapevine.ai';

    return { success: true, secret: secret, baseUrl: baseUrl };
  } catch (error) {
    console.error('Error getting secret:', error);
    return { success: false, error: 'Failed to load secret' };
  }
});

resolver.define('saveSecret', async (req): Promise<SaveSecretResponse> => {
  try {
    const { secret } = req.payload as SaveSigningSecretRequest;
    const { cloudId } = req.context;

    if (!secret || secret.trim() === '') {
      return { success: false, error: 'Secret cannot be empty' };
    }

    if (!cloudId) {
      return { success: false, error: 'Missing cloud ID context' };
    }

    await storage.set('CONFLUENCE_SIGNING_SECRET', secret.trim());

    try {
      const webtriggerUrl = await webTrigger.getUrl('backfill-trigger');

      const eventPayload = {
        eventType: 'avi:grapevine:configured:signing-secret',
        signingSecret: secret.trim(),
        webtriggerUrl: webtriggerUrl,
        cloudId: cloudId,
        timestamp: new Date().toISOString(),
      };

      const backendResponse = await invokeRemote('grapevine-connector', {
        path: `/webhooks/confluence`,
        method: 'POST',
        body: JSON.stringify(eventPayload),
        headers: {
          'Content-Type': 'application/json',
          'x-confluence-signing-secret': secret.trim(),
        },
      });

      if (!backendResponse.ok) {
        console.error('Failed to notify backend:', backendResponse.status, await backendResponse.text());
      } else {
        console.log('Successfully notified backend of signing secret configuration');
      }
    } catch (webhookError) {
      console.error('Error triggering webhook:', webhookError);
    }

    return { success: true, message: 'Signing secret saved successfully' };
  } catch (error) {
    console.error('Error saving secret:', error);
    return { success: false, error: 'Failed to save secret' };
  }
});

export const handler = resolver.getDefinitions();