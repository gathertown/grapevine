export interface AppConfig {
  ADMIN_WEB_UI_BACKEND_PORT?: number;
  CONTROL_DATABASE_URL?: string;
  destinations?: {
    database?: {
      url?: string;
    };
  };
}

import { Pool } from 'pg';

export interface ConfigManager {
  getConfigValue: (_key: string, _dbConnection: Pool) => Promise<unknown>;
  saveConfigValue: (_key: string, _value: unknown, _dbConnection: Pool) => Promise<boolean>;
  getAllConfigValues: (_dbConnection: Pool) => Promise<Record<string, unknown>>;
}

export interface UploadInfo {
  filename: string;
  location: string;
  size: number;
  uploadedAt: string;
}

export interface IngestJobPayload {
  source: string;
  config: {
    uri: string;
    filename: string;
  };
}
