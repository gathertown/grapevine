## corporate-context repo runbook

### Start the local environment

- Install tool versions: `mise install`
- Start dev stack: `mise dev`

Local URLs (when running `mise dev`):

- Admin UI: `http://localhost:5173`
- Admin backend API: `http://localhost:5002/api`
- MCP server: `http://localhost:8000`

### Auth / test tenant (for manual UI testing)

- Username: `brent+local@gather.town`
- Password: `fake-password!`
- Tenant: **Devin Test Env** (id: `ead3852142e3445e`)

### API key (for backend/MCP calls)

If you need to call the admin backend or MCP server, mint an API key in the Admin UI:

1. Log into the Admin UI.
2. Navigate to **API Keys** (left nav).
3. Create a new key (include "Verification Agent" in the name).
4. Use it in requests as: `Authorization: Bearer <GRAPEVINE_API_KEY>`

### Logs

- Use the terminal output from `mise dev` and service logs to debug failures.
