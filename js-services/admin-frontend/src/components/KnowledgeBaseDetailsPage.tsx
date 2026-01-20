import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Text, Button, Input } from '@gathertown/gather-design-system';
import { knowledgeBasesApi, type KnowledgeBase, type Article } from '../api/knowledge-bases';

export const KnowledgeBaseDetailsPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const [newArticleTitle, setNewArticleTitle] = useState('');
  const [addingArticle, setAddingArticle] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  const loadData = useCallback(async () => {
    if (!id) return;

    try {
      setLoading(true);
      const [kbData, articlesData] = await Promise.all([
        knowledgeBasesApi.get(id),
        knowledgeBasesApi.listArticles(id),
      ]);
      setKb(kbData);
      setArticles(articlesData.articles);
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

  const handleAddArticle = async () => {
    if (!id || !newArticleTitle.trim()) return;

    try {
      setAddingArticle(true);
      await knowledgeBasesApi.addArticle(id, newArticleTitle);
      setNewArticleTitle('');
      setShowAddForm(false);
      await loadData();
    } catch (error) {
      console.error('Failed to add article:', error);
    } finally {
      setAddingArticle(false);
    }
  };

  const handleDeleteArticle = async (articleId: string) => {
    if (!id || !confirm('Delete this article?')) return;

    try {
      await knowledgeBasesApi.deleteArticle(id, articleId);
      await loadData();
    } catch (error) {
      console.error('Failed to delete article:', error);
    }
  };

  const handleGenerateAll = async () => {
    if (!id) return;

    for (const article of articles) {
      navigate(`/knowledge-bases/${id}/articles/${article.id}/generate`);
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  };

  if (loading || !kb) {
    return (
      <div style={{ width: '100%' }}>
        <Text>Loading...</Text>
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <Button kind="transparent" onClick={() => navigate('/knowledge-bases')}>
            ← Back to Knowledge Bases
          </Button>
          <h1 style={{ fontSize: '32px', fontWeight: 'bold', margin: 0 }}>{kb.name}</h1>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button onClick={() => navigate(`/knowledge-bases/${id}/config`)}>Configure</Button>
          <Button onClick={handleGenerateAll} disabled={articles.length === 0}>
            Generate All
          </Button>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          width: '100%',
        }}
      >
        <h2 style={{ fontSize: '20px', fontWeight: 'bold', margin: 0 }}>Articles</h2>
        <Button onClick={() => setShowAddForm(!showAddForm)}>
          {showAddForm ? 'Cancel' : 'Add Article'}
        </Button>
      </div>

      {showAddForm && (
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', width: '100%' }}>
          <Input
            value={newArticleTitle}
            onChange={(e) => setNewArticleTitle(e.target.value)}
            placeholder="Article title"
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAddArticle();
            }}
            style={{ flex: 1 }}
          />
          <Button onClick={handleAddArticle} disabled={addingArticle || !newArticleTitle.trim()}>
            {addingArticle ? 'Adding...' : 'Add'}
          </Button>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
        {articles.length === 0 ? (
          <Text>No articles yet. Add some to get started!</Text>
        ) : (
          articles.map((article) => (
            <div
              key={article.id}
              style={{
                padding: '16px',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                width: '100%',
              }}
            >
              <div
                style={{
                  flex: 1,
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                }}
                onClick={() => navigate(`/knowledge-bases/${id}/articles/${article.id}`)}
              >
                <h3 style={{ fontSize: '18px', fontWeight: 'bold', margin: 0 }}>{article.title}</h3>
                <Text color="tertiary">
                  {Object.keys(article.content).length > 0
                    ? `Last updated ${new Date(article.updated_at).toLocaleString()}`
                    : 'Not generated yet'}
                </Text>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <Button
                  size="sm"
                  onClick={() => navigate(`/knowledge-bases/${id}/articles/${article.id}/generate`)}
                >
                  {Object.keys(article.content).length > 0 ? 'Regenerate' : 'Generate'}
                </Button>
                <Button
                  size="sm"
                  kind="transparent"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteArticle(article.id);
                  }}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
