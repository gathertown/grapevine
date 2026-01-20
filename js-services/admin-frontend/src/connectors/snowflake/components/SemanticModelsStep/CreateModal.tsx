import { useState } from 'react';
import { Button, Flex, Text, Input, Modal, Select } from '@gathertown/gather-design-system';
import {
  useCreateSemanticModel,
  useSnowflakeStages,
  useSnowflakeWarehouses,
  useSnowflakeSemanticViews,
  useSemanticModels,
  SemanticModelType,
  type CreateSemanticModelParams,
} from '../../snowflakeApi';

interface CreateSemanticModelModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export const CreateSemanticModelModal = ({ onClose, onSuccess }: CreateSemanticModelModalProps) => {
  const [type, setType] = useState<SemanticModelType>(SemanticModelType.MODEL);
  const [name, setName] = useState('');
  const [stagePath, setStagePath] = useState('');
  const [database, setDatabase] = useState('');
  const [schema, setSchema] = useState('');
  const [selectedViewId, setSelectedViewId] = useState('');
  const [description, setDescription] = useState('');
  const [warehouse, setWarehouse] = useState('');
  const { mutate: createModel, isPending, error } = useCreateSemanticModel();
  const {
    data: warehousesData,
    isLoading: isLoadingWarehouses,
    error: warehousesError,
  } = useSnowflakeWarehouses();
  const { data: stagesData, isLoading: isLoadingStages, error: stagesError } = useSnowflakeStages();
  const {
    data: semanticViewsData,
    isLoading: isLoadingSemanticViews,
    error: semanticViewsError,
  } = useSnowflakeSemanticViews();
  const { data: existingModelsData } = useSemanticModels();

  // Compute available semantic views (exclude already-tracked ones)
  const existingModels = existingModelsData?.semanticModels || [];
  const availableSemanticViews = (() => {
    if (!semanticViewsData?.semanticViews || !Array.isArray(semanticViewsData.semanticViews)) {
      return [];
    }

    // Filter out views that are already tracked
    return semanticViewsData.semanticViews.filter((view) => {
      if (!view) return false;
      const viewRecord = view as Record<string, unknown>;
      const viewName = (view.name || viewRecord['NAME']) as string | undefined;
      const viewDb = (view.database_name || viewRecord['DATABASE_NAME']) as string | undefined;
      const viewSchema = (view.schema_name || viewRecord['SCHEMA_NAME']) as string | undefined;

      if (!viewName || !viewDb || !viewSchema) return false;

      // Check if this view is already tracked
      const isTracked = existingModels.some(
        (model) =>
          model.type === SemanticModelType.VIEW &&
          model.database_name === viewDb &&
          model.schema_name === viewSchema &&
          model.name === viewName
      );

      return !isTracked;
    });
  })();

  // Handler for when a semantic view is selected from dropdown
  const handleSemanticViewSelect = (viewId: string) => {
    setSelectedViewId(viewId);

    if (!viewId) {
      setDatabase('');
      setSchema('');
      setName('');
      return;
    }

    // Find the selected view and auto-populate fields
    const selectedView = availableSemanticViews.find((view) => {
      const viewRecord = view as Record<string, unknown>;
      const viewName = (view.name || viewRecord['NAME']) as string;
      const viewDb = (view.database_name || viewRecord['DATABASE_NAME']) as string;
      const viewSchema = (view.schema_name || viewRecord['SCHEMA_NAME']) as string;
      return `${viewDb}.${viewSchema}.${viewName}` === viewId;
    });

    if (selectedView) {
      const viewRecord = selectedView as Record<string, unknown>;
      const viewName = (selectedView.name || viewRecord['NAME']) as string;
      const viewDb = (selectedView.database_name || viewRecord['DATABASE_NAME']) as string;
      const viewSchema = (selectedView.schema_name || viewRecord['SCHEMA_NAME']) as string;

      setDatabase(viewDb);
      setSchema(viewSchema);
      setName(viewName);
    }
  };

  const canSubmitModel =
    warehouse.trim().length > 0 &&
    name.trim().length > 0 &&
    stagePath.trim().length > 0 &&
    !isPending;

  const canSubmitView =
    warehouse.trim().length > 0 &&
    selectedViewId.trim().length > 0 &&
    database.trim().length > 0 &&
    schema.trim().length > 0 &&
    !isPending;

  const canSubmit = type === SemanticModelType.MODEL ? canSubmitModel : canSubmitView;

