/**
 * Sample Questions Data Access Layer (DAL)
 *
 * Handles all database operations related to sample_questions and sample_answers tables
 * These are tenant database operations, not control database
 */

import { Pool } from 'pg';
import { createLogger } from '../logger';

const logger = createLogger('sample-questions-dal');

export interface SampleQuestion {
  id: string;
  question_text: string;
  source: string;
  source_id: string;
  score: number;
  metadata: Record<string, unknown>;
  created_at: Date;
  updated_at: Date;
}

export interface SampleAnswer {
  id: string;
  question_id: string;
  answer_text: string;
  confidence_score: number;
  source_documents: Record<string, unknown>;
  generated_at: Date;
  created_at: Date;
  updated_at: Date;
}

export interface SampleQuestionWithAnswers extends SampleQuestion {
  answers: SampleAnswer[];
}

export interface SampleQuestionsFilter {
  answered?: boolean;
  source?: string;
  limit?: number;
}

export interface SampleQuestionsCount {
  total: number;
  answered: number;
  unanswered: number;
}

export interface SampleQuestionWithAnswer {
  id: string;
  question_text: string;
  source: string;
  source_id: string;
  score: number;
  metadata: Record<string, unknown>;
  created_at: Date;
  updated_at: Date;
  answer_text: string;
  answer_id: string;
}

/**
 * Get multiple highest scoring sample questions that don't have answers yet
 */
export async function getHighestScoringUnansweredQuestions(
  db: Pool,
  limit: number = 1
): Promise<SampleQuestion[]> {
  try {
    const query = `
      SELECT sq.id, sq.question_text, sq.source, sq.source_id, sq.score, sq.metadata, sq.created_at, sq.updated_at
      FROM sample_questions sq
      LEFT JOIN sample_answers sa ON sq.id = sa.question_id
      WHERE sa.question_id IS NULL
      ORDER BY sq.score DESC
      LIMIT $1
    `;

    const result = await db.query(query, [limit]);

    if (result.rows.length === 0) {
      logger.info('No unanswered sample questions found');
      return [];
    }

    const questions: SampleQuestion[] = result.rows.map((row) => ({
      id: row.id,
      question_text: row.question_text,
      source: row.source,
      source_id: row.source_id,
      score: parseFloat(row.score) || 0,
      metadata: row.metadata || {},
      created_at: row.created_at,
      updated_at: row.updated_at,
    }));

    logger.info(`Retrieved ${questions.length} highest scoring unanswered questions`, {
      count: questions.length,
      limit,
    });

    return questions;
  } catch (error) {
    logger.error('Error retrieving highest scoring unanswered questions', {
      error: error instanceof Error ? error.message : 'Unknown error',
      limit,
    });
    throw error;
  }
}

/**
 * Delete a sample question and its associated answers
 */
export async function deleteSampleQuestion(db: Pool, questionId: string): Promise<boolean> {
  try {
    const result = await db.query('DELETE FROM sample_questions WHERE id = $1', [questionId]);

    const wasDeleted = result.rowCount === 1;

    logger.info('Sample question deletion', {
      questionId,
      wasDeleted,
      rowCount: result.rowCount,
    });

    return wasDeleted;
  } catch (error) {
    logger.error('Error deleting sample question', {
      error: error instanceof Error ? error.message : 'Unknown error',
      questionId,
    });
    throw error;
  }
}

/**
 * Update the score of a sample question
 */
export async function updateSampleQuestionScore(
  db: Pool,
  questionId: string,
  newScore: number
): Promise<boolean> {
  try {
    const result = await db.query(
      `
      UPDATE sample_questions
      SET score = $1, updated_at = CURRENT_TIMESTAMP
      WHERE id = $2
      `,
      [newScore, questionId]
    );

    const wasUpdated = result.rowCount === 1;

    logger.info('Sample question score update', {
      questionId,
      newScore,
      wasUpdated,
      rowCount: result.rowCount,
    });

    return wasUpdated;
  } catch (error) {
    logger.error('Error updating sample question score', {
      error: error instanceof Error ? error.message : 'Unknown error',
      questionId,
      newScore,
    });
    throw error;
  }
}

/**
 * Store a sample answer for a question
 */
export async function storeSampleAnswer(
  db: Pool,
  questionId: string,
  answerText: string,
  confidenceScore: number = 0.8,
  sourceDocuments: Record<string, unknown> = {}
): Promise<boolean> {
  try {
    await db.query(
      `
      INSERT INTO sample_answers (
        question_id, answer_text, confidence_score,
        source_documents, generated_at
      ) VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
      `,
      [questionId, answerText, confidenceScore, JSON.stringify(sourceDocuments)]
    );

    logger.info('Stored sample answer', {
      questionId,
      answerLength: answerText.length,
      confidenceScore,
    });

    return true;
  } catch (error) {
    logger.error('Error storing sample answer', {
      error: error instanceof Error ? error.message : 'Unknown error',
      questionId,
      answerLength: answerText.length,
      confidenceScore,
    });
    throw error;
  }
}

