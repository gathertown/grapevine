import {
  SQSClient,
  ReceiveMessageCommand,
  DeleteMessageCommand,
  SendMessageCommand,
  Message as SqsMessage,
} from '@aws-sdk/client-sqs';
import { z } from 'zod';
import { logger } from '../utils/logger';
import { nr } from '@corporate-context/backend-common';

type ProcessFunction<T> = (messageData: T, processor?: SQSJobProcessor<T>) => Promise<void>;

export interface SQSJobProcessorOptions<T> {
  queueArn: string;
  schema: z.ZodType<T>;
  processFunction: ProcessFunction<T>;
  maxMessages?: number; // 1-10
  waitTimeSeconds?: number; // 0-20
  visibilityTimeoutSeconds?: number; // seconds
  maxConcurrency?: number; // Maximum number of messages to process concurrently
  sqsClient?: SQSClient;
}

export class SQSJobProcessor<T> {
  private readonly queueArn: string;
  private readonly schema: z.ZodType<T>;
  private readonly processFunction: ProcessFunction<T>;
  private readonly maxMessages: number;
  private readonly waitTimeSeconds: number;
  private readonly visibilityTimeoutSeconds: number;
  private readonly maxConcurrency: number;
  private readonly sqs: SQSClient;

  private running = false;
  private shutdownRequested = false;
  private inFlightMessages = new Set<string>(); // Track currently processing message IDs

  constructor(options: SQSJobProcessorOptions<T>) {
    this.queueArn = options.queueArn;
    this.schema = options.schema;
    this.processFunction = options.processFunction;
    this.maxMessages = options.maxMessages ?? 1;
    this.waitTimeSeconds = options.waitTimeSeconds ?? 20;
    this.visibilityTimeoutSeconds = options.visibilityTimeoutSeconds ?? 300;
    this.maxConcurrency = options.maxConcurrency ?? 20;
    this.sqs = options.sqsClient ?? this.createDefaultSQSClient();
  }

  private createDefaultSQSClient(): SQSClient {
    const region = process.env.AWS_REGION;
    const endpointUrl = process.env.AWS_ENDPOINT_URL;
    const hasExplicitCreds = !!process.env.AWS_ACCESS_KEY_ID && !!process.env.AWS_SECRET_ACCESS_KEY;

    const config = {
      ...(region ? { region } : {}),
      ...(endpointUrl ? { endpoint: endpointUrl } : {}),
      ...(hasExplicitCreds
        ? {
            credentials: {
              accessKeyId: process.env.AWS_ACCESS_KEY_ID as string,
              secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY as string,
            },
          }
        : {}),
    };

    if (endpointUrl) {
      logger.info(`SQS Job Processor configured for LocalStack at ${endpointUrl}`, { endpointUrl });
    }

    return new SQSClient(config);
  }

  // TODO @vic centralize with admin-web-ui/backend/src/sqs-client.ts
  private arnToUrl(arn: string): string {
    // Convert SQS ARN to queue URL
    // ARN format: arn:aws:sqs:region:account-id:queue-name
    const parts = arn.split(':');
    if (parts.length !== 6 || parts[0] !== 'arn' || parts[1] !== 'aws' || parts[2] !== 'sqs') {
      throw new Error(`Invalid SQS ARN format: ${arn}`);
    }

    const region = parts[3];
    const accountId = parts[4];
    const queueName = parts[5];

    return `https://sqs.${region}.amazonaws.com/${accountId}/${queueName}`;
  }

  private setupSignalHandlers(): void {
    const handler = (signal: NodeJS.Signals) => {
      logger.info(`Received ${signal}, initiating graceful shutdown...`, { signal });
      this.shutdownRequested = true;
    };
    process.on('SIGINT', handler);
    process.on('SIGTERM', handler);
  }

  private parseMessageBody(message: SqsMessage): T | null {
    const body = message.Body ?? '';
    if (!body) {
      logger.warn('Received empty message body');
      return null;
    }

    // Parse JSON first
    let jsonData: unknown;
    try {
      jsonData = JSON.parse(body);
    } catch (err) {
      logger.error('Failed to parse message body as JSON', err);
      return null;
    }

    // Validate against provided Zod schema
    try {
      const validatedMessage = this.schema.parse(jsonData);
      return validatedMessage;
    } catch (err) {
      logger.error('Failed to validate message against schema', err);
      return null;
    }
  }

  private async processMessage(message: SqsMessage): Promise<boolean> {
    try {
      const parsed = this.parseMessageBody(message);
      if (!parsed) return false;

      await this.processFunction(parsed, this);
      return true;
    } catch (err) {
      logger.error('Error processing message', err);
      return false;
    }
  }

  private async deleteMessage(queueUrl: string, receiptHandle?: string): Promise<boolean> {
    if (!receiptHandle) {
      logger.warn('Message missing ReceiptHandle, cannot delete');
      return false;
    }
    try {
      await this.sqs.send(
        new DeleteMessageCommand({
          QueueUrl: queueUrl,
          ReceiptHandle: receiptHandle,
        })
      );
      return true;
    } catch (err) {
      logger.warn('Failed to delete processed message', err);
      return false;
    }
  }

