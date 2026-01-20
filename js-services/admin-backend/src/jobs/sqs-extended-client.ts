/**
 * SQS Extended Client Support
 *
 * Implements the same S3 payload offloading pattern as the Python amazon-sqs-extended-client library.
 * When message payloads exceed 256KB, stores the payload in S3 and sends a pointer in SQS.
 *
 * Message format (compatible with Python extended client):
 * ["software.amazon.payloadoffloading.PayloadS3Pointer", {"s3BucketName": "bucket", "s3Key": "uuid"}]
 */

import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { randomUUID } from 'crypto';
import { logger } from '../utils/logger.js';

// Constants matching the Python extended client
const MESSAGE_POINTER_CLASS = 'software.amazon.payloadoffloading.PayloadS3Pointer';
const RESERVED_ATTRIBUTE_NAME = 'ExtendedPayloadSize';
const DEFAULT_MESSAGE_SIZE_THRESHOLD = 256 * 1024; // 256 KB

/**
 * Configuration for the SQS Extended Client
 */
export interface SqsExtendedClientConfig {
  s3BucketName: string;
  s3Client: S3Client;
  messageSizeThreshold?: number;
}

/**
 * Result of preparing a message for SQS
 */
export interface PreparedMessage {
  messageBody: string;
  messageAttributes?: Record<string, { DataType: string; StringValue: string }>;
}

/**
 * S3 pointer structure stored in SQS message body
 */
interface S3Pointer {
  s3BucketName: string;
  s3Key: string;
}

/**
 * SQS Extended Client for handling large message payloads via S3
 */
export class SqsExtendedClient {
  private s3Client: S3Client;
  private s3BucketName: string;
  private messageSizeThreshold: number;

  constructor(config: SqsExtendedClientConfig) {
    this.s3Client = config.s3Client;
    this.s3BucketName = config.s3BucketName;
    this.messageSizeThreshold = config.messageSizeThreshold ?? DEFAULT_MESSAGE_SIZE_THRESHOLD;
  }

  /**
   * Check if a message body exceeds the size threshold
   */
  private isLargeMessage(messageBody: string): boolean {
    return Buffer.byteLength(messageBody, 'utf8') > this.messageSizeThreshold;
  }

  /**
   * Store payload in S3 and return the S3 key
   */
  private async storeInS3(payload: string): Promise<string> {
    const s3Key = randomUUID();

    await this.s3Client.send(
      new PutObjectCommand({
        Bucket: this.s3BucketName,
        Key: s3Key,
        Body: payload,
        ContentType: 'application/json',
      })
    );

    logger.info('Stored large SQS message payload in S3', {
      bucket: this.s3BucketName,
      key: s3Key,
      payload_size: Buffer.byteLength(payload, 'utf8'),
    });

    return s3Key;
  }

  /**
   * Create the S3 pointer message body (compatible with Python extended client)
   */
  private createS3PointerMessage(pointer: S3Pointer): string {
    return JSON.stringify([MESSAGE_POINTER_CLASS, pointer]);
  }

  /**
   * Prepare a message for sending to SQS.
   * If the message exceeds the size threshold, stores it in S3 and returns a pointer.
   */
  async prepareMessage(messageBody: string): Promise<PreparedMessage> {
    if (!this.isLargeMessage(messageBody)) {
      return { messageBody };
    }

    // Store in S3
    const s3Key = await this.storeInS3(messageBody);

    // Create pointer message
    const pointer: S3Pointer = {
      s3BucketName: this.s3BucketName,
      s3Key,
    };

    const pointerMessage = this.createS3PointerMessage(pointer);
    const originalSize = Buffer.byteLength(messageBody, 'utf8');

    return {
      messageBody: pointerMessage,
      messageAttributes: {
        [RESERVED_ATTRIBUTE_NAME]: {
          DataType: 'Number',
          StringValue: originalSize.toString(),
        },
      },
    };
  }
}

// Lazy-initialized extended client
let extendedClient: SqsExtendedClient | null = null;
let extendedClientInitialized = false;

/**
 * Get the S3 bucket name for SQS extended client
 */
function getExtendedClientBucketName(): string | undefined {
  return process.env.INGEST_WEBHOOK_DATA_S3_BUCKET_NAME;
}

/**
 * Check if SQS extended client is enabled
 */
export function isSqsExtendedClientEnabled(): boolean {
  return !!getExtendedClientBucketName();
}

/**
 * Get or create the SQS extended client instance.
 * Returns null if not configured.
 */
export function getSqsExtendedClient(): SqsExtendedClient | null {
  if (extendedClientInitialized) {
    return extendedClient;
  }

  extendedClientInitialized = true;

  const bucketName = getExtendedClientBucketName();
  if (!bucketName) {
    logger.info('SQS extended client not configured - large payloads will fail');
    return null;
  }

  const region = process.env.AWS_REGION;
  const endpointUrl = process.env.AWS_ENDPOINT_URL;
  const hasExplicitCreds = !!process.env.AWS_ACCESS_KEY_ID && !!process.env.AWS_SECRET_ACCESS_KEY;

  const s3Client = new S3Client({
    ...(region ? { region } : {}),
    ...(endpointUrl ? { endpoint: endpointUrl, forcePathStyle: true } : {}),
    ...(hasExplicitCreds
      ? {
          credentials: {
            accessKeyId: process.env.AWS_ACCESS_KEY_ID as string,
            secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY as string,
            ...(process.env.AWS_SESSION_TOKEN
              ? { sessionToken: process.env.AWS_SESSION_TOKEN }
              : {}),
          },
        }
      : {}),
  });

  extendedClient = new SqsExtendedClient({
    s3BucketName: bucketName,
    s3Client,
  });

  logger.info('SQS extended client initialized', { bucket: bucketName });

  return extendedClient;
}
