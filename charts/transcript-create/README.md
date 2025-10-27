# transcript-create Helm Chart

Official Helm chart for deploying transcript-create on Kubernetes.

## Features

- **Production-ready**: Secure defaults with Pod Security Standards
- **Highly available**: Multiple replicas with Pod Disruption Budgets
- **Autoscaling**: HPA for both API and Worker based on metrics
- **GPU support**: AMD ROCm and NVIDIA CUDA configurations
- **Monitoring**: Built-in Prometheus ServiceMonitor
- **Security**: Network policies, non-root containers, secret management
- **Flexible**: Extensive configuration via values files

## Prerequisites

- Kubernetes 1.25+
- Helm 3.10+
- PersistentVolume provisioner with ReadWriteMany support
- GPU nodes (for workers)
- Optional: Prometheus Operator (for monitoring)
- Optional: cert-manager (for TLS certificates)

## Installation

### Quick Start

```bash
# Add the repository (when published)
# helm repo add transcript-create https://subculture-collective.github.io/transcript-create

# Install with default values (development)
helm install transcript-create ./charts/transcript-create \
  --namespace transcript-create \
  --create-namespace
```

### Production Installation

1. **Create secrets**:
   ```bash
   kubectl create secret generic transcript-secrets \
     --from-literal=database-url='postgresql+psycopg://user:pass@host:5432/db' \
     --from-literal=session-secret="$(openssl rand -hex 32)" \
     --from-literal=hf-token='your-hf-token' \
     --namespace transcript-create
   ```

2. **Create custom values file** (`my-values.yaml`):
   ```yaml
   global:
     environment: production
     domain: api.example.com

   image:
     repository: ghcr.io/subculture-collective/transcript-create
     tag: "1.0.0"

   api:
     replicaCount: 5
     ingress:
       enabled: true
       hosts:
         - host: api.example.com
           paths:
             - path: /
               pathType: Prefix

   worker:
     replicaCount: 3
     gpu:
       enabled: true
       type: amd

   externalServices:
     database:
       enabled: true
     redis:
       enabled: true
       url: redis://my-redis:6379/0

   secrets:
     existingSecret: transcript-secrets
   ```

3. **Install**:
   ```bash
   helm install transcript-create ./charts/transcript-create \
     -f my-values.yaml \
     --namespace transcript-create \
     --create-namespace
   ```

## Configuration

### Values Files

The chart includes three pre-configured values files:

- `values.yaml` - Default values with documentation
- `values-dev.yaml` - Development environment (minimal resources)
- `values-prod.yaml` - Production environment (HA, autoscaling, security)

### Key Configuration Options

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.environment` | Deployment environment | `production` |
| `global.domain` | Base domain for ingress | `your-domain.com` |
| `image.repository` | Docker image repository | `transcript-create` |
| `image.tag` | Image tag | `latest` |
| `api.replicaCount` | Number of API replicas | `3` |
| `api.autoscaling.enabled` | Enable HPA for API | `true` |
| `worker.replicaCount` | Number of worker replicas | `2` |
| `worker.gpu.enabled` | Enable GPU for workers | `true` |
| `worker.gpu.type` | GPU type (amd/nvidia) | `amd` |
| `persistence.data.size` | Data PVC size | `500Gi` |
| `secrets.existingSecret` | Name of existing secret | `transcript-secrets` |

### Full Configuration

See `values.yaml` for all available configuration options.

## Upgrading

### Helm Upgrade

```bash
# Upgrade to new version
helm upgrade transcript-create ./charts/transcript-create \
  -f my-values.yaml \
  --namespace transcript-create
```

### Rollback

```bash
# View release history
helm history transcript-create -n transcript-create

# Rollback to previous version
helm rollback transcript-create -n transcript-create

# Rollback to specific revision
helm rollback transcript-create 2 -n transcript-create
```

## Uninstallation

```bash
# Delete the release
helm uninstall transcript-create -n transcript-create

# Delete namespace (optional)
kubectl delete namespace transcript-create
```

## Customization

### GPU Configuration

#### NVIDIA GPUs

```yaml
worker:
  gpu:
    enabled: true
    type: nvidia
  resources:
    requests:
      nvidia.com/gpu: 1
    limits:
      nvidia.com/gpu: 1
