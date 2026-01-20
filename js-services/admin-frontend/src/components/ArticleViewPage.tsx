import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Text, Button } from '@gathertown/gather-design-system';
import { MarkdownRenderer } from './shared/MarkdownRenderer';
import { knowledgeBasesApi, type KnowledgeBase, type Article } from '../api/knowledge-bases';

export const ArticleViewPage = () => {
  const { id, articleId } = useParams<{ id: string; articleId: string }>();
  const navigate = useNavigate();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [articles, setArticles] = useState<Article[]>([]);
  const [currentArticle, setCurrentArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    if (!id || !articleId) return;

    try {
      setLoading(true);
      const [kbData, articlesData] = await Promise.all([
        knowledgeBasesApi.get(id),
        knowledgeBasesApi.listArticles(id),
      ]);
      setKb(kbData);
      setArticles(articlesData.articles);
      const article = articlesData.articles.find((a) => a.id === articleId);
      setCurrentArticle(article || null);
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

  if (loading || !kb || !currentArticle) {
    return (
      <div style={{ width: '100%' }}>
        <Text>Loading...</Text>
      </div>
    );
  }

  const currentIndex = articles.findIndex((a) => a.id === articleId);
  const hasNext = currentIndex >= 0 && currentIndex < articles.length - 1;
  const hasPrev = currentIndex > 0;

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
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <Button kind="transparent" onClick={() => navigate(`/knowledge-bases/${id}`)}>
            ← Back to {kb.name}
          </Button>
          <h1 style={{ fontSize: '32px', fontWeight: 'bold', margin: 0 }}>
            {currentArticle.title}
          </h1>
          {Object.keys(currentArticle.content).length > 0 && (
            <Text color="tertiary">
              Last updated {new Date(currentArticle.updated_at).toLocaleString()}
            </Text>
          )}
        </div>
        <Button onClick={() => navigate(`/knowledge-bases/${id}/articles/${articleId}/generate`)}>
          {Object.keys(currentArticle.content).length > 0 ? 'Regenerate' : 'Generate'}
        </Button>
      </div>

      <div style={{ display: 'flex', gap: '8px' }}>
        <Button
          disabled={!hasPrev}
          onClick={() => {
            const prevArticle = articles[currentIndex - 1];
            if (hasPrev && prevArticle) {
              navigate(`/knowledge-bases/${id}/articles/${prevArticle.id}`);
            }
          }}
        >
          ← Previous
        </Button>
        <Button
          disabled={!hasNext}
          onClick={() => {
            const nextArticle = articles[currentIndex + 1];
            if (hasNext && nextArticle) {
              navigate(`/knowledge-bases/${id}/articles/${nextArticle.id}`);
            }
          }}
        >
          Next →
        </Button>
      </div>

      {Object.keys(currentArticle.content).length === 0 ? (
        <div
          style={{
            padding: '24px',
            border: '1px solid #e0e0e0',
            borderRadius: '8px',
            width: '100%',
          }}
        >
          <Text>This article hasn't been generated yet. Click Generate to create content.</Text>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', width: '100%' }}>
          {kb.config.template.map((field) => {
            const fieldContent = currentArticle.content[field.field_name];
            if (!fieldContent) return null;

            return (
              <div
                key={field.field_name}
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
                <h2 style={{ fontSize: '20px', fontWeight: 'bold', margin: 0 }}>
                  {field.field_name.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                </h2>
                <MarkdownRenderer
                  style={{
                    fontSize: '14px',
                    lineHeight: '1.6',
                  }}
                >
                  {String(fieldContent)}
                </MarkdownRenderer>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
