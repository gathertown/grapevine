import {
  SSMParameter,
  CreateParameterRequest,
  UpdateParameterRequest,
  SQSQueue,
  SQSMessage,
} from '../types';

const API_BASE = '/api';

async function apiRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API Error: ${response.status} - ${error}`);
  }

  // Handle empty response bodies (e.g., 204 No Content)
  const contentLength = response.headers.get('content-length');
  if (response.status === 204 || contentLength === '0') {
    return undefined as T;
  }

  // Check if there's actually content to parse
  const contentType = response.headers.get('content-type');
  if (!contentType || !contentType.includes('application/json')) {
    const text = await response.text();
    if (!text.trim()) {
      return undefined as T;
    }
  }

  return response.json();
}

export const ssmApi = {
  async listParameters(prefix?: string): Promise<SSMParameter[]> {
    const params = new URLSearchParams();
    if (prefix) {
      params.append('prefix', prefix);
    }
    return apiRequest<SSMParameter[]>(`/ssm/parameters?${params}`);
  },

  async getParameter(name: string): Promise<SSMParameter> {
    return apiRequest<SSMParameter>(`/ssm/parameters/${encodeURIComponent(name)}`);
  },

  async createParameter(parameter: CreateParameterRequest): Promise<void> {
    return apiRequest('/ssm/parameters', {
      method: 'POST',
      body: JSON.stringify(parameter),
    });
  },

  async updateParameter(name: string, update: UpdateParameterRequest): Promise<void> {
    return apiRequest(`/ssm/parameters/${encodeURIComponent(name)}`, {
      method: 'PUT',
      body: JSON.stringify(update),
    });
  },

  async deleteParameter(name: string): Promise<void> {
    return apiRequest(`/ssm/parameters/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    });
  },
};

export const sqsApi = {
  async listQueues(): Promise<SQSQueue[]> {
    return apiRequest<SQSQueue[]>('/sqs/queues');
  },

  async getQueueAttributes(queueUrl: string): Promise<SQSQueue> {
    return apiRequest<SQSQueue>(`/sqs/queues/${encodeURIComponent(queueUrl)}/attributes`);
  },

  async purgeQueue(queueUrl: string): Promise<void> {
    return apiRequest(`/sqs/queues/${encodeURIComponent(queueUrl)}/purge`, {
      method: 'POST',
    });
  },

  async getMessages(queueUrl: string, maxMessages: number = 10): Promise<SQSMessage[]> {
    return apiRequest<SQSMessage[]>(
      `/sqs/queues/${encodeURIComponent(queueUrl)}/messages?maxMessages=${maxMessages}`
    );
  },

  async deleteMessage(queueUrl: string, receiptHandle: string): Promise<void> {
    return apiRequest(
      `/sqs/queues/${encodeURIComponent(queueUrl)}/messages/${encodeURIComponent(receiptHandle)}`,
      {
        method: 'DELETE',
      }
    );
  },

  async sendMessage(
    queueUrl: string,
    messageBody: string,
    messageAttributes?: Record<
      string,
      { StringValue?: string; BinaryValue?: string; DataType: string }
    >,
    messageGroupId?: string,
    messageDeduplicationId?: string
  ): Promise<void> {
    return apiRequest(`/sqs/queues/${encodeURIComponent(queueUrl)}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        messageBody,
        messageAttributes,
        messageGroupId,
        messageDeduplicationId,
      }),
    });
  },
};
