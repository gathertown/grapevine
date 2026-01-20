import { useState, useEffect } from 'react';
import { ssmApi } from '../api/client';
import { SSMParameter } from '../types';
import { ParameterModal } from './ParameterModal';

export function SSMParameterList() {
  const [parameters, setParameters] = useState<SSMParameter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedParameter, setSelectedParameter] = useState<SSMParameter | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [expandedParams, setExpandedParams] = useState<Set<string>>(new Set());
  const [parameterValues, setParameterValues] = useState<
    Map<string, { value: string; loading: boolean }>
  >(new Map());

  useEffect(() => {
    loadParameters();
  }, []);

  const loadParameters = async () => {
    try {
      setLoading(true);
      setError(null);
      const params = await ssmApi.listParameters();
      setParameters(params);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load parameters');
    } finally {
      setLoading(false);
    }
  };

  const toggleExpanded = async (parameterName: string) => {
    const newExpanded = new Set(expandedParams);

    if (expandedParams.has(parameterName)) {
      newExpanded.delete(parameterName);
    } else {
      newExpanded.add(parameterName);
      // Fetch the parameter value if we don't have it yet
      if (!parameterValues.has(parameterName)) {
        await fetchParameterValue(parameterName);
      }
    }

    setExpandedParams(newExpanded);
  };

  const fetchParameterValue = async (parameterName: string) => {
    try {
      // Set loading state
      const newValues = new Map(parameterValues);
      newValues.set(parameterName, { value: '', loading: true });
      setParameterValues(newValues);

      // Fetch the parameter with its value
      const parameter = await ssmApi.getParameter(parameterName);

      // Update with actual value
      newValues.set(parameterName, { value: parameter.value, loading: false });
      setParameterValues(newValues);
    } catch (err) {
      console.error('Failed to fetch parameter value:', err);
      const newValues = new Map(parameterValues);
      newValues.set(parameterName, { value: 'Failed to load', loading: false });
      setParameterValues(newValues);
    }
  };

  const handleEdit = (parameter: SSMParameter) => {
    setSelectedParameter(parameter);
  };

  const handleDelete = async (parameterName: string) => {
    if (!confirm(`Are you sure you want to delete parameter "${parameterName}"?`)) {
      return;
    }

    try {
      await ssmApi.deleteParameter(parameterName);
      await loadParameters();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete parameter');
    }
  };

  const handleSave = async () => {
    await loadParameters();
    setSelectedParameter(null);
    setShowCreateModal(false);
    // Clear cached values so they get refetched
    setParameterValues(new Map());
  };

  const filteredParameters = parameters.filter((param) =>
    param.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (loading) {
    return <div className="loading">Loading parameters...</div>;
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1rem',
        }}
      >
        <h2>SSM Parameters</h2>
        <button className="btn-primary" onClick={() => setShowCreateModal(true)}>
          Create Parameter
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      <input
        type="text"
        className="search-bar"
        placeholder="Search parameters..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
      />

      <div className="parameter-list">
        {filteredParameters.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#888' }}>
            {searchQuery ? 'No parameters match your search.' : 'No parameters found.'}
          </div>
        ) : (
          filteredParameters.map((param) => {
            const isExpanded = expandedParams.has(param.name);
            const valueData = parameterValues.get(param.name);

            return (
              <div key={param.name} className="parameter-item">
                <div
                  className={`parameter-row ${isExpanded ? 'expanded' : ''}`}
                  onClick={() => toggleExpanded(param.name)}
                >
                  <div className="parameter-basic-info">
                    <div className="parameter-name">{param.name}</div>
                    <div className="parameter-type">{param.type}</div>
                    <div className="parameter-version">v{param.version}</div>
                    <div className="parameter-modified">
                      {new Date(param.lastModifiedDate).toLocaleDateString()}
                    </div>
                  </div>
                  <span className={`expand-icon ${isExpanded ? 'expanded' : ''}`}>▶</span>
                </div>

                {isExpanded && (
                  <div className="parameter-details">
                    {param.description && (
                      <div className="parameter-description">{param.description}</div>
                    )}

                    <div
                      className={`parameter-value ${valueData?.loading ? 'loading' : ''} ${param.type === 'SecureString' ? 'encrypted' : ''}`}
                    >
                      {valueData?.loading ? (
                        'Loading value...'
                      ) : valueData?.value ? (
                        param.type === 'SecureString' ? (
                          <div>
                            <div
                              style={{
                                marginBottom: '0.5rem',
                                color: '#ff6b6b',
                                fontSize: '0.9rem',
                              }}
                            >
                              🔒 Decrypted SecureString:
                            </div>
                            {valueData.value}
                          </div>
                        ) : (
                          valueData.value
                        )
                      ) : (
                        'Click to expand and view value'
                      )}
                    </div>

                    <div style={{ marginBottom: '1rem', color: '#888', fontSize: '0.9rem' }}>
                      <strong>Last Modified:</strong>{' '}
                      {new Date(param.lastModifiedDate).toLocaleString()}
                      {param.keyId && (
                        <>
                          <br />
                          <strong>KMS Key:</strong> {param.keyId}
                        </>
                      )}
                    </div>

                    <div className="parameter-actions">
                      <button
                        className="btn-secondary"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEdit(param);
                        }}
                      >
                        Edit
                      </button>
                      <button
                        className="btn-danger"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(param.name);
                        }}
                      >
                        Delete
                      </button>
                      {valueData && !valueData.loading && (
                        <button
                          className="btn-secondary"
                          onClick={(e) => {
                            e.stopPropagation();
                            navigator.clipboard.writeText(valueData.value);
                          }}
                        >
                          Copy Value
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {selectedParameter && (
        <ParameterModal
          parameter={selectedParameter}
          onClose={() => setSelectedParameter(null)}
          onSave={handleSave}
        />
      )}

      {showCreateModal && (
        <ParameterModal onClose={() => setShowCreateModal(false)} onSave={handleSave} />
      )}
    </div>
  );
}
