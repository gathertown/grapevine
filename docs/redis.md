# Redis Integration

A redis endpoint is already available in production via the `REDIS_PRIMARY_ENDPOINT` environment variable. However, we need to make it available locally.

## Incremental Implementation Steps

### Phase 1: Basic Client & Health Check ✅

1. **Create Redis client module** (`src/clients/redis.py`) ✅

   - Basic connection wrapper using redis-py
   - Configuration from `REDIS_PRIMARY_ENDPOINT` env var (defaults to `localhost:6379`)
   - Simple ping() method for health checks
   - Async-first API following project patterns
   - Singleton pattern with connection management
   - Added `redis>=5.2.0` dependency to `pyproject.toml`

2. **Add Redis health check** (`src/mcp/health.py`) ✅
   - Added redis check to comprehensive health endpoint (`/health`)
   - Will pass in production, fail locally (expected until Phase 2)

### Phase 2: Local Development

3. **Add Redis to Tilt** (`Tiltfile`)
   - Add redis:7-alpine service
   - Expose on localhost:6379
   - Set `REDIS_PRIMARY_ENDPOINT=localhost:6379` for local dev

## Success Criteria

- Health check passes in production
- Local dev environment includes working Redis instance
- Health check passes locally
- Foundation ready for caching/session features

## Implementation Details

### Redis Client (`src/clients/redis.py`)

The Redis client module provides:

- **RedisClient class**: Centralized client manager with lazy connection initialization
- **Configuration**: Uses `REDIS_PRIMARY_ENDPOINT` environment variable, defaults to `localhost:6379`
- **Connection management**: Includes retry logic, health checks, and connection pooling
- **Public API**:
  - `ping()`: Health check function
  - `get_client()`: Get Redis client instance
  - `close()`: Close connections
  - `get_connection_url()`: Get configured connection URL

### Health Check Integration

Redis health checks are now integrated into:

- **`/health`**: Comprehensive health endpoint with all service checks
- **`/health/ready`**: Readiness probe for Kubernetes deployments
- **Caching**: Results cached for 5 minutes (success) or 1 minute (failure)
- **Error handling**: Gracefully handles connection failures without crashing health endpoints

### Usage Example

```python
from src.clients.redis import ping, get_client

# Health check
is_healthy = await ping()

# Get client for operations
client = await get_client()
await client.set("key", "value")
value = await client.get("key")
```
