import express, { Request, Response } from 'express';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { dbMiddleware } from '../middleware/db-middleware.js';
import { logger } from '../utils/logger.js';
import { getSqsClient, isSqsConfigured } from '../jobs/sqs-client.js';

const router = express.Router();

// Apply database middleware to all routes in this router
router.use(dbMiddleware);

// Define types for better type safety
interface SampleQuestion {
  id: string;
  question_text: string;
  source: string;
  source_id: string;
  score: number;
  metadata: Record<string, unknown>;
  created_at: Date;
  updated_at: Date;
}

interface SampleAnswer {
  id: string;
  question_id: string;
  answer_text: string;
  confidence_score: number;
  source_documents: Record<string, unknown>;
  generated_at: Date;
  created_at: Date;
  updated_at: Date;
}

interface SampleQuestionWithAnswers extends SampleQuestion {
  answers: SampleAnswer[];
}

/**
 * GET /api/sample-questions/answered
 * Returns answered sample questions with their answers
 */
router.get('/answered', requireAdmin, async (req: Request, res: Response) => {
  try {
    const limit = parseInt(req.query.limit as string) || 20;

    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    // Query for answered questions with their answers
    const questionsQuery = `
      SELECT
        sq.id,
        sq.question_text,
        sq.source,
        sq.source_id,
        sq.score,
        sq.metadata,
        sq.created_at,
        sq.updated_at
      FROM sample_questions sq
      WHERE EXISTS (SELECT 1 FROM sample_answers sa WHERE sa.question_id = sq.id)
      ORDER BY sq.score DESC, sq.created_at DESC
      LIMIT $1
    `;

    const questionsResult = await req.db.query(questionsQuery, [limit]);

    if (questionsResult.rows.length === 0) {
      return res.json({
        questions: [],
        count: 0,
        limit,
      });
    }

    // Get question IDs for answers query
    const questionIds = questionsResult.rows.map((row) => row.id);

    // Query for all answers for these questions
    const answersQuery = `
      SELECT
        sa.id,
        sa.question_id,
        sa.answer_text,
        sa.confidence_score,
        sa.source_documents,
        sa.generated_at,
        sa.created_at,
        sa.updated_at
      FROM sample_answers sa
      WHERE sa.question_id = ANY($1)
      ORDER BY sa.confidence_score DESC, sa.created_at DESC
    `;

    const answersResult = await req.db.query(answersQuery, [questionIds]);

    // Group answers by question_id
    const answersByQuestionId = new Map<string, SampleAnswer[]>();
    for (const row of answersResult.rows) {
      const answer: SampleAnswer = {
        id: row.id,
        question_id: row.question_id,
        answer_text: row.answer_text,
        confidence_score: parseFloat(row.confidence_score) || 0,
        source_documents: row.source_documents || {},
        generated_at: row.generated_at,
        created_at: row.created_at,
        updated_at: row.updated_at,
      };

      if (!answersByQuestionId.has(row.question_id)) {
        answersByQuestionId.set(row.question_id, []);
      }
      const answers = answersByQuestionId.get(row.question_id);
      if (answers) {
        answers.push(answer);
      }
    }

    // Combine questions with their answers
    const questions: SampleQuestionWithAnswers[] = questionsResult.rows.map((row) => ({
      id: row.id,
      question_text: row.question_text,
      source: row.source,
      source_id: row.source_id,
      score: parseFloat(row.score) || 0,
      metadata: row.metadata || {},
      created_at: row.created_at,
      updated_at: row.updated_at,
      answers: answersByQuestionId.get(row.id) || [],
    }));

    logger.info('Retrieved answered sample questions', {
      tenantId: req.user.tenantId,
      count: questions.length,
      limit,
    });

    res.json({
      questions,
      count: questions.length,
      limit,
    });
  } catch (error) {
    logger.error('Error retrieving answered sample questions', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * GET /api/sample-questions/unanswered
 * Returns unanswered sample questions
 */
router.get('/unanswered', requireAdmin, async (req: Request, res: Response) => {
  try {
    const limit = parseInt(req.query.limit as string) || 20;

    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    // Query for unanswered questions
    const questionsQuery = `
      SELECT
        sq.id,
        sq.question_text,
        sq.source,
        sq.source_id,
        sq.score,
        sq.metadata,
        sq.created_at,
        sq.updated_at
      FROM sample_questions sq
      WHERE NOT EXISTS (SELECT 1 FROM sample_answers sa WHERE sa.question_id = sq.id)
      ORDER BY sq.score DESC, sq.created_at DESC
      LIMIT $1
    `;

    const result = await req.db.query(questionsQuery, [limit]);

    const questions: SampleQuestionWithAnswers[] = result.rows.map((row) => ({
      id: row.id,
      question_text: row.question_text,
      source: row.source,
      source_id: row.source_id,
      score: parseFloat(row.score) || 0,
      metadata: row.metadata || {},
      created_at: row.created_at,
      updated_at: row.updated_at,
      answers: [], // Unanswered questions have no answers
    }));

    logger.info('Retrieved unanswered sample questions', {
      tenantId: req.user.tenantId,
      count: questions.length,
      limit,
    });

    res.json({
      questions,
      count: questions.length,
      limit,
    });
  } catch (error) {
    logger.error('Error retrieving unanswered sample questions', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * POST /api/sample-questions
 * Triggers the sample question answerer job
 */
router.post('/', requireAdmin, async (req: Request, res: Response) => {
  try {
    if (!req.user?.tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!isSqsConfigured()) {
      return res.status(503).json({ error: 'SQS is not configured' });
    }

    const tenantId = req.user.tenantId;
    const sqsClient = getSqsClient();

    // Send the sample question answerer job to SQS
    await sqsClient.sendSampleQuestionAnswererJob(tenantId);

    logger.info('Triggered sample question answerer job', {
      tenantId,
      triggeredBy: req.user.email || req.user.id,
    });

    res.json({
      message: 'Sample question answerer job triggered successfully',
      tenantId,
    });
  } catch (error) {
    logger.error('Error triggering sample question answerer job', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      triggeredBy: req.user?.email || req.user?.id,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

export { router as sampleQuestionsRouter };
