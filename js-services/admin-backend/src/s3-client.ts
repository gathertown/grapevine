/**
 * S3 Client Initialization
 * Handles AWS S3/Supabase Storage client setup
 */

import {
  S3Client,
  S3ClientConfig,
  CreateMultipartUploadCommand,
  UploadPartCommand,
  CompleteMultipartUploadCommand,
  GetObjectCommand,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { logger } from './utils/logger.js';

// Initialize S3 client (supports both AWS S3 and LocalStack)
let s3Client: S3Client | null = null;
const S3_STORAGE_ENDPOINT = process.env.S3_STORAGE_ENDPOINT;
const AWS_ENDPOINT_URL = process.env.AWS_ENDPOINT_URL;

if (process.env.S3_BUCKET_NAME) {
  const s3Config: S3ClientConfig = {
    // Use path-style addressing (required for LocalStack and some S3-compatible services)
    forcePathStyle: true,
  };

  // Set region
  if (process.env.AWS_REGION) {
    s3Config.region = process.env.AWS_REGION;
  }

  // Configure endpoint (prioritize S3_STORAGE_ENDPOINT, fallback to AWS_ENDPOINT_URL for LocalStack)
  const endpointUrl = S3_STORAGE_ENDPOINT || AWS_ENDPOINT_URL;
  if (endpointUrl) {
    s3Config.endpoint = endpointUrl;
  }

  // Configure credentials
  const hasExplicitCreds = !!process.env.AWS_ACCESS_KEY_ID && !!process.env.AWS_SECRET_ACCESS_KEY;
  if (hasExplicitCreds) {
    s3Config.credentials = {
      accessKeyId: process.env.AWS_ACCESS_KEY_ID as string,
      secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY as string,
    };
  }

  s3Client = new S3Client(s3Config);

  if (endpointUrl) {
    logger.info(`S3 client initialized with endpoint: ${endpointUrl}`, { endpoint: endpointUrl });
  } else {
    logger.info('S3 client initialized for AWS S3');
  }
} else {
  logger.info('S3 configuration not found - S3 uploads will be disabled');
}

/**
 * Get the S3 client instance
 */
function getS3Client(): S3Client {
  if (!s3Client) {
    throw new Error('S3 client not initialized - check configuration');
  }
  return s3Client;
}

/**
 * Check if S3 is configured
 */
function isS3Configured(): boolean {
  return s3Client !== null && !!process.env.S3_BUCKET_NAME;
}

/**
 * Get the S3 bucket name
 */
function getS3BucketName(): string {
  const bucketName = process.env.S3_BUCKET_NAME;
  if (!bucketName) {
    throw new Error('S3_BUCKET_NAME not configured');
  }
  return bucketName;
}

export {
  s3Client,
  getS3Client,
  isS3Configured,
  getS3BucketName,
  // Re-export AWS SDK components for convenience
  CreateMultipartUploadCommand,
  UploadPartCommand,
  CompleteMultipartUploadCommand,
  GetObjectCommand,
  getSignedUrl,
};
