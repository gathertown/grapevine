import { memo, useState, useRef, useEffect } from 'react';
import type { FC, FormEvent, ChangeEvent } from 'react';
import { Flex, Text, Button, Modal, Box } from '@gathertown/gather-design-system';
import { MarkdownRenderer } from './shared/MarkdownRenderer';
import { useAuth } from '../hooks/useAuth';
import { getConfig } from '../lib/config';

interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: Date;
}

interface StreamEvent {
  type: string;
  data?: unknown;
}

interface EventLog {
  id: string;
  type: string;
  summary: string;
  data?: unknown;
  timestamp: Date;
}

const AgentChatPage: FC = memo(() => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [responseId, setResponseId] = useState<string | null>(null);
  const [events, setEvents] = useState<EventLog[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventLog | null>(null);
  const [showEventsPanel, setShowEventsPanel] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { getAccessToken } = useAuth();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const createEventSummary = (event: StreamEvent): string => {
    const { type, data } = event;

    switch (type) {
      case 'status':
        return typeof data === 'string' ? data : 'Status update';
      case 'tool_call':
        if (typeof data === 'object' && data !== null) {
          const toolData = data as { tool_name?: string; status?: string };
          return `🔧 ${toolData.tool_name || 'Tool'} - ${toolData.status || 'running'}`;
        }
        return '🔧 Tool call';
      case 'tool_result':
        if (typeof data === 'object' && data !== null) {
          const resultData = data as { summary?: string };
          return `✅ ${resultData.summary || 'Tool completed'}`;
        }
        return '✅ Tool result';
      case 'final_answer':
        return '🎯 Answer ready';
      case 'message':
        if (typeof data === 'object' && data !== null) {
          const msgData = data as { role?: string };
          return `💬 ${msgData.role || 'message'}`;
        }
        return '💬 Message';
      case 'trace_info':
        return '📊 Trace info';
      default:
        return `${type}`;
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setEvents([]); // Clear events for new request

    try {
      const workosToken = await getAccessToken();
      if (!workosToken) {
        throw new Error('No authentication token available');
      }

      // Get internal JWT for MCP authentication
      const jwtResponse = await fetch('/api/mcp/jwt', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${workosToken}`,
        },
      });

      if (!jwtResponse.ok) {
        throw new Error('Failed to get agent authentication token');
      }

      const { token: mcpToken } = await jwtResponse.json();

      const config = getConfig();
      const mcpBaseUrl = config.MCP_BASE_URL || 'http://localhost:8000';
      const url = `${mcpBaseUrl}/v1/ask/stream`;

      console.log('Sending request with previous_response_id:', responseId);

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${mcpToken}`,
        },
        body: JSON.stringify({
          query: inputValue,
          previous_response_id: responseId,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentAnswer = '';
      const agentMessageId = `agent-${Date.now()}`;

      setMessages((prev) => [
        ...prev,
        {
          id: agentMessageId,
          role: 'agent',
          content: '',
          timestamp: new Date(),
        },
      ]);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim() || !line.startsWith('data: ')) continue;

          const data = line.slice(6);
          if (data === '[DONE]') continue;

          try {
            const event: StreamEvent = JSON.parse(data);

            // Add event to the log
            const eventLog: EventLog = {
              id: `event-${Date.now()}-${Math.random()}`,
              type: event.type,
              summary: createEventSummary(event),
              data: event.data,
              timestamp: new Date(),
            };
            setEvents((prev) => [...prev, eventLog]);

            // Handle different event types from stream_advanced_search_answer
            if (event.type === 'final_answer' && event.data && typeof event.data === 'object') {
              // Extract answer and response_id from final_answer event
              const eventData = event.data as { answer?: string; response_id?: string };
              const answer = eventData.answer || '';
              const newResponseId = eventData.response_id;

              currentAnswer = answer;
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === agentMessageId ? { ...msg, content: currentAnswer } : msg
                )
              );

              // Store response_id for next message
              if (newResponseId) {
                console.log('Received new response_id:', newResponseId);
                setResponseId(newResponseId);
              } else {
                console.warn('No response_id in final_answer event');
              }
            }
          } catch (err) {
            console.error('Error parsing SSE event:', err);
          }
        }
      }
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage: Message = {
        id: `agent-error-${Date.now()}`,
        role: 'agent',
        content: `Error: ${error instanceof Error ? error.message : 'Unknown error occurred'}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
  };

  const handleClearConversation = () => {
    setMessages([]);
    setResponseId(null);
    setEvents([]);
  };

  const handleEventClick = (event: EventLog) => {
    setSelectedEvent(event);
  };

  const handleCloseModal = () => {
    setSelectedEvent(null);
  };

  return (
    <Flex
      direction="column"
      width="100%"
      gap={16}
      style={{
        height: 'calc(100vh - 120px)',
        maxHeight: 'calc(100vh - 120px)',
      }}
    >
      <Flex
        direction="row"
        gap={16}
        style={{
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        {/* Messages and input column */}
        <Flex
          direction="column"
          style={{
            flex: 1,
            minHeight: 0,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Messages panel */}
          <Flex
            direction="column"
            gap={12}
            px={12}
            py={8}
            borderWidth={1}
            borderStyle="solid"
            borderColor="secondary"
            borderRadius={8}
            backgroundColor="secondary"
            style={{
              flex: 1,
              overflow: 'auto',
            }}
          >
            {messages.length === 0 ? (
              <Flex align="center" justify="center" style={{ height: '100%' }}>
                <Text color="tertiary">Start a conversation with the agent</Text>
              </Flex>
            ) : (
              messages.map((message) => (
                <Flex
                  key={message.id}
                  direction="column"
                  gap={4}
                  py={6}
                  style={{
                    borderRadius: '8px',
                    backgroundColor:
                      message.role === 'user'
                        ? 'var(--color-background-tertiary)'
                        : 'var(--color-background-primary)',
                    alignSelf: message.role === 'user' ? 'flex-end' : 'flex-start',
                    maxWidth: '80%',
                  }}
                >
                  <Text fontSize="xs" color="tertiary" fontWeight="bold">
                    {message.role === 'user' ? 'You' : 'Agent'}
                  </Text>
                  <MarkdownRenderer
                    style={{
                      fontSize: '14px',
                      lineHeight: '1.5',
                    }}
                  >
                    {message.content || '...'}
                  </MarkdownRenderer>
                  <Text fontSize="xxs" color="tertiary">
                    {message.timestamp.toLocaleTimeString()}
                  </Text>
                </Flex>
              ))
            )}
            <div ref={messagesEndRef} />
          </Flex>

          {/* Input area - always visible at bottom */}
          <Flex direction="column" gap={12} style={{ flexShrink: 0 }}>
            {/* Events display during loading */}
            {isLoading && events.length > 0 && (
              <Flex
                direction="column"
                gap={4}
                py={6}
                style={{
                  borderRadius: '8px',
                  backgroundColor: 'var(--color-background-tertiary)',
                }}
              >
                <Text fontSize="xs" fontWeight="bold" color="tertiary">
                  Processing...
                </Text>
                <Text fontSize="xs" color="tertiary">
                  {events[events.length - 1]?.summary}
                </Text>
              </Flex>
            )}

            <form onSubmit={handleSubmit}>
              <Flex gap={8}>
                <Box
                  borderWidth={2}
                  borderStyle="solid"
                  borderColor="tertiary"
                  borderRadius={8}
                  backgroundColor="primary"
                  style={{ flex: 1 }}
                >
                  <textarea
                    value={inputValue}
                    onChange={handleInputChange}
                    placeholder="Type your message... (Shift+Enter for new line, Enter to send)"
                    disabled={isLoading}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleSubmit(e as unknown as FormEvent);
                      }
                    }}
                    style={{
                      width: '100%',
                      minHeight: '80px',
                      padding: '12px',
                      border: 'none',
                      backgroundColor: 'transparent',
                      color: 'var(--color-text-primary)',
                      fontFamily: 'inherit',
                      fontSize: '14px',
                      resize: 'vertical',
                      outline: 'none',
                    }}
                  />
                </Box>
                <Flex direction="column" gap={8} style={{ width: '120px' }}>
                  <Button
                    type="submit"
                    disabled={isLoading || !inputValue.trim()}
                    style={{ height: '80px', width: '100%' }}
                  >
                    {isLoading ? 'Sending...' : 'Send'}
                  </Button>
                  {messages.length > 0 && (
                    <Button onClick={handleClearConversation} kind="secondary" size="sm">
                      Clear
                    </Button>
                  )}
                  {events.length > 0 && (
                    <Button
                      onClick={() => setShowEventsPanel(!showEventsPanel)}
                      kind="secondary"
                      size="sm"
                    >
                      {showEventsPanel ? 'Hide' : 'Show'} Events ({events.length})
                    </Button>
                  )}
                </Flex>
              </Flex>
            </form>
          </Flex>
        </Flex>

        {/* Events panel - overlay popover */}
        {showEventsPanel && events.length > 0 && (
          <Flex
            direction="column"
            gap={8}
            py={8}
            borderWidth={1}
            borderStyle="solid"
            borderColor="secondary"
            borderRadius={8}
            backgroundColor="secondary"
            style={{
              position: 'absolute',
              right: '0',
              top: '0',
              bottom: '0',
              width: '280px',
              overflow: 'auto',
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
              zIndex: 1,
            }}
          >
            <Flex justify="space-between" align="center" px={8}>
              <Text fontSize="xs" fontWeight="bold" color="tertiary">
                Events ({events.length})
              </Text>
              <Button
                onClick={() => setShowEventsPanel(false)}
                kind="transparent"
                size="xs"
                iconOnly
              >
                ✕
              </Button>
            </Flex>
            {events.map((event) => (
              <div
                key={event.id}
                style={{
                  cursor: 'pointer',
                }}
                onClick={() => handleEventClick(event)}
              >
                <Flex
                  px={8}
                  py={6}
                  style={{
                    borderRadius: '4px',
                    backgroundColor: 'var(--color-background-primary)',
                  }}
                >
                  <Text fontSize="xs">{event.summary}</Text>
                </Flex>
              </div>
            ))}
          </Flex>
        )}
      </Flex>

      {/* Event details modal */}
      {selectedEvent && (
        <Modal open={true} onOpenChange={handleCloseModal}>
          <Modal.Content variant="auto" style={{ maxWidth: '800px', width: '90vw', zIndex: 100 }}>
            <Modal.Header
              title="Event Details"
              belowTitle={
                <Text fontSize="sm" color="tertiary">
                  {selectedEvent.summary} • Type: {selectedEvent.type}
                </Text>
              }
            />
            <Modal.Body>
              <Flex
                direction="column"
                px={12}
                py={12}
                style={{
                  borderRadius: '8px',
                  backgroundColor: 'var(--color-background-secondary)',
                  maxHeight: '500px',
                  overflow: 'auto',
                }}
              >
                <pre style={{ margin: 0, fontSize: '12px', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(selectedEvent.data, null, 2)}
                </pre>
              </Flex>
            </Modal.Body>
            <Modal.Footer>
              <Flex justify="flex-end">
                <Button onClick={handleCloseModal} kind="secondary">
                  Close
                </Button>
              </Flex>
            </Modal.Footer>
          </Modal.Content>
        </Modal>
      )}
    </Flex>
  );
});

AgentChatPage.displayName = 'AgentChatPage';

export { AgentChatPage };
