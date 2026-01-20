/**
 * Checkpoint File Finder
 *
 * Finds and parses checkpoint files in a dataset directory.
 * Files follow one of these patterns:
 * - YYYY-MM-DD_HH-MM-SS_<description>.json (with timestamp)
 * - YYYY-MM-DD_<description>.json (without timestamp)
 */

import { readdirSync, existsSync, statSync } from 'fs';
import { join, basename } from 'path';
import type { CheckpointFile } from './types';

/**
 * Regex for checkpoint filename format: YYYY-MM-DD_[HH-MM-SS_]<description>.json
 * Timestamp is optional to support both formats:
 * - 2025-12-01_09-30-00_standup.json (with timestamp)
 * - 2025-12-01_standup.json (without timestamp)
 */
const CHECKPOINT_FILENAME_REGEX = /^(\d{4}-\d{2}-\d{2})_(?:(\d{2}-\d{2}-\d{2})_)?(.+)\.json$/;

/**
 * Check if a filename is a checkpoint file (not truth or generated)
 */
function isCheckpointFile(filename: string): boolean {
  // Exclude truth and generated files
  if (filename.endsWith('-truth.json') || filename.endsWith('-generated.json')) {
    return false;
  }

  // Must match checkpoint pattern
  return CHECKPOINT_FILENAME_REGEX.test(filename);
}

/**
 * Parse a checkpoint filename into its components
 */
export function parseCheckpointFilename(filename: string): CheckpointFile | null {
  const match = filename.match(CHECKPOINT_FILENAME_REGEX);
  if (!match) {
    return null;
  }

  const [, date, timestamp, description] = match;
  if (!date || !description) {
    return null;
  }

  return {
    filename,
    date,
    timestamp: timestamp || '00-00-00', // Default for date-only files
    description,
    path: '', // Will be set by caller
  };
}

/**
 * Find all checkpoint files in a directory
 *
 * @param datasetPath - Path to the dataset directory
 * @param options - Filter options
 * @returns Sorted list of checkpoint files (chronologically)
 */
export function findCheckpointFiles(
  datasetPath: string,
  options: {
    from?: string; // Start date (YYYY-MM-DD)
    until?: string; // End date (YYYY-MM-DD)
    filter?: string; // Filter by filename substring
  } = {}
): CheckpointFile[] {
  // Validate path exists
  if (!existsSync(datasetPath)) {
    throw new Error(`Dataset directory not found: ${datasetPath}`);
  }

  const stats = statSync(datasetPath);
  if (!stats.isDirectory()) {
    throw new Error(`Dataset path is not a directory: ${datasetPath}`);
  }

  // Find all checkpoint files
  const files = readdirSync(datasetPath);
  const checkpointFiles: CheckpointFile[] = [];

  for (const filename of files) {
    if (!isCheckpointFile(filename)) {
      continue;
    }

    const parsed = parseCheckpointFilename(filename);
    if (!parsed) {
      continue;
    }

    // Apply date filters
    if (options.from && parsed.date < options.from) {
      continue;
    }
    if (options.until && parsed.date > options.until) {
      continue;
    }

    // Apply filename filter
    if (options.filter && !filename.includes(options.filter)) {
      continue;
    }

    checkpointFiles.push({
      ...parsed,
      path: join(datasetPath, filename),
    });
  }

  // Sort chronologically (by date, then timestamp)
  checkpointFiles.sort((a, b) => {
    const dateCompare = a.date.localeCompare(b.date);
    if (dateCompare !== 0) {
      return dateCompare;
    }
    return a.timestamp.localeCompare(b.timestamp);
  });

  return checkpointFiles;
}

/**
 * Get the truth file path for a checkpoint
 */
export function getTruthFilePath(checkpoint: CheckpointFile): string {
  const base = basename(checkpoint.filename, '.json');
  const dir = checkpoint.path.replace(checkpoint.filename, '');
  return join(dir, `${base}-truth.json`);
}

/**
 * Check if a truth file exists for a checkpoint
 */
export function hasTruthFile(checkpoint: CheckpointFile): boolean {
  const truthPath = getTruthFilePath(checkpoint);
  return existsSync(truthPath);
}
