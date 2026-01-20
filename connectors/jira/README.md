# Jira Auth Proxy

This is a Forge app that acts as an authentication proxy for Jira webhooks, forwarding events to the Grapevine gatekeeper service.

See [developer.atlassian.com/platform/forge/](https://developer.atlassian.com/platform/forge) for documentation and tutorials explaining Forge.

## Requirements

- [Atlassian Forge CLI](https://developer.atlassian.com/platform/forge/set-up-forge/)

## Local Testing

To test the Jira connector locally with your development environment:

### 1. Start your local environment

```bash
# Start Tilt and all local services
tilt up
```

### 2. Start ngrok tunnel to port 8001

The gatekeeper service runs on port 8001 locally. You need to expose it via ngrok:

```bash
ngrok http 8001
```

Copy the ngrok URL (e.g., `https://abc123.ngrok-free.app`)

### 3. Set the GATEKEEPER_URL environment variable

```bash
export GATEKEEPER_URL=https://your-ngrok-url.ngrok-free.app
```

### 4. Deploy the connector to local environment

```bash
./deploy.sh local
```

This will:
- Use your ngrok URL as the gatekeeper endpoint
- Generate the manifest with local configuration
- Deploy to Forge

### 5. Install the app

If this is your first time deploying:

```bash
forge install
```

Select your Jira site when prompted.

## Deployment

### Staging

```bash
./deploy.sh staging
```

### Production

```bash
./deploy.sh production
```

## Notes

- The `deploy.sh` script handles environment-specific configuration
- Local deployments require the `GATEKEEPER_URL` environment variable
- Staging and production use predefined gatekeeper URLs
- Once installed, the app picks up new deployments automatically

## Support

See [Get help](https://developer.atlassian.com/platform/forge/get-help/) for how to get help and provide feedback.
