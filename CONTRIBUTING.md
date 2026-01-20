# Contributing to Grapevine

## Project Status

**This repository is provided as-is.** It was open-sourced as a reference implementation and learning resource. There are no active maintainers reviewing or merging pull requests.

You are welcome to:

- **Fork the repository** and develop your own version
- **Use the code** as a starting point for your own projects
- **Learn from the implementation** patterns and architecture

## Forking and Development

If you fork this project and want to develop it further, the sections below provide guidance on development setup and code quality standards.

### Prerequisites

- **Python 3.13+**
- **Node.js 20+** and **Yarn**
- **Docker** and **Docker Compose**
- **mise** (recommended for toolchain management)

### Development Setup

```bash
# Install mise (recommended)
brew install mise

# Install managed tools
mise install

# Install Python dependencies
uv sync --group test

# Install JavaScript dependencies
cd js-services
yarn install
yarn build
cd ..

# Start infrastructure (PostgreSQL, OpenSearch, Redis, LocalStack)
mise dev

# Initial database setup
mise setup
```

### Service Ports

| Service           | Port | URL                   |
| ----------------- | ---- | --------------------- |
| MCP Server        | 8000 | http://localhost:8000 |
| Ingest Gatekeeper | 8001 | http://localhost:8001 |
| Admin Frontend    | 5173 | http://localhost:5173 |
| Admin Backend     | 5002 | http://localhost:5002 |
| PostgreSQL        | 5422 | localhost:5422        |
| OpenSearch        | 9200 | http://localhost:9200 |
| Redis             | 6379 | localhost:6379        |
| LocalStack        | 4566 | http://localhost:4566 |

## Code Quality

### Python

We use **ruff** for linting/formatting and **mypy** for type checking:

```bash
# Auto-fix and verify
uv run ruff check --fix && uv run ruff format && uv run ruff check && uv run mypy && uv run vulture
```

### JavaScript/TypeScript

We use **ESLint** and **Prettier**:

```bash
cd js-services && yarn format && yarn lint && yarn type-check && yarn build
```

## Testing

### Python

```bash
uv run pytest tests/ -v
```

### JavaScript

```bash
cd js-services && yarn test
```

## Adding Connectors

See [connector-ingestion-implementation-guide.md](docs/connector-ingestion-implementation-guide.md) for guidance on adding new data source connectors.

## Database Migrations

See [migrations.md](docs/migrations.md) for migration documentation.
