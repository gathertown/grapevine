import { memo, useEffect, useState } from 'react';
import type { FC } from 'react';
import { Flex, Text, Box, Button, Loader } from '@gathertown/gather-design-system';
import { apiClient } from '../api/client';
import { SectionContainer } from './shared';

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

const QuestionCard: FC<{ question: SampleQuestionWithAnswers; isAnswered: boolean }> = memo(
  ({ question, isAnswered }) => {
    return (
      <Box
        p={16}
        borderRadius={8}
        borderWidth={1}
        borderStyle="solid"
        borderColor="tertiary"
        backgroundColor="primary"
      >
        <Flex direction="column" gap={12}>
          {/* Question */}
          <Flex direction="column" gap={4}>
            <Text fontSize="md" fontWeight="medium" color="primary">
              {question.question_text}
            </Text>
            <Flex gap={8} align="center">
              <Text fontSize="xs" color="tertiary">
                Source: {question.source}
              </Text>
              <Text fontSize="xs" color="tertiary">
                Score: {question.score.toFixed(2)}
              </Text>
            </Flex>
          </Flex>

          {/* Answer (if available) */}
          {isAnswered && question.answers && question.answers.length > 0 && (
            <Flex direction="column" gap={8}>
              {question.answers.map((answer) => (
                <Box key={answer.id} p={12} backgroundColor="secondary" borderRadius={6}>
                  <Flex direction="column" gap={4}>
                    <Text fontSize="sm" color="primary">
                      {answer.answer_text}
                    </Text>
                    <Text fontSize="xs" color="tertiary">
                      Confidence: {(answer.confidence_score * 100).toFixed(1)}%
                    </Text>
                  </Flex>
                </Box>
              ))}
            </Flex>
          )}
        </Flex>
      </Box>
    );
  }
);

QuestionCard.displayName = 'QuestionCard';

const SampleQuestionsPage: FC = memo(() => {
  const [answeredQuestions, setAnsweredQuestions] = useState<SampleQuestionWithAnswers[]>([]);
  const [unansweredQuestions, setUnansweredQuestions] = useState<SampleQuestionWithAnswers[]>([]);
  const [loadingAnswered, setLoadingAnswered] = useState(true);
  const [loadingUnanswered, setLoadingUnanswered] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggeringJob, setTriggeringJob] = useState(false);

  const fetchAnsweredQuestions = async () => {
    try {
      setLoadingAnswered(true);
      const data: SampleQuestionsResponse = await apiClient.get(
        '/api/sample-questions/answered?limit=20'
      );
      setAnsweredQuestions(data.questions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
    } finally {
      setLoadingAnswered(false);
    }
  };

  const fetchUnansweredQuestions = async () => {
    try {
      setLoadingUnanswered(true);
      const data: SampleQuestionsResponse = await apiClient.get(
        '/api/sample-questions/unanswered?limit=10'
      );
      setUnansweredQuestions(data.questions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
    } finally {
      setLoadingUnanswered(false);
    }
  };

  const triggerSampleQuestionsJob = async () => {
    try {
      setTriggeringJob(true);
      setError(null);
      await apiClient.post('/api/sample-questions', {});
      // Optionally refresh the data after triggering the job
      // Note: The job runs asynchronously, so answers won't appear immediately
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger sample questions job');
    } finally {
      setTriggeringJob(false);
    }
  };

  useEffect(() => {
    fetchAnsweredQuestions();
    fetchUnansweredQuestions();
  }, []);

  if (error) {
    return (
      <Flex direction="column" gap={16} align="center">
        <Text color="tertiary" fontSize="md">
          Error: {error}
        </Text>
        <Button
          onClick={() => {
            setError(null);
            fetchAnsweredQuestions();
            fetchUnansweredQuestions();
          }}
        >
          Retry
        </Button>
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={32}>
      {/* Trigger Job Section */}
      <SectionContainer>
        <Flex direction="column" gap={16}>
          <Text fontSize="lg" fontWeight="bold" color="primary">
            Sample Questions Job
          </Text>
          <Flex direction="column" gap={12}>
            <Text fontSize="sm" color="tertiary">
              Trigger the sample question answerer job to generate new answers from your knowledge
              base.
            </Text>
            <Flex>
              <Button onClick={triggerSampleQuestionsJob} disabled={triggeringJob} kind="primary">
                {triggeringJob ? 'Triggering Job...' : 'Trigger Sample Questions Job'}
              </Button>
            </Flex>
          </Flex>
        </Flex>
      </SectionContainer>

      {/* Answered Questions Section */}
      <SectionContainer>
        <Flex direction="column" gap={16}>
          <Flex align="center" gap={12}>
            <Text fontSize="lg" fontWeight="bold" color="primary">
              Answered Questions
            </Text>
            <Text fontSize="sm" color="tertiary">
              {loadingAnswered ? 'Loading...' : `(${answeredQuestions.length} questions)`}
            </Text>
          </Flex>

          {loadingAnswered ? (
            <Flex justify="center" align="center" direction="column" gap={16} py={32}>
              <Loader size="md" />
              <Text fontSize="md" color="tertiary">
                Loading answered questions...
              </Text>
            </Flex>
          ) : answeredQuestions.length === 0 ? (
            <Flex justify="center" align="center" direction="column" gap={16} p={24}>
              <Loader size="md" />
              <Text color="tertiary" fontSize="md" textAlign="center">
                Working on generating answers from your knowledge base...
              </Text>
              <Text color="tertiary" fontSize="sm" textAlign="center">
                Questions will appear here as answers are generated
              </Text>
            </Flex>
          ) : (
            <Flex direction="column" gap={12}>
              {answeredQuestions.map((question) => (
                <QuestionCard key={question.id} question={question} isAnswered={true} />
              ))}
            </Flex>
          )}
        </Flex>
      </SectionContainer>

      {/* Unanswered Questions Section */}
      <SectionContainer>
        <Flex direction="column" gap={16}>
          <Flex align="center" gap={12}>
            <Text fontSize="lg" fontWeight="bold" color="primary">
              Top Unanswered Questions
            </Text>
            <Text fontSize="sm" color="tertiary">
              {loadingUnanswered ? 'Loading...' : `(${unansweredQuestions.length} questions)`}
            </Text>
          </Flex>

          {loadingUnanswered ? (
            <Flex justify="center" align="center" direction="column" gap={16} py={32}>
              <Loader size="md" />
              <Text fontSize="md" color="tertiary">
                Loading unanswered questions...
              </Text>
            </Flex>
          ) : unansweredQuestions.length === 0 ? (
            <Flex justify="center" p={24}>
              <Text color="tertiary" fontSize="md">
                No unanswered questions found. Questions will be extracted from your data sources
                automatically.
              </Text>
            </Flex>
          ) : (
            <Flex direction="column" gap={12}>
              {unansweredQuestions.map((question) => (
                <QuestionCard key={question.id} question={question} isAnswered={false} />
              ))}
            </Flex>
          )}
        </Flex>
      </SectionContainer>
    </Flex>
  );
});

SampleQuestionsPage.displayName = 'SampleQuestionsPage';

export { SampleQuestionsPage };
