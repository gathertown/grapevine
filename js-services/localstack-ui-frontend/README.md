# LocalStack UI Frontend

React frontend for managing LocalStack SSM parameters with a side pane service selector.

## Features

- **Service Selector**: Expandable sidebar (currently supports SSM)
- **SSM Parameter Management**:
  - List and search parameters
  - Create new parameters (String, StringList, SecureString)
  - Edit existing parameters
  - Delete parameters
  - View parameter metadata

## Configuration

The frontend proxies API requests to the backend running on port 3001. Make sure the backend is running before starting the frontend.
