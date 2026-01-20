import {
  SSMClient as AWSSSMClient,
  GetParameterCommand,
  PutParameterCommand,
  DeleteParameterCommand,
  PutParameterCommandInput,
  ParameterNotFound,
  ParameterType,
  ParameterTier,
} from '@aws-sdk/client-ssm';
import { logger, LogContext } from '../logger';

interface CacheEntry {
  value: string;
  decrypt: boolean;
}

export class SSMClient {
  private client: AWSSSMClient;
  private parameterCache: Map<string, CacheEntry>;

  constructor(region?: string) {
    const awsRegion = region || process.env.AWS_REGION || 'us-east-1';
    const endpointUrl = process.env.AWS_ENDPOINT_URL;

    const explicitCredentials =
      process.env.AWS_ACCESS_KEY_ID !== undefined &&
      process.env.AWS_SECRET_ACCESS_KEY !== undefined;
    const credentials = explicitCredentials
      ? {
          accessKeyId: process.env.AWS_ACCESS_KEY_ID as string,
          secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY as string,
          ...(process.env.AWS_SESSION_TOKEN ? { sessionToken: process.env.AWS_SESSION_TOKEN } : {}),
        }
      : undefined;

    this.client = new AWSSSMClient({
      region: awsRegion,
      ...(endpointUrl ? { endpoint: endpointUrl } : {}),
      ...(credentials ? { credentials } : {}),
    });
    this.parameterCache = new Map();

    if (endpointUrl) {
      logger.info(`SSM client configured for LocalStack at ${endpointUrl}`);
    }
  }

  private getKmsKeyId(): string {
    const keyId = process.env.KMS_KEY_ID;
    if (!keyId) {
      throw new Error('No KMS key ID found. Set KMS_KEY_ID environment variable.');
    }
    return keyId;
  }

  async getParameter(
    parameterName: string,
    decrypt: boolean = true,
    useCache: boolean = true
  ): Promise<string | null> {
    return LogContext.run(
      { operation: 'get-parameter', parameterName, decrypt, useCache },
      async () => {
        const cacheKey = `${parameterName}:${decrypt}`;

        if (useCache && this.parameterCache.has(cacheKey)) {
          logger.debug(`Retrieved parameter ${parameterName} from cache`);
          const cached = this.parameterCache.get(cacheKey);
          return cached ? cached.value : null;
        }

        try {
          const command = new GetParameterCommand({
            Name: parameterName,
            WithDecryption: decrypt,
          });

          const response = await this.client.send(command);
          const value = response.Parameter?.Value;

          if (!value) {
            return null;
          }

          if (useCache) {
            this.parameterCache.set(cacheKey, { value, decrypt });
            logger.debug(`Cached parameter ${parameterName}`);
          }

          logger.debug(`Retrieved parameter ${parameterName} from SSM`);
          return value;
        } catch (error) {
          if (error instanceof ParameterNotFound) {
            logger.warn(`Parameter ${parameterName} not found in SSM`);
            return null;
          }
          const wrappedError = error instanceof Error ? error : new Error(String(error));
          logger.error(`Failed to get parameter ${parameterName}`, wrappedError);
          throw error;
        }
      }
    );
  }

  async putParameter(
    parameterName: string,
    value: string,
    description?: string,
    overwrite: boolean = true
  ): Promise<boolean> {
    return LogContext.run({ operation: 'put-parameter', parameterName, overwrite }, async () => {
      try {
        const putParams: PutParameterCommandInput = {
          Name: parameterName,
          Value: value,
          Type: ParameterType.SECURE_STRING,
          Tier: ParameterTier.ADVANCED,
          Overwrite: overwrite,
          KeyId: this.getKmsKeyId(),
        };

        if (description) {
          putParams.Description = description;
        }

        const command = new PutParameterCommand(putParams);
        await this.client.send(command);

        // Invalidate cache for this parameter
        const keysToRemove = Array.from(this.parameterCache.keys()).filter((key) =>
          key.startsWith(`${parameterName}:`)
        );
        keysToRemove.forEach((key) => this.parameterCache.delete(key));

        logger.info(`Successfully stored parameter ${parameterName}`);
        return true;
      } catch (error) {
        const wrappedError = error instanceof Error ? error : new Error(String(error));
        logger.error(`Failed to put parameter ${parameterName}`, wrappedError);
        return false;
      }
    });
  }