  private async pollAndProcess(): Promise<void> {
    const queueUrl = this.arnToUrl(this.queueArn);
    logger.info(`Starting SQS job processor for queue: ${this.queueArn}`, {
      queueArn: this.queueArn,
      maxConcurrency: this.maxConcurrency,
    });
    this.running = true;

    while (this.running && !this.shutdownRequested) {
      try {
        // Check if we're at or near concurrency limit
        const currentConcurrency = this.inFlightMessages.size;
        if (currentConcurrency >= this.maxConcurrency) {
          logger.debug(`At concurrency limit, waiting before polling`, {
            currentConcurrency,
            maxConcurrency: this.maxConcurrency,
          });
          // Wait a bit before checking again
          await new Promise((resolve) => setTimeout(resolve, 100));
          continue;
        }

        // Calculate how many messages we can fetch based on available concurrency
        const availableSlots = this.maxConcurrency - currentConcurrency;
        const messagesToFetch = Math.min(this.maxMessages, availableSlots);

        const resp = await this.sqs.send(
          new ReceiveMessageCommand({
            QueueUrl: queueUrl,
            MaxNumberOfMessages: messagesToFetch,
            WaitTimeSeconds: this.waitTimeSeconds,
            VisibilityTimeout: this.visibilityTimeoutSeconds,
            AttributeNames: ['All'],
            MessageAttributeNames: ['All'],
          })
        );

        const messages = resp.Messages ?? [];
        if (messages.length === 0) {
          continue;
        }

        logger.info(`Received ${messages.length} messages from queue`, {
          messageCount: messages.length,
          currentConcurrency,
          maxConcurrency: this.maxConcurrency,
        });

        // Process messages with fire-and-forget pattern (don't await)
        for (const message of messages) {
          const messageId = message.MessageId ?? `unknown-${Date.now()}`;
          this.inFlightMessages.add(messageId);

          // Start processing without awaiting
          // Note: processMessageAsync has comprehensive try-catch-finally,
          // so it never rejects and no .catch() is needed
          void this.processMessageAsync(queueUrl, message, messageId);
        }

        logger.debug(`Started processing ${messages.length} messages concurrently`, {
          newInFlight: messages.length,
          totalInFlight: this.inFlightMessages.size,
        });

        // Record custom event for monitoring concurrency
        nr?.recordCustomEvent('SlackBotMessageConcurrency', {
          inFlightMessages: this.inFlightMessages.size,
          maxConcurrency: this.maxConcurrency,
          messagesReceived: messages.length,
          queueArn: this.queueArn,
        });
      } catch (err) {
        logger.error('Error in polling loop', err);
        // Brief pause before retrying on error
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    }

    logger.info('SQS job processor polling stopped, waiting for in-flight messages...');
  }

  /**
   * Process a single message asynchronously and handle cleanup
   */
  private async processMessageAsync(
    queueUrl: string,
    message: SqsMessage,
    messageId: string
  ): Promise<void> {
    try {
      const success = await this.processMessage(message);
      if (success) {
        await this.deleteMessage(queueUrl, message.ReceiptHandle);
        logger.debug(`Message processed successfully`, { messageId });
      } else {
        logger.error('Message processing failed, leaving in queue for retry', { messageId });
      }
    } catch (err) {
      logger.error('Error handling message', err, { messageId });
    } finally {
      // Always remove from in-flight tracking
      this.inFlightMessages.delete(messageId);
      logger.debug(`Message removed from in-flight tracking`, {
        messageId,
        remainingInFlight: this.inFlightMessages.size,
      });
    }
  }

  async start(): Promise<void> {
    this.setupSignalHandlers();
    try {
      await this.pollAndProcess();
    } catch (err) {
      if ((err as Error & { name: string })?.name === 'AbortError') {
        logger.info('SQS processor aborted');
      } else {
        logger.error('SQS processor error', err);
      }
    } finally {
      await this.shutdown();
    }
  }

  async shutdown(): Promise<void> {
    logger.info('Shutting down SQS job processor...', {
      inFlightCount: this.inFlightMessages.size,
    });
    this.running = false;
    this.shutdownRequested = true;

    // Wait for in-flight messages to complete with a timeout
    const shutdownTimeoutMs = 30000; // 30 seconds
    const startTime = Date.now();
    const checkInterval = 500; // Check every 500ms

    while (this.inFlightMessages.size > 0) {
      const elapsed = Date.now() - startTime;
      if (elapsed >= shutdownTimeoutMs) {
        logger.warn('Shutdown timeout reached, forcing shutdown with messages still in flight', {
          remainingInFlight: this.inFlightMessages.size,
          elapsedMs: elapsed,
        });
        break;
      }

      logger.info('Waiting for in-flight messages to complete...', {
        remainingInFlight: this.inFlightMessages.size,
        elapsedMs: elapsed,
      });

      await new Promise((resolve) => setTimeout(resolve, checkInterval));
    }

    logger.info('SQS job processor shutdown complete', {
      finalInFlightCount: this.inFlightMessages.size,
    });
  }

  /**
   * Returns true when the processor has started its polling loop
   * and has not been requested to shut down.
   */
  isRunning(): boolean {
    return this.running && !this.shutdownRequested;
  }

  /**
   * Get the current number of messages being processed
   */
  getActiveMessageCount(): number {
    return this.inFlightMessages.size;
  }

  /**
   * Send a message to the same queue this processor is reading from
   */
  async sendMessage(messageData: T): Promise<void> {
    const queueUrl = this.arnToUrl(this.queueArn);

    try {
      const sendMessageCommand: {
        QueueUrl: string;
        MessageBody: string;
        MessageGroupId?: string;
      } = {
        QueueUrl: queueUrl,
        MessageBody: JSON.stringify(messageData),
      };

      // For FIFO queues, MessageGroupId is required
      if (this.queueArn.endsWith('.fifo')) {
        sendMessageCommand.MessageGroupId = 'default';
      }

      await this.sqs.send(new SendMessageCommand(sendMessageCommand));

      logger.info('Successfully sent message to queue', {
        queueArn: this.queueArn,
      });
    } catch (err) {
      logger.error('Failed to send message to queue', err, {
        queueArn: this.queueArn,
      });
      throw err;
    }
  }
}

export default SQSJobProcessor;
