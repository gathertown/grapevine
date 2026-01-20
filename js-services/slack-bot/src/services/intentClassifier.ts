import OpenAI from 'openai';
import { config } from '../config';
import { logger } from '../utils/logger';

export type Intent = 'TRIAGE' | 'QA';

export class IntentClassifier {
  private openai: OpenAI;

  constructor() {
    this.openai = new OpenAI({
      apiKey: config.openaiApiKey,
    });
  }

  async classify(text: string): Promise<Intent> {
    try {
      const response = await this.openai.chat.completions.create({
        model: 'gpt-4o',
        messages: [
          {
            role: 'system',
            content: `You are an intent classifier for a Slack bot.
Your job is to categorize the user's message into one of two categories:
1. "TRIAGE": The user is reporting a bug, requesting a feature, or asking for a ticket to be created/updated. They might say things like "file a ticket", "report this bug", "something is broken", "feature request", or describe an issue they are facing that needs engineering attention.
2. "QA": The user is asking a question about how something works, looking for documentation, or asking for information.

Respond ONLY with "TRIAGE" or "QA".`,
          },
          {
            role: 'user',
            content: text,
          },
        ],
        temperature: 0,
        max_tokens: 10,
      });

      const content = response.choices[0]?.message?.content?.trim().toUpperCase();

      if (content === 'TRIAGE') {
        return 'TRIAGE';
      }

      return 'QA';
    } catch (error) {
      logger.error('Error classifying intent', error);
      // Default to QA on error as it's the safer fallback
      return 'QA';
    }
  }
}

export const intentClassifier = new IntentClassifier();
