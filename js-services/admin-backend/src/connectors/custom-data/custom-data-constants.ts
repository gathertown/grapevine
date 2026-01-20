/**
 * Constants for Custom Data connector
 */

// Entity type for custom data documents (matches Python ArtifactEntity enum)
export const CUSTOM_DATA_DOCUMENT_ENTITY = 'custom_data_document';

// Document source name (matches Python DocumentSource enum)
export const CUSTOM_DATA_SOURCE = 'custom_data';

// Ingest job source identifier
export const CUSTOM_DATA_INGEST_SOURCE = 'custom_data_ingest';

/**
 * Generate entity ID for custom data documents
 * Format: {slug}::{item_id}
 */
export function getCustomDataDocumentEntityId(slug: string, itemId: string): string {
  return `${slug}::${itemId}`;
}

/**
 * Generate document ID for search index (OpenSearch/Turbopuffer)
 * Format: custom_data_{slug}_{item_id}
 */
export function getCustomDataDocumentId(slug: string, itemId: string): string {
  return `${CUSTOM_DATA_SOURCE}_${slug}_${itemId}`;
}
