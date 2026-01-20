import React, { useState } from 'react';
import { sqsApi } from '../api/client';

interface MessageAttribute {
  key: string;
  value: string;
  dataType: string;
}

interface SendMessageFormProps {
  queueUrl: string;
  queueName: string;
  onSuccess: () => void;
  onError: (error: string) => void;
}

export function SendMessageForm({ queueUrl, queueName, onSuccess, onError }: SendMessageFormProps) {
  const [messageBody, setMessageBody] = useState('');
  const [messageGroupId, setMessageGroupId] = useState('');
  const [messageDeduplicationId, setMessageDeduplicationId] = useState('');
  const [messageAttributes, setMessageAttributes] = useState<MessageAttribute[]>([
    { key: '', value: '', dataType: 'String' },
  ]);
  const [sending, setSending] = useState(false);

  const isFifoQueue = queueName.endsWith('.fifo');

  const handleAddAttribute = () => {
    setMessageAttributes([...messageAttributes, { key: '', value: '', dataType: 'String' }]);
  };

  const handleRemoveAttribute = (index: number) => {
    if (messageAttributes.length > 1) {
      setMessageAttributes(messageAttributes.filter((_, i) => i !== index));
    }
  };

  const handleAttributeChange = (index: number, field: keyof MessageAttribute, value: string) => {
    const updated = messageAttributes.map((attr, i) =>
      i === index ? { ...attr, [field]: value } : attr
    );
    setMessageAttributes(updated);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!messageBody.trim()) {
      onError('Message body is required');
      return;
    }

    if (isFifoQueue && !messageGroupId.trim()) {
      onError('Message Group ID is required for FIFO queues');
      return;
    }

    setSending(true);

    try {
      // Build message attributes, filtering out empty ones
      const attrs: Record<
        string,
        { StringValue?: string; BinaryValue?: string; DataType: string }
      > = {};
      messageAttributes.forEach((attr) => {
        if (attr.key.trim() && attr.value.trim()) {
          attrs[attr.key] = {
            StringValue: attr.value,
            DataType: attr.dataType,
          };
        }
      });

      await sqsApi.sendMessage(
        queueUrl,
        messageBody,
        Object.keys(attrs).length > 0 ? attrs : undefined,
        isFifoQueue ? messageGroupId : undefined,
        isFifoQueue && messageDeduplicationId ? messageDeduplicationId : undefined
      );

      // Reset form
      setMessageBody('');
      setMessageGroupId('');
      setMessageDeduplicationId('');
      setMessageAttributes([{ key: '', value: '', dataType: 'String' }]);

      onSuccess();
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to send message');
    } finally {
      setSending(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: '1rem' }}>
      <h4 style={{ marginBottom: '1rem' }}>Send Message to {queueName}</h4>

      <div style={{ marginBottom: '1rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
          Message Body *
        </label>
        <textarea
          value={messageBody}
          onChange={(e) => setMessageBody(e.target.value)}
          placeholder="Enter your message content here..."
          rows={4}
          style={{
            width: '100%',
            padding: '0.5rem',
            border: '1px solid #ddd',
            borderRadius: '4px',
            fontFamily: 'monospace',
            fontSize: '0.9rem',
          }}
          required
        />
      </div>

      {isFifoQueue && (
        <>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
              Message Group ID * (FIFO Queue)
            </label>
            <input
              type="text"
              value={messageGroupId}
              onChange={(e) => setMessageGroupId(e.target.value)}
              placeholder="Enter message group ID"
              style={{
                width: '100%',
                padding: '0.5rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
              }}
              required
            />
          </div>
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
              Message Deduplication ID
            </label>
            <input
              type="text"
              value={messageDeduplicationId}
              onChange={(e) => setMessageDeduplicationId(e.target.value)}
              placeholder="Enter deduplication ID (optional if content-based deduplication enabled)"
              style={{
                width: '100%',
                padding: '0.5rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
              }}
            />
          </div>
        </>
      )}

      <div style={{ marginBottom: '1rem' }}>
        <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 'bold' }}>
          Message Attributes (Optional)
        </label>
        {messageAttributes.map((attr, index) => (
          <div key={index} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <input
              type="text"
              value={attr.key}
              onChange={(e) => handleAttributeChange(index, 'key', e.target.value)}
              placeholder="Attribute name"
              style={{
                flex: '1',
                padding: '0.25rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
              }}
            />
            <input
              type="text"
              value={attr.value}
              onChange={(e) => handleAttributeChange(index, 'value', e.target.value)}
              placeholder="Attribute value"
              style={{
                flex: '2',
                padding: '0.25rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
              }}
            />
            <select
              value={attr.dataType}
              onChange={(e) => handleAttributeChange(index, 'dataType', e.target.value)}
              style={{
                padding: '0.25rem',
                border: '1px solid #ddd',
                borderRadius: '4px',
              }}
            >
              <option value="String">String</option>
              <option value="Number">Number</option>
              <option value="Binary">Binary</option>
            </select>
            {messageAttributes.length > 1 && (
              <button
                type="button"
                onClick={() => handleRemoveAttribute(index)}
                className="btn-secondary"
                style={{ padding: '0.25rem 0.5rem', fontSize: '0.8rem' }}
              >
                Remove
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          onClick={handleAddAttribute}
          className="btn-secondary"
          style={{ fontSize: '0.8rem', padding: '0.25rem 0.5rem' }}
        >
          Add Attribute
        </button>
      </div>

      <div style={{ display: 'flex', gap: '1rem' }}>
        <button
          type="submit"
          className="btn-primary"
          disabled={sending || !messageBody.trim() || (isFifoQueue && !messageGroupId.trim())}
        >
          {sending ? 'Sending...' : 'Send Message'}
        </button>
      </div>
    </form>
  );
}
