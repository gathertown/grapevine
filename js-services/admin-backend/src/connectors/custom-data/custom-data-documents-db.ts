/**
 * Data Access Layer for Custom Data Documents
 *
 * This module provides database operations for ingesting custom documents
 * into the ingest_artifact table for processing by the indexing pipeline.
 */

import type { Pool } from 'pg';
import { randomUUID } from 'crypto';
import { logger, LogContext } from '../../utils/logger';
import {
  CUSTOM_DATA_DOCUMENT_ENTITY,
  getCustomDataDocumentEntityId,
} from './custom-data-constants';

export { getCustomDataDocumentEntityId };

export interface CustomDocumentInput {
  id: string;
  name: string;
  description?: string;
  content: string;
  customFields?: Record<string, unknown>;
}

export interface CustomDocumentArtifact {
  id: string;
  entity: string;
  entity_id: string;
  content: { content: string };
  metadata: Record<string, unknown>;
  source_updated_at: string;
}

/**
 * Upsert a custom document artifact
 * Updates only if the new source_updated_at is newer than existing
 */
export async function upsertCustomDocumentArtifact(
  pool: Pool,
  slug: string,
  document: CustomDocumentInput
): Promise<CustomDocumentArtifact> {
  return LogContext.run(
    { slug, document_id: document.id, operation: 'upsert-custom-document-artifact' },
    async () => {
      const artifactId = randomUUID();
      const entityId = getCustomDataDocumentEntityId(slug, document.id);
      const ingestJobId = randomUUID(); // Generate a job ID for this ingestion
      const sourceUpdatedAt = new Date().toISOString();

      // Content structure matches CustomDataDocument artifact content
      const content = { content: document.content };

      // Metadata includes all document fields for search and display
      const metadata: Record<string, unknown> = {
        name: document.name,
        description: document.description || null,
        slug,
        item_id: document.id,
        ...document.customFields,
      };

      try {
        await pool.query(
          `INSERT INTO ingest_artifact (id, entity, entity_id, ingest_job_id, content, metadata, source_updated_at)
           VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
           ON CONFLICT (entity, entity_id) DO UPDATE SET
             id = EXCLUDED.id,
             ingest_job_id = EXCLUDED.ingest_job_id,
             content = EXCLUDED.content,
             metadata = EXCLUDED.metadata,
             source_updated_at = EXCLUDED.source_updated_at
           WHERE ingest_artifact.source_updated_at < EXCLUDED.source_updated_at`,
          [
            artifactId,
            CUSTOM_DATA_DOCUMENT_ENTITY,
            entityId,
            ingestJobId,
            JSON.stringify(content),
            JSON.stringify(metadata),
            sourceUpdatedAt,
          ]
        );

        logger.info('Upserted custom document artifact', {
          artifact_id: artifactId,
          entity_id: entityId,
          slug,
          document_id: document.id,
        });

        return {
          id: artifactId,
          entity: CUSTOM_DATA_DOCUMENT_ENTITY,
          entity_id: entityId,
          content,
          metadata,
          source_updated_at: sourceUpdatedAt,
        };
      } catch (error) {
        logger.error('Failed to upsert custom document artifact', {
          error,
          slug,
          document_id: document.id,
        });
        throw error;
      }
    }
  );
}

/**
 * Upsert multiple custom document artifacts in a batch
 */
export async function upsertCustomDocumentArtifactsBatch(
  pool: Pool,
  slug: string,
  documents: CustomDocumentInput[]
): Promise<CustomDocumentArtifact[]> {
  return LogContext.run(
    { slug, document_count: documents.length, operation: 'upsert-custom-document-artifacts-batch' },
    async () => {
      if (documents.length === 0) {
        return [];
      }

      const ingestJobId = randomUUID();
      const sourceUpdatedAt = new Date().toISOString();
      const artifacts: CustomDocumentArtifact[] = [];

      const client = await pool.connect();
      try {
        await client.query('BEGIN');

        for (const document of documents) {
          const artifactId = randomUUID();
          const entityId = getCustomDataDocumentEntityId(slug, document.id);
          const content = { content: document.content };
          const metadata: Record<string, unknown> = {
            name: document.name,
            description: document.description || null,
            slug,
            item_id: document.id,
            ...document.customFields,
          };

          await client.query(
            `INSERT INTO ingest_artifact (id, entity, entity_id, ingest_job_id, content, metadata, source_updated_at)
             VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
             ON CONFLICT (entity, entity_id) DO UPDATE SET
               id = EXCLUDED.id,
               ingest_job_id = EXCLUDED.ingest_job_id,
               content = EXCLUDED.content,
               metadata = EXCLUDED.metadata,
               source_updated_at = EXCLUDED.source_updated_at
             WHERE ingest_artifact.source_updated_at < EXCLUDED.source_updated_at`,
            [
              artifactId,
              CUSTOM_DATA_DOCUMENT_ENTITY,
              entityId,
              ingestJobId,
              JSON.stringify(content),
              JSON.stringify(metadata),
              sourceUpdatedAt,
            ]
          );

          artifacts.push({
            id: artifactId,
            entity: CUSTOM_DATA_DOCUMENT_ENTITY,
            entity_id: entityId,
            content,
            metadata,
            source_updated_at: sourceUpdatedAt,
          });
        }

        await client.query('COMMIT');

        logger.info('Batch upserted custom document artifacts', {
          slug,
          document_count: documents.length,
          ingest_job_id: ingestJobId,
        });

        return artifacts;
      } catch (error) {
        await client.query('ROLLBACK');
        logger.error('Failed to batch upsert custom document artifacts', {
          error,
          slug,
          document_count: documents.length,
        });
        throw error;
      } finally {
        client.release();
      }
    }
  );
}

