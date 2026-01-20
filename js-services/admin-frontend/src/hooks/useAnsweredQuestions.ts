import { useState, useEffect } from 'react';
import { apiClient } from '../api/client';

interface SampleQuestion {
  id: string;
  question_text: string;
  source: string;
  source_id: string;
  score: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface SampleAnswer {
  id: string;
  question_id: string;
  answer_text: string;
  confidence_score: number;
  source_documents: Record<string, unknown>;
  generated_at: string;
  created_at: string;
  updated_at: string;
}

interface SampleQuestionWithAnswers extends SampleQuestion {
  answers: SampleAnswer[];
}

interface SampleQuestionsResponse {
  questions: SampleQuestionWithAnswers[];
  count: number;
  limit: number;
}

export const useAnsweredQuestions = () => {
  const [answeredQuestions, setAnsweredQuestions] = useState<SampleQuestionWithAnswers[]>([]);

  const fetchAnsweredQuestions = async () => {
    try {
      const data: SampleQuestionsResponse = await apiClient.get(
        '/api/sample-questions/answered?limit=3'
      );
      setAnsweredQuestions(data.questions);
    } catch {
      //
    }
  };

  useEffect(() => {
    fetchAnsweredQuestions();
  }, []);

  return { answeredQuestions };
};