```

#### AMD ROCm GPUs

```yaml
worker:
  gpu:
    enabled: true
    type: amd
  resources:
    requests:
      amd.com/gpu: 1
    limits:
      amd.com/gpu: 1
```

### External Services

Use managed databases and services:

```yaml
externalServices:
  database:
    enabled: true
    # URL provided via secrets
  redis:
    enabled: true
    url: redis://my-redis.cache.svc:6379/0
  opensearch:
    enabled: true
    url: https://my-opensearch.search.svc:9200
```

### Ingress Configuration

#### NGINX Ingress

```yaml
api:
  ingress:
    enabled: true
    className: nginx
    annotations:
      cert-manager.io/cluster-issuer: letsencrypt-prod
      nginx.ingress.kubernetes.io/ssl-redirect: "true"
    hosts:
      - host: api.example.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: api-tls
        hosts:
          - api.example.com
```

#### AWS ALB

```yaml
api:
  ingress:
    enabled: true
    className: alb
    annotations:
      alb.ingress.kubernetes.io/scheme: internet-facing
      alb.ingress.kubernetes.io/target-type: ip
      alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}, {"HTTPS": 443}]'
```

### Monitoring

Enable Prometheus monitoring:

```yaml
monitoring:
  serviceMonitor:
    enabled: true
    interval: 30s
  podMonitor:
    enabled: true
    interval: 30s
```

### Autoscaling

Configure HPA for API:

```yaml
api:
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 20
    targetCPUUtilizationPercentage: 70
    targetMemoryUtilizationPercentage: 80
```

Configure HPA for Worker with custom metrics:

```yaml
worker:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    customMetrics:
      - type: Pods
        pods:
          metric:
            name: videos_pending
          target:
            type: AverageValue
            averageValue: "5"
```

## Development

### Testing the Chart

```bash
# Lint the chart
helm lint charts/transcript-create

# Test template rendering
helm template transcript-create charts/transcript-create \
  -f charts/transcript-create/values-dev.yaml \
  --debug

# Dry-run installation
helm install transcript-create charts/transcript-create \
  --dry-run --debug \
  -f charts/transcript-create/values-dev.yaml
```

### Packaging

```bash
# Package the chart
helm package charts/transcript-create

# Update dependencies (if any)
helm dependency update charts/transcript-create
```

## Troubleshooting

### Check Release Status

```bash
helm status transcript-create -n transcript-create
helm get values transcript-create -n transcript-create
helm get manifest transcript-create -n transcript-create
```

### Debug Template Issues

```bash
# Render templates with debug output
helm template transcript-create charts/transcript-create \
  -f my-values.yaml \
  --debug > /tmp/rendered.yaml

# Check specific template
helm get manifest transcript-create -n transcript-create | grep -A 20 "kind: Deployment"
```

### Common Issues

#### 1. Image Pull Errors

Ensure image pull secrets are configured:

```yaml
image:
  pullSecrets:
    - name: ghcr-pull-secret
```

#### 2. PVC Not Binding

Check storage class exists:

```bash
kubectl get storageclass
```

Update PVC configuration:

```yaml
persistence:
  data:
    storageClass: your-storage-class
```

#### 3. Ingress Not Working

Verify ingress controller is installed:

```bash
kubectl get pods -n ingress-nginx
```

Check ingress status:

```bash
kubectl describe ingress -n transcript-create
```

## Examples

### Minimal Development Setup

```bash
helm install transcript-create charts/transcript-create \
  -f charts/transcript-create/values-dev.yaml \
  --set api.replicaCount=1 \
  --set worker.replicaCount=1 \
  --set worker.gpu.enabled=false \
  --namespace transcript-create \
  --create-namespace
```

### Production with Cloud SQL

```yaml
externalServices:
  database:
    enabled: true
    # Connection via Cloud SQL Proxy sidecar

# Add Cloud SQL Proxy to API deployment
# (requires custom template or init container configuration)
```

### High Availability Production

```bash
helm install transcript-create charts/transcript-create \
  -f charts/transcript-create/values-prod.yaml \
  --set api.replicaCount=10 \
  --set worker.replicaCount=5 \
  --namespace transcript-create \
  --create-namespace
```

## Support

- GitHub Issues: https://github.com/subculture-collective/transcript-create/issues
- Documentation: https://github.com/subculture-collective/transcript-create/tree/main/docs/kubernetes

## License

See main repository LICENSE file.