  const handleSubmit = () => {
    const params: CreateSemanticModelParams = {
      name: name.trim(),
      type,
    };

    // Add type-specific fields
    if (type === SemanticModelType.MODEL) {
      params.stage_path = stagePath.trim();
    } else {
      params.database_name = database.trim();
      params.schema_name = schema.trim();
    }

    // Add optional description
    if (description.trim()) {
      params.description = description.trim();
    }

    // Add required warehouse
    params.warehouse = warehouse.trim();

    createModel(params, {
      onSuccess: () => {
        onSuccess();
      },
    });
  };

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content variant="default" showOverlay style={{ maxWidth: 600 }}>
        <Modal.Header
          title={`Add Semantic ${type === SemanticModelType.MODEL ? 'Model' : 'View'}`}
        />
        <Modal.Body style={{ padding: 16, gap: 16 }}>
          <Flex direction="column" gap={16}>
            {/* Type Selector */}
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="semibold">
                Type *
              </Text>
              <Flex direction="row" gap={16}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="type"
                    value={SemanticModelType.MODEL}
                    checked={type === SemanticModelType.MODEL}
                    onChange={() => {
                      setType(SemanticModelType.MODEL);
                      setName('');
                      setSelectedViewId('');
                      setDatabase('');
                      setSchema('');
                    }}
                    disabled={isPending}
                  />
                  <Text fontSize="sm">Semantic Model (YAML file in stage)</Text>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name="type"
                    value={SemanticModelType.VIEW}
                    checked={type === SemanticModelType.VIEW}
                    onChange={() => {
                      setType(SemanticModelType.VIEW);
                      setName('');
                      setStagePath('');
                    }}
                    disabled={isPending}
                  />
                  <Text fontSize="sm">Semantic View (database object)</Text>
                </label>
              </Flex>
              <Text fontSize="xs" color="secondary">
                {type === SemanticModelType.MODEL
                  ? 'A YAML file stored in a Snowflake stage that defines your semantic model'
                  : 'A database object that provides a semantic layer over your data'}
              </Text>
            </Flex>

            {/* Conditional: Name field only for Models */}
            {type === SemanticModelType.MODEL && (
              <Flex direction="column" gap={8}>
                <Text fontSize="sm" fontWeight="semibold">
                  Name *
                </Text>
                <Input
                  placeholder="My Semantic Model"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={isPending}
                />
                <Text fontSize="xs" color="secondary">
                  A descriptive name for this semantic model
                </Text>
              </Flex>
            )}

            {/* Conditional: Stage Path for Models */}
            {type === SemanticModelType.MODEL && (
              <Flex direction="column" gap={8}>
                <Text fontSize="sm" fontWeight="semibold">
                  Stage Path *
                </Text>
                {isLoadingStages ? (
                  <Text fontSize="xs" color="secondary">
                    Loading stages...
                  </Text>
                ) : stagesError ? (
                  <Flex direction="column" gap={4}>
                    <Input
                      placeholder="@my_stage/models/my_model.yaml"
                      value={stagePath}
                      onChange={(e) => setStagePath(e.target.value)}
                      disabled={isPending}
                    />
                    <Text fontSize="xs" color="dangerPrimary">
                      Failed to load stages: {stagesError.message}
                    </Text>
                  </Flex>
                ) : stagesData &&
                  Array.isArray(stagesData.stages) &&
                  stagesData.stages.length > 0 ? (
                  <Flex direction="column" gap={8}>
                    <Select
                      value={stagePath.split('/')[0] || ''}
                      onChange={(value) => setStagePath(value)}
                      disabled={isPending}
                      placeholder="Select a stage"
                      options={stagesData.stages
                        .filter(
                          (stage) =>
                            stage &&
                            (stage.name || (stage as Record<string, unknown>)['NAME']) &&
                            (stage.database_name ||
                              (stage as Record<string, unknown>)['DATABASE_NAME']) &&
                            (stage.schema_name || (stage as Record<string, unknown>)['SCHEMA_NAME'])
                        )
                        .map((stage) => {
                          const stageRecord = stage as Record<string, unknown>;
                          const name = (stage.name || stageRecord['NAME']) as string;
                          const dbName = (stage.database_name ||
                            stageRecord['DATABASE_NAME']) as string;
                          const schemaName = (stage.schema_name ||
                            stageRecord['SCHEMA_NAME']) as string;
                          const fullPath = `@${dbName}.${schemaName}.${name}`;
                          return {
                            label: fullPath,
                            value: fullPath,
                          };
                        })}
                    />
                    <Input
                      placeholder="@my_stage/models/my_model.yaml"
                      value={stagePath}
                      onChange={(e) => setStagePath(e.target.value)}
                      disabled={isPending}
                    />
                    <Text fontSize="xs" color="secondary">
                      Select a stage above, then edit the full path to include your YAML file (e.g.,
                      add /models/my_model.yaml)
                    </Text>
                  </Flex>
                ) : (
                  <Input
                    placeholder="@my_stage/models/my_model.yaml"
                    value={stagePath}
                    onChange={(e) => setStagePath(e.target.value)}
                    disabled={isPending}
                  />
                )}
                {!(
                  stagesData &&
                  Array.isArray(stagesData.stages) &&
                  stagesData.stages.length > 0
                ) && (
                  <Text fontSize="xs" color="secondary">
                    Path to the YAML file in your Snowflake stage (e.g.,
                    @my_stage/models/my_model.yaml)
                  </Text>
                )}
              </Flex>
            )}