/**
 * Get a custom document artifact by slug and item ID
 * Returns null if not found, throws on database errors
 */
export async function getCustomDocumentArtifact(
  pool: Pool,
  slug: string,
  itemId: string
): Promise<CustomDocumentArtifact | null> {
  return LogContext.run(
    { slug, item_id: itemId, operation: 'get-custom-document-artifact' },
    async () => {
      const entityId = getCustomDataDocumentEntityId(slug, itemId);

      const result = await pool.query(
        `SELECT id, entity, entity_id, content, metadata, source_updated_at
         FROM ingest_artifact
         WHERE entity = $1 AND entity_id = $2`,
        [CUSTOM_DATA_DOCUMENT_ENTITY, entityId]
      );

      if (result.rows.length === 0) {
        return null;
      }

      const row = result.rows[0];
      return {
        id: row.id,
        entity: row.entity,
        entity_id: row.entity_id,
        content: row.content,
        metadata: row.metadata,
        source_updated_at: row.source_updated_at,
      };
    }
  );
}

/**
 * Delete a custom document artifact by slug and item ID
 * Returns false if not found, throws on database errors
 */
export async function deleteCustomDocumentArtifact(
  pool: Pool,
  slug: string,
  itemId: string
): Promise<boolean> {
  return LogContext.run(
    { slug, item_id: itemId, operation: 'delete-custom-document-artifact' },
    async () => {
      const entityId = getCustomDataDocumentEntityId(slug, itemId);

      const result = await pool.query(
        `DELETE FROM ingest_artifact
         WHERE entity = $1 AND entity_id = $2
         RETURNING id`,
        [CUSTOM_DATA_DOCUMENT_ENTITY, entityId]
      );

      if (result.rows.length === 0) {
        logger.warn('Custom document artifact not found for deletion', {
          slug,
          item_id: itemId,
          entity_id: entityId,
        });
        return false;
      }

      logger.info('Deleted custom document artifact', {
        slug,
        item_id: itemId,
        entity_id: entityId,
      });

      return true;
    }
  );
}

/**
 * Escape special characters for SQL LIKE pattern matching.
 * In SQL LIKE:
 * - underscore (_) is a single-character wildcard
 * - percent (%) is a multi-character wildcard
 * - backslash (\) is the escape character
 * All must be escaped to match literal characters.
 */
function escapeForLike(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/%/g, '\\%').replace(/_/g, '\\_');
}

/**
 * Delete all documents for a custom data type by slug using batched processing.
 * Yields batches of deleted document IDs for incremental search index cleanup.
 *
 * This uses a cursor-based approach to avoid loading all IDs into memory at once,
 * which is important for data types with many documents.
 *
 * Uses metadata->>'slug' for exact slug matching to avoid issues with slugs
 * that share prefixes or contain underscores (e.g., 'test' vs 'test_data').
 */
export async function* deleteDocumentsBySlugBatched(
  client: Pool | { query: Pool['query'] },
  slug: string,
  batchSize: number = 1000
): AsyncGenerator<string[]> {
  let lastId: string | null = null;
  let hasMore = true;

  while (hasMore) {
    // Query by metadata->>'slug' for exact matching
    // This avoids prefix-based matching issues with underscores in slugs
    let selectResult: { rows: { id: string }[]; rowCount: number | null };
    if (lastId) {
      selectResult = await client.query(
        `SELECT id FROM documents
         WHERE source = $1 AND metadata->>'slug' = $2 AND id > $3
         ORDER BY id LIMIT $4`,
        ['custom_data', slug, lastId, batchSize]
      );
    } else {
      selectResult = await client.query(
        `SELECT id FROM documents
         WHERE source = $1 AND metadata->>'slug' = $2
         ORDER BY id LIMIT $3`,
        ['custom_data', slug, batchSize]
      );
    }

    if (selectResult.rows.length === 0) {
      hasMore = false;
      break;
    }

    const idsToDelete = selectResult.rows.map((row: { id: string }) => row.id);

    // Update cursor for next iteration
    const lastRow = selectResult.rows[selectResult.rows.length - 1];
    lastId = lastRow?.id ?? null;
    hasMore = selectResult.rows.length === batchSize;

    if (idsToDelete.length > 0) {
      // Delete this batch
      await client.query(`DELETE FROM documents WHERE id = ANY($1)`, [idsToDelete]);
      yield idsToDelete;
    }
  }
}

/**
 * Delete all documents for a custom data type by slug.
 * Returns all deleted document IDs for search index cleanup.
 *
 * Note: For data types with many documents, prefer using deleteDocumentsBySlugBatched
 * to process incrementally and avoid memory issues.
 */
export async function deleteDocumentsBySlug(
  client: Pool | { query: Pool['query'] },
  slug: string
): Promise<string[]> {
  const allDeletedIds: string[] = [];

  for await (const batch of deleteDocumentsBySlugBatched(client, slug)) {
    allDeletedIds.push(...batch);
  }

  return allDeletedIds;
}

/**
 * Delete all artifacts for a custom data type by slug
 * Returns the count of deleted artifacts
 */
export async function deleteArtifactsBySlug(
  client: Pool | { query: Pool['query'] },
  slug: string
): Promise<number> {
  // Escape special chars in slug for LIKE pattern
  const escapedSlug = escapeForLike(slug);
  // Entity ID format: {slug}::{item_id}
  // The :: delimiter ensures we won't match longer slugs
  const entityIdPrefix = `${escapedSlug}::%`;

  const result = await client.query(
    `DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id LIKE $2 ESCAPE '\\' RETURNING id`,
    [CUSTOM_DATA_DOCUMENT_ENTITY, entityIdPrefix]
  );

  return result.rowCount || 0;
}
