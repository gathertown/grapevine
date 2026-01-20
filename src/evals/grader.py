import json

from src.clients.openai import get_async_openai_client

# LLM Grader version - increment this when making changes to grading logic
GRADER_VERSION = "v2"

# Grader model
GRADER_MODEL = "gpt-4o"

# Grading rubric
rubric = """
1/5 - The answer is completely wrong, misleading, or unhelpful
2/5 - The answer has major issues with accuracy or completeness
3/5 - The answer is partially correct but missing key information
4/5 - The answer is mostly correct with minor issues
5/5 - The answer is accurate, complete, and helpful
"""


async def grade_answer(answer: str, query: str, expected_answer: str) -> int:
    grading_prompt = f"""
You are an expert evaluator. Please grade the following answer to a technical question using the rubric below.

RUBRIC: {rubric}


QUESTION: {query}


EXPECTED ANSWER: {expected_answer}


ACTUAL ANSWER: {answer}


Questions to ask during evaluation:

1. **Accuracy Assessment:**
   - Does the actual answer contain any factual errors?
   - Are the technical details correct?
   - Are there any misleading statements?

2. **Completeness Check:**
   - Does the actual answer address the main question(s)?
   - Does it cover all the key points from the expected answer?
   - Are there significant gaps in information?

3. **Usefulness Evaluation:**
   - Is all the information in the answer relevant and useful?
   - Would this answer help someone with this question?
   - Is the information actionable or informative?

4. **Style**
   - Is the answer clear, concise, and easy to understand?
   - Are text and code blocks formatted correctly?


Assign a score based on the rubric. Output ONLY a JSON object with the following format:
{{
    "score": <integer from 1 to 5>,
    "reasoning": "<brief explanation of why you gave this score>"
}}

Only output the JSON object, no additional text.
    """

    try:
        client = get_async_openai_client()
        response = await client.chat.completions.create(
            model=GRADER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert evaluator. Grade answers based on accuracy, completeness, and usefulness.",
                },
                {"role": "user", "content": grading_prompt},
            ],
            temperature=0.0,
        )

        response_text = (response.choices[0].message.content or "").strip()

        # Parse the JSON response
        try:
            # Strip markdown code blocks if present
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]  # Remove ```json
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]  # Remove ```
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]  # Remove trailing ```
            cleaned_text = cleaned_text.strip()

            grading_result = json.loads(cleaned_text)
            score = grading_result.get("score", -1)

            # Validate score is in range
            if not isinstance(score, int) or score < 1 or score > 5:
                print(f"Invalid score returned: {score}. Setting to -1.")
                return -1

            return score
        except json.JSONDecodeError:
            print(f"Failed to parse grading response as JSON: {response_text[:200]}...")
            return -1

    except Exception as e:
        print(f"Error during grading: {str(e)}")
        return -1
