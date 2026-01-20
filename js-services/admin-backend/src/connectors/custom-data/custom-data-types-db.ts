/**
 * Data Access Layer for Custom Data Types
 *
 * This module provides database operations for the custom_data_types table
 * in tenant databases. Custom data types define schemas for user-defined
 * document types that can be ingested via the Custom Data API.
 */

import type { Pool } from 'pg';
import { randomUUID } from 'crypto';
import { logger, LogContext } from '../../utils/logger';
import { CUSTOM_DATA_DOCUMENT_ENTITY, CUSTOM_DATA_SOURCE } from './custom-data-constants';

export enum CustomDataTypeState {
  ENABLED = 'enabled',
  DISABLED = 'disabled',
  DELETED = 'deleted',
}

export enum CustomFieldType {
  TEXT = 'text',
  NUMBER = 'number',
  DATE = 'date',
}

export interface CustomFieldDefinition {
  name: string;
  type: CustomFieldType | 'text' | 'date' | 'number'; // Allow both enum and string for backwards compatibility
  required?: boolean;
  description?: string;
}

export interface CustomFieldsSchema {
  fields: CustomFieldDefinition[];
  version: number;
}

export interface CustomDataType {
  id: string;
  display_name: string;
  slug: string;
  description: string | null;
  custom_fields: CustomFieldsSchema;
  state: CustomDataTypeState;
  created_at: string;
  updated_at: string;
}

export interface CreateCustomDataTypeData {
  display_name: string;
  description?: string;
  custom_fields?: CustomFieldsSchema;
}

export interface UpdateCustomDataTypeData {
  display_name?: string;
  description?: string | null;
  custom_fields?: CustomFieldsSchema;
  state?: CustomDataTypeState;
}

/**
 * Generate a URL-safe slug from a display name
 * @throws Error if the resulting slug is empty
 */
export function generateSlug(displayName: string): string {
  const slug = displayName
    .toLowerCase()
    .replace(/\s+/g, '-') // spaces → hyphens
    .replace(/[^a-z0-9-]/g, '') // remove special chars
    .replace(/-+/g, '-') // collapse multiple hyphens
    .replace(/^-|-$/g, ''); // trim hyphens

  if (slug.length === 0) {
    throw new Error('INVALID_DISPLAY_NAME');
  }

  return slug;
}

/**
 * Get all custom data types for a tenant (excluding deleted)
 */
export async function getCustomDataTypes(pool: Pool): Promise<CustomDataType[]> {
  return LogContext.run({ operation: 'get-custom-data-types' }, async () => {
    try {
      const result = await pool.query(
        `SELECT id, display_name, slug, description, custom_fields, state, created_at, updated_at
         FROM custom_data_types
         WHERE state != $1
         ORDER BY created_at DESC`,
        [CustomDataTypeState.DELETED]
      );

      return result.rows;
    } catch (error) {
      logger.error('Failed to get custom data types', { error });
      return [];
    }
  });
}

/**
 * Get a single custom data type by ID
 */
export async function getCustomDataTypeById(
  pool: Pool,
  id: string
): Promise<CustomDataType | null> {
  return LogContext.run(
    { custom_data_type_id: id, operation: 'get-custom-data-type-by-id' },
    async () => {
      try {
        const result = await pool.query(
          `SELECT id, display_name, slug, description, custom_fields, state, created_at, updated_at
         FROM custom_data_types
         WHERE id = $1 AND state != $2`,
          [id, CustomDataTypeState.DELETED]
        );

        return result.rows.length > 0 ? result.rows[0] : null;
      } catch (error) {
        logger.error('Failed to get custom data type', { error, customDataTypeId: id });
        return null;
      }
    }
  );
}

/**
 * Get a single custom data type by slug
 */
