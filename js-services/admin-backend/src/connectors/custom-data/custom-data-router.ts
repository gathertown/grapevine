import { Router } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware';
import { logger } from '../../utils/logger';
import {
  getCustomDataTypes,
  getCustomDataTypeById,
  getCustomDataTypeStats,
  createCustomDataType,
  updateCustomDataType,
  hasEnabledCustomDataTypes,
  CustomDataTypeState,
  CustomFieldsSchema,
} from './custom-data-types-db';
import { setCustomDataHasTypes } from './custom-data-config';
import { deleteCustomDataTypeWithData } from './custom-data-service';

const customDataRouter = Router();

/**
 * Helper to update the connector status based on whether there are enabled types
 */
async function updateConnectorStatus(tenantId: string, db: import('pg').Pool): Promise<void> {
  try {
    const hasTypes = await hasEnabledCustomDataTypes(db);
    await setCustomDataHasTypes(tenantId, hasTypes);
  } catch (error) {
    // Log but don't fail the request
    logger.error('Failed to update custom data connector status', { error, tenantId });
  }
}

// List all custom data types for a tenant
customDataRouter.get('/types', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  try {
    const documentTypes = await getCustomDataTypes(req.db);
    return res.json({ documentTypes });
  } catch (error) {
    logger.error('Failed to list custom data types', error, { tenant_id: tenantId });
    return res.status(500).json({ error: 'Failed to list custom data types' });
  }
});

// Get stats for a custom data type (document count, etc.)
customDataRouter.get('/types/:id/stats', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  const { id } = req.params;

  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  if (!id) {
    return res.status(400).json({ error: 'Data type ID is required' });
  }

  try {
    // First get the data type to get its slug
    const documentType = await getCustomDataTypeById(req.db, id);

    if (!documentType) {
      return res.status(404).json({ error: 'Data type not found' });
    }

    const stats = await getCustomDataTypeStats(req.db, documentType.slug);
    return res.json(stats);
  } catch (error) {
    logger.error('Failed to get custom data type stats', error, {
      tenant_id: tenantId,
      custom_data_type_id: id,
    });
    return res.status(500).json({ error: 'Failed to get data type stats' });
  }
});

// Get a single custom data type by ID
customDataRouter.get('/types/:id', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  const { id } = req.params;

  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  if (!id) {
    return res.status(400).json({ error: 'Data type ID is required' });
  }

  try {
    const documentType = await getCustomDataTypeById(req.db, id);

    if (!documentType) {
      return res.status(404).json({ error: 'Data type not found' });
    }

    return res.json({ documentType });
  } catch (error) {
    logger.error('Failed to get custom data type', error, {
      tenant_id: tenantId,
      custom_data_type_id: id,
    });
    return res.status(500).json({ error: 'Failed to get custom data type' });
  }
});

// Create a new custom data type
customDataRouter.post('/types', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  const { display_name, description, custom_fields } = req.body;

  // Validate required fields
  if (!display_name || typeof display_name !== 'string' || display_name.trim().length === 0) {
    return res
      .status(400)
      .json({ error: 'display_name is required and must be a non-empty string' });
  }

  // Validate optional description
  if (description !== undefined && typeof description !== 'string') {
    return res.status(400).json({ error: 'description must be a string' });
  }

  // Validate custom_fields structure if provided
  if (custom_fields !== undefined) {
    if (typeof custom_fields !== 'object' || custom_fields === null) {
      return res.status(400).json({ error: 'custom_fields must be an object' });
    }

    if (!Array.isArray(custom_fields.fields)) {
      return res.status(400).json({ error: 'custom_fields.fields must be an array' });
    }

    // Validate each field definition
    for (const field of custom_fields.fields) {
      if (!field.name || typeof field.name !== 'string') {
        return res.status(400).json({ error: 'Each custom field must have a name' });
      }
      if (!field.type || !['text', 'date', 'number'].includes(field.type)) {
        return res.status(400).json({
          error: `Invalid field type for "${field.name}". Must be one of: text, date, number`,
        });
      }
    }
  }

  try {
    const documentType = await createCustomDataType(req.db, {
      display_name: display_name.trim(),
      description: description?.trim(),
      custom_fields,
    });

    if (!documentType) {
      return res.status(500).json({ error: 'Failed to create data type' });
    }

    // Update connector status
    await updateConnectorStatus(tenantId, req.db);

    return res.status(201).json({ documentType });
  } catch (error: unknown) {
    // Handle duplicate slug error
    if (error instanceof Error && error.message === 'DUPLICATE_SLUG') {
      return res.status(409).json({
        error: 'A data type with this name already exists. Please choose a different name.',
      });
    }

    // Handle invalid display name (results in empty slug)
    if (error instanceof Error && error.message === 'INVALID_DISPLAY_NAME') {
      return res.status(400).json({
        error:
          'Display name must contain at least one alphanumeric character to generate a valid identifier.',
      });
    }

    logger.error('Failed to create custom data type', error, {
      tenant_id: tenantId,
      display_name,
    });
    return res.status(500).json({ error: 'Failed to create data type' });
  }
});

