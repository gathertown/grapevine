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
