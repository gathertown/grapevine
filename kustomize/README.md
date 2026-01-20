# Kustomize Multi-Environment Configuration

This directory contains Kubernetes configurations for Grapevine services using Kustomize for multi-environment support.

## Directory Structure

```
kustomize/
├── base/                          # Shared base configurations
│   ├── kustomization.yaml
│   ├── namespaces.yaml
│   ├── grapevine-services/        # API services with ingress
│   │   ├── kustomization.yaml
│   │   ├── ingest-gatekeeper.yaml
│   │   ├── grapevine-api.yaml
│   │   ├── grapevine-app.yaml
│   │   ├── migrations.yaml
│   │   └── steward.yaml
│   └── grapevine-workers/         # Background workers
│       ├── kustomization.yaml
│       ├── index-worker.yaml
│       ├── ingest-worker.yaml
│       ├── cron-worker.yaml
│       ├── ambient-extraction.yaml
│       └── slackbot.yaml
└── overlays/                      # Environment-specific configs
    ├── devenv/                    # Development environment
    │   ├── kustomization.yaml
    │   ├── replicas-patch.yaml
    │   ├── ingress-patch.yaml
    │   └── ...
    ├── staging/
    │   ├── kustomization.yaml
    │   ├── replicas-patch.yaml
    │   ├── resources-patch.yaml
    │   └── ingress-patch.yaml
    └── production/
        ├── kustomization.yaml
        ├── replicas-patch.yaml
        └── ingress-patch.yaml
```

## Customization Required

Before deploying, you must customize the following in your overlay kustomization files:

### 1. Container Registry

Update the `images` section in your overlay's `kustomization.yaml` to point to your container registry:

```yaml
images:
  - name: REGISTRY/grapevine-api
    newName: your-registry.com/grapevine-api
    newTag: your-tag
```

### 2. Hostnames

Update the ingress patches (`ingress-patch.yaml`) with your actual domain names:

```yaml
spec:
  rules:
    - host: app.yourdomain.com
```

### 3. Secrets

The base configurations reference Kubernetes secrets that must be created in your cluster:

- `grapevine-api-secrets`
- `grapevine-app-secrets`
- `ingest-gatekeeper-secrets`
- `steward-secrets`
- `migrations-secrets`
- `ingest-worker-secrets`
- `index-worker-secrets`
- `cron-worker-secrets`
- `slackbot-secrets`
- `ambient-extraction-secrets`

You can create these secrets using your preferred secrets management solution (e.g., Sealed Secrets, External Secrets Operator, Vault, etc.).

### 4. Image Pull Secrets

If using a private container registry, ensure the `priv-docker-registry` secret exists in your cluster.

## Deployment Commands

### Production Deployment

```bash
# Recommended: Direct overlay deployment
kubectl apply -k kustomize/overlays/production/
```

### Staging Deployment

```bash
kubectl apply -k kustomize/overlays/staging/
```

### Development Environment

```bash
kubectl apply -k kustomize/overlays/devenv/
```

## Environment Differences

### Base Configuration

- **Replicas**: 1 (minimal for development)
- **Hostnames**: `example.com` placeholders (must be overridden)
- **Images**: `REGISTRY/grapevine-*` placeholders (must be overridden)
- **Resources**: Standard requests/limits from original configs

### Staging Environment

- **Replicas**: Reduced counts (2-5 per service)
- **Resources**: Lower CPU/memory for cost optimization
- **Hostname**: Override with your staging domain (e.g., `*.stg.yourdomain.com`)

### Production Environment

- **Replicas**: Full production scale (5-80 per service)
- **Resources**: Full production resource allocation
- **Hostname**: Override with your production domain (e.g., `*.yourdomain.com`)

## Adding New Environments

To add a new environment (e.g., `qa`):

1. Create `overlays/qa/` directory
2. Create `kustomization.yaml` with base reference:
   ```yaml
   apiVersion: kustomize.config.k8s.io/v1beta1
   kind: Kustomization
   resources:
     - ../../base
   images:
     - name: REGISTRY/grapevine-api
       newName: your-registry/grapevine-api
       newTag: qa
     # ... other images
   patches:
     - path: ingress-patch.yaml
   ```
3. Add environment-specific patches (replicas, resources, ingress, etc.)
4. Deploy with `kubectl apply -k kustomize/overlays/qa/`

## Modifying Configurations

- **Shared changes**: Edit files in `base/`
- **Environment-specific**: Edit patches in `overlays/{environment}/`
- **New services**: Add to appropriate `base/` subdirectory and update kustomization.yaml files

## Service Accounts

Each service has a corresponding `serviceAccountName` defined. You'll need to create these service accounts in your cluster:

- `grapevine-api`
- `grapevine`
- `grapevine-ingest-gatekeeper-sa`
- `steward`
- `migrations-sa`
- `ingest-worker`
- `index-worker`
- `cron-worker`
- `slackbot`
- `ambient-extraction`

For AWS EKS, you may want to configure these with IAM Roles for Service Accounts (IRSA) for secure AWS access.

## Optional Components

### ServiceMonitors

The base configurations include Prometheus ServiceMonitor resources. If you're not using Prometheus Operator, you can exclude these using a patch:

```yaml
patches:
  - target:
      kind: ServiceMonitor
    patch: |-
      $patch: delete
      apiVersion: monitoring.coreos.com/v1
      kind: ServiceMonitor
      metadata:
        name: ignored
```

### Reloader

The deployments are annotated with `reloader.stakater.com/auto: 'true'` for automatic restarts when secrets/configmaps change. This requires the [Stakater Reloader](https://github.com/stakater/Reloader) to be installed in your cluster.
