import { Router } from 'express';
import { requireAdmin } from '../../../middleware/auth-middleware';
import { logger } from '../../../utils/logger';
import {
  getSemanticModelsByTenantId,
  getSemanticModelById,
  createSemanticModel,
  updateSemanticModel,
  deleteSemanticModel,
  SemanticModelState,
  SemanticModelType,
} from '../snowflake-semantic-models-db';

const snowflakeSemanticModelsRouter = Router();

// List all semantic models for a tenant
snowflakeSemanticModelsRouter.get('/', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  try {
    const semanticModels = await getSemanticModelsByTenantId(req.db);
    return res.json({ semanticModels });
  } catch (error) {
    logger.error('Failed to list semantic models', error, {
      tenant_id: tenantId,
    });
    return res.status(500).json({ error: 'Failed to list semantic models' });
  }
});

// Get a single semantic model by ID
snowflakeSemanticModelsRouter.get('/:id', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  const { id } = req.params;

  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  if (!id) {
    return res.status(400).json({ error: 'Semantic model ID is required' });
  }

  try {
    const semanticModel = await getSemanticModelById(req.db, id);

    if (!semanticModel) {
      return res.status(404).json({ error: 'Semantic model not found' });
    }

    return res.json({ semanticModel });
  } catch (error) {
    logger.error('Failed to get semantic model', error, {
      tenant_id: tenantId,
      semantic_model_id: id,
    });
    return res.status(500).json({ error: 'Failed to get semantic model' });
  }
});

// Create a new semantic model or view
snowflakeSemanticModelsRouter.post('/', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  const { name, type, stage_path, database_name, schema_name, description, warehouse } = req.body;

  // Validate required fields
  if (!name || typeof name !== 'string' || name.trim().length === 0) {
    return res.status(400).json({ error: 'name is required and must be a non-empty string' });
  }

  if (!type || (type !== SemanticModelType.MODEL && type !== SemanticModelType.VIEW)) {
    return res.status(400).json({
      error: `type is required and must be either "${SemanticModelType.MODEL}" or "${SemanticModelType.VIEW}"`,
    });
  }

  // Validate type-specific required fields
  if (type === SemanticModelType.MODEL) {
    if (!stage_path || typeof stage_path !== 'string' || stage_path.trim().length === 0) {
      return res.status(400).json({
        error: 'stage_path is required for semantic models and must be a non-empty string',
      });
    }
  }

  if (type === SemanticModelType.VIEW) {
    if (!database_name || typeof database_name !== 'string' || database_name.trim().length === 0) {
      return res.status(400).json({
        error: 'database_name is required for semantic views and must be a non-empty string',
      });
    }
    if (!schema_name || typeof schema_name !== 'string' || schema_name.trim().length === 0) {
      return res.status(400).json({
        error: 'schema_name is required for semantic views and must be a non-empty string',
      });
    }
  }

  // Validate required warehouse field
  if (!warehouse || typeof warehouse !== 'string' || warehouse.trim().length === 0) {
    return res.status(400).json({
      error: 'warehouse is required and must be a non-empty string (e.g., COMPUTE_WH)',
    });
  }

  // Validate optional fields
  if (description !== undefined && typeof description !== 'string') {
    return res.status(400).json({ error: 'description must be a string' });
  }

  try {
    // TODO: Validate that the semantic model/view exists in Snowflake
    // This will be implemented when the Snowflake API client is ready (CONN-345)

    const semanticModel = await createSemanticModel(req.db, {
      name: name.trim(),
      type,
      stage_path: stage_path?.trim(),
      database_name: database_name?.trim(),
      schema_name: schema_name?.trim(),
      description: description?.trim(),
      warehouse: warehouse?.trim(),
    });

    if (!semanticModel) {
      return res.status(500).json({ error: `Failed to create semantic ${type}` });
    }

    return res.status(201).json({ semanticModel });
  } catch (error: unknown) {
    // Handle duplicate errors from DAL
    if (error instanceof Error && error.message === 'DUPLICATE_STAGE_PATH') {
      return res.status(409).json({
        error: 'A semantic model with this stage path already exists for your organization',
      });
    }
    if (error instanceof Error && error.message === 'DUPLICATE_VIEW_NAME') {
      return res.status(409).json({
        error: 'A semantic view with this name already exists in this database and schema',
      });
    }
    if (error instanceof Error && error.message === 'MISSING_STAGE_PATH') {
      return res.status(400).json({ error: 'stage_path is required for semantic models' });
    }
    if (error instanceof Error && error.message === 'MISSING_DATABASE_SCHEMA') {
      return res
        .status(400)
        .json({ error: 'database_name and schema_name are required for semantic views' });
    }

    logger.error(`Failed to create semantic ${type || 'model'}`, error, {
      tenant_id: tenantId,
      name,
      type,
    });
    return res.status(500).json({ error: `Failed to create semantic ${type || 'model'}` });
  }
});

