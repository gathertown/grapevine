import type { Block, KnownBlock, ContextBlock, SectionBlock, DividerBlock } from '@slack/types';
import type { StreamEvent } from '../common';
import type { TranslatedPhrases } from '../i18n/phrases';
import { DEFAULT_PHRASES_EN } from '../i18n/phrases';

interface Step {
  icon: string;
  action: string;
  actionPast: string;
}

export interface ProgressState {
  recentSteps: Step[];
  fastAnswer: string | null;
  phrases: TranslatedPhrases;
}

const MAX_VISIBLE_STEPS = 2;

export function createProgressState(
  phrases: TranslatedPhrases = DEFAULT_PHRASES_EN
): ProgressState {
  return {
    recentSteps: [{ icon: '🔍', action: phrases.searching, actionPast: phrases.searched }],
    fastAnswer: null,
    phrases,
  };
}

/**
 * ThrottledProgressUpdater drains progress events at a steady cadence.
 *
 * Events arrive in bursts: 0---000---000000---0
 * We display at steady pace: 0---0---0---0---0---0
 *
 * All events are processed (state accumulates), but Slack updates happen
 * at regular intervals to avoid burst updates.
 */
export class ThrottledProgressUpdater {
  private state: ProgressState;
  private pendingEvents: StreamEvent[] = [];
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private lastUpdateState: ProgressState | null = null;
  private isRunning = false;
  private hasProcessedFirstEvent = false;
  private readonly intervalMs: number;
  private readonly onUpdate: (state: ProgressState) => Promise<void>;

  constructor(
    initialState: ProgressState,
    onUpdate: (state: ProgressState) => Promise<void>,
    intervalMs: number = 2500
  ) {
    this.state = initialState;
    this.onUpdate = onUpdate;
    this.intervalMs = intervalMs;
  }

  /**
   * Start the throttled update loop
   */
  start(): void {
    if (this.isRunning) return;
    this.isRunning = true;

    // Record initial state (don't send update - already posted initial message)
    this.lastUpdateState = {
      ...this.state,
      recentSteps: [...this.state.recentSteps],
    };

    // Start interval to drain pending events
    this.intervalId = setInterval(() => {
      void this.tick();
    }, this.intervalMs);
  }

  /**
   * Queue an event to be processed
   */
  pushEvent(event: StreamEvent): void {
    this.pendingEvents.push(event);

    // Process first event immediately so users see progress right away
    if (!this.hasProcessedFirstEvent) {
      this.hasProcessedFirstEvent = true;
      void this.tick();
    }
  }

  /**
   * Set fast answer (bypasses queue, updates state immediately)
   */
  setFastAnswer(answer: string): void {
    this.state = setFastAnswer(this.state, answer);
    // Fast answer should be shown immediately since it's user-facing content
    void this.onUpdate(this.state);
    this.lastUpdateState = {
      ...this.state,
      recentSteps: [...this.state.recentSteps],
    };
  }

  /**
   * Stop the interval and flush any remaining events
   */
  async stop(): Promise<void> {
    this.isRunning = false;

    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }

    // Process all remaining events
    let event = this.pendingEvents.shift();
    while (event) {
      this.state = updateProgressState(this.state, event);
      event = this.pendingEvents.shift();
    }

    // Send final update if state changed
    if (this.hasStateChanged()) {
      await this.onUpdate(this.state);
      this.lastUpdateState = {
        ...this.state,
        recentSteps: [...this.state.recentSteps],
      };
    }
  }

  /**
   * Get current state (for external access)
   */
  getState(): ProgressState {
    return this.state;
  }

  private async tick(): Promise<void> {
    // Process one pending event per tick
    const event = this.pendingEvents.shift();
    if (event) {
      this.state = updateProgressState(this.state, event);

      // Only send update if state actually changed
      if (this.hasStateChanged()) {
        try {
          await this.onUpdate(this.state);
          this.lastUpdateState = {
            ...this.state,
            recentSteps: [...this.state.recentSteps],
          };
        } catch {
          // Progress updates are best-effort; don't let failures break the interval
        }
      }
    }
  }

  private hasStateChanged(): boolean {
    if (!this.lastUpdateState) return true;
    if (this.state.fastAnswer !== this.lastUpdateState.fastAnswer) return true;
    if (this.state.recentSteps.length !== this.lastUpdateState.recentSteps.length) return true;
    return this.state.recentSteps.some(
      (step, i) =>
        step.icon !== this.lastUpdateState?.recentSteps[i]?.icon ||
        step.action !== this.lastUpdateState?.recentSteps[i]?.action
    );
  }
}

interface ToolDisplay {
  icon: string;
  action: string;
  actionPast: string;
}

