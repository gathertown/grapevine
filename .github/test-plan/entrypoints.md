1. Admin Panel & Configuration Scenarios (web UI)
   For scenarios involving setup, settings, billing, onboarding, or viewing dashboards.

- Action: Open the Admin UI in the browser.
- Base URL: Use `http://localhost:5173` (local) or `https://app.getgrapevine.ai` (prod).
  If a Devenv Admin UI URL is provided in the prompt context, prefer that.
  When writing **Entry:** lines, you can use:
  - Just the path (e.g. `/integrations`) if the environment is obvious.
  - Or a full URL (e.g. `$DEVENV_ADMIN_URL/integrations` if a devenv URL is provided, or `http://localhost:5173/integrations` otherwise) if clarity helps.

2. MCP Server Scenarios (search / ask)
   For scenarios involving searching, asking questions, or fetching documents via the MCP server.
   Choose either the REST API (curl/Postman) or MCP Inspector as the entry point, depending on what best matches the behavior in code.

Option A: REST API (curl / Postman)

- Endpoint: `POST $DEVENV_MCP_URL/v1/ask` (if a Devenv MCP API is provided in the prompt context) or `POST http://localhost:8000/v1/ask` (otherwise)
- Auth: Bearer token (mint in Admin UI → API Keys)
  Entry example: `curl -X POST http://localhost:8000/v1/ask ...` (include the full body in Steps)

Option B: MCP Inspector

- Standard Inspector command: `npx @modelcontextprotocol/inspector uv run src/mcp/server.py`
  Entry example: `npx @modelcontextprotocol/inspector uv run src/mcp/server.py`

3. Backend & Maintenance Scenarios (CLI)
   For scenarios involving admin/backend jobs, usage/billing tooling, or maintenance scripts.

- Action: Run commands in a terminal at the repo root.
  Use one of these (or a command you found in the diff) as the **Entry:** line:
  - Generate tenant token: `uv run python scripts/generate_mcp_token.py --tenant-id <ID>`
  - View usage summary: `uv run python -m src.usage.cli summary --days 30`
  - Generate usage report: `uv run python -m src.usage.cli report --format table`
  - Reset tenant trial: `uv run python -m src.usage.cli reset-trial --tenant <ID>`
  - Run migrations: `mise migrations migrate --control --all-tenants`

4. Slack Bot Scenarios
   For scenarios involving end-user interaction in Slack (DMs, mentions, flows).

- Action: Open Slack directly.
  Entry examples:
  - Entry: Open Grapevine App Home in Slack
  - Entry: DM the Grapevine bot in Slack
