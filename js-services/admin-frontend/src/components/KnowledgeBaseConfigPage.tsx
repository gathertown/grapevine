import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Text, Button, Input, TextArea } from '@gathertown/gather-design-system';
import { knowledgeBasesApi, type KnowledgeBase, type TemplateField } from '../api/knowledge-bases';

export const KnowledgeBaseConfigPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [contextPrompt, setContextPrompt] = useState('');
  const [template, setTemplate] = useState<TemplateField[]>([]);

  const loadData = useCallback(async () => {
    if (!id) return;

    try {
      setLoading(true);
      const kbData = await knowledgeBasesApi.get(id);
      setKb(kbData);
      setContextPrompt(kbData.config.context_gathering_prompt || '');
      setTemplate(kbData.config.template || []);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    if (id) {
      loadData();
    }
  }, [id, loadData]);

  const handleSave = async () => {
    if (!id) return;

    try {
      setSaving(true);
      await knowledgeBasesApi.update(id, {
        config: {
          context_gathering_prompt: contextPrompt,
          template,
        },
      });
      navigate(`/knowledge-bases/${id}`);
    } catch (error) {
      console.error('Failed to save config:', error);
    } finally {
      setSaving(false);
    }
  };

  const addField = () => {
    setTemplate([...template, { field_name: '', field_prompt: '' }]);
  };

  const updateField = (index: number, updates: Partial<TemplateField>) => {
    const newTemplate = [...template];
    const currentField = newTemplate[index];
    if (!currentField) return;

    const updatedField: TemplateField = {
      field_name: updates.field_name ?? currentField.field_name,
      field_prompt: updates.field_prompt ?? currentField.field_prompt,
    };
    newTemplate[index] = updatedField;
    setTemplate(newTemplate);
  };

  const removeField = (index: number) => {
    setTemplate(template.filter((_, i) => i !== index));
  };

  if (loading || !kb) {
    return (
      <div style={{ width: '100%' }}>
        <Text>Loading...</Text>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', width: '100%' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          width: '100%',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <Button kind="transparent" onClick={() => navigate(`/knowledge-bases/${id}`)}>
            ← Back to {kb.name}
          </Button>
          <h1 style={{ fontSize: '32px', fontWeight: 'bold', margin: 0 }}>Configuration</h1>
        </div>
        <Button onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </Button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 'bold', margin: 0 }}>
          Context Gathering Prompt
        </h2>
        <Text color="tertiary">
          This prompt will be used to gather context about each article before generating fields
        </Text>
        <TextArea
          value={contextPrompt}
          onChange={(e) => setContextPrompt(e.target.value)}
          placeholder="e.g., Search for and summarize all relevant information about this topic..."
          rows={4}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', width: '100%' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            width: '100%',
          }}
        >
          <h2 style={{ fontSize: '20px', fontWeight: 'bold', margin: 0 }}>Template Fields</h2>
          <Button onClick={addField}>Add Field</Button>
        </div>

        {template.length === 0 ? (
          <Text>No fields defined yet. Add fields to structure your articles.</Text>
        ) : (
          template.map((field, index) => (
            <div
              key={index}
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                padding: '16px',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                width: '100%',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  width: '100%',
                }}
              >
                <h3 style={{ fontSize: '16px', fontWeight: 'bold', margin: 0 }}>
                  Field {index + 1}
                </h3>
                <Button size="sm" kind="transparent" onClick={() => removeField(index)}>
                  Remove
                </Button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', width: '100%' }}>
                <span style={{ fontSize: '14px', fontWeight: 'bold' }}>Field Name</span>
                <Input
                  value={field.field_name}
                  onChange={(e) => updateField(index, { field_name: e.target.value })}
                  placeholder="e.g., summary, key_points, examples"
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', width: '100%' }}>
                <span style={{ fontSize: '14px', fontWeight: 'bold' }}>Field Prompt</span>
                <TextArea
                  value={field.field_prompt}
                  onChange={(e) => updateField(index, { field_prompt: e.target.value })}
                  placeholder="e.g., Generate a concise summary of this topic..."
                  rows={3}
                />
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
