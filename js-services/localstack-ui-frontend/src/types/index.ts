export interface SSMParameter {
  name: string;
  value: string;
  type: 'String' | 'StringList' | 'SecureString';
  description?: string;
  version: number;
  lastModifiedDate: string;
  keyId?: string;
}

export interface CreateParameterRequest {
  name: string;
  value: string;
  type: 'String' | 'StringList' | 'SecureString';
  description?: string;
}

export interface UpdateParameterRequest {
  value: string;
  description?: string;
}

export interface SQSQueue {
  queueUrl: string;
  queueName: string;
  attributes: {
    approximateNumberOfMessages: number;
    approximateNumberOfMessagesNotVisible: number;
    approximateNumberOfMessagesDelayed: number;
    createdTimestamp: number;
    lastModifiedTimestamp: number;
    queueArn: string;
    visibilityTimeout: number;
    messageRetentionPeriod: number;
    maxReceiveCount?: number;
    deadLetterTargetArn?: string;
  };
}

export interface SQSMessage {
  messageId: string;
  receiptHandle: string;
  body: string;
  attributes?: Record<string, string>;
  messageAttributes?: Record<
    string,
    { StringValue?: string; BinaryValue?: string; DataType: string }
  >;
}

export interface SendMessageRequest {
  messageBody: string;
  messageGroupId?: string;
  messageDeduplicationId?: string;
  messageAttributes?: Record<
    string,
    { StringValue?: string; BinaryValue?: string; DataType: string }
  >;
}
