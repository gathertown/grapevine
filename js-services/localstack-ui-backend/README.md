# LocalStack UI Backend

Express.js backend API for managing LocalStack AWS services, starting with SSM Parameter Store.

## Features

- **SSM Parameter Store API**:
  - List parameters with search/filtering
  - Get individual parameters
  - Create new parameters
  - Update existing parameters
  - Delete parameters
- **LocalStack Integration**: Configured to work with LocalStack on `localhost:4566`
- **In-Memory Store**: Maintains parameter state for improved UX

## API Endpoints

### SSM Parameters

- `GET /api/ssm/parameters?prefix=<path>` - List parameters
- `GET /api/ssm/parameters/:name` - Get specific parameter
- `POST /api/ssm/parameters` - Create new parameter
- `PUT /api/ssm/parameters/:name` - Update parameter
- `DELETE /api/ssm/parameters/:name` - Delete parameter

### Health Check

- `GET /health` - Service health check

## LocalStack Configuration

The service is configured to connect to LocalStack with:

- Endpoint: `http://localhost:4566`
- Region: `us-east-1`
- Credentials: `test` / `test`

Make sure LocalStack is running before starting the backend service.
