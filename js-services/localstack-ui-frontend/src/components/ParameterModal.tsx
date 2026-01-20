import React, { useState, useEffect } from 'react';
import { ssmApi } from '../api/client';
import { SSMParameter, CreateParameterRequest, UpdateParameterRequest } from '../types';

interface ParameterModalProps {
  parameter?: SSMParameter;
  onClose: () => void;
  onSave: () => void;
}

export function ParameterModal({ parameter, onClose, onSave }: ParameterModalProps) {
  const [name, setName] = useState('');
  const [value, setValue] = useState('');
  const [type, setType] = useState<'String' | 'StringList' | 'SecureString'>('String');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!parameter;

  useEffect(() => {
    if (parameter) {
      setName(parameter.name);
      setValue(parameter.value);
      setType(parameter.type);
      setDescription(parameter.description || '');
    }
  }, [parameter]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!name.trim() || !value.trim()) {
      setError('Name and value are required');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      if (isEditing) {
        const updateRequest: UpdateParameterRequest = {
          value,
          description: description || undefined,
        };
        await ssmApi.updateParameter(name, updateRequest);
      } else {
        const createRequest: CreateParameterRequest = {
          name,
          value,
          type,
          description: description || undefined,
        };
        await ssmApi.createParameter(createRequest);
      }
      onSave();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save parameter');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal">
        <h2>{isEditing ? 'Edit Parameter' : 'Create Parameter'}</h2>

        {error && <div className="error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="name">Name</label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isEditing}
              placeholder="/path/to/parameter"
            />
          </div>

          {!isEditing && (
            <div className="form-group">
              <label htmlFor="type">Type</label>
              <select
                id="type"
                value={type}
                onChange={(e) =>
                  setType(e.target.value as 'String' | 'StringList' | 'SecureString')
                }
                style={{
                  width: '100%',
                  padding: '0.5em',
                  fontSize: '1em',
                  borderRadius: '4px',
                  border: '1px solid #ccc',
                  backgroundColor: '#1a1a1a',
                  color: 'inherit',
                }}
              >
                <option value="String">String</option>
                <option value="StringList">StringList</option>
                <option value="SecureString">SecureString</option>
              </select>
            </div>
          )}

          <div className="form-group">
            <label htmlFor="value">Value</label>
            <textarea
              id="value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Parameter value"
            />
          </div>

          <div className="form-group">
            <label htmlFor="description">Description (optional)</label>
            <input
              id="description"
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Parameter description"
            />
          </div>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Saving...' : 'Save'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
