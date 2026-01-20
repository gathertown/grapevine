import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Text, Button } from '@gathertown/gather-design-system';
import {
  knowledgeBasesApi,
  type KnowledgeBase,
  type Article,
  type GenerateEvent,
} from '../api/knowledge-bases';

type FieldStatus = 'pending' | 'generating' | 'complete' | 'error';

interface FieldState {
  name: string;
  status: FieldStatus;
  content?: string;
  error?: string;
}

export const ArticleGeneratePage = () => {
  const { id, articleId } = useParams<{ id: string; articleId: string }>();
  const navigate = useNavigate();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [contextGathering, setContextGathering] = useState(false);
  const [context, setContext] = useState('');
  const [fields, setFields] = useState<FieldState[]>([]);

  const loadData = useCallback(async () => {
    if (!id || !articleId) return;

    try {
      setLoading(true);
      const [kbData, articlesData] = await Promise.all([
        knowledgeBasesApi.get(id),
        knowledgeBasesApi.listArticles(id),
      ]);
      setKb(kbData);
      const articleData = articlesData.articles.find((a) => a.id === articleId);
      setArticle(articleData || null);

      if (kbData.config.template) {
        setFields(
          kbData.config.template.map((field) => ({
            name: field.field_name,
            status: 'pending' as FieldStatus,
          }))
        );
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  }, [id, articleId]);

  useEffect(() => {
    if (id && articleId) {
      loadData();
    }
  }, [id, articleId, loadData]);

  const handleGenerate = async () => {
    if (!id || !articleId) return;

    try {
      setGenerating(true);
      setContextGathering(true);
      setContext('');

      await knowledgeBasesApi.generateArticle(id, articleId, (event: GenerateEvent) => {
        switch (event.type) {
          case 'context_start':
            setContextGathering(true);
            break;

          case 'context_complete':
            setContextGathering(false);
            setContext(event.context);
            break;

          case 'field_start':
            setFields((prev) =>
              prev.map((f) => (f.name === event.field_name ? { ...f, status: 'generating' } : f))
            );
            break;

          case 'field_complete':
            setFields((prev) =>
              prev.map((f) =>
                f.name === event.field_name
                  ? { ...f, status: 'complete', content: event.content }
                  : f
              )
            );
            break;

          case 'field_error':
            setFields((prev) =>
              prev.map((f) =>
                f.name === event.field_name ? { ...f, status: 'error', error: event.error } : f
              )
            );
            break;

          case 'complete':
            setGenerating(false);
            break;

          case 'error':
            console.error('Generation error:', event.error);
            setGenerating(false);
            break;
        }
      });
    } catch (error) {
      console.error('Failed to generate article:', error);
      setGenerating(false);
    }
  };

  if (loading || !kb || !article) {
    return (
      <div style={{ padding: '24px' }}>
        <Text>Loading...</Text>
      </div>
    );
  }

  const getStatusIcon = (status: FieldStatus) => {
    switch (status) {
      case 'pending':
        return '⏸';
      case 'generating':
        return '⏳';
      case 'complete':
        return '✅';
      case 'error':
        return '❌';
    }
  };

  return (
    <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <Button
            kind="transparent"
            onClick={() => navigate(`/knowledge-bases/${id}/articles/${articleId}`)}
          >
            ← Back to Article
          </Button>
          <h1 style={{ fontSize: '32px', fontWeight: 'bold', margin: 0 }}>
            Generate: {article.title}
          </h1>
          {generating && (
            <div
              style={{
                padding: '8px 12px',
                backgroundColor: '#fff3cd',
                border: '1px solid #ffeeba',
                borderRadius: '4px',
                color: '#856404',
                fontSize: '14px',
                marginTop: '8px',
              }}
            >
              ⚠️ If you refresh this page, the generation status will be broken, but generation will
              still be running.
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button onClick={handleGenerate} disabled={generating || kb.config.template.length === 0}>
            {generating ? 'Generating...' : 'Start Generation'}
          </Button>
          <Button
            kind="secondary"
            onClick={() => navigate(`/knowledge-bases/${id}/articles/${articleId}`)}
            disabled={generating}
          >
            View Article
          </Button>
        </div>
      </div>

      {kb.config.template.length === 0 && (
        <div
          style={{
            padding: '16px',
            border: '1px solid #ffa500',
            borderRadius: '8px',
            backgroundColor: '#fff3cd',
          }}
        >
          <Text>
            No template fields configured. Please{' '}
            <Button kind="transparent" onClick={() => navigate(`/knowledge-bases/${id}/config`)}>
              configure the knowledge base
            </Button>{' '}
            first.
          </Text>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 'bold', margin: 0 }}>Progress</h2>

        <div
          style={{
            padding: '16px',
            border: '1px solid #e0e0e0',
            borderRadius: '8px',
            backgroundColor: contextGathering ? '#f0f8ff' : '#f9f9f9',
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
            <span style={{ fontWeight: 'bold' }}>Gathering Context</span>
            <span>
              {contextGathering ? '⏳ In Progress' : context ? '✅ Complete' : '⏸ Pending'}
            </span>
          </div>
        </div>

        {context && (
          <div
            style={{
              padding: '16px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              border: '1px solid #e0e0e0',
              borderRadius: '8px',
            }}
          >
            <span style={{ fontSize: '14px', fontWeight: 'bold' }}>Context Gathered:</span>
            <span style={{ fontSize: '14px', whiteSpace: 'pre-wrap' }}>
              {context.substring(0, 500)}
              {context.length > 500 ? '...' : ''}
            </span>
          </div>
        )}

        {fields.map((field) => (
          <div
            key={field.name}
            style={{
              padding: '16px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              border: '1px solid #e0e0e0',
              borderRadius: '8px',
              backgroundColor:
                field.status === 'generating'
                  ? '#f0f8ff'
                  : field.status === 'complete'
                    ? '#f0fff4'
                    : field.status === 'error'
                      ? '#fff0f0'
                      : '#f9f9f9',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 'bold' }}>
                {field.name.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
              </span>
              <span>
                {getStatusIcon(field.status)} {field.status}
              </span>
            </div>

            {field.content && (
              <span style={{ fontSize: '14px', whiteSpace: 'pre-wrap' }}>
                {field.content.substring(0, 300)}
                {field.content.length > 300 ? '...' : ''}
              </span>
            )}

            {field.error && (
              <span style={{ fontSize: '14px', color: '#d32f2f' }}>Error: {field.error}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
