import { apiClient } from '../api/client';
import { statsApi } from '../api/stats';

// Constant for how many sources need to be set up before starting to answer sample questions
// Including Slack export, but not including Slack configuration in step 1
export const SOURCES_NEEDED_TO_START_ANSWERING = 2;

// Add a slight delay after setting up the source - I'm not sure what the guarantee
// is for timing for the `/api/sources` endpoint to return the new source, so
// adding a small delay to be safe especially with the limited testing
export const TIME_TO_WAIT_BEFORE_CHECKING_MS = 5_000; // 5 seconds

/**
 * Check if we should start answering sample questions based on the number of configured sources.
 * If exactly the required number of sources are set up, triggers the sample questions job.
 * Includes a delay to give sources time to hydrate.
 */
export async function checkIfWeShouldStartAnsweringSampleQuestions(): Promise<void> {
  // Give sources time to hydrate before checking
  setTimeout(async () => {
    try {
      // Get current source statistics
      const sourceStats = await statsApi.getSourceStats();

      // Count how many sources have been set up (just need to exist as keys)
      const sourceCount = Object.keys(sourceStats).length;

      // If we have exactly the required number of sources, trigger the job
      if (sourceCount === SOURCES_NEEDED_TO_START_ANSWERING) {
        console.log(`Found ${sourceCount} configured sources, triggering sample questions job`);
        await apiClient.post('/api/sample-questions', {});
      } else if (sourceCount < SOURCES_NEEDED_TO_START_ANSWERING) {
        console.log(
          `Found ${sourceCount} configured sources, need ${SOURCES_NEEDED_TO_START_ANSWERING} to start answering sample questions`
        );
      } else {
        console.log(
          `Found ${sourceCount} configured sources, sample questions job should already be running`
        );
      }
    } catch (error) {
      console.error('Error checking if we should start answering sample questions:', error);
      // Don't throw the error to avoid disrupting the normal flow of integration setup
    }
  }, TIME_TO_WAIT_BEFORE_CHECKING_MS);
}
