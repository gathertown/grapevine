import { useState, useRef, useEffect } from 'react';
import { Button, Flex, Text } from '@gathertown/gather-design-system';
import { type CustomFieldDefinition } from '../../customDataApi';
import { CustomFieldItem } from './CustomFieldItem';
import { CustomFieldEditor } from './CustomFieldEditor';

interface CustomFieldsListProps {
  fields: CustomFieldDefinition[];
  onChange: (fields: CustomFieldDefinition[]) => void;
  showHeader?: boolean;
}

export const CustomFieldsList = ({
  fields,
  onChange,
  showHeader = true,
}: CustomFieldsListProps) => {
  const [isAddingField, setIsAddingField] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const editorRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to editor when it appears
  useEffect(() => {
    if (isAddingField && editorRef.current) {
      editorRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [isAddingField]);

  const handleAddField = (field: CustomFieldDefinition) => {
    onChange([...fields, field]);
    setIsAddingField(false);
  };

  const handleEditField = (index: number, field: CustomFieldDefinition) => {
    const newFields = [...fields];
    newFields[index] = field;
    onChange(newFields);
    setEditingIndex(null);
  };

  const handleDeleteField = (index: number) => {
    onChange(fields.filter((_, i) => i !== index));
  };

  return (
    <Flex direction="column" gap={12}>
      {showHeader && (
        <Flex direction="column" gap={4}>
          <Flex direction="row" gap={8} style={{ alignItems: 'center' }}>
            <Text fontSize="sm" fontWeight="semibold">
              Custom Fields
            </Text>
            <Flex
              style={{
                padding: '2px 8px',
                backgroundColor: '#e3f2fd',
                border: '1px solid #2196f3',
                borderRadius: '4px',
              }}
            >
              <span style={{ fontSize: '11px', color: '#1976d2' }}>Optional</span>
            </Flex>
          </Flex>
          <Text fontSize="xs" color="secondary">
            Add fields to provide semantic context for the AI agent
          </Text>
        </Flex>
      )}

      {/* Fields list */}
      {fields.length > 0 && (
        <Flex
          direction="column"
          style={{
            border: '1px solid #dee2e6',
            borderRadius: '6px',
            overflow: 'hidden',
          }}
        >
          {fields.map((field, index) =>
            editingIndex === index ? (
              <Flex key={index} style={{ padding: '12px', backgroundColor: '#f8f9fa' }}>
                <CustomFieldEditor
                  initialField={field}
                  onSave={(updatedField) => handleEditField(index, updatedField)}
                  onCancel={() => setEditingIndex(null)}
                  isEditing
                />
              </Flex>
            ) : (
              <CustomFieldItem
                key={index}
                field={field}
                onEdit={() => setEditingIndex(index)}
                onDelete={() => handleDeleteField(index)}
              />
            )
          )}
        </Flex>
      )}

      {/* Add field button or editor */}
      {isAddingField ? (
        <div ref={editorRef}>
          <CustomFieldEditor onSave={handleAddField} onCancel={() => setIsAddingField(false)} />
        </div>
      ) : (
        <Button
          onClick={() => setIsAddingField(true)}
          kind="secondary"
          size="sm"
          style={{
            width: '100%',
            padding: '12px',
            backgroundColor: '#f8f9fa',
            border: '1px dashed #dee2e6',
            color: '#666',
          }}
        >
          + Add Custom Field
        </Button>
      )}
    </Flex>
  );
};
