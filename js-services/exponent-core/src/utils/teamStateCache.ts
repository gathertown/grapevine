/**
 * Team state cache for mapping canonical states to Linear state UUIDs
 * Ported from @exponent/task-extraction/src/utils/teamStateCache.ts
 */

import { LinearClient } from '@linear/sdk';

export type StateKey = 'todo' | 'in_progress' | 'in_review' | 'done' | 'canceled';

// Why infer state keys? Linear lets every team rename or add workflow states,
// and the API does not expose a normalized semantic label. Our agents, prompts,
// and downstream diff UIs reason in terms of a tiny canonical set of buckets
// (todo/in_progress/in_review/done/canceled). The mapping logic below takes the
// live state metadata returned by Linear and classifies each entry into one of
// those canonical buckets using the state "type" plus a few heuristics on the
// name. This keeps the agent experience simple (we only ever ask it to emit the
// canonical keys) while still allowing tenants to customize their workflow
// names—in other words, the UUIDs and human labels always come from Linear at
// runtime, but our reasoning surface stays small and consistent.

export type TeamStateInfo = {
  stateIdsByKey: Partial<Record<StateKey, string>>;
  labelsById: Record<string, string>;
};

const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

const stateCache = new Map<string, { expiresAt: number; promise: Promise<TeamStateInfo> }>();

export async function getTeamStateInfo(apiKey: string, teamId: string): Promise<TeamStateInfo> {
  const cacheKey = `${apiKey}:${teamId}`;
  const now = Date.now();
  const cached = stateCache.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    return cached.promise;
  }

  const promise = fetchTeamStateInfo(apiKey, teamId);
  stateCache.set(cacheKey, { expiresAt: now + CACHE_TTL_MS, promise });

  try {
    const info = await promise;
    stateCache.set(cacheKey, {
      expiresAt: now + CACHE_TTL_MS,
      promise: Promise.resolve(info),
    });
    return info;
  } catch (error) {
    stateCache.delete(cacheKey);
    throw error;
  }
}

async function fetchTeamStateInfo(apiKey: string, teamId: string): Promise<TeamStateInfo> {
  const client = new LinearClient({ apiKey });
  const team = await client.team(teamId);
  const statesConnection = await team.states();
  const stateIdsByKey: Partial<Record<StateKey, string>> = {};
  const labelsById: Record<string, string> = {};

  for (const state of statesConnection.nodes) {
    labelsById[state.id] = state.name;
    const key = inferStateKey(state.name, state.type ?? '');
    if (key && !stateIdsByKey[key]) {
      stateIdsByKey[key] = state.id;
    }
  }

  return { stateIdsByKey, labelsById };
}

const STATE_TYPE_MAP: Record<string, StateKey> = {
  backlog: 'todo',
  unstarted: 'todo',
  triage: 'todo',
  started: 'in_progress',
  completed: 'done',
  canceled: 'canceled',
};

function inferStateKey(name: string, type: string): StateKey | undefined {
  // Linear exposes only two hints per workflow state: the free-form name and a
  // broad type (unstarted/started/completed/canceled). Teams can have several
  // "started" states (In Progress, Review, QA) or rename completed states to
  // "Accepted". To keep our agent instructions short, we classify each state
  // into the closest canonical bucket using the type first and then keywords in
  // the name. The goal is not to be perfect; it's to keep emitting deterministic
  // UUIDs even when teams tweak their workflow vocabulary.
  const normalizedType = type.toLowerCase();
  if (STATE_TYPE_MAP[normalizedType]) {
    const mapped = STATE_TYPE_MAP[normalizedType];
    if (mapped === 'in_progress' && name.toLowerCase().includes('review')) {
      return 'in_review';
    }
    return mapped;
  }

  const normalizedName = name.toLowerCase();
  if (normalizedName.includes('review')) {
    return 'in_review';
  }
  if (
    normalizedName.includes('progress') ||
    normalizedName.includes('doing') ||
    normalizedName.includes('active')
  ) {
    return 'in_progress';
  }
  if (
    normalizedName.includes('done') ||
    normalizedName.includes('complete') ||
    normalizedName.includes('finish') ||
    normalizedName.includes('finished')
  ) {
    return 'done';
  }
  if (
    normalizedName.includes('cancel') ||
    normalizedName.includes("won't") ||
    normalizedName.includes('wont') ||
    normalizedName.includes('abandon')
  ) {
    return 'canceled';
  }

  if (
    normalizedName.includes('todo') ||
    normalizedName.includes('backlog') ||
    normalizedName.includes('triage')
  ) {
    return 'todo';
  }

  return undefined;
}