// Re-export existing functions for backwards compatibility
export async function getSampleQuestions(
  db: Pool,
  filter: SampleQuestionsFilter = {}
): Promise<SampleQuestionWithAnswers[]> {
  const { answered, source, limit = 20 } = filter;

  try {
    // Build filtering conditions
    const conditions: string[] = [];
    const values: unknown[] = [];
    let paramIndex = 1;

    if (answered === true) {
      conditions.push('EXISTS (SELECT 1 FROM sample_answers sa WHERE sa.question_id = sq.id)');
    } else if (answered === false) {
      conditions.push('NOT EXISTS (SELECT 1 FROM sample_answers sa WHERE sa.question_id = sq.id)');
    }

    if (source) {
      conditions.push(`sq.source = $${paramIndex++}`);
      values.push(source);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    // First query: get questions
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
      ${whereClause}
      ORDER BY sq.score DESC, sq.created_at DESC
      LIMIT $${paramIndex}
    `;

    values.push(limit);

    const questionsResult = await db.query(questionsQuery, values);

    if (questionsResult.rows.length === 0) {
      logger.info('No sample questions found', { filter });
      return [];
    }

    // Extract question IDs for answers query
    const questionIds = questionsResult.rows.map((row) => row.id);

    // Second query: get all answers for these questions
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

    const answersResult = await db.query(answersQuery, [questionIds]);

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

    logger.info(`Retrieved ${questions.length} sample questions`, {
      filter,
      totalReturned: questions.length,
    });

    return questions;
  } catch (error) {
    logger.error('Error retrieving sample questions', {
      error: error instanceof Error ? error.message : 'Unknown error',
      filter,
    });
    throw error;
  }
}

export async function getSampleQuestionById(
  db: Pool,
  questionId: string
): Promise<SampleQuestionWithAnswers | null> {
  try {
    // First query: get the question
    const questionQuery = `
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
      WHERE sq.id = $1
    `;

    const questionResult = await db.query(questionQuery, [questionId]);

    if (questionResult.rows.length === 0) {
      return null;
    }

    // Second query: get all answers for this question
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
      WHERE sa.question_id = $1
      ORDER BY sa.confidence_score DESC, sa.created_at DESC
    `;

    const answersResult = await db.query(answersQuery, [questionId]);

    const answers: SampleAnswer[] = answersResult.rows.map((row) => ({
      id: row.id,
      question_id: row.question_id,
      answer_text: row.answer_text,
      confidence_score: parseFloat(row.confidence_score) || 0,
      source_documents: row.source_documents || {},
      generated_at: row.generated_at,
      created_at: row.created_at,
      updated_at: row.updated_at,
    }));

    const questionRow = questionResult.rows[0];
    const question: SampleQuestionWithAnswers = {
      id: questionRow.id,
      question_text: questionRow.question_text,
      source: questionRow.source,
      source_id: questionRow.source_id,
      score: parseFloat(questionRow.score) || 0,
      metadata: questionRow.metadata || {},
      created_at: questionRow.created_at,
      updated_at: questionRow.updated_at,
      answers,
    };

    logger.info(`Retrieved sample question`, {
      questionId,
      hasAnswers: question.answers && question.answers.length > 0,
    });

    return question;
  } catch (error) {
    logger.error('Error retrieving sample question by ID', {
      error: error instanceof Error ? error.message : 'Unknown error',
      questionId,
    });
    throw error;
  }
}

export async function getSampleQuestionsCount(
  db: Pool,
  filter: SampleQuestionsFilter = {}
): Promise<SampleQuestionsCount> {
  try {
    const { source } = filter;

    const conditions: string[] = [];
    const values: unknown[] = [];
    let paramIndex = 1;

    if (source) {
      conditions.push(`sq.source = $${paramIndex++}`);
      values.push(source);
    }

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    const query = `
      SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN EXISTS (SELECT 1 FROM sample_answers sa WHERE sa.question_id = sq.id) THEN 1 END) as answered,
        COUNT(CASE WHEN NOT EXISTS (SELECT 1 FROM sample_answers sa WHERE sa.question_id = sq.id) THEN 1 END) as unanswered
      FROM sample_questions sq
      ${whereClause}
    `;

    const result = await db.query(query, values);
    const row = result.rows[0];

    const counts: SampleQuestionsCount = {
      total: parseInt(row.total) || 0,
      answered: parseInt(row.answered) || 0,
      unanswered: parseInt(row.unanswered) || 0,
    };

    logger.info('Retrieved sample questions count', {
      counts,
      filter,
    });

    return counts;
  } catch (error) {
    logger.error('Error getting sample questions count', {
      error: error instanceof Error ? error.message : 'Unknown error',
      filter,
    });
    throw error;
  }
}

/**
 * Get sample questions with their answers (simplified - one answer per question)
 * Uses the existing getSampleQuestions function for DRY code
 */
export async function getSampleQuestionsWithAnswers(
  db: Pool,
  limit: number = 3
): Promise<SampleQuestionWithAnswer[]> {
  const questionsWithAnswers = await getSampleQuestions(db, {
    answered: true,
    limit,
  });

  // Transform to flatten structure - take first answer for each question
  const questions: SampleQuestionWithAnswer[] = questionsWithAnswers
    .filter((q) => q.answers.length > 0)
    .map((q) => {
      const firstAnswer = q.answers[0]; // Safe since we filter for length > 0 above
      if (!firstAnswer) {
        throw new Error('Expected answer to exist after filtering');
      }
      return {
        id: q.id,
        question_text: q.question_text,
        source: q.source,
        source_id: q.source_id,
        score: q.score,
        metadata: q.metadata,
        created_at: q.created_at,
        updated_at: q.updated_at,
        answer_text: firstAnswer.answer_text,
        answer_id: firstAnswer.id,
      };
    });

  logger.info(`Retrieved ${questions.length} sample questions with answers`, {
    limit,
    totalReturned: questions.length,
  });

  return questions;
}
