import { useState } from 'react';
import { Button, Flex, Text, Input, Select } from '@gathertown/gather-design-system';
import { type CustomFieldDefinition, type CustomFieldType } from '../../customDataApi';

const FIELD_TYPE_OPTIONS = [
  { label: 'Text', value: 'text' },
  { label: 'Date', value: 'date' },
  { label: 'Number', value: 'number' },
];

interface CustomFieldEditorProps {
  initialField?: CustomFieldDefinition;
  onSave: (field: CustomFieldDefinition) => void;
  onCancel: () => void;
  isEditing?: boolean;
}

export const CustomFieldEditor = ({
  initialField,
  onSave,
  onCancel,
  isEditing = false,
}: CustomFieldEditorProps) => {
  const [name, setName] = useState(initialField?.name || '');
  const [type, setType] = useState<CustomFieldType>(initialField?.type || 'text');
  const [description, setDescription] = useState(initialField?.description || '');
  const [required, setRequired] = useState(initialField?.required || false);

  const handleSave = () => {
    if (!name.trim()) return;

    const field: CustomFieldDefinition = {
      name: name.trim().toLowerCase().replace(/\s+/g, '_'),
      type,
      required,
      description: description.trim() || undefined,
    };

    onSave(field);
  };

  const canSave = name.trim().length > 0;

  return (
    <Flex
      direction="column"
      gap={16}
      style={{
        padding: '16px',
        backgroundColor: '#fafafa',
        border: '2px solid #6366f1',
        borderRadius: '6px',
      }}
    >
      <span style={{ fontSize: '14px', fontWeight: 600, color: '#6366f1' }}>
        {isEditing ? '✎ Editing Field' : '+ Adding New Field'}
      </span>

      {/* Name and Type row */}
      <Flex direction="row" gap={12}>
        <Flex direction="column" gap={4} style={{ flex: 1 }}>
          <Text fontSize="xs" fontWeight="semibold">
            Field Name <span style={{ color: '#dc3545' }}>*</span>
          </Text>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., severity"
          />
        </Flex>
        <Flex direction="column" gap={4} style={{ flex: 1 }}>
          <Text fontSize="xs" fontWeight="semibold">
            Type <span style={{ color: '#dc3545' }}>*</span>
          </Text>
          <Select
            value={type}
            onChange={(value) => setType(value as CustomFieldType)}
            options={FIELD_TYPE_OPTIONS}
          />
        </Flex>
      </Flex>

      {/* Description */}
      <Flex direction="column" gap={4}>
        <Text fontSize="xs" fontWeight="semibold">
          Description
        </Text>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe what this field represents..."
          style={{
            width: '100%',
            padding: '10px 12px',
            border: '1px solid #dee2e6',
            borderRadius: '6px',
            fontSize: '14px',
            fontFamily: 'inherit',
            resize: 'vertical',
            minHeight: '60px',
          }}
        />
        <Text fontSize="xs" color="secondary">
          This description helps the AI agent understand the field&apos;s purpose
        </Text>
      </Flex>

      {/* Required checkbox */}
      <Flex direction="row" gap={8} style={{ alignItems: 'center' }}>
        <input
          type="checkbox"
          id="field-required"
          checked={required}
          onChange={(e) => setRequired(e.target.checked)}
        />
        <label htmlFor="field-required" style={{ fontSize: '13px', cursor: 'pointer' }}>
          Required field
        </label>
      </Flex>

      {/* Actions */}
      <Flex
        direction="row"
        gap={8}
        style={{
          justifyContent: 'flex-end',
          paddingTop: '12px',
          borderTop: '1px solid #eee',
        }}
      >
        <Button onClick={onCancel} kind="secondary" size="sm">
          Cancel
        </Button>
        <Button onClick={handleSave} kind="primary" size="sm" disabled={!canSave}>
          {isEditing ? 'Save Field' : 'Add Field'}
        </Button>
      </Flex>
    </Flex>
  );
};
