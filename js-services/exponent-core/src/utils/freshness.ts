import { createLogger } from '@corporate-context/backend-common';
const logger = createLogger('exponent-core');

const MILLIS_THRESHOLD = 1_000_000_000_000; // 1e12, roughly Sat Sep 09 2001

// Default freshness window: 1 hour
// This window is applied uniformly across all artifact types (Slack, meetings, GitHub PRs)
// to prevent reprocessing of stale content that arrives via delayed webhooks.
export const DEFAULT_FRESHNESS_WINDOW_MS = 60 * 60 * 1000;

function parseNumericTimestamp(value: number): number | null {
  if (!Number.isFinite(value)) {
    return null;
  }

  return value > MILLIS_THRESHOLD ? Math.trunc(value) : Math.trunc(value * 1000);
}

function parseStringTimestamp(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const directParse = Date.parse(trimmed);
  if (!Number.isNaN(directParse)) {
    return directParse;
  }

  let candidate = trimmed.replace(/\sUTC$/i, 'Z');

  const candidateParse = Date.parse(candidate);
  if (!Number.isNaN(candidateParse)) {
    return candidateParse;
  }

  candidate = candidate.replace(' ', 'T');

  const isoLikeParse = Date.parse(candidate.endsWith('Z') ? candidate : `${candidate}Z`);
  if (!Number.isNaN(isoLikeParse)) {
    return isoLikeParse;
  }

  // Handle Slack timestamp format (e.g., "1234567890.123456" = seconds.microseconds)
  if (/^\d+\.\d+$/.test(trimmed)) {
    const numeric = parseFloat(trimmed);
    if (!Number.isNaN(numeric)) {
      return parseNumericTimestamp(numeric);
    }
  }

  const numeric = Number(trimmed);
  if (!Number.isNaN(numeric)) {
    return parseNumericTimestamp(numeric);
  }

  return null;
}

export function coerceTimestampToMillis(value: unknown): number | null {
  if (value instanceof Date) {
    const time = value.getTime();
    return Number.isFinite(time) ? time : null;
  }

  if (typeof value === 'number') {
    return parseNumericTimestamp(value);
  }

  if (typeof value === 'string') {
    return parseStringTimestamp(value);
  }

  return null;
}

export type FreshnessEvaluation = {
  isFresh: boolean;
  timestampMs: number | null;
  ageMs: number | null;
};

export function assessFreshness(
  value: unknown,
  options: { now?: number; windowMs?: number } = {}
): FreshnessEvaluation {
  const windowMs = options.windowMs ?? DEFAULT_FRESHNESS_WINDOW_MS;
  const now = options.now ?? Date.now();

  const timestampMs = coerceTimestampToMillis(value);
  if (timestampMs == null) {
    return {
      isFresh: false,
      timestampMs: null,
      ageMs: null,
    };
  }

  const ageMs = now - timestampMs;
  if (ageMs < 0) {
    logger.warn('Freshness check encountered future timestamp', {
      timestampMs,
      now,
      ageMs,
    });
    return {
      isFresh: true,
      timestampMs,
      ageMs,
    };
  }

  if (ageMs === 0) {
    return {
      isFresh: true,
      timestampMs,
      ageMs,
    };
  }

  return {
    isFresh: ageMs <= windowMs,
    timestampMs,
    ageMs,
  };
}

export function formatFreshnessForLogging(freshness: FreshnessEvaluation, originalValue: unknown) {
  return {
    parsedTimestamp:
      freshness.timestampMs != null ? new Date(freshness.timestampMs).toISOString() : originalValue,
    ageMinutes: freshness.ageMs != null ? Math.floor(freshness.ageMs / 60000) : null,
    freshnessWindowMs: DEFAULT_FRESHNESS_WINDOW_MS,
  };
}