            {/* Conditional: Select Semantic View for Views */}
            {type === SemanticModelType.VIEW && (
              <Flex direction="column" gap={8}>
                <Text fontSize="sm" fontWeight="semibold">
                  Select Semantic View *
                </Text>
                {isLoadingSemanticViews ? (
                  <Text fontSize="xs" color="secondary">
                    Loading semantic views from Snowflake...
                  </Text>
                ) : semanticViewsError ? (
                  <Flex
                    direction="column"
                    gap={8}
                    style={{
                      padding: '12px',
                      backgroundColor: '#f8d7da',
                      borderRadius: '8px',
                      border: '1px solid #f5c2c7',
                    }}
                  >
                    <Text fontSize="sm" color="dangerPrimary" fontWeight="semibold">
                      Failed to load semantic views
                    </Text>
                    <Text fontSize="xs" color="dangerPrimary">
                      {semanticViewsError.message}
                    </Text>
                  </Flex>
                ) : availableSemanticViews.length > 0 ? (
                  <>
                    <Select
                      value={selectedViewId}
                      onChange={handleSemanticViewSelect}
                      disabled={isPending}
                      placeholder="Select a semantic view to import"
                      options={availableSemanticViews.map((view) => {
                        const viewRecord = view as Record<string, unknown>;
                        const viewName = (view.name || viewRecord['NAME']) as string;
                        const viewDb = (view.database_name ||
                          viewRecord['DATABASE_NAME']) as string;
                        const viewSchema = (view.schema_name ||
                          viewRecord['SCHEMA_NAME']) as string;
                        const fullPath = `${viewDb}.${viewSchema}.${viewName}`;
                        return {
                          label: fullPath,
                          value: fullPath,
                        };
                      })}
                    />
                    <Text fontSize="xs" color="secondary">
                      Select an existing semantic view from Snowflake to track in Grapevine
                    </Text>
                  </>
                ) : (
                  <Flex
                    direction="column"
                    gap={8}
                    style={{
                      padding: '12px',
                      backgroundColor: '#fff3cd',
                      borderRadius: '8px',
                      border: '1px solid #ffc107',
                    }}
                  >
                    <Text fontSize="sm" fontWeight="semibold">
                      ⚠️ No Semantic Views Available
                    </Text>
                    <Text fontSize="xs" color="secondary">
                      No semantic views available to import. All existing views are already tracked,
                      or none exist in Snowflake.
                    </Text>
                    <Text fontSize="xs" color="secondary">
                      Create a semantic view in Snowflake first, then return here to import it.
                    </Text>
                  </Flex>
                )}
              </Flex>
            )}

            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="semibold">
                Description
              </Text>
              <Input
                placeholder="Optional description of this model"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={isPending}
              />
            </Flex>

            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="semibold">
                Warehouse *
              </Text>
              {isLoadingWarehouses ? (
                <Text fontSize="xs" color="secondary">
                  Loading warehouses...
                </Text>
              ) : warehousesError ? (
                <Flex direction="column" gap={4}>
                  <Input
                    placeholder="MY_WAREHOUSE"
                    value={warehouse}
                    onChange={(e) => setWarehouse(e.target.value)}
                    disabled={isPending}
                  />
                  <Text fontSize="xs" color="dangerPrimary">
                    Failed to load warehouses: {warehousesError.message}
                  </Text>
                </Flex>
              ) : warehousesData &&
                Array.isArray(warehousesData.warehouses) &&
                warehousesData.warehouses.length > 0 ? (
                <Select
                  value={warehouse}
                  onChange={(value) => setWarehouse(value)}
                  disabled={isPending}
                  placeholder="Select a warehouse"
                  options={warehousesData.warehouses
                    .filter((wh) => wh && (wh.name || (wh as Record<string, unknown>)['NAME']))
                    .map((wh) => {
                      const whRecord = wh as Record<string, unknown>;
                      const name = (wh.name || whRecord['NAME'] || 'Unknown') as string;
                      const size = (wh.size || whRecord['SIZE'] || '') as string;
                      const state = (wh.state || whRecord['STATE'] || '') as string;
                      const details = [size, state].filter(Boolean).join(', ');
                      return {
                        label: details ? `${name} (${details})` : name,
                        value: name,
                      };
                    })}
                />
              ) : (
                <Input
                  placeholder="MY_WAREHOUSE"
                  value={warehouse}
                  onChange={(e) => setWarehouse(e.target.value)}
                  disabled={isPending}
                />
              )}
              <Text fontSize="xs" color="secondary">
                Warehouse required for executing queries against this model
              </Text>
            </Flex>

            {error && (
              <Flex
                direction="column"
                gap={8}
                style={{
                  padding: '12px',
                  backgroundColor: '#f8d7da',
                  borderRadius: '8px',
                  border: '1px solid #f5c2c7',
                }}
              >
                <Text color="dangerPrimary" fontWeight="semibold">
                  Error: {error.message}
                </Text>
              </Flex>
            )}
          </Flex>
        </Modal.Body>
        <Modal.Footer>
          <Flex gap={8} style={{ justifyContent: 'flex-end' }}>
            <Button onClick={onClose} kind="secondary" size="sm" disabled={isPending}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              kind="primary"
              size="sm"
              loading={isPending}
              disabled={!canSubmit}
            >
              Add Model
            </Button>
          </Flex>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
};
