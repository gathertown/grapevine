import { OpenAI } from 'openai';
import { config } from './config';

// Lazy initialize clients
let openai: OpenAI | null = null;
export const getOpenAI = (): OpenAI => {
  if (!openai) {
    openai = new OpenAI({
      apiKey: config.openaiApiKey,
    });
  }
  return openai;
};

// Multi-tenant client factories
const tenantClients = {
  openai: new Map<string, OpenAI>(),
};

export const getTenantOpenAI = async (tenantId: string): Promise<OpenAI> => {
  if (!tenantClients.openai.has(tenantId)) {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error(`OpenAI API key not found in environment variables`);
    }
    const client = new OpenAI({ apiKey });
    tenantClients.openai.set(tenantId, client);
  }
  const client = tenantClients.openai.get(tenantId);
  if (!client) {
    throw new Error(`Failed to retrieve OpenAI client for tenant ${tenantId}`);
  }
  return client;
};
