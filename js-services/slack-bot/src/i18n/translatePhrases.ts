import { makeBackendRequest } from '../common';
import { logger } from '../utils/logger';
import { DEFAULT_PHRASES_EN, TranslatedPhrases } from './phrases';

/**
 * Detect the language of a message and translate UI phrases if needed.
 * Uses the MCP backend to perform the translation.
 */
export async function getPhrasesForMessage(
  tenantId: string,
  messageText: string
): Promise<{ phrases: TranslatedPhrases; detectedLanguage: string }> {
  try {
    // Build a prompt that asks the LLM to detect language and translate phrases
    const translationPrompt = `You are a translation assistant. Analyze the following user message and:

1. Detect the language of the message
2. If the message is NOT in English, translate the UI phrases below to match the detected language

USER MESSAGE:
"""
${messageText}
"""

UI PHRASES TO TRANSLATE (JSON):
${JSON.stringify(DEFAULT_PHRASES_EN, null, 2)}

IMPORTANT RULES:
- Preserve all placeholders like {dashboardUrl}, {userId} exactly as-is
- Keep emoji characters unchanged  
- Keep Slack formatting characters (* for bold, _ for italic, \` for code) unchanged
- Maintain the exact same JSON structure and keys

RESPOND WITH ONLY THIS JSON FORMAT (no markdown, no explanation):
{
  "detectedLanguage": "<ISO 639-1 code like 'en', 'ja', 'ko', 'zh', 'es', etc.>",
  "phrases": <the translated phrases object, or the original if English>
}`;

    const result = await makeBackendRequest(
      tenantId,
      translationPrompt,
      undefined, // userEmail
      undefined, // files
      undefined, // previousResponseId
      undefined, // permissionAudience
      true, // nonBillable - translation is internal overhead
      'minimal', // reasoningEffort - we want speed
      'low', // verbosity
      'ask_agent', // toolName - use fast variant (doesn't support disableTools)
      true, // disableTools - not supported by ask_agent_fast
      undefined, // writeTools
      'markdown' // outputFormat
    );

    if (!result?.answer) {
      logger.warn('No translation result from MCP, using English defaults', {
        tenantId,
        operation: 'translate-phrases',
      });
      return { phrases: DEFAULT_PHRASES_EN, detectedLanguage: 'en' };
    }

    // Parse the JSON response
    const jsonContent = result.answer
      .replace(/^```json?\n?|\n?```$/g, '') // Remove markdown code blocks if present
      .trim();

    const parsed = JSON.parse(jsonContent) as {
      detectedLanguage: string;
      phrases: TranslatedPhrases;
    };

    logger.info('Successfully detected language and translated phrases', {
      tenantId,
      detectedLanguage: parsed.detectedLanguage,
      operation: 'translate-phrases',
    });

    return {
      phrases: parsed.phrases,
      detectedLanguage: parsed.detectedLanguage,
    };
  } catch (error) {
    logger.error(
      'Failed to translate phrases via MCP, falling back to English',
      error instanceof Error ? error : new Error(String(error)),
      {
        tenantId,
        operation: 'translate-phrases',
      }
    );
    return { phrases: DEFAULT_PHRASES_EN, detectedLanguage: 'en' };
  }
}
