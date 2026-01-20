# Modern TypeScript Monorepo Build System

This monorepo uses **nx + Yarn 3 + swc** for blazing-fast builds and excellent developer experience.

## Architecture

- **nx**: Task orchestration, caching, and dependency graph management
- **Yarn 3 (Berry)**: Modern package management with workspace support
- **swc**: Rust-based TypeScript/JavaScript compiler (20-70x faster than tsc)

## Quick Start

```bash
# Install dependencies
yarn install

# Build all packages
yarn build

# Build only changed packages
yarn build:affected

# Run development servers with hot-reloading
yarn nx run <package>:serve:dev  # e.g. admin-backend:serve:dev

# Type check all packages
yarn type-check

# Lint all packages
yarn lint

# View dependency graph
yarn graph
```

## Available Commands

### Development (nx-native)

- `yarn nx run <package>:serve` - Run production server for a package
- `yarn nx run <package>:serve:dev` - Run dev server with watch mode and auto-restart
- `yarn nx run-many --target=serve:dev --projects=admin-backend,admin-frontend` - Run multiple dev servers

### Building

- `yarn build` - Build all packages with swc
- `yarn build:affected` - Build only affected packages
- `yarn nx run <package>:build` - Build specific package

### Code Quality

- `yarn type-check` - TypeScript type checking (all packages)
- `yarn type-check:affected` - Type check only affected packages
- `yarn lint` - Lint all packages
- `yarn lint:fix` - Auto-fix linting issues
- `yarn format` - Format code with Prettier
- `yarn format:check` - Check formatting

### Testing

- `yarn test` - Run all tests
- `yarn test:affected` - Run tests for affected packages

### Utilities

- `yarn graph` - View interactive dependency graph
- `yarn reset` - Clear nx cache
- `yarn clean` - Remove build outputs and node_modules

## Package Structure

```
js-services/
├── admin-backend/       # Admin API server
├── admin-frontend/      # Admin React UI (Vite)
├── backend-common/      # Shared backend utilities
├── slack-bot/          # Slack bot application
├── localstack-ui-backend/   # LocalStack UI API
└── localstack-ui-frontend/  # LocalStack UI (React/Vite)
```

## Build Performance

- **Full build**: ~10 seconds (all 6 packages)
- **Incremental builds**: < 2 seconds (with nx caching)
- **swc compilation**: 20-70x faster than tsc
- **Parallel execution**: Automatic dependency-aware parallelization

## Key Features

1. **Smart Caching**: nx caches build outputs and only rebuilds what changed
2. **Affected Commands**: Run tasks only for packages affected by your changes
3. **Parallel Execution**: Automatically runs independent tasks in parallel
4. **Type Safety**: Full TypeScript support with declaration files
5. **Fast Compilation**: swc compiles TypeScript without type checking for speed
6. **Workspace Protocol**: Yarn workspaces for seamless monorepo development

## Configuration Files

- `nx.json` - nx workspace configuration with shared `targetDefaults`
- `.swcrc` - Shared swc compiler configuration
- `eslint.shared.cjs` - Shared ESLint configuration factories
- `.yarnrc.yml` - Yarn 3 configuration
- `*/project.json` - Minimal per-package nx configuration (inherits from targetDefaults)
- `*/tsconfig.json` - TypeScript configuration (for IDE and type checking)

## Migrating from npm

This project was migrated from npm workspaces. Key improvements:

- **80% faster builds** with swc instead of tsc
- **Better caching** with nx computation caching
- **Smarter rebuilds** with affected commands
- **Improved DX** with parallel execution and dependency graph
- **Reduced disk usage** with Yarn's improved dependency resolution

## Troubleshooting

### Clear cache if builds are acting strange

```bash
yarn reset
```

### Reinstall dependencies

```bash
rm -rf node_modules yarn.lock
yarn install
```

### View what will be affected by changes

```bash
yarn nx affected --graph
```

### Debug build issues

```bash
yarn nx build <package> --verbose
```
