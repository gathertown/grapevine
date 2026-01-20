import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Text, Button, Input } from '@gathertown/gather-design-system';
import { knowledgeBasesApi, type KnowledgeBase } from '../api/knowledge-bases';

export const KnowledgeBaseListPage = () => {
  const navigate = useNavigate();
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newKbName, setNewKbName] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);

  useEffect(() => {
    loadKnowledgeBases();
  }, []);

  const loadKnowledgeBases = async () => {
    try {
      setLoading(true);
      const response = await knowledgeBasesApi.list();
      setKnowledgeBases(response.knowledge_bases);
    } catch (error) {
      console.error('Failed to load knowledge bases:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newKbName.trim()) return;

    try {
      setCreating(true);
      const kb = await knowledgeBasesApi.create(newKbName, {
        context_gathering_prompt: '',
        template: [],
      });
      setNewKbName('');
      setShowCreateForm(false);
      navigate(`/knowledge-bases/${kb.id}/config`);
    } catch (error) {
      console.error('Failed to create knowledge base:', error);
    } finally {
      setCreating(false);
    }
  };

  if (loading) {
    return (
      <div style={{ width: '100%' }}>
        <Text>Loading knowledge bases...</Text>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', width: '100%' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          width: '100%',
        }}
      >
        <h1 style={{ fontSize: '32px', fontWeight: 'bold', margin: 0 }}>Knowledge Bases</h1>
        <Button onClick={() => setShowCreateForm(!showCreateForm)}>
          {showCreateForm ? 'Cancel' : 'Create New'}
        </Button>
      </div>

      {showCreateForm && (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', width: '100%' }}>
          <Input
            value={newKbName}
            onChange={(e) => setNewKbName(e.target.value)}
            placeholder="Knowledge base name"
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreate();
            }}
            style={{ flex: 1 }}
          />
          <Button onClick={handleCreate} disabled={creating || !newKbName.trim()}>
            {creating ? 'Creating...' : 'Create'}
          </Button>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
        {knowledgeBases.length === 0 ? (
          <Text>No knowledge bases yet. Create one to get started!</Text>
        ) : (
          knowledgeBases.map((kb) => (
            <div
              key={kb.id}
              style={{
                padding: '16px',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                cursor: 'pointer',
                width: '100%',
              }}
              onClick={() => navigate(`/knowledge-bases/${kb.id}`)}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 'bold', margin: 0 }}>{kb.name}</h3>
                <Text color="tertiary">Created {new Date(kb.created_at).toLocaleDateString()}</Text>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