  async deleteParameter(parameterName: string): Promise<boolean> {
    return LogContext.run({ operation: 'delete-parameter', parameterName }, async () => {
      try {
        const command = new DeleteParameterCommand({
          Name: parameterName,
        });

        await this.client.send(command);

        // Invalidate cache for this parameter
        const keysToRemove = Array.from(this.parameterCache.keys()).filter((key) =>
          key.startsWith(`${parameterName}:`)
        );
        keysToRemove.forEach((key) => this.parameterCache.delete(key));

        logger.info(`Successfully deleted parameter ${parameterName}`);
        return true;
      } catch (error) {
        if (error instanceof ParameterNotFound) {
          logger.warn(`Parameter ${parameterName} not found in SSM`);
          return false;
        }
        const wrappedError = error instanceof Error ? error : new Error(String(error));
        logger.error(`Failed to delete parameter ${parameterName}`, wrappedError);
        return false;
      }
    });
  }

  async getSigningSecret(tenantId: string, sourceType: string): Promise<string | null> {
    const parameterName = `/${tenantId}/signing-secret/${sourceType}`;
    return this.getParameter(parameterName, true);
  }

  async storeSigningSecret(tenantId: string, sourceType: string, secret: string): Promise<boolean> {
    const parameterName = `/${tenantId}/signing-secret/${sourceType}`;
    const description = `Webhook signing secret for ${tenantId} ${sourceType}`;
    return this.putParameter(parameterName, secret, description, true);
  }

  async getApiKey(tenantId: string, keyName: string): Promise<string | null> {
    const parameterName = `/${tenantId}/api-key/${keyName}`;
    return this.getParameter(parameterName, true);
  }

  async storeApiKey(tenantId: string, keyName: string, keyValue: string): Promise<boolean> {
    const parameterName = `/${tenantId}/api-key/${keyName}`;
    const description = `API key ${keyName} for ${tenantId}`;
    return this.putParameter(parameterName, keyValue, description, true);
  }

  async getDbCredential(tenantId: string, credentialName: string): Promise<string | null> {
    const parameterName = `/${tenantId}/db-credential/${credentialName}`;
    return this.getParameter(parameterName, true);
  }

  async storeDbCredential(
    tenantId: string,
    credentialName: string,
    credentialValue: string
  ): Promise<boolean> {
    const parameterName = `/${tenantId}/db-credential/${credentialName}`;
    const description = `Database credential ${credentialName} for ${tenantId}`;
    return this.putParameter(parameterName, credentialValue, description, true);
  }

  clearCache(): void {
    this.parameterCache.clear();
    logger.debug('Cleared SSM parameter cache');
  }

  getCacheSize(): number {
    return this.parameterCache.size;
  }

  // Configuration getter helper methods
  async getGithubToken(tenantId: string): Promise<string | null> {
    return this.getApiKey(tenantId, 'GITHUB_TOKEN');
  }

  async getGithubWebhookSecret(tenantId: string): Promise<string | null> {
    return this.getSigningSecret(tenantId, 'github');
  }

  async getSlackToken(tenantId: string): Promise<string | null> {
    return this.getApiKey(tenantId, 'SLACK_BOT_TOKEN');
  }

  async getSlackSigningSecret(tenantId: string): Promise<string | null> {
    return this.getSigningSecret(tenantId, 'slack');
  }

  async getNotionSigningSecret(tenantId: string): Promise<string | null> {
    return this.getSigningSecret(tenantId, 'notion');
  }

  async getNotionToken(tenantId: string): Promise<string | null> {
    return this.getApiKey(tenantId, 'NOTION_TOKEN');
  }

  async getLinearApiKey(tenantId: string): Promise<string | null> {
    return this.getApiKey(tenantId, 'LINEAR_API_KEY');
  }

  async getLinearAccessToken(tenantId: string): Promise<string | null> {
    return this.getApiKey(tenantId, 'LINEAR_ACCESS_TOKEN');
  }
}
