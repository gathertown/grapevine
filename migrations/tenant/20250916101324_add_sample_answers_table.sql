-- Add sample_answers table for first-time questions feature
-- This table stores generated answers for sample questions, enabling flexible answer regeneration

CREATE TABLE sample_answers (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    question_id UUID REFERENCES sample_questions(id) ON DELETE CASCADE,
    answer_text TEXT,
    confidence_score FLOAT CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    source_documents JSONB,
    generated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Performance index for question-based lookups
CREATE INDEX idx_sample_answers_question_id ON sample_answers(question_id);

-- Index for confidence-based filtering
CREATE INDEX idx_sample_answers_confidence ON sample_answers(confidence_score DESC);