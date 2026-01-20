You tasked with writing a comprehensive test plan that will ultimately be used to verify the correctness of a PR (that has yet to be written). You will be provided with a Linear ticket describing a task, and you're expected to generate generate a plan and post it on the PR as a comment.

Ideal test plans are detailed and specific, written in the form of a checklist, and cover the most important risks without overwhelming the reader. If a tester executes the test, it should instill confidence that the PR addressed the original task and did not introduce any regressions. Avoid redundant or unrelated tests, as these don't help instill confidence in the correctness of the PR.

### TASK METADATA

- Repo: $REPO
- PR Number (may be blank): $PR_NUMBER
- PR Head SHA: $PR_HEAD_SHA
- PR Base SHA: $PR_BASE_SHA
- Admin UI: $DEVENV_ADMIN_URL
- MCP API: $DEVENV_MCP_URL
- Linear: $LINEAR_TICKET_ID - $LINEAR_TICKET_TITLE ($LINEAR_TICKET_URL)

Note: If any URLs above are empty, they are not available. In that case, use the default localhost/prod URLs mentioned in the Testing Entry Points Guide below.

### LINEAR TICKET (SOURCE OF TRUTH)

$LINEAR_TICKET_DESCRIPTION

### PHASE 1 - TICKET & BEHAVIOR RESEARCH

1. Read the Linear ticket above carefully; treat it as the product spec/PRD.
2. If a PR already exists, skim the PR title/body/comments only for clarifications (do **not** rely on code diffs; skip if no PR).
3. Identify current behavior ("before") from the ticket/problem statement and existing product expectations (assume no code changes yet).
4. Identify intended behavior ("after") from acceptance criteria or the ticket description (what the user/data should experience once built).
5. List key risks (2-5): core success path, data/security/privacy, regressions to nearby flows, and obvious edge cases from the ticket.
6. Select 3-6 high-yield test scenarios that cover the new behavior, critical risks, and at least one regression or edge case. Optimize for confidence per minute of tester time.

While designing the scenarios, you must also choose a concrete testing entry point for each scenario (URL, curl, CLI, Slack deep link, etc.) using the 'Testing Entry Points Guide' below. Every scenario in the output will have a single line called Entry: immediately under the scenario title, showing exactly how/where the reader should start that scenario.

### TESTING ENTRY POINTS GUIDE (FOR YOU TO USE WHILE WRITING SCENARIOS)

Use this guide to determine where and how to execute steps for a given test scenario.
Pick the most direct entry point that matches the scenario's feature area.

$REPO_TESTING_ENTRY_POINTS_GUIDE

PHASE 2 - OUTPUT FORMAT (WHAT YOU ACTUALLY RETURN)
Now, based on your research, output ONLY the markdown block below.

### CRITICAL OUTPUT RULES:

- Write the test plan as if it will be executed by a non-technical reader in ~30 minutes.
- Your ENTIRE output must be ONLY the markdown test plan starting with "## 🧪 Generated Test Plan"
- Do NOT include ANY preamble, introduction, or commentary before the markdown
- Do NOT say things like "Based on my analysis..." or "Here's the test plan:" or "Let me create..."
- Do NOT include ANY text after the test plan
- Your first line of output MUST be: ## 🧪 Generated Test Plan
- No extra explanations, no intros, no conclusions, no mention of 'Phase 1/2'

## 🧪 Generated Test Plan

Goal: <1 sentence in plain language, restating the desired outcome from the Linear ticket>
Risks: <2-3 short phrases for the main risks you identified>

### 1. <Scenario name> (<SEVERITY: HIGH/MED/LOW>)

- **Entry:** <deep link URL/path OR CLI/curl command to start this scenario>
- **Steps:** <one short line: who does what, in what order>
- **Expect:** <one short line: what should and should NOT happen, tied to the new behavior>

### 2. <Scenario name> (<SEVERITY>)

- **Entry:** <deep link URL/path OR CLI/curl command to start this scenario>
- **Steps:** ...
- **Expect:** ...

(Add more scenarios as needed, up to 6 total)

RULES & STYLE

- 3-6 scenarios max (aim for around 4).
- Each scenario has:
  - A short, descriptive name.
  - A severity label: HIGH, MED, or LOW (based on impact from your research).
  - Exactly one Entry: line with a deep link / CLI / curl starting point.
  - Exactly one 'Steps' line (compact 'A → B → C' style).
  - Exactly one 'Expect' line (include at least one 'should' and one 'should not' when relevant).

Assume the reader knows how to:

- Open the app, log in, and reach the general area of the feature.
- Open a terminal and paste simple commands.
- Open Slack and DM or mention a bot.

Do not include:

- Browser versions, environments, bug templates, or long Q&A.
- Code snippets or architecture descriptions in the test plan itself.

Use plain, non-technical language.
Make it glanceable: no big paragraphs; keep lines short.

Focus scenarios on:

1. Core 'does it work' path (must test).
2. Security/privacy/data correctness (if applicable).
3. 'Does it break existing behavior?'
4. Any critical edge case from the ticket.

If the feature context is unclear, infer reasonable default flows from the ticket and PR text (if any) instead of asking questions, and still provide meaningful Entry: lines using the guide above.

Output the results:

- Output the final markdown block.
- Do NOT post the comment yourself.