function getToolDisplay(toolName: string, phrases: TranslatedPhrases): ToolDisplay {
  const map: Record<string, ToolDisplay> = {
    semantic_search: { icon: '🔍', action: phrases.searching, actionPast: phrases.searched },
    keyword_search: { icon: '🔍', action: phrases.searching, actionPast: phrases.searched },
    get_document: { icon: '📖', action: phrases.reading, actionPast: phrases.read },
    get_document_metadata: { icon: '📖', action: phrases.reading, actionPast: phrases.read },
    list_documents: { icon: '📋', action: phrases.listing, actionPast: phrases.listed },
  };
  return map[toolName] || { icon: '⚙️', action: phrases.processing, actionPast: phrases.processed };
}

export function updateProgressState(state: ProgressState, event: StreamEvent): ProgressState {
  const newState = { ...state, recentSteps: [...state.recentSteps] };
  const { type, data } = event;
  const phrases = state.phrases;

  switch (type) {
    case 'tool_call': {
      if (typeof data === 'object' && data !== null) {
        const toolData = data as { tool_name?: string; status?: string };
        if (toolData.status === 'starting') {
          const display = getToolDisplay(toolData.tool_name || 'tool', phrases);
          const newStep: Step = {
            icon: display.icon,
            action: display.action,
            actionPast: display.actionPast,
          };
          newState.recentSteps.push(newStep);
          if (newState.recentSteps.length > MAX_VISIBLE_STEPS) {
            newState.recentSteps.shift();
          }
        }
      }
      break;
    }
    case 'tool_result': {
      const thinkingStep: Step = {
        icon: '🧠',
        action: phrases.thinking,
        actionPast: phrases.analyzed,
      };
      newState.recentSteps.push(thinkingStep);
      if (newState.recentSteps.length > MAX_VISIBLE_STEPS) {
        newState.recentSteps.shift();
      }
      break;
    }
    case 'agent_decision': {
      if (typeof data === 'object' && data !== null) {
        const d = data as { decision?: string };
        if (d.decision === 'finish') {
          const writingStep: Step = {
            icon: '✍️',
            action: phrases.writing,
            actionPast: phrases.drafted,
          };
          newState.recentSteps.push(writingStep);
          if (newState.recentSteps.length > MAX_VISIBLE_STEPS) {
            newState.recentSteps.shift();
          }
        }
      }
      break;
    }
  }
  return newState;
}

export function setFastAnswer(state: ProgressState, answer: string): ProgressState {
  return { ...state, fastAnswer: answer };
}

function buildProgressLine(state: ProgressState): string {
  const { recentSteps, phrases } = state;
  if (recentSteps.length === 0) return `${phrases.workingOnYourAnswer} 🔍 ${phrases.searching}…`;

  const pipeline = recentSteps
    .map((step, i) => {
      const isLast = i === recentSteps.length - 1;
      return isLast ? `${step.icon} ${step.action}…` : `${step.icon} ${step.actionPast}`;
    })
    .join(' → ');

  return `${phrases.workingOnYourAnswer} ${pipeline}`;
}

export function buildProgressBlocks(state: ProgressState): (KnownBlock | Block)[] {
  const blocks: (KnownBlock | Block)[] = [];
  const { phrases } = state;

  const progressContext: ContextBlock = {
    type: 'context',
    elements: [{ type: 'mrkdwn', text: buildProgressLine(state) }],
  };
  blocks.push(progressContext);

  if (state.fastAnswer) {
    const divider: DividerBlock = { type: 'divider' };
    blocks.push(divider);

    // Header indicating this is a preliminary answer
    const previewHeader: ContextBlock = {
      type: 'context',
      elements: [{ type: 'mrkdwn', text: phrases.quickAnswerHeader }],
    };
    blocks.push(previewHeader);

    // Fast answer in blockquote style to look like "thinking out loud"
    const answerSection: SectionBlock = {
      type: 'section',
      expand: true,
      text: { type: 'mrkdwn', text: `>${state.fastAnswer.split('\n').join('\n>')}` },
    };
    blocks.push(answerSection);
  }

  return blocks;
}

export function buildProgressMessage(state: ProgressState): string {
  const { phrases } = state;
  let text = buildProgressLine(state);
  if (state.fastAnswer) {
    text += `\n---\n${phrases.quickAnswerHeader}\n>${state.fastAnswer.split('\n').join('\n>')}`;
  }
  return text;
}

export function getInitialProgressBlocks(
  phrases: TranslatedPhrases = DEFAULT_PHRASES_EN
): (KnownBlock | Block)[] {
  return buildProgressBlocks(createProgressState(phrases));
}

export function getInitialProgressMessage(phrases: TranslatedPhrases = DEFAULT_PHRASES_EN): string {
  return `${phrases.workingOnYourAnswer} 🔍 ${phrases.searching}…`;
}
