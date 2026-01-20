/**
 * Linear URL utility functions
 */

/**
 * Extract Linear issue identifier from URL
 * @param url - Linear issue URL
 * @returns Issue identifier (e.g., "EXP-60") or null if not found
 */
export function extractLinearIdFromUrl(url: string): string | null {
  try {
    // Match Linear URL pattern: .../issue/{ID}/...
    // The ID is typically in format like EXP-60, ABC-123, etc.
    const match = url.match(/\/issue\/([A-Z]+-\d+)/i);
    return match ? match[1].toUpperCase() : null;
  } catch {
    return null;
  }
}

/**
 * Build Linear issue URL from identifier
 * @param identifier - Issue identifier (e.g., "EXP-60")
 * @param fullUrl - Optional full URL to use instead of building one
 * @returns Linear issue URL
 */
export function buildLinearUrl(identifier: string, fullUrl?: string): string {
  if (fullUrl) {
    return fullUrl;
  }
  return `https://linear.app/issue/${identifier}`;
}
