import express, { Request, Response } from 'express';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { dbMiddleware } from '../middleware/db-middleware.js';
import { logger } from '../utils/logger.js';
import { generateInternalJWT } from '../jwt-generator.js';

const router = express.Router();

router.use(dbMiddleware);

interface TemplateField {
  field_name: string;
  field_prompt: string;
}

interface KnowledgeBaseConfig {
  context_gathering_prompt: string;
  template: TemplateField[];
}

interface KnowledgeBase {
  id: string;
  name: string;
  config: KnowledgeBaseConfig;
  created_at: Date;
  updated_at: Date;
}

interface Article {
  id: string;
  kb_id: string;
  title: string;
  content: Record<string, unknown>;
  created_at: Date;
  updated_at: Date;
}

/**
 * GET /api/knowledge-bases
 * List all knowledge bases for a tenant
 */
router.get('/', requireAdmin, async (req: Request, res: Response) => {
  try {
    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const result = await req.db.query('SELECT * FROM knowledge_bases ORDER BY created_at DESC');

    const knowledgeBases: KnowledgeBase[] = result.rows.map((row) => ({
      id: row.id,
      name: row.name,
      config: row.config,
      created_at: row.created_at,
      updated_at: row.updated_at,
    }));

    res.json({ knowledge_bases: knowledgeBases });
  } catch (error) {
    logger.error('Error listing knowledge bases', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * GET /api/knowledge-bases/:id
 * Get a specific knowledge base
 */
router.get('/:id', requireAdmin, async (req: Request, res: Response) => {
  try {
    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const result = await req.db.query('SELECT * FROM knowledge_bases WHERE id = $1', [
      req.params.id,
    ]);

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Knowledge base not found' });
    }

    const kb: KnowledgeBase = {
      id: result.rows[0].id,
      name: result.rows[0].name,
      config: result.rows[0].config,
      created_at: result.rows[0].created_at,
      updated_at: result.rows[0].updated_at,
    };

    res.json(kb);
  } catch (error) {
    logger.error('Error getting knowledge base', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      kbId: req.params.id,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * POST /api/knowledge-bases
 * Create a new knowledge base
 */
router.post('/', requireAdmin, async (req: Request, res: Response) => {
  try {
    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const { name, config } = req.body;

    if (!name || !config) {
      return res.status(400).json({ error: 'Name and config are required' });
    }

    const result = await req.db.query(
      'INSERT INTO knowledge_bases (name, config) VALUES ($1, $2) RETURNING *',
      [name, config]
    );

    const kb: KnowledgeBase = {
      id: result.rows[0].id,
      name: result.rows[0].name,
      config: result.rows[0].config,
      created_at: result.rows[0].created_at,
      updated_at: result.rows[0].updated_at,
    };

    logger.info('Created knowledge base', {
      tenantId: req.user.tenantId,
      kbId: kb.id,
      name: kb.name,
    });

    res.status(201).json(kb);
  } catch (error) {
    logger.error('Error creating knowledge base', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * PATCH /api/knowledge-bases/:id
 * Update a knowledge base
 */
router.patch('/:id', requireAdmin, async (req: Request, res: Response) => {
  try {
    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const { name, config } = req.body;
    const updates: string[] = [];
    const values: unknown[] = [];
    let paramCount = 1;

    if (name !== undefined) {
      updates.push(`name = $${paramCount++}`);
      values.push(name);
    }

    if (config !== undefined) {
      updates.push(`config = $${paramCount++}`);
      values.push(config);
    }

    if (updates.length === 0) {
      return res.status(400).json({ error: 'No updates provided' });
    }

    updates.push(`updated_at = CURRENT_TIMESTAMP`);
    values.push(req.params.id);

    const result = await req.db.query(
      `UPDATE knowledge_bases SET ${updates.join(', ')} WHERE id = $${paramCount} RETURNING *`,
      values
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Knowledge base not found' });
    }

    const kb: KnowledgeBase = {
      id: result.rows[0].id,
      name: result.rows[0].name,
      config: result.rows[0].config,
      created_at: result.rows[0].created_at,
      updated_at: result.rows[0].updated_at,
    };

    logger.info('Updated knowledge base', {
      tenantId: req.user.tenantId,
      kbId: kb.id,
    });

    res.json(kb);
  } catch (error) {
    logger.error('Error updating knowledge base', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      kbId: req.params.id,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * DELETE /api/knowledge-bases/:id
 * Delete a knowledge base
 */
router.delete('/:id', requireAdmin, async (req: Request, res: Response) => {
  try {
    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const result = await req.db.query('DELETE FROM knowledge_bases WHERE id = $1 RETURNING id', [
      req.params.id,
    ]);

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Knowledge base not found' });
    }

    logger.info('Deleted knowledge base', {
      tenantId: req.user.tenantId,
      kbId: req.params.id,
    });

    res.status(204).send();
  } catch (error) {
    logger.error('Error deleting knowledge base', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      kbId: req.params.id,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * GET /api/knowledge-bases/:id/articles
 * List articles in a knowledge base
 */
router.get('/:id/articles', requireAdmin, async (req: Request, res: Response) => {
  try {
    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const result = await req.db.query(
      'SELECT * FROM knowledge_base_articles WHERE kb_id = $1 ORDER BY title',
      [req.params.id]
    );

    const articles: Article[] = result.rows.map((row) => ({
      id: row.id,
      kb_id: row.kb_id,
      title: row.title,
      content: row.content,
      created_at: row.created_at,
      updated_at: row.updated_at,
    }));

    res.json({ articles });
  } catch (error) {
    logger.error('Error listing articles', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      kbId: req.params.id,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * POST /api/knowledge-bases/:id/articles
 * Add an article to a knowledge base
 */
router.post('/:id/articles', requireAdmin, async (req: Request, res: Response) => {
  try {
    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const { title } = req.body;

    if (!title) {
      return res.status(400).json({ error: 'Title is required' });
    }

    const result = await req.db.query(
      'INSERT INTO knowledge_base_articles (kb_id, title, content) VALUES ($1, $2, $3) RETURNING *',
      [req.params.id, title, {}]
    );

    const article: Article = {
      id: result.rows[0].id,
      kb_id: result.rows[0].kb_id,
      title: result.rows[0].title,
      content: result.rows[0].content,
      created_at: result.rows[0].created_at,
      updated_at: result.rows[0].updated_at,
    };

    logger.info('Added article to knowledge base', {
      tenantId: req.user.tenantId,
      kbId: req.params.id,
      articleId: article.id,
      title: article.title,
    });

    res.status(201).json(article);
  } catch (error) {
    logger.error('Error adding article', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      kbId: req.params.id,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * DELETE /api/knowledge-bases/:id/articles/:articleId
 * Delete an article from a knowledge base
 */
router.delete('/:id/articles/:articleId', requireAdmin, async (req: Request, res: Response) => {
  try {
    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const result = await req.db.query(
      'DELETE FROM knowledge_base_articles WHERE id = $1 AND kb_id = $2 RETURNING id',
      [req.params.articleId, req.params.id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Article not found' });
    }

    logger.info('Deleted article from knowledge base', {
      tenantId: req.user.tenantId,
      kbId: req.params.id,
      articleId: req.params.articleId,
    });

    res.status(204).send();
  } catch (error) {
    logger.error('Error deleting article', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      kbId: req.params.id,
      articleId: req.params.articleId,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * POST /api/knowledge-bases/:id/articles/:articleId/generate
 * Generate content for an article using ask_agent_streaming
 */
router.post(
  '/:id/articles/:articleId/generate',
  requireAdmin,
  async (req: Request, res: Response) => {
    try {
      if (!req.user?.tenantId) {
        return res.status(400).json({ error: 'Tenant ID is required' });
      }

      if (!req.db) {
        return res.status(500).json({ error: 'Database connection unavailable' });
      }

      // Get the knowledge base config
      const kbResult = await req.db.query('SELECT config FROM knowledge_bases WHERE id = $1', [
        req.params.id,
      ]);

      if (kbResult.rows.length === 0) {
        return res.status(404).json({ error: 'Knowledge base not found' });
      }

      // Get the article
      const articleResult = await req.db.query(
        'SELECT * FROM knowledge_base_articles WHERE id = $1 AND kb_id = $2',
        [req.params.articleId, req.params.id]
      );

      if (articleResult.rows.length === 0) {
        return res.status(404).json({ error: 'Article not found' });
      }

      const article = articleResult.rows[0];
      const config: KnowledgeBaseConfig = kbResult.rows[0].config;

      // Set up SSE headers
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');

      const generatedContent: Record<string, string> = {};

      // Generate internal JWT for MCP authentication
      const mcpToken = await generateInternalJWT(req.user.tenantId, undefined, req.user.email);

      // Helper function to call MCP /v1/ask/stream endpoint
      const streamAskAgent = async (
        query: string,
        previousResponseId?: string
      ): Promise<{ answer: string; responseId?: string }> => {
        const mcpBaseUrl = process.env.MCP_BASE_URL || 'http://localhost:8000';
        const response = await fetch(`${mcpBaseUrl}/v1/ask/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${mcpToken}`,
          },
          body: JSON.stringify({
            query,
            previous_response_id: previousResponseId,
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
        let answer = '';
        let responseId: string | undefined;

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
              const event = JSON.parse(data);
              if (event.type === 'final_answer' && event.data) {
                answer = event.data.answer || '';
                responseId = event.data.response_id;
              }
            } catch (err) {
              console.error('Error parsing SSE event:', err);
            }
          }
        }

        return { answer, responseId };
      };

      // First, gather context
      const contextQuery = `${config.context_gathering_prompt}\n\nArticle title: ${article.title}`;

      res.write(`data: ${JSON.stringify({ type: 'context_start' })}\n\n`);

      let contextResponseId: string | undefined;
      try {
        const { answer: context, responseId } = await streamAskAgent(contextQuery);
        contextResponseId = responseId;
        res.write(`data: ${JSON.stringify({ type: 'context_complete', context })}\n\n`);
      } catch (error) {
        logger.error('Error gathering context', {
          error: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined,
        });
        res.write(
          `data: ${JSON.stringify({
            type: 'error',
            error: `Failed to gather context: ${error instanceof Error ? error.message : String(error)}`,
          })}\n\n`
        );
        res.end();
        return;
      }

      // Generate all fields in parallel using the context response_id
      const fieldPromises = config.template.map(async (field) => {
        res.write(
          `data: ${JSON.stringify({ type: 'field_start', field_name: field.field_name })}\n\n`
        );

        try {
          const fieldQuery = `I am asking you to generate content for one knowledge base article
          field. Use the context you've gathered, but ignore the previous instructions about
          formatting, instead formatting as appropriate for the
          field ${field.field_name} withe following instructions: ${field.field_prompt}\n\nArticle title: ${article.title}`;
          const { answer } = await streamAskAgent(fieldQuery, contextResponseId);
          generatedContent[field.field_name] = answer;

          res.write(
            `data: ${JSON.stringify({
              type: 'field_complete',
              field_name: field.field_name,
              content: answer,
            })}\n\n`
          );
        } catch (error) {
          logger.error('Error generating field', {
            error: error instanceof Error ? error.message : String(error),
            stack: error instanceof Error ? error.stack : undefined,
            fieldName: field.field_name,
          });
          res.write(
            `data: ${JSON.stringify({
              type: 'field_error',
              field_name: field.field_name,
              error: `Failed to generate field: ${error instanceof Error ? error.message : String(error)}`,
            })}\n\n`
          );
        }
      });

      await Promise.all(fieldPromises);

      // Update the article with generated content
      await req.db.query(
        'UPDATE knowledge_base_articles SET content = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2',
        [generatedContent, req.params.articleId]
      );

      res.write(`data: ${JSON.stringify({ type: 'complete', content: generatedContent })}\n\n`);
      res.end();

      logger.info('Generated article content', {
        tenantId: req.user.tenantId,
        kbId: req.params.id,
        articleId: req.params.articleId,
      });
    } catch (error) {
      logger.error('Error generating article', {
        error: error instanceof Error ? error.message : 'Unknown error',
        tenantId: req.user?.tenantId,
        kbId: req.params.id,
        articleId: req.params.articleId,
      });

      if (!res.headersSent) {
        res.status(500).json({ error: 'Internal server error' });
      } else {
        res.write(`data: ${JSON.stringify({ type: 'error', error: 'Internal server error' })}\n\n`);
        res.end();
      }
    }
  }
);

export { router as knowledgeBasesRouter };
