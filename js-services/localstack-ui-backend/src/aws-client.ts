import {
  SSMClient,
  GetParameterCommand,
  PutParameterCommand,
  DeleteParameterCommand,
  DescribeParametersCommand,
  GetParametersByPathCommand,
  ParameterType,
  ParameterTier,
  Parameter,
  ParameterMetadata,
} from '@aws-sdk/client-ssm';

import {
  SQSClient,
  ListQueuesCommand,
  GetQueueAttributesCommand,
  PurgeQueueCommand,
  ReceiveMessageCommand,
  DeleteMessageCommand,
  SendMessageCommand,
  Message,
  MessageAttributeValue,
} from '@aws-sdk/client-sqs';

// Define interface for queue attributes that may contain optional fields
interface QueueAttributes {
  [key: string]: string | undefined;
  MaxReceiveCount?: string;
  RedrivePolicy?: string;
}

export class LocalStackSSMClient {
  private client: SSMClient;

  constructor() {
    this.client = new SSMClient({
      region: 'us-east-1',
      endpoint: 'http://localhost:4566',
      credentials: {
        accessKeyId: 'test',
        secretAccessKey: 'test',
      },
    });
  }

  async listParameters(prefix?: string): Promise<ParameterMetadata[]> {
    try {
      const allParameters: ParameterMetadata[] = [];
      let nextToken: string | undefined;

      do {
        const command = new DescribeParametersCommand({
          NextToken: nextToken,
          MaxResults: 50,
          ...(prefix && { ParameterFilters: [{ Key: 'Name', Values: [prefix] }] }),
        });

        const response = await this.client.send(command);

        if (response.Parameters) {
          allParameters.push(...response.Parameters);
        }

        nextToken = response.NextToken;
      } while (nextToken);

      return allParameters;
    } catch (error) {
      console.error('Error listing parameters:', error);
      return [];
    }
  }

  async getParametersByPath(path: string): Promise<Parameter[]> {
    try {
      const allParameters: Parameter[] = [];
      let nextToken: string | undefined;

      do {
        const command = new GetParametersByPathCommand({
          Path: path,
          Recursive: true,
          WithDecryption: true,
          NextToken: nextToken,
          MaxResults: 50,
        });

        const response = await this.client.send(command);

        if (response.Parameters) {
          allParameters.push(...response.Parameters);
        }

        nextToken = response.NextToken;
      } while (nextToken);

      return allParameters;
    } catch (error) {
      console.error('Error getting parameters by path:', error);
      return [];
    }
  }

  async getParameter(name: string): Promise<Parameter | null> {
    try {
      const command = new GetParameterCommand({
        Name: name,
        WithDecryption: true,
      });

      const response = await this.client.send(command);
      return response.Parameter || null;
    } catch (error) {
      console.error(`Error getting parameter ${name}:`, error);
      return null;
    }
  }

  async putParameter(
    name: string,
    value: string,
    type: ParameterType,
    description?: string,
    overwrite = true
  ): Promise<boolean> {
    try {
      const command = new PutParameterCommand({
        Name: name,
        Value: value,
        Type: type,
        Tier: ParameterTier.ADVANCED,
        Description: description,
        Overwrite: overwrite,
      });

      await this.client.send(command);
      return true;
    } catch (error) {
      console.error(`Error putting parameter ${name}:`, error);
      return false;
    }
  }

  async deleteParameter(name: string): Promise<boolean> {
    try {
      const command = new DeleteParameterCommand({
        Name: name,
      });

      await this.client.send(command);
      return true;
    } catch (error) {
      console.error(`Error deleting parameter ${name}:`, error);
      return false;
    }
  }
}

export class LocalStackSQSClient {
  private client: SQSClient;

  constructor() {
    this.client = new SQSClient({
      region: 'us-east-1',
      endpoint: 'http://localhost:4566',
      credentials: {
        accessKeyId: 'test',
        secretAccessKey: 'test',
      },
    });
  }

  async listQueues(): Promise<
    Array<{ queueUrl: string; queueName: string; attributes: Record<string, unknown> }>
  > {
    try {
      const listCommand = new ListQueuesCommand({});
      const listResponse = await this.client.send(listCommand);

      if (!listResponse.QueueUrls || listResponse.QueueUrls.length === 0) {
        return [];
      }

      const queuesWithAttributes = await Promise.all(
        listResponse.QueueUrls.map(async (queueUrl) => {
          const attributesCommand = new GetQueueAttributesCommand({
            QueueUrl: queueUrl,
            AttributeNames: ['All'],
          });

          const attributesResponse = await this.client.send(attributesCommand);
          const attrs = (attributesResponse.Attributes as QueueAttributes) || {};

          return {
            queueUrl,
            queueName: this.extractQueueNameFromUrl(queueUrl),
            attributes: {
              approximateNumberOfMessages: parseInt(attrs.ApproximateNumberOfMessages || '0'),
              approximateNumberOfMessagesNotVisible: parseInt(
                attrs.ApproximateNumberOfMessagesNotVisible || '0'
              ),
              approximateNumberOfMessagesDelayed: parseInt(
                attrs.ApproximateNumberOfMessagesDelayed || '0'
              ),
              createdTimestamp: parseInt(attrs.CreatedTimestamp || '0'),
              lastModifiedTimestamp: parseInt(attrs.LastModifiedTimestamp || '0'),
              queueArn: attrs.QueueArn || '',
              visibilityTimeout: parseInt(attrs.VisibilityTimeout || '30'),
              messageRetentionPeriod: parseInt(attrs.MessageRetentionPeriod || '345600'),
              maxReceiveCount: attrs.MaxReceiveCount ? parseInt(attrs.MaxReceiveCount) : undefined,
              deadLetterTargetArn: attrs.RedrivePolicy
                ? JSON.parse(attrs.RedrivePolicy).deadLetterTargetArn
                : undefined,
            },
          };
        })
      );

      return queuesWithAttributes;
    } catch (error) {
      console.error('Error listing queues:', error);
      return [];
    }
  }

