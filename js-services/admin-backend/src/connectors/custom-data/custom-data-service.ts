/**
 * Service layer for Custom Data operations
 *
 * This module handles business logic and transactional operations
 * for custom data types, keeping the router thin and focused on HTTP concerns.
 */

import type { Pool } from 'pg';
import { logger, LogContext } from '../../utils/logger';
import { CustomDataTypeState } from './custom-data-types-db';
import { deleteDocumentsBySlugBatched, deleteArtifactsBySlug } from './custom-data-documents-db';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client';

export interface DeleteCustomDataTypeResult {
  success: boolean;
  deletedId: string;
  documentsDeleted: number;
  artifactsDeleted: number;
  searchIndexDeleteTriggered: boolean;
}

/**
 * Delete a custom data type along with all its documents and artifacts.
 * Uses a database transaction to ensure atomicity - all operations succeed or all fail.
 * Also triggers deletion from search indices (OpenSearch/Turbopuffer) via SQS.
 */
export async function deleteCustomDataTypeWithData(
  pool: Pool,
  tenantId: string,
  id: string
): Promise<DeleteCustomDataTypeResult | null> {
  return LogContext.run(
    { custom_data_type_id: id, operation: 'delete-custom-data-type-with-data' },
    async () => {
      const client = await pool.connect();

      try {
        await client.query('BEGIN');

        // Get the data type to retrieve its slug before deletion
        const documentTypeResult = await client.query(
          `SELECT id, slug FROM custom_data_types
           WHERE id = $1 AND state != $2`,
          [id, CustomDataTypeState.DELETED]
        );

        if (documentTypeResult.rows.length === 0) {
          await client.query('ROLLBACK');
          return null;
        }

        const { slug } = documentTypeResult.rows[0];

        // Delete documents in batches and collect IDs for search index deletion
        // We collect all IDs first and only send SQS messages AFTER commit succeeds
        // to avoid inconsistency if the transaction rolls back
        const allDeletedDocumentIds: string[] = [];

        for await (const batchIds of deleteDocumentsBySlugBatched(client, slug)) {
          allDeletedDocumentIds.push(...batchIds);
        }

        // Delete artifacts
        const artifactsDeletedCount = await deleteArtifactsBySlug(client, slug);

        // Soft delete the data type
        const deleteResult = await client.query(
          `UPDATE custom_data_types
           SET state = $1
           WHERE id = $2 AND state != $1
           RETURNING id`,
          [CustomDataTypeState.DELETED, id]
        );

        if (deleteResult.rows.length === 0) {
          await client.query('ROLLBACK');
          return null;
        }

        await client.query('COMMIT');

        // Only trigger search index deletion AFTER successful commit
        // This prevents inconsistency if transaction had rolled back
        let searchIndexDeleteTriggered = false;
        if (allDeletedDocumentIds.length > 0 && isSqsConfigured()) {
          // Send delete messages in batches of 1000 to avoid oversized SQS messages
          const BATCH_SIZE = 1000;
          for (let i = 0; i < allDeletedDocumentIds.length; i += BATCH_SIZE) {
            const batch = allDeletedDocumentIds.slice(i, i + BATCH_SIZE);
            try {
              await getSqsClient().sendDeleteJob(tenantId, batch);
              searchIndexDeleteTriggered = true;
              logger.info('Triggered search index deletion for document batch', {
                custom_data_type_id: id,
                slug,
                batch_size: batch.length,
                batch_number: Math.floor(i / BATCH_SIZE) + 1,
                total_batches: Math.ceil(allDeletedDocumentIds.length / BATCH_SIZE),
              });
            } catch (deleteError) {
              // Log but continue with remaining batches
              logger.error('Failed to trigger search index deletion for batch', {
                error: deleteError,
                custom_data_type_id: id,
                slug,
                batch_size: batch.length,
              });
            }
          }
        }

        logger.info('Deleted custom data type with documents and artifacts', {
          custom_data_type_id: id,
          slug,
          documents_deleted: allDeletedDocumentIds.length,
          artifacts_deleted: artifactsDeletedCount,
          search_index_delete_triggered: searchIndexDeleteTriggered,
        });

        return {
          success: true,
          deletedId: id,
          documentsDeleted: allDeletedDocumentIds.length,
          artifactsDeleted: artifactsDeletedCount,
          searchIndexDeleteTriggered,
        };
      } catch (error) {
        await client.query('ROLLBACK');
        logger.error('Failed to delete custom data type with data', {
          error,
          custom_data_type_id: id,
        });
        throw error;
      } finally {
        client.release();
      }
    }
  );
}
