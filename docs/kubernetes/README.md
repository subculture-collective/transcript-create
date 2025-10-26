# Kubernetes Deployment Guide

This guide provides comprehensive instructions for deploying transcript-create on Kubernetes using the provided manifests and Helm chart.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start with Helm](#quick-start-with-helm)
3. [Manual Deployment with kubectl](#manual-deployment-with-kubectl)
4. [Configuration](#configuration)
5. [Storage Requirements](#storage-requirements)
6. [GPU Configuration](#gpu-configuration)
7. [Monitoring and Observability](#monitoring-and-observability)
8. [Scaling](#scaling)
9. [Upgrades and Rollbacks](#upgrades-and-rollbacks)
10. [Troubleshooting](#troubleshooting)
11. [Cloud Provider Specifics](#cloud-provider-specifics)

## Prerequisites

Before deploying transcript-create on Kubernetes, ensure you have:

### Required Tools

- **kubectl** (v1.25+): Kubernetes command-line tool
  ```bash
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x kubectl && sudo mv kubectl /usr/local/bin/
  ```

- **Helm** (v3.10+): Kubernetes package manager
  ```bash
  curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
  ```

- **Cloud CLI** (for your provider):
  - GCP: `gcloud`
  - AWS: `aws` and `eksctl`
  - Azure: `az`

### Cluster Requirements

- **Kubernetes version**: 1.25 or later
- **Node resources**:
  - API nodes: 2+ CPUs, 4GB+ RAM per node
  - Worker nodes: GPU nodes with 8GB+ RAM
- **Storage**: CSI driver with `ReadWriteMany` support
- **Networking**: CNI with NetworkPolicy support (Calico, Cilium, etc.)
- **Optional add-ons**:
  - cert-manager (for TLS certificates)
  - Prometheus Operator (for monitoring)
  - Ingress Controller (NGINX, Traefik, or cloud provider)

### External Dependencies

You'll need to set up or have access to:

- **PostgreSQL** (v14+): Database for job and video metadata
- **Redis** (v7+): Caching layer (optional but recommended)
- **OpenSearch/Elasticsearch** (optional): Full-text search backend
- **GPU nodes**: For worker transcription (AMD ROCm or NVIDIA CUDA)

## Quick Start with Helm

### 1. Add the Repository

```bash
# Clone the repository
git clone https://github.com/subculture-collective/transcript-create.git
cd transcript-create
```

### 2. Create Secrets

Create a `secrets.yaml` file with your credentials:

```yaml
# secrets-values.yaml
secrets:
  databaseUrl: "postgresql+psycopg://user:password@postgres-host:5432/transcripts"
  sessionSecret: "<generate-with-openssl-rand-hex-32>"
  hfToken: "<your-huggingface-token>"
  oauthGoogleClientId: "<your-google-client-id>"
  oauthGoogleClientSecret: "<your-google-client-secret>"
  stripeApiKey: "<your-stripe-api-key>"
  stripeWebhookSecret: "<your-stripe-webhook-secret>"
```

**Security Note**: For production, use Kubernetes Secrets, SealedSecrets, or external-secrets-operator instead of storing secrets in values files.

```bash
# Create secret manually
kubectl create secret generic transcript-secrets \
  --from-literal=database-url='postgresql+psycopg://user:pass@host:5432/db' \
  --from-literal=session-secret="$(openssl rand -hex 32)" \
  --from-literal=hf-token='your-hf-token' \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 3. Configure Values

Edit `charts/transcript-create/values-prod.yaml` or create your own values file:

```yaml
global:
  environment: production
  domain: your-domain.com

image:
  repository: your-registry/transcript-create
  tag: "1.0.0"

api:
  replicaCount: 3
  ingress:
    enabled: true
    hosts:
      - host: api.your-domain.com
        paths:
          - path: /
            pathType: Prefix

worker:
  replicaCount: 2
  gpu:
    enabled: true
    type: amd  # or nvidia

externalServices:
  database:
    enabled: true
  redis:
    enabled: true
    url: redis://your-redis:6379/0
  opensearch:
    enabled: true
    url: https://your-opensearch:9200

secrets:
  existingSecret: transcript-secrets
```

### 4. Install the Chart

```bash
# Development environment
helm install transcript-create ./charts/transcript-create \
  -f charts/transcript-create/values-dev.yaml \
  --namespace transcript-create \
  --create-namespace

# Production environment
helm install transcript-create ./charts/transcript-create \
  -f charts/transcript-create/values-prod.yaml \
  -f secrets-values.yaml \
  --namespace transcript-create \
  --create-namespace
```

### 5. Verify Deployment

```bash
# Check pod status
kubectl get pods -n transcript-create

# Check service endpoints
kubectl get svc -n transcript-create

# Check ingress
kubectl get ingress -n transcript-create

# View logs
kubectl logs -n transcript-create -l app.kubernetes.io/component=api --tail=50
kubectl logs -n transcript-create -l app.kubernetes.io/component=worker --tail=50
```

## Manual Deployment with kubectl

If you prefer to deploy without Helm:

### 1. Create Namespace

```bash
kubectl create namespace transcript-create
```

### 2. Apply Manifests

```bash
# Apply in order
kubectl apply -f k8s/secrets.yaml -n transcript-create
kubectl apply -f k8s/configmap.yaml -n transcript-create
kubectl apply -f k8s/data-pvc.yaml -n transcript-create
kubectl apply -f k8s/migrations-job.yaml -n transcript-create

# Wait for migrations to complete
kubectl wait --for=condition=complete job/transcript-migrations -n transcript-create --timeout=300s

# Deploy services
kubectl apply -f k8s/api-deployment.yaml -n transcript-create
kubectl apply -f k8s/worker-deployment.yaml -n transcript-create
kubectl apply -f k8s/api-service.yaml -n transcript-create
kubectl apply -f k8s/ingress.yaml -n transcript-create

# Apply autoscaling and policies
kubectl apply -f k8s/hpa.yaml -n transcript-create
kubectl apply -f k8s/poddisruptionbudget.yaml -n transcript-create

# Optional: monitoring
kubectl apply -f k8s/servicemonitor.yaml -n transcript-create
kubectl apply -f k8s/networkpolicy.yaml -n transcript-create
```

### 3. Customize Configuration

Before applying, edit the manifests to match your environment:

- **k8s/configmap.yaml**: Update domain, Redis/OpenSearch URLs
- **k8s/secrets.yaml**: Add your actual secrets (or use SealedSecrets)
- **k8s/data-pvc.yaml**: Adjust storage class and size
- **k8s/ingress.yaml**: Update hostname and TLS settings
- **k8s/worker-deployment.yaml**: Configure GPU type and node selectors

## Configuration

### Environment Variables

Key configuration options in ConfigMap:

| Variable | Description | Default |
|----------|-------------|---------|
| `WHISPER_MODEL` | Whisper model size | `large-v3` |
| `WHISPER_BACKEND` | Backend for API | `faster-whisper` |
| `WHISPER_BACKEND_WORKER` | Backend for workers | `whisper` |
| `CHUNK_SECONDS` | Audio chunk size | `900` |
| `SEARCH_BACKEND` | Search engine | `opensearch` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `ENABLE_RATE_LIMITING` | Rate limit requests | `true` |

### Secrets Configuration

Required secrets (create via kubectl or SealedSecrets):

- `database-url`: PostgreSQL connection string
- `session-secret`: Random secret for sessions (32+ chars)
- `hf-token`: HuggingFace token for diarization (optional)
- `oauth-google-client-id`: Google OAuth (optional)
- `oauth-google-client-secret`: Google OAuth (optional)
- `stripe-api-key`: Stripe billing (optional)
- `stripe-webhook-secret`: Stripe webhooks (optional)

## Storage Requirements

### Storage Classes

The deployment requires two PVCs with `ReadWriteMany` access:

1. **Data PVC** (`transcript-data`):
   - Size: 500Gi (adjustable)
   - Purpose: Video files, audio, temporary processing files
   - Access: Shared across all workers

2. **Cache PVC** (`transcript-cache`):
   - Size: 50Gi (adjustable)
   - Purpose: ML model cache (Whisper, diarization models)
   - Access: Shared across API and workers

### Cloud Provider Storage

- **GKE**: Use GCS CSI driver with `standard-rwo` or Filestore
- **EKS**: Use EFS CSI driver with `efs-sc`
- **AKS**: Use Azure Files with `azurefile` storage class

Example for AWS EFS:

```bash
# Create EFS storage class
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: efs-sc
provisioner: efs.csi.aws.com
parameters:
  provisioningMode: efs-ap
  fileSystemId: fs-123456789
  directoryPerms: "700"
EOF
```

## GPU Configuration

### AMD ROCm GPUs

The worker deployment is pre-configured for AMD ROCm GPUs:

```yaml
# k8s/worker-deployment.yaml
nodeSelector:
  workload-type: gpu

tolerations:
- key: amd.com/gpu
  operator: Exists
  effect: NoSchedule

resources:
  limits:
    amd.com/gpu: 1

volumeMounts:
- name: dev-kfd
  mountPath: /dev/kfd
- name: dev-dri
  mountPath: /dev/dri
```

### NVIDIA CUDA GPUs

For NVIDIA GPUs, modify the worker deployment:

```yaml
resources:
  limits:
    nvidia.com/gpu: 1

tolerations:
- key: nvidia.com/gpu
  operator: Exists
  effect: NoSchedule

# Remove ROCm-specific device mounts
```

### GPU Node Setup

Label GPU nodes:

```bash
kubectl label nodes <gpu-node-name> workload-type=gpu
```

Install GPU operator:

```bash
# For NVIDIA
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/gpu-operator/master/deployments/gpu-operator.yaml

# For AMD ROCm
# Follow vendor-specific instructions
```

## Monitoring and Observability

### Prometheus Integration

If you have Prometheus Operator installed:

```bash
kubectl apply -f k8s/servicemonitor.yaml -n transcript-create
```

Metrics endpoints:
- API: `http://transcript-api:8000/metrics`
- Worker: Pod metrics via PodMonitor

### Grafana Dashboards

Import the provided Grafana dashboards:

```bash
kubectl create configmap grafana-dashboard-transcript \
  --from-file=config/grafana/dashboards/ \
  -n monitoring
```

### Health Checks

Health check endpoints on API:
- Liveness: `GET /live` - Process alive check
- Readiness: `GET /ready` - Dependency check (DB, storage)
- Detailed: `GET /health/detailed` - Full status report

## Scaling

### Manual Scaling

```bash
# Scale API
kubectl scale deployment transcript-api --replicas=5 -n transcript-create

# Scale workers
kubectl scale deployment transcript-worker --replicas=3 -n transcript-create
```

### Horizontal Pod Autoscaling

HPA is enabled by default in the Helm chart:

**API Autoscaling**:
- Min: 3, Max: 10
- Target CPU: 70%
- Target Memory: 80%

**Worker Autoscaling**:
- Min: 2, Max: 5
- Based on `videos_pending` metric (requires Prometheus Adapter)

To disable HPA:

```bash
kubectl delete hpa transcript-api-hpa transcript-worker-hpa -n transcript-create
```

### Prometheus Adapter for Custom Metrics

Install Prometheus Adapter for worker queue-based scaling:

```bash
helm install prometheus-adapter prometheus-community/prometheus-adapter \
  --set prometheus.url=http://prometheus.monitoring.svc \
  --set rules.custom[0].seriesQuery='videos_pending' \
  --set rules.custom[0].resources.overrides.namespace.resource=namespace \
  --set rules.custom[0].name.as='videos_pending' \
  --set rules.custom[0].metricsQuery='avg(videos_pending{<<.LabelMatchers>>})'
```

## Upgrades and Rollbacks

### Upgrade with Helm

```bash
# Upgrade to new version
helm upgrade transcript-create ./charts/transcript-create \
  -f charts/transcript-create/values-prod.yaml \
  --namespace transcript-create

# Check rollout status
kubectl rollout status deployment/transcript-api -n transcript-create
kubectl rollout status deployment/transcript-worker -n transcript-create
```

### Rollback

```bash
# List releases
helm history transcript-create -n transcript-create

# Rollback to previous version
helm rollback transcript-create -n transcript-create

# Rollback to specific revision
helm rollback transcript-create 2 -n transcript-create
```

### Rolling Updates

The deployments use RollingUpdate strategy:
- **API**: `maxSurge: 1`, `maxUnavailable: 0` (zero-downtime)
- **Worker**: `maxSurge: 0`, `maxUnavailable: 1` (GPU constraint)

## Troubleshooting

### Common Issues

#### 1. Pods Not Starting

```bash
# Check pod events
kubectl describe pod <pod-name> -n transcript-create

# Check logs
kubectl logs <pod-name> -n transcript-create --previous
```

Common causes:
- Image pull errors: Check `imagePullSecrets`
- Resource limits: Check node capacity
- Volume mount issues: Verify PVC is bound

#### 2. Database Connection Errors

```bash
# Test database connectivity from a pod
kubectl run -it --rm debug --image=postgres:16 --restart=Never -- \
  psql "postgresql://user:pass@host:5432/db"
```

Verify:
- Database URL in secrets
- Network policies allow egress
- Database service is accessible

#### 3. GPU Not Available

```bash
# Check GPU resources
kubectl describe node <gpu-node-name>

# Check worker pod GPU allocation
kubectl get pod <worker-pod> -n transcript-create -o json | jq '.spec.containers[0].resources'
```

Verify:
- GPU operator installed
- Node labeled correctly
- Device plugin running

#### 4. High Memory Usage

Workers may need more memory for large models:

```bash
# Increase worker memory
kubectl patch deployment transcript-worker -n transcript-create -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"worker","resources":{"limits":{"memory":"32Gi"}}}]}}}}'
```

### Debug Commands

```bash
# Get all resources
kubectl get all -n transcript-create

# Check resource usage
kubectl top pods -n transcript-create
kubectl top nodes

# View events
kubectl get events -n transcript-create --sort-by='.lastTimestamp'

# Shell into pod
kubectl exec -it <pod-name> -n transcript-create -- /bin/bash

# Port forward to API
kubectl port-forward svc/transcript-api 8000:8000 -n transcript-create
```

### Logs Collection

```bash
# API logs
kubectl logs -n transcript-create -l app.kubernetes.io/component=api --tail=100

# Worker logs
kubectl logs -n transcript-create -l app.kubernetes.io/component=worker --tail=100 -f

# Migration logs
kubectl logs job/transcript-migrations -n transcript-create

# Export logs to file
kubectl logs -n transcript-create deployment/transcript-api --since=1h > api-logs.txt
```

## Cloud Provider Specifics

### Google Kubernetes Engine (GKE)

#### 1. Create Cluster

```bash
gcloud container clusters create transcript-cluster \
  --zone us-central1-a \
  --num-nodes 3 \
  --machine-type n1-standard-4 \
  --enable-autoscaling \
  --min-nodes 3 \
  --max-nodes 10 \
  --enable-network-policy

# Add GPU node pool
gcloud container node-pools create gpu-pool \
  --cluster transcript-cluster \
  --zone us-central1-a \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --num-nodes 2 \
  --machine-type n1-standard-8 \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 5
```

#### 2. Install GPU Drivers

```bash
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded.yaml
```

#### 3. Cloud SQL Proxy

For managed PostgreSQL:

```yaml
# Add to API deployment
- name: cloud-sql-proxy
  image: gcr.io/cloudsql-docker/gce-proxy:latest
  command:
    - "/cloud_sql_proxy"
    - "-instances=PROJECT:REGION:INSTANCE=tcp:5432"
  securityContext:
    runAsNonRoot: true
```

### Amazon EKS

#### 1. Create Cluster

```bash
eksctl create cluster \
  --name transcript-cluster \
  --region us-west-2 \
  --nodes 3 \
  --node-type t3.xlarge \
  --nodes-min 3 \
  --nodes-max 10 \
  --with-oidc

# Add GPU node group
eksctl create nodegroup \
  --cluster transcript-cluster \
  --region us-west-2 \
  --name gpu-workers \
  --node-type g4dn.xlarge \
  --nodes 2 \
  --nodes-min 2 \
  --nodes-max 5
```

#### 2. Install EBS CSI Driver

```bash
kubectl apply -k "github.com/kubernetes-sigs/aws-ebs-csi-driver/deploy/kubernetes/overlays/stable/?ref=release-1.24"
```

#### 3. ALB Ingress Controller

```bash
helm repo add eks https://aws.github.io/eks-charts
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=transcript-cluster
```

### Azure Kubernetes Service (AKS)

#### 1. Create Cluster

```bash
az aks create \
  --resource-group transcript-rg \
  --name transcript-cluster \
  --node-count 3 \
  --node-vm-size Standard_D4s_v3 \
  --enable-cluster-autoscaler \
  --min-count 3 \
  --max-count 10 \
  --network-plugin azure

# Add GPU node pool
az aks nodepool add \
  --resource-group transcript-rg \
  --cluster-name transcript-cluster \
  --name gpupool \
  --node-count 2 \
  --node-vm-size Standard_NC6s_v3 \
  --min-count 2 \
  --max-count 5 \
  --enable-cluster-autoscaler
```

#### 2. Azure Files Storage

```bash
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: azurefile
provisioner: file.csi.azure.com
parameters:
  skuName: Premium_LRS
reclaimPolicy: Delete
volumeBindingMode: Immediate
allowVolumeExpansion: true
EOF
```

## Next Steps

1. **Set up monitoring**: Configure Prometheus and Grafana
2. **Configure backups**: Set up database and media backups
3. **Enable TLS**: Install cert-manager and configure certificates
4. **Set up CI/CD**: Automate deployments with GitHub Actions
5. **Performance testing**: Load test your deployment
6. **Security hardening**: Enable network policies, Pod Security Standards

## Additional Resources

- [Kubernetes Best Practices](https://kubernetes.io/docs/concepts/configuration/overview/)
- [Helm Documentation](https://helm.sh/docs/)
- [GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/getting-started.html)
- [Prometheus Operator](https://prometheus-operator.dev/)

## Support

For issues and questions:
- GitHub Issues: https://github.com/subculture-collective/transcript-create/issues
- Documentation: https://github.com/subculture-collective/transcript-create/tree/main/docs
