import OpenAI from 'openai';
import { config } from '../config';
import { logger } from '../utils/logger';
import { Message } from '../types';

export class MutatingActionClassifier {
  private openai: OpenAI;

  constructor() {
    this.openai = new OpenAI({
      apiKey: config.openaiApiKey,
    });
  }

  async detectsMutatingAction(
    currentMessage: string,
    contextMessages: Message[] = []
  ): Promise<boolean> {
    try {
      // Build conversation history for context
      const conversationMessages: Array<{
        role: 'system' | 'user' | 'assistant';
        content: string;
      }> = [
        {
          role: 'system',
          content: `You are a classifier that detects if a user's message is requesting a mutating action (create, update, delete, assign, etc.) vs. just asking a question.

Consider the conversation context to understand references like "it", "this", "that ticket", etc.

Mutating actions include:
- Creating tickets/issues
- Updating status, priority, assignee
- Editing titles, descriptions
- Deleting or archiving items
- Any write operation

Questions/read-only include:
- "What is X?"
- "Show me Y"
- "Get ticket Z"
- "What's the status of..."

Respond with ONLY "true" or "false".`,
        },
      ];

      // Add context messages
      for (const msg of contextMessages) {
        conversationMessages.push({
          role: msg.role,
          content: msg.content,
        });
      }

      // Add current message
      conversationMessages.push({
        role: 'user',
        content: currentMessage,
      });

      const response = await this.openai.chat.completions.create({
        model: 'gpt-4o',
        messages: conversationMessages,
        temperature: 0,
      });

      const result = response.choices[0]?.message?.content?.trim().toLowerCase();
      return result === 'true';
    } catch (error) {
      logger.error('Error classifying mutating action', error);
      // Default to false (safer - allows race mode)
      return false;
    }
  }
}

export const mutatingActionClassifier = new MutatingActionClassifier();