// Update a custom data type
customDataRouter.put('/types/:id', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  const { id } = req.params;

  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  if (!id) {
    return res.status(400).json({ error: 'Data type ID is required' });
  }

  const { display_name, description, custom_fields, state } = req.body;

  // Validate that at least one field is being updated
  if (
    display_name === undefined &&
    description === undefined &&
    custom_fields === undefined &&
    state === undefined
  ) {
    return res.status(400).json({ error: 'At least one field must be provided for update' });
  }

  // Validate field types
  if (
    display_name !== undefined &&
    (typeof display_name !== 'string' || display_name.trim().length === 0)
  ) {
    return res.status(400).json({ error: 'display_name must be a non-empty string if provided' });
  }

  if (description !== undefined && description !== null && typeof description !== 'string') {
    return res.status(400).json({ error: 'description must be a string or null if provided' });
  }

  // Only allow enabled/disabled states via update - deleted requires using DELETE endpoint
  const allowedStates = [CustomDataTypeState.ENABLED, CustomDataTypeState.DISABLED];
  if (state !== undefined && !allowedStates.includes(state as CustomDataTypeState)) {
    return res.status(400).json({
      error: `state must be one of: ${allowedStates.join(', ')}. Use DELETE endpoint to delete.`,
    });
  }

  // Validate custom_fields structure if provided
  if (custom_fields !== undefined) {
    if (typeof custom_fields !== 'object' || custom_fields === null) {
      return res.status(400).json({ error: 'custom_fields must be an object' });
    }

    if (!Array.isArray(custom_fields.fields)) {
      return res.status(400).json({ error: 'custom_fields.fields must be an array' });
    }

    // Validate each field definition
    for (const field of custom_fields.fields) {
      if (!field.name || typeof field.name !== 'string') {
        return res.status(400).json({ error: 'Each custom field must have a name' });
      }
      if (!field.type || !['text', 'date', 'number'].includes(field.type)) {
        return res.status(400).json({
          error: `Invalid field type for "${field.name}". Must be one of: text, date, number`,
        });
      }
    }
  }

  try {
    const updateData: {
      display_name?: string;
      description?: string | null;
      custom_fields?: CustomFieldsSchema;
      state?: CustomDataTypeState;
    } = {};

    if (display_name !== undefined) {
      updateData.display_name = display_name.trim();
    }

    if (description !== undefined) {
      updateData.description = description === null ? null : description.trim();
    }

    if (custom_fields !== undefined) {
      updateData.custom_fields = custom_fields;
    }

    if (state !== undefined) {
      updateData.state = state;
    }

    const documentType = await updateCustomDataType(req.db, id, updateData);

    if (!documentType) {
      return res.status(404).json({ error: 'Data type not found' });
    }

    // Update connector status if state changed
    if (state !== undefined) {
      await updateConnectorStatus(tenantId, req.db);
    }

    return res.json({ documentType });
  } catch (error) {
    logger.error('Failed to update custom data type', error, {
      tenant_id: tenantId,
      custom_data_type_id: id,
    });
    return res.status(500).json({ error: 'Failed to update data type' });
  }
});

// Delete a custom data type (soft delete) and its documents/artifacts
customDataRouter.delete('/types/:id', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  const { id } = req.params;

  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  if (!id) {
    return res.status(400).json({ error: 'Data type ID is required' });
  }

  try {
    const result = await deleteCustomDataTypeWithData(req.db, tenantId, id);

    if (!result) {
      return res.status(404).json({ error: 'Data type not found' });
    }

    // Update connector status (non-critical)
    await updateConnectorStatus(tenantId, req.db);

    return res.json(result);
  } catch (error) {
    logger.error('Failed to delete custom data type', error, {
      tenant_id: tenantId,
      custom_data_type_id: id,
    });
    return res.status(500).json({ error: 'Failed to delete data type' });
  }
});

export { customDataRouter };