  async getQueueAttributes(
    queueUrl: string
  ): Promise<{ queueUrl: string; queueName: string; attributes: Record<string, unknown> } | null> {
    try {
      const command = new GetQueueAttributesCommand({
        QueueUrl: queueUrl,
        AttributeNames: ['All'],
      });

      const response = await this.client.send(command);
      const attrs = (response.Attributes as QueueAttributes) || {};

      return {
        queueUrl,
        queueName: this.extractQueueNameFromUrl(queueUrl),
        attributes: {
          approximateNumberOfMessages: parseInt(attrs.ApproximateNumberOfMessages || '0'),
          approximateNumberOfMessagesNotVisible: parseInt(
            attrs.ApproximateNumberOfMessagesNotVisible || '0'
          ),
          approximateNumberOfMessagesDelayed: parseInt(
            attrs.ApproximateNumberOfMessagesDelayed || '0'
          ),
          createdTimestamp: parseInt(attrs.CreatedTimestamp || '0'),
          lastModifiedTimestamp: parseInt(attrs.LastModifiedTimestamp || '0'),
          queueArn: attrs.QueueArn || '',
          visibilityTimeout: parseInt(attrs.VisibilityTimeout || '30'),
          messageRetentionPeriod: parseInt(attrs.MessageRetentionPeriod || '345600'),
          maxReceiveCount: attrs.MaxReceiveCount ? parseInt(attrs.MaxReceiveCount) : undefined,
          deadLetterTargetArn: attrs.RedrivePolicy
            ? JSON.parse(attrs.RedrivePolicy).deadLetterTargetArn
            : undefined,
        },
      };
    } catch (error) {
      console.error(`Error getting queue attributes for ${queueUrl}:`, error);
      return null;
    }
  }

  async purgeQueue(queueUrl: string): Promise<boolean> {
    try {
      const command = new PurgeQueueCommand({
        QueueUrl: queueUrl,
      });

      await this.client.send(command);
      return true;
    } catch (error) {
      console.error(`Error purging queue ${queueUrl}:`, error);
      return false;
    }
  }

  async receiveMessages(queueUrl: string, maxMessages: number = 10): Promise<Message[]> {
    try {
      const command = new ReceiveMessageCommand({
        QueueUrl: queueUrl,
        MaxNumberOfMessages: Math.min(maxMessages, 10),
        WaitTimeSeconds: 1,
        AttributeNames: ['All'],
        MessageAttributeNames: ['All'],
      });

      const response = await this.client.send(command);
      return response.Messages || [];
    } catch (error) {
      console.error(`Error receiving messages from ${queueUrl}:`, error);
      return [];
    }
  }

  async deleteMessage(queueUrl: string, receiptHandle: string): Promise<boolean> {
    try {
      const command = new DeleteMessageCommand({
        QueueUrl: queueUrl,
        ReceiptHandle: receiptHandle,
      });

      await this.client.send(command);
      return true;
    } catch (error) {
      console.error(`Error deleting message from ${queueUrl}:`, error);
      return false;
    }
  }

  async sendMessage(
    queueUrl: string,
    messageBody: string,
    messageGroupId?: string,
    messageAttributes?: Record<string, MessageAttributeValue>,
    messageDeduplicationId?: string
  ): Promise<boolean> {
    try {
      const command = new SendMessageCommand({
        QueueUrl: queueUrl,
        MessageBody: messageBody,
        ...(messageGroupId && { MessageGroupId: messageGroupId }),
        ...(messageDeduplicationId && { MessageDeduplicationId: messageDeduplicationId }),
        MessageAttributes: messageAttributes,
      });

      await this.client.send(command);
      return true;
    } catch (error) {
      console.error(`Error sending message to ${queueUrl}:`, error);
      return false;
    }
  }

  private extractQueueNameFromUrl(queueUrl: string): string {
    // Extract queue name from URL like http://localhost:4566/000000000000/my-queue
    const parts = queueUrl.split('/');
    return parts[parts.length - 1] || '';
  }
}
