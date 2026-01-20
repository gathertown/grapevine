import { useState } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { useSemanticModels, SemanticModelState, type SemanticModel } from '../../snowflakeApi';
import { SnowflakeConfig } from '../../snowflakeConfig';
import { SemanticModelCard } from './SemanticModelCard';
import { CreateSemanticModelModal } from './CreateModal';
import { EditSemanticModelModal } from './EditModal';
import { DeleteSemanticModelModal } from './DeleteModal';

interface SemanticModelsStepProps {
  config: SnowflakeConfig;
}

export const SemanticModelsStep = ({ config }: SemanticModelsStepProps) => {
  const isConnected = !!config.SNOWFLAKE_OAUTH_TOKEN_PAYLOAD;
  const { data, isLoading, error, refetch } = useSemanticModels();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<SemanticModel | null>(null);
  const [deletingModel, setDeletingModel] = useState<SemanticModel | null>(null);

  if (!isConnected) {
    return (
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
          ⚠️ Connect Snowflake First
        </Text>
        <Text fontSize="sm" color="secondary">
          Please connect your Snowflake account before managing semantic models.
        </Text>
      </Flex>
    );
  }

  if (isLoading) {
    return (
      <Flex direction="column" gap={8}>
        <Text fontSize="sm">Loading semantic models...</Text>
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex direction="column" gap={8}>
        <Text color="dangerPrimary" fontWeight="semibold">
          Error loading semantic models: {error.message}
        </Text>
      </Flex>
    );
  }

  const models = (data?.semanticModels || []).filter(
    (model) => model.state !== SemanticModelState.DELETED
  );

  return (
    <Flex direction="column" gap={16} style={{ width: '100%' }}>
      <Flex direction="column" gap={8}>
        <Text fontSize="md" fontWeight="semibold">
          Semantic Models
        </Text>
        <Text fontSize="sm" color="secondary">
          Manage YAML semantic models for Snowflake Cortex Analyst. These models define your
          business logic and data relationships for natural language queries.
        </Text>
      </Flex>

      <Flex
        direction="row"
        gap={8}
        style={{ alignItems: 'center', justifyContent: 'space-between' }}
      >
        <Text fontSize="sm" color="secondary">
          {models.length} {models.length === 1 ? 'model' : 'models'} configured
        </Text>
        <Button onClick={() => setIsCreateModalOpen(true)} kind="primary" size="sm">
          Add Semantic Model
        </Button>
      </Flex>

      {models.length === 0 ? (
        <Flex
          direction="column"
          gap={8}
          style={{
            padding: '24px',
            backgroundColor: '#f8f9fa',
            borderRadius: '8px',
            border: '1px dashed #dee2e6',
            textAlign: 'center',
          }}
        >
          <Text fontSize="sm" color="secondary">
            No semantic models configured yet.
          </Text>
          <Text fontSize="sm" color="secondary">
            Add your first semantic model to start querying with natural language.
          </Text>
        </Flex>
      ) : (
        <Flex direction="column" gap={12}>
          {models.map((model) => (
            <SemanticModelCard
              key={model.id}
              model={model}
              onEdit={() => setEditingModel(model)}
              onDelete={() => setDeletingModel(model)}
            />
          ))}
        </Flex>
      )}

      {isCreateModalOpen && (
        <CreateSemanticModelModal
          onClose={() => setIsCreateModalOpen(false)}
          onSuccess={() => {
            setIsCreateModalOpen(false);
            refetch();
          }}
        />
      )}

      {editingModel && (
        <EditSemanticModelModal
          model={editingModel}
          onClose={() => setEditingModel(null)}
          onSuccess={() => {
            setEditingModel(null);
            refetch();
          }}
        />
      )}

      {deletingModel && (
        <DeleteSemanticModelModal
          model={deletingModel}
          onClose={() => setDeletingModel(null)}
          onSuccess={() => {
            setDeletingModel(null);
            refetch();
          }}
        />
      )}
    </Flex>
  );
};
