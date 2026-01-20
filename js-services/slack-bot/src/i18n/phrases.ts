/**
 * All UI phrases that may need translation.
 * These serve as the English defaults and translation keys.
 */
export interface UIPhrasesEN {
  // Fallback/error messages
  fallbackAnswer: string;
  processingState: string;
  noSourcesSetup: string; // Has {dashboardUrl} placeholder

  // Progress indicators
  workingOnYourAnswer: string;
  quickAnswerHeader: string;
  completeAnswerHeader: string;

  // Tool action verbs (present/past)
  searching: string;
  searched: string;
  reading: string;
  read: string;
  listing: string;
  listed: string;
  processing: string;
  processed: string;
  thinking: string;
  analyzed: string;
  writing: string;
  drafted: string;

  // Guest user messages
  guestUserDM: string;
  guestUserChannelReply: string; // Has {userId} placeholder
}

export const DEFAULT_PHRASES_EN: UIPhrasesEN = {
  // Fallback/error messages
  fallbackAnswer: 'Sorry, I had trouble answering that question. Feel free to try again!',
  processingState:
    "Thanks for adding initial sources! I'm still processing, I should be able to answer in a few more minutes",
  noSourcesSetup:
    "It looks like you don't have any sources setup yet - add some in the <{dashboardUrl}|Grapevine dashboard> so I can help!",

  // Progress indicators
  workingOnYourAnswer: 'Working on your answer:',
  quickAnswerHeader: '💭 _Quick answer while I search for more details:_',
  completeAnswerHeader: '✅ *Complete Answer:*',

  // Tool action verbs
  searching: 'Searching',
  searched: 'Searched',
  reading: 'Reading',
  read: 'Read',
  listing: 'Listing',
  listed: 'Listed',
  processing: 'Processing',
  processed: 'Processed',
  thinking: 'Thinking',
  analyzed: 'Analyzed',
  writing: 'Writing',
  drafted: 'Drafted',

  // Guest user messages
  guestUserDM:
    "Hi! This bot is currently available only for full workspace members. Guest users and external collaborators (Slack Connect) don't have access to this feature. If you need assistance, please reach out to a full workspace member.",
  guestUserChannelReply:
    "<@{userId}> Sorry, this bot is currently available only for full workspace members. Guest and external users don't have access. I've sent you a DM with more information.",
};

export type TranslatedPhrases = UIPhrasesEN;