export async function getCustomDataTypeBySlug(
  pool: Pool,
  slug: string
): Promise<CustomDataType | null> {
  return LogContext.run({ slug, operation: 'get-custom-data-type-by-slug' }, async () => {
    try {
      const result = await pool.query(
        `SELECT id, display_name, slug, description, custom_fields, state, created_at, updated_at
         FROM custom_data_types
         WHERE slug = $1 AND state != $2`,
        [slug, CustomDataTypeState.DELETED]
      );

      return result.rows.length > 0 ? result.rows[0] : null;
    } catch (error) {
      logger.error('Failed to get custom data type by slug', { error, slug });
      return null;
    }
  });
}

/**
 * Check if there are any enabled custom data types
 */
export async function hasEnabledCustomDataTypes(pool: Pool): Promise<boolean> {
  return LogContext.run({ operation: 'has-enabled-custom-data-types' }, async () => {
    try {
      const result = await pool.query(`SELECT 1 FROM custom_data_types WHERE state = $1 LIMIT 1`, [
        CustomDataTypeState.ENABLED,
      ]);

      return result.rows.length > 0;
    } catch (error) {
      logger.error('Failed to check for enabled custom data types', { error });
      return false;
    }
  });
}

/**
 * Create a new custom data type
 */
export async function createCustomDataType(
  pool: Pool,
  data: CreateCustomDataTypeData
): Promise<CustomDataType | null> {
  const slug = generateSlug(data.display_name);

  return LogContext.run(
    {
      display_name: data.display_name,
      slug,
      operation: 'create-custom-data-type',
    },
    async () => {
      const id = randomUUID();
      const customFields: CustomFieldsSchema = data.custom_fields || { fields: [], version: 1 };

      // Check for existing deleted type with same slug - reactivate it
      try {
        const existingDeleted = await pool.query(
          `SELECT id FROM custom_data_types WHERE slug = $1 AND state = $2`,
          [slug, CustomDataTypeState.DELETED]
        );

        if (existingDeleted.rows.length > 0) {
          const updateResult = await pool.query(
            `UPDATE custom_data_types
             SET state = $1, display_name = $2, description = $3, custom_fields = $4
             WHERE id = $5
             RETURNING id, display_name, slug, description, custom_fields, state, created_at, updated_at`,
            [
              CustomDataTypeState.ENABLED,
              data.display_name,
              data.description || null,
              JSON.stringify(customFields),
              existingDeleted.rows[0].id,
            ]
          );

          return updateResult.rows[0];
        }
      } catch (checkError) {
        logger.error('Error checking for existing deleted type', { error: checkError });
        // Continue with normal create flow
      }

      try {
        const result = await pool.query(
          `INSERT INTO custom_data_types
           (id, display_name, slug, description, custom_fields, state)
           VALUES ($1, $2, $3, $4, $5, $6)
           RETURNING id, display_name, slug, description, custom_fields, state, created_at, updated_at`,
          [
            id,
            data.display_name,
            slug,
            data.description || null,
            JSON.stringify(customFields),
            CustomDataTypeState.ENABLED,
          ]
        );

        return result.rows[0];
      } catch (error: unknown) {
        // Check for unique constraint violation (duplicate slug)
        if (error && typeof error === 'object' && 'code' in error && error.code === '23505') {
          logger.warn('Custom data type with this slug already exists', { slug });
          throw new Error('DUPLICATE_SLUG');
        }

        logger.error('Failed to create custom data type', {
          error,
          displayName: data.display_name,
        });
        return null;
      }
    }
  );
}

/**
 * Update a custom data type
 */