// Update a semantic model
snowflakeSemanticModelsRouter.put('/:id', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  const { id } = req.params;

  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  if (!id) {
    return res.status(400).json({ error: 'Semantic model ID is required' });
  }

  const { name, description, warehouse, state } = req.body;

  // Validate that at least one field is being updated
  if (
    name === undefined &&
    description === undefined &&
    warehouse === undefined &&
    state === undefined
  ) {
    return res.status(400).json({ error: 'At least one field must be provided for update' });
  }

  // Validate field types
  if (name !== undefined && (typeof name !== 'string' || name.trim().length === 0)) {
    return res.status(400).json({ error: 'name must be a non-empty string if provided' });
  }

  if (description !== undefined && description !== null && typeof description !== 'string') {
    return res.status(400).json({ error: 'description must be a string or null if provided' });
  }

  if (
    warehouse !== undefined &&
    warehouse !== null &&
    (typeof warehouse !== 'string' || warehouse.trim().length === 0)
  ) {
    return res.status(400).json({ error: 'warehouse must be a non-empty string or null' });
  }

  if (
    state !== undefined &&
    !Object.values(SemanticModelState).includes(state as SemanticModelState)
  ) {
    return res.status(400).json({
      error: `state must be one of: ${Object.values(SemanticModelState).join(', ')}`,
    });
  }

  try {
    const updateData: {
      name?: string;
      description?: string | null;
      warehouse?: string | null;
      state?: SemanticModelState;
    } = {};

    if (name !== undefined) {
      updateData.name = name.trim();
    }

    if (description !== undefined) {
      updateData.description = description === null ? null : description.trim();
    }

    if (warehouse !== undefined) {
      updateData.warehouse = warehouse === null ? null : warehouse.trim();
    }

    if (state !== undefined) {
      updateData.state = state;
    }

    const semanticModel = await updateSemanticModel(req.db, id, updateData);

    if (!semanticModel) {
      return res.status(404).json({ error: 'Semantic model not found' });
    }

    return res.json({ semanticModel });
  } catch (error) {
    logger.error('Failed to update semantic model', error, {
      tenant_id: tenantId,
      semantic_model_id: id,
    });
    return res.status(500).json({ error: 'Failed to update semantic model' });
  }
});

// Delete a semantic model
snowflakeSemanticModelsRouter.delete('/:id', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  const { id } = req.params;

  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  if (!req.db) {
    return res.status(500).json({ error: 'Database connection not available' });
  }

  if (!id) {
    return res.status(400).json({ error: 'Semantic model ID is required' });
  }

  try {
    const success = await deleteSemanticModel(req.db, id);

    if (!success) {
      return res.status(404).json({ error: 'Semantic model not found' });
    }

    return res.json({ success: true, deletedId: id });
  } catch (error) {
    logger.error('Failed to delete semantic model', error, {
      tenant_id: tenantId,
      semantic_model_id: id,
    });
    return res.status(500).json({ error: 'Failed to delete semantic model' });
  }
});

export { snowflakeSemanticModelsRouter };
