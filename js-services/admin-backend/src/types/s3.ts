export interface S3Config {
  endpoint?: string;
  region?: string;
  bucketName?: string;
  accessKeyId?: string;
  secretAccessKey?: string;
}

export interface MultipartUploadPart {
  ETag: string;
  PartNumber: number;
}

import { S3Client as AWSS3Client } from '@aws-sdk/client-s3';

export interface S3Client {
  getS3Client: () => AWSS3Client;
  isS3Configured: () => boolean;
  getS3BucketName: () => string | undefined;
}