export async function updateCustomDataType(
  pool: Pool,
  id: string,
  data: UpdateCustomDataTypeData
): Promise<CustomDataType | null> {
  return LogContext.run(
    {
      custom_data_type_id: id,
      updated_fields: Object.keys(data),
      operation: 'update-custom-data-type',
    },
    async () => {
      // Build dynamic update query
      const updates: string[] = [];
      const values: (string | boolean | null | undefined)[] = [];
      let paramIndex = 1;

      if (data.display_name !== undefined) {
        updates.push(`display_name = $${paramIndex++}`);
        values.push(data.display_name);
      }

      if (data.description !== undefined) {
        updates.push(`description = $${paramIndex++}`);
        values.push(data.description || null);
      }

      if (data.custom_fields !== undefined) {
        updates.push(`custom_fields = $${paramIndex++}`);
        values.push(JSON.stringify(data.custom_fields));
      }

      if (data.state !== undefined) {
        updates.push(`state = $${paramIndex++}`);
        values.push(data.state);
      }

      if (updates.length === 0) {
        logger.warn('No fields to update', { customDataTypeId: id });
        return null;
      }

      // Add WHERE clause parameters
      values.push(id);

      const query = `
        UPDATE custom_data_types
        SET ${updates.join(', ')}
        WHERE id = $${paramIndex++} AND state != '${CustomDataTypeState.DELETED}'
        RETURNING id, display_name, slug, description, custom_fields, state, created_at, updated_at
      `;

      try {
        const result = await pool.query(query, values);

        if (result.rows.length === 0) {
          logger.warn('Custom data type not found for update', { customDataTypeId: id });
          return null;
        }

        return result.rows[0];
      } catch (error) {
        logger.error('Failed to update custom data type', {
          error,
          customDataTypeId: id,
        });
        return null;
      }
    }
  );
}

/**
 * Delete a custom data type (soft delete by setting state to DELETED)
 */
export async function deleteCustomDataType(pool: Pool, id: string): Promise<boolean> {
  return LogContext.run(
    { custom_data_type_id: id, operation: 'delete-custom-data-type' },
    async () => {
      try {
        const result = await pool.query(
          `UPDATE custom_data_types
         SET state = $1
         WHERE id = $2 AND state != $1
         RETURNING id, display_name`,
          [CustomDataTypeState.DELETED, id]
        );

        if (result.rows.length === 0) {
          logger.warn('Custom data type not found for deletion or already deleted', {
            customDataTypeId: id,
          });
          return false;
        }

        return true;
      } catch (error) {
        logger.error('Failed to delete custom data type', {
          error,
          customDataTypeId: id,
        });
        return false;
      }
    }
  );
}

export interface CustomDataTypeStats {
  documentCount: number;
  artifactCount: number;
}

/**
 * Get stats (document and artifact counts) for a custom data type by its slug
 */
export async function getCustomDataTypeStats(
  pool: Pool,
  slug: string
): Promise<CustomDataTypeStats> {
  return LogContext.run({ slug, operation: 'get-custom-data-type-stats' }, async () => {
    // Escape underscores in slug for LIKE pattern (underscore is a single-char wildcard in SQL LIKE)
    const escapedSlug = slug.replace(/_/g, '\\_');
    // Document ID format: custom_data_{slug}_{item_id}
    const documentIdPrefix = `custom\\_data\\_${escapedSlug}\\_`;
    // Artifact entity_id format: {slug}::{item_id} - also needs escaping for LIKE
    const entityIdPrefix = `${escapedSlug}::`;

    try {
      const [documentCountResult, artifactCountResult] = await Promise.all([
        pool.query(
          `SELECT COUNT(*) as count FROM documents WHERE source = $1 AND id LIKE $2 ESCAPE '\\'`,
          [CUSTOM_DATA_SOURCE, `${documentIdPrefix}%`]
        ),
        pool.query(
          `SELECT COUNT(*) as count FROM ingest_artifact WHERE entity = $1 AND entity_id LIKE $2 ESCAPE '\\'`,
          [CUSTOM_DATA_DOCUMENT_ENTITY, `${entityIdPrefix}%`]
        ),
      ]);

      return {
        documentCount: parseInt(documentCountResult.rows[0]?.count || '0', 10),
        artifactCount: parseInt(artifactCountResult.rows[0]?.count || '0', 10),
      };
    } catch (error) {
      logger.error('Failed to get custom data type stats', { error, slug });
      return { documentCount: 0, artifactCount: 0 };
    }
  });
}
