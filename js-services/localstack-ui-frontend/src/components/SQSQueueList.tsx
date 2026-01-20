import { useState, useEffect } from 'react';
import { sqsApi } from '../api/client';
import { SQSQueue, SQSMessage } from '../types';
import { SendMessageForm } from './SendMessageForm';

export function SQSQueueList() {
  const [queues, setQueues] = useState<SQSQueue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedQueues, setExpandedQueues] = useState<Set<string>>(new Set());
  const [queueMessages, setQueueMessages] = useState<Map<string, SQSMessage[]>>(new Map());
  const [messagesLoading, setMessagesLoading] = useState<Set<string>>(new Set());
  const [refreshing, setRefreshing] = useState<Set<string>>(new Set());
  const [showSendForm, setShowSendForm] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadQueues();
  }, []);

  const loadQueues = async () => {
    try {
      setLoading(true);
      setError(null);
      const queueList = await sqsApi.listQueues();
      setQueues(queueList);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load queues');
    } finally {
      setLoading(false);
    }
  };

  const refreshQueue = async (queueUrl: string) => {
    try {
      setRefreshing((prev) => new Set(prev).add(queueUrl));
      const updatedQueue = await sqsApi.getQueueAttributes(queueUrl);
      setQueues((prev) =>
        prev.map((queue) => (queue.queueUrl === queueUrl ? updatedQueue : queue))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh queue');
    } finally {
      setRefreshing((prev) => {
        const newSet = new Set(prev);
        newSet.delete(queueUrl);
        return newSet;
      });
    }
  };

  const toggleExpanded = async (queueUrl: string) => {
    const newExpanded = new Set(expandedQueues);

    if (expandedQueues.has(queueUrl)) {
      newExpanded.delete(queueUrl);
      // Clear messages when collapsing
      setQueueMessages((prev) => {
        const newMap = new Map(prev);
        newMap.delete(queueUrl);
        return newMap;
      });
    } else {
      newExpanded.add(queueUrl);
      await fetchQueueMessages(queueUrl);
    }

    setExpandedQueues(newExpanded);
  };

  const fetchQueueMessages = async (queueUrl: string) => {
    try {
      setMessagesLoading((prev) => new Set(prev).add(queueUrl));
      const messages = await sqsApi.getMessages(queueUrl, 10);
      setQueueMessages((prev) => new Map(prev).set(queueUrl, messages));
    } catch (err) {
      console.error('Failed to fetch messages:', err);
      setQueueMessages((prev) => new Map(prev).set(queueUrl, []));
    } finally {
      setMessagesLoading((prev) => {
        const newSet = new Set(prev);
        newSet.delete(queueUrl);
        return newSet;
      });
    }
  };

  const handlePurgeQueue = async (queueUrl: string, queueName: string) => {
    if (
      !confirm(
        `Are you sure you want to purge all messages from queue "${queueName}"? This action cannot be undone.`
      )
    ) {
      return;
    }

    try {
      await sqsApi.purgeQueue(queueUrl);
      await refreshQueue(queueUrl);
      // If expanded, refresh messages too
      if (expandedQueues.has(queueUrl)) {
        await fetchQueueMessages(queueUrl);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to purge queue');
    }
  };

  const handleDeleteMessage = async (
    queueUrl: string,
    receiptHandle: string,
    messageId: string
  ) => {
    if (!confirm(`Are you sure you want to delete message ${messageId}?`)) {
      return;
    }

    try {
      await sqsApi.deleteMessage(queueUrl, receiptHandle);
      await fetchQueueMessages(queueUrl);
      await refreshQueue(queueUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete message');
    }
  };

  const toggleSendForm = (queueUrl: string) => {
    setShowSendForm((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(queueUrl)) {
        newSet.delete(queueUrl);
      } else {
        newSet.add(queueUrl);
      }
      return newSet;
    });
  };

  const handleSendSuccess = async (queueUrl: string) => {
    setShowSendForm((prev) => {
      const newSet = new Set(prev);
      newSet.delete(queueUrl);
      return newSet;
    });
    await refreshQueue(queueUrl);
    if (expandedQueues.has(queueUrl)) {
      await fetchQueueMessages(queueUrl);
    }
  };

  const handleSendError = (errorMessage: string) => {
    setError(errorMessage);
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleString();
  };

  const formatMessageBody = (body: string, maxLength: number = 200) => {
    if (body.length <= maxLength) return body;
    return `${body.substring(0, maxLength)}...`;
  };

  if (loading) {
    return <div className="loading">Loading queues...</div>;
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
        <h2>SQS Queues</h2>
        <button className="btn-primary" onClick={loadQueues}>
          Refresh All
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="parameter-list">
        {queues.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#888' }}>
            No SQS queues found.
          </div>
        ) : (
          queues.map((queue) => {
            const isExpanded = expandedQueues.has(queue.queueUrl);
            const messages = queueMessages.get(queue.queueUrl) || [];
            const isMessagesLoading = messagesLoading.has(queue.queueUrl);
            const isRefreshing = refreshing.has(queue.queueUrl);
            const totalMessages =
              queue.attributes.approximateNumberOfMessages +
              queue.attributes.approximateNumberOfMessagesNotVisible +
              queue.attributes.approximateNumberOfMessagesDelayed;

            return (
              <div key={queue.queueUrl} className="parameter-item">
                <div
                  className={`parameter-row ${isExpanded ? 'expanded' : ''}`}
                  onClick={() => toggleExpanded(queue.queueUrl)}
                >
                  <div className="parameter-basic-info">
                    <div className="parameter-name">{queue.queueName}</div>
                    <div className="parameter-type">
                      {totalMessages} message{totalMessages !== 1 ? 's' : ''}
                    </div>
                    <div className="parameter-version">
                      {queue.attributes.approximateNumberOfMessages} visible
                    </div>
                    <div className="parameter-modified">
                      {formatDate(queue.attributes.lastModifiedTimestamp)}
                    </div>
                  </div>
                  <span className={`expand-icon ${isExpanded ? 'expanded' : ''}`}>▶</span>
                </div>

                {isExpanded && (
                  <div className="parameter-details">
                    <div style={{ marginBottom: '1rem' }}>
                      <div style={{ marginBottom: '0.5rem', fontSize: '0.9rem', color: '#888' }}>
                        <strong>Queue URL:</strong> {queue.queueUrl}
                      </div>
                      <div style={{ marginBottom: '0.5rem', fontSize: '0.9rem', color: '#888' }}>
                        <strong>ARN:</strong> {queue.attributes.queueArn}
                      </div>
                      <div style={{ marginBottom: '0.5rem', fontSize: '0.9rem', color: '#888' }}>
                        <strong>Created:</strong> {formatDate(queue.attributes.createdTimestamp)}
                      </div>
                      <div style={{ marginBottom: '0.5rem', fontSize: '0.9rem', color: '#888' }}>
                        <strong>Visibility Timeout:</strong> {queue.attributes.visibilityTimeout}s
                      </div>
                      <div style={{ marginBottom: '0.5rem', fontSize: '0.9rem', color: '#888' }}>
                        <strong>Message Retention:</strong>{' '}
                        {Math.floor(queue.attributes.messageRetentionPeriod / 86400)} days
                      </div>
                    </div>

                    <div style={{ marginBottom: '1rem' }}>
                      <div style={{ display: 'flex', gap: '1rem', marginBottom: '0.5rem' }}>
                        <div>
                          <strong>Visible:</strong> {queue.attributes.approximateNumberOfMessages}
                        </div>
                        <div>
                          <strong>In Flight:</strong>{' '}
                          {queue.attributes.approximateNumberOfMessagesNotVisible}
                        </div>
                        <div>
                          <strong>Delayed:</strong>{' '}
                          {queue.attributes.approximateNumberOfMessagesDelayed}
                        </div>
                      </div>
                    </div>

                    <div className="parameter-actions" style={{ marginBottom: '1rem' }}>
                      <button
                        className="btn-secondary"
                        onClick={(e) => {
                          e.stopPropagation();
                          refreshQueue(queue.queueUrl);
                        }}
                        disabled={isRefreshing}
                      >
                        {isRefreshing ? 'Refreshing...' : 'Refresh'}
                      </button>
                      <button
                        className="btn-secondary"
                        onClick={(e) => {
                          e.stopPropagation();
                          fetchQueueMessages(queue.queueUrl);
                        }}
                        disabled={isMessagesLoading}
                      >
                        {isMessagesLoading ? 'Loading Messages...' : 'Reload Messages'}
                      </button>
                      <button
                        className="btn-primary"
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleSendForm(queue.queueUrl);
                        }}
                      >
                        {showSendForm.has(queue.queueUrl) ? 'Cancel' : 'Send Message'}
                      </button>
                      <button
                        className="btn-danger"
                        onClick={(e) => {
                          e.stopPropagation();
                          handlePurgeQueue(queue.queueUrl, queue.queueName);
                        }}
                        disabled={totalMessages === 0}
                      >
                        Purge Queue
                      </button>
                    </div>

                    {showSendForm.has(queue.queueUrl) && (
                      <SendMessageForm
                        queueUrl={queue.queueUrl}
                        queueName={queue.queueName}
                        onSuccess={() => handleSendSuccess(queue.queueUrl)}
                        onError={handleSendError}
                      />
                    )}

                    {isMessagesLoading ? (
                      <div>Loading messages...</div>
                    ) : messages.length > 0 ? (
                      <div style={{ marginTop: '1rem' }}>
                        <h4>Messages (showing up to 10):</h4>
                        {messages.map((message) => (
                          <div
                            key={message.messageId}
                            style={{
                              border: '1px solid #ddd',
                              borderRadius: '4px',
                              padding: '1rem',
                              marginBottom: '0.5rem',
                              backgroundColor: '#f9f9f9',
                            }}
                          >
                            <div
                              style={{ marginBottom: '0.5rem', fontSize: '0.8rem', color: '#666' }}
                            >
                              <strong>ID:</strong> {message.messageId}
                            </div>
                            <div
                              style={{
                                marginBottom: '0.5rem',
                                fontFamily: 'monospace',
                                fontSize: '0.9rem',
                                color: '#333',
                              }}
                            >
                              {formatMessageBody(message.body)}
                            </div>
                            {message.body.length > 200 && (
                              <details style={{ marginBottom: '0.5rem' }}>
                                <summary style={{ cursor: 'pointer', color: '#007bff' }}>
                                  Show full message
                                </summary>
                                <div
                                  style={{
                                    fontFamily: 'monospace',
                                    fontSize: '0.8rem',
                                    marginTop: '0.5rem',
                                    whiteSpace: 'pre-wrap',
                                    backgroundColor: '#fff',
                                    padding: '0.5rem',
                                    border: '1px solid #eee',
                                  }}
                                >
                                  {message.body}
                                </div>
                              </details>
                            )}
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                              <button
                                className="btn-secondary"
                                style={{ fontSize: '0.8rem', padding: '0.25rem 0.5rem' }}
                                onClick={() => navigator.clipboard.writeText(message.body)}
                              >
                                Copy Body
                              </button>
                              <button
                                className="btn-danger"
                                style={{ fontSize: '0.8rem', padding: '0.25rem 0.5rem' }}
                                onClick={() =>
                                  handleDeleteMessage(
                                    queue.queueUrl,
                                    message.receiptHandle,
                                    message.messageId
                                  )
                                }
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ marginTop: '1rem', color: '#888', fontStyle: 'italic' }}>
                        No messages in queue
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
