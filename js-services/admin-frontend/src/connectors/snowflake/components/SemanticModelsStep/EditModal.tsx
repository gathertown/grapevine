import { useState } from 'react';
import { Button, Flex, Text, Input, Modal, Select } from '@gathertown/gather-design-system';
import {
  useUpdateSemanticModel,
  useSnowflakeWarehouses,
  SemanticModelState,
  type SemanticModel,
  type UpdateSemanticModelParams,
} from '../../snowflakeApi';

interface EditSemanticModelModalProps {
  model: SemanticModel;
  onClose: () => void;
  onSuccess: () => void;
}

export const EditSemanticModelModal = ({
  model,
  onClose,
  onSuccess,
}: EditSemanticModelModalProps) => {
  const [name, setName] = useState(model.name);
  const [description, setDescription] = useState(model.description || '');
  const [warehouse, setWarehouse] = useState(model.warehouse || '');
  const [enabled, setEnabled] = useState(model.state === SemanticModelState.ENABLED);
  const { mutate: updateModel, isPending, error } = useUpdateSemanticModel();
  const {
    data: warehousesData,
    isLoading: isLoadingWarehouses,
    error: warehousesError,
  } = useSnowflakeWarehouses();

  const canSubmit = name.trim().length > 0 && !isPending;

  const handleSubmit = () => {
    const params: UpdateSemanticModelParams = {};
    let hasChanges = false;

    if (name.trim() !== model.name) {
      params.name = name.trim();
      hasChanges = true;
    }

    if (description.trim() !== (model.description || '')) {
      params.description = description.trim() || null;
      hasChanges = true;
    }

    if (warehouse.trim() !== (model.warehouse || '')) {
      params.warehouse = warehouse.trim() || null;
      hasChanges = true;
    }

    // Only update state if the enabled checkbox actually changed
    const originalEnabled = model.state === SemanticModelState.ENABLED;
    if (enabled !== originalEnabled) {
      params.state = enabled ? SemanticModelState.ENABLED : SemanticModelState.DISABLED;
      hasChanges = true;
    }

    if (!hasChanges) {
      onClose();
      return;
    }

    updateModel(
      { id: model.id, params },
      {
        onSuccess: () => {
          onSuccess();
        },
      }
    );
  };

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content variant="default" showOverlay style={{ maxWidth: 600 }}>
        <Modal.Header title={`Edit Semantic ${model.type === 'model' ? 'Model' : 'View'}`} />
        <Modal.Body style={{ padding: 16, gap: 16 }}>
          <Flex direction="column" gap={16}>
            {/* Type Display (Read-only) */}
            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="semibold">
                Type
              </Text>
              <Input
                value={
                  model.type === 'model'
                    ? 'Semantic Model (YAML file in stage)'
                    : 'Semantic View (database object)'
                }
                disabled
              />
              <Text fontSize="xs" color="secondary">
                Type cannot be changed after creation
              </Text>
            </Flex>

            <Flex direction="column" gap={8}>
              <Text fontSize="sm" fontWeight="semibold">
                Name *
              </Text>
              <Input
                placeholder={model.type === 'model' ? 'My Semantic Model' : 'My Semantic View'}
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isPending}
              />
            </Flex>

            {/* Conditional: Stage Path for Models */}
            {model.type === 'model' && (
              <Flex direction="column" gap={8}>
                <Text fontSize="sm" fontWeight="semibold">
                  Stage Path (Read-only)
                </Text>
                <Input value={model.stage_path || ''} disabled />
                <Text fontSize="xs" color="secondary">
                  Stage path cannot be changed after creation
                </Text>
              </Flex>
            )}

            {/* Conditional: Database and Schema for Views */}
            {model.type === 'view' && (
              <>
                <Flex direction="column" gap={8}>
                  <Text fontSize="sm" fontWeight="semibold">
                    Database (Read-only)
                  </Text>
                  <Input value={model.database_name || ''} disabled />
                  <Text fontSize="xs" color="secondary">
                    Database cannot be changed after creation
                  </Text>
                </Flex>
                <Flex direction="column" gap={8}>
                  <Text fontSize="sm" fontWeight="semibold">
                    Schema (Read-only)
                  </Text>
                  <Input value={model.schema_name || ''} disabled />
                  <Text fontSize="xs" color="secondary">
                    Schema cannot be changed after creation
                  </Text>
                </Flex>
              </>
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
                Warehouse
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
                  placeholder="Select a warehouse (optional)"
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
                Optional: Specify a warehouse to use for queries with this model
              </Text>
            </Flex>

            <Flex direction="row" gap={8} style={{ alignItems: 'center' }}>
              <input
                type="checkbox"
                id="enabled-checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                disabled={isPending}
              />
              <label htmlFor="enabled-checkbox">
                <Text fontSize="sm">Enabled</Text>
              </label>
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
              Save Changes
            </Button>
          </Flex>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
};
