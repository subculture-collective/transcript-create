# Kubernetes Production Deployment Guide

Complete guide for deploying transcript-create on Kubernetes with Helm or raw manifests, covering GPU configuration, scaling, monitoring, and production best practices.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation Methods](#installation-methods)
3. [Helm Deployment](#helm-deployment)
4. [Manual kubectl Deployment](#manual-kubectl-deployment)
5. [GPU Configuration](#gpu-configuration)
6. [Storage Configuration](#storage-configuration)
7. [Ingress and SSL/TLS](#ingress-and-ssltls)
8. [Scaling and High Availability](#scaling-and-high-availability)
9. [Monitoring and Observability](#monitoring-and-observability)
10. [Secrets Management](#secrets-management)
11. [Upgrades and Rollbacks](#upgrades-and-rollbacks)
12. [Disaster Recovery](#disaster-recovery)
13. [Cloud Provider Specifics](#cloud-provider-specifics)
14. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Tools

```bash
# Install kubectl
KUBECTL_VERSION="$(curl -L -s https://dl.k8s.io/release/stable.txt)"
curl -LO "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin/

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Verify installations
kubectl version --client
helm version
```

### Cluster Requirements

**Minimum Production Cluster:**
- Kubernetes version: 1.25+
- 3 worker nodes minimum (for HA)
- GPU nodes: 1+ with ROCm or CUDA support
- Storage: PersistentVolume provisioner with ReadWriteMany support
- Ingress controller: nginx, traefik, or cloud provider load balancer
- Optional: cert-manager for automatic SSL certificates
- Optional: Prometheus Operator for monitoring

**Resource Requirements:**

API Pods:
- CPU: 500m-2000m per pod
- Memory: 1-4 GB per pod
- Replicas: 3-5 for production

Worker Pods:
- CPU: 2000m-4000m per pod
- Memory: 8-16 GB per pod
- GPU: 1 per pod
- Replicas: Based on GPU node availability

Database (if running in cluster):
- CPU: 1000m-2000m
- Memory: 4-8 GB
- Storage: 100+ GB (preferably SSD)

## Installation Methods

### Quick Comparison

| Method | Best For | Pros | Cons |
|--------|----------|------|------|
| Helm | Production, most scenarios | Easy upgrades, parameterized config | Learning curve |
| kubectl | Testing, simple deployments | Simple, direct control | Manual updates |

## Helm Deployment

### 1. Prepare Secrets

```bash
# Create namespace
kubectl create namespace transcript-create

# Create secrets
kubectl create secret generic transcript-secrets \
  --from-literal=database-url='postgresql+psycopg://user:pass@postgres-host:5432/transcripts' \
  --from-literal=session-secret="$(openssl rand -hex 32)" \
  --from-literal=hf-token='hf_your_token_here' \
  --from-literal=stripe-api-key='sk_live_...' \
  --from-literal=stripe-webhook-secret='whsec_...' \
  --from-literal=oauth-google-client-secret='your-secret' \
  --from-literal=oauth-twitch-client-secret='your-secret' \
  --namespace transcript-create

# Verify secrets
kubectl get secrets -n transcript-create
```

### 2. Create Values File

Create `production-values.yaml`:

```yaml
# Global configuration
global:
  environment: production
  domain: api.example.com  # Replace with your domain

# Image configuration
image:
  repository: ghcr.io/subculture-collective/transcript-create
  tag: "1.0.0"  # Pin to specific version
  pullPolicy: IfNotPresent

# API configuration
api:
  replicaCount: 5
  
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 2000m
      memory: 4Gi
  
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
    targetMemoryUtilizationPercentage: 80
  
  ingress:
    enabled: true
    className: nginx  # or traefik, alb, etc.
    annotations:
      cert-manager.io/cluster-issuer: letsencrypt-prod
      nginx.ingress.kubernetes.io/rate-limit: "100"
      nginx.ingress.kubernetes.io/ssl-redirect: "true"
    hosts:
      - host: api.example.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: transcript-tls
        hosts:
          - api.example.com

# Worker configuration
worker:
  replicaCount: 3
  
  resources:
    requests:
      cpu: 2000m
      memory: 8Gi
    limits:
      cpu: 4000m
      memory: 16Gi
  
  gpu:
    enabled: true
    type: amd  # or nvidia
    count: 1
  
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 6
    targetCPUUtilizationPercentage: 80

# External services
externalServices:
  database:
    enabled: true
    # Using external managed database
  redis:
    enabled: true
    url: redis://redis-service:6379/0
  opensearch:
    enabled: true
    url: http://opensearch:9200

# Secrets (using existing secret)
secrets:
  existingSecret: transcript-secrets

# Persistence
persistence:
  data:
    enabled: true
    storageClass: fast-ssd  # Replace with your storage class
    size: 500Gi
    accessMode: ReadWriteMany
  cache:
    enabled: true
    storageClass: fast-ssd
    size: 100Gi
    accessMode: ReadWriteMany

# Monitoring
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 30s

# Pod Disruption Budget
podDisruptionBudget:
  enabled: true
  minAvailable: 2

# Network policies
networkPolicy:
  enabled: true

# Security context
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
  seccompProfile:
    type: RuntimeDefault
```

### 3. Install with Helm

```bash
# Install
helm install transcript-create ./charts/transcript-create \
  -f production-values.yaml \
  --namespace transcript-create \
  --create-namespace

# Or upgrade if already installed
helm upgrade transcript-create ./charts/transcript-create \
  -f production-values.yaml \
  --namespace transcript-create

# Check status
helm status transcript-create -n transcript-create
kubectl get pods -n transcript-create -w
```

### 4. Verify Deployment

```bash
# Check all resources
kubectl get all -n transcript-create

# Check ingress
kubectl get ingress -n transcript-create

# Test API health
curl https://api.example.com/health

# Check logs
kubectl logs -f deployment/transcript-api -n transcript-create
kubectl logs -f deployment/transcript-worker -n transcript-create
```

## Manual kubectl Deployment

See [k8s/README.md](../../k8s/README.md) for raw manifest deployment.

### Quick Deploy

```bash
# Create namespace
kubectl create namespace transcript-create

# Create secrets
kubectl create secret generic transcript-secrets \
  --from-literal=database-url='postgresql+psycopg://...' \
  --from-literal=session-secret="$(openssl rand -hex 32)" \
  --namespace transcript-create

# Apply manifests
kubectl apply -f k8s/configmap.yaml -n transcript-create
kubectl apply -f k8s/data-pvc.yaml -n transcript-create
kubectl apply -f k8s/migrations-job.yaml -n transcript-create

# Wait for migrations
kubectl wait --for=condition=complete job/transcript-migrations \
  -n transcript-create --timeout=300s

# Deploy services
kubectl apply -f k8s/api-deployment.yaml -n transcript-create
kubectl apply -f k8s/worker-deployment.yaml -n transcript-create
kubectl apply -f k8s/api-service.yaml -n transcript-create
kubectl apply -f k8s/ingress.yaml -n transcript-create

# Apply policies
kubectl apply -f k8s/hpa.yaml -n transcript-create
kubectl apply -f k8s/poddisruptionbudget.yaml -n transcript-create
kubectl apply -f k8s/networkpolicy.yaml -n transcript-create

# Monitoring (if Prometheus Operator installed)
kubectl apply -f k8s/servicemonitor.yaml -n transcript-create
```

## GPU Configuration

### AMD ROCm GPUs

#### Prerequisites
- ROCm drivers installed on nodes
- Node labeled: `gpu.amd.com/device=rocm`
- Device plugin installed

#### Install AMD GPU Device Plugin

```bash
kubectl apply -f https://raw.githubusercontent.com/RadeonOpenCompute/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml
```

#### Worker Pod Configuration

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: transcript-worker
spec:
  template:
    spec:
      nodeSelector:
        gpu.amd.com/device: rocm
      containers:
      - name: worker
        resources:
          limits:
            amd.com/gpu: 1  # Request 1 AMD GPU
        volumeMounts:
        - name: dev-kfd
          mountPath: /dev/kfd
        - name: dev-dri
          mountPath: /dev/dri
        securityContext:
          capabilities:
            add:
            - SYS_PTRACE
      volumes:
      - name: dev-kfd
        hostPath:
          path: /dev/kfd
      - name: dev-dri
        hostPath:
          path: /dev/dri
      tolerations:
      - key: amd.com/gpu
        operator: Exists
        effect: NoSchedule
```

### NVIDIA CUDA GPUs

#### Prerequisites
- NVIDIA drivers installed on nodes
- Node labeled: `gpu.nvidia.com/device=cuda`
- NVIDIA GPU Operator installed

#### Install NVIDIA GPU Operator

```bash
helm repo add nvidia https://helm.ngc.nvidia.com/nvidia
helm repo update

helm install --wait --generate-name \
  -n gpu-operator --create-namespace \
  nvidia/gpu-operator
```

#### Worker Pod Configuration

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: transcript-worker
spec:
  template:
    spec:
      nodeSelector:
        nvidia.com/gpu.present: "true"
      containers:
      - name: worker
        resources:
          limits:
            nvidia.com/gpu: 1  # Request 1 NVIDIA GPU
      tolerations:
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
```

#### Verify GPU Access

```bash
# Check GPU nodes
kubectl get nodes -l nvidia.com/gpu.present=true
# or for AMD
kubectl get nodes -l gpu.amd.com/device=rocm

# Check GPU resources
kubectl describe node <gpu-node-name>

# Test GPU in pod
kubectl exec -it <worker-pod> -n transcript-create -- rocm-smi
# or
kubectl exec -it <worker-pod> -n transcript-create -- nvidia-smi
```

## Storage Configuration

### ReadWriteMany Storage

Required for `/data` volume shared across API and worker pods.

#### Cloud Provider Storage Classes

**AWS EKS - EFS:**
```bash
# Install EFS CSI driver
kubectl apply -k "github.com/kubernetes-sigs/aws-efs-csi-driver/deploy/kubernetes/overlays/stable/?ref=master"

# Create EFS file system (via AWS console or CLI)
# Create StorageClass
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: efs-sc
provisioner: efs.csi.aws.com
parameters:
  provisioningMode: efs-ap
  fileSystemId: fs-xxxxx  # Your EFS ID
  directoryPerms: "700"
EOF
```

**GKE - Filestore:**
```bash
# Filestore CSI driver is pre-installed on GKE 1.21+
# Create StorageClass
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: filestore-sc
provisioner: filestore.csi.storage.gke.io
parameters:
  tier: standard  # or premium
  network: default
volumeBindingMode: WaitForFirstConsumer
EOF
```

**AKS - Azure Files:**
```bash
# Azure Files CSI driver is pre-installed
# Create StorageClass
kubectl apply -f - <<EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: azurefile-premium
provisioner: file.csi.azure.com
parameters:
  skuName: Premium_LRS
mountOptions:
  - dir_mode=0777
  - file_mode=0777
  - uid=1000
  - gid=1000
EOF
```

### Update PVC Storage Class

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: transcript-data
spec:
  storageClassName: efs-sc  # or filestore-sc, azurefile-premium
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 500Gi
```

## Ingress and SSL/TLS

### Install cert-manager

```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Verify installation
kubectl get pods -n cert-manager
```

### Create ClusterIssuer

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com  # Replace with your email
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
```

```bash
kubectl apply -f cluster-issuer.yaml
```

### Configure Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: transcript-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - api.example.com
    secretName: transcript-tls
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: transcript-api
            port:
              number: 8000
```

## Scaling and High Availability

### Horizontal Pod Autoscaling

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: transcript-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: transcript-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
      - type: Percent
        value: 100
        periodSeconds: 30
      - type: Pods
        value: 2
        periodSeconds: 30
      selectPolicy: Max
```

### Pod Disruption Budget

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: transcript-api-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: transcript-api
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: transcript-worker-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: transcript-worker
```

### Pod Anti-Affinity

Ensure pods are distributed across nodes:

```yaml
spec:
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
            - key: app
              operator: In
              values:
              - transcript-api
          topologyKey: kubernetes.io/hostname
```

## Monitoring and Observability

### Prometheus Integration

Install Prometheus Operator:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
```

### ServiceMonitor

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: transcript-metrics
  namespace: transcript-create
spec:
  selector:
    matchLabels:
      app: transcript-api
  endpoints:
  - port: http
    path: /metrics
    interval: 30s
```

### Grafana Dashboards

```bash
# Access Grafana
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80

# Login: admin / prom-operator
# Add Prometheus data source
# Import dashboards from config/grafana/dashboards/
```

### Logging with Loki

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm install loki grafana/loki-stack \
  --namespace monitoring \
  --set grafana.enabled=false \
  --set prometheus.enabled=false
```

## Secrets Management

### Kubernetes Secrets

Basic secrets management (development/small production):

```bash
kubectl create secret generic transcript-secrets \
  --from-literal=key=value \
  --namespace transcript-create
```

### External Secrets Operator

For production, use external secret management:

```bash
# Install External Secrets Operator
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets \
  external-secrets/external-secrets \
  --namespace external-secrets-system \
  --create-namespace

# Configure SecretStore (example for AWS Secrets Manager)
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: aws-secrets-manager
  namespace: transcript-create
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets-sa
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: transcript-secrets
  namespace: transcript-create
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: transcript-secrets
  data:
  - secretKey: database-url
    remoteRef:
      key: transcript/database-url
  - secretKey: session-secret
    remoteRef:
      key: transcript/session-secret
EOF
```

## Upgrades and Rollbacks

### Zero-Downtime Upgrade

```bash
# Update Helm values or image tag
helm upgrade transcript-create ./charts/transcript-create \
  -f production-values.yaml \
  --namespace transcript-create \
  --set image.tag=1.1.0

# Monitor rollout
kubectl rollout status deployment/transcript-api -n transcript-create
kubectl rollout status deployment/transcript-worker -n transcript-create

# Check for errors
kubectl logs -f deployment/transcript-api -n transcript-create --tail=50
```

### Rollback

```bash
# Rollback to previous version
helm rollback transcript-create --namespace transcript-create

# Or rollback to specific revision
helm rollback transcript-create 2 --namespace transcript-create

# Check revision history
helm history transcript-create --namespace transcript-create
```

### Manual Deployment Rollback

```bash
# Check rollout history
kubectl rollout history deployment/transcript-api -n transcript-create

# Rollback
kubectl rollout undo deployment/transcript-api -n transcript-create

# Rollback to specific revision
kubectl rollout undo deployment/transcript-api --to-revision=2 -n transcript-create
```

## Disaster Recovery

### Velero Backup

Install Velero for cluster backups:

```bash
# Install Velero (example for AWS)
velero install \
  --provider aws \
  --plugins velero/velero-plugin-for-aws:v1.8.0 \
  --bucket transcript-backups \
  --backup-location-config region=us-east-1 \
  --snapshot-location-config region=us-east-1 \
  --secret-file ./credentials-velero

# Create backup schedule
velero schedule create transcript-daily \
  --schedule="0 2 * * *" \
  --include-namespaces transcript-create

# Manual backup
velero backup create transcript-backup-$(date +%Y%m%d) \
  --include-namespaces transcript-create

# Restore
velero restore create --from-backup transcript-backup-20250115
```

## Cloud Provider Specifics

### Amazon EKS

See [aws.md](./aws.md) for detailed AWS deployment guide.

**Quick Start:**
```bash
eksctl create cluster \
  --name transcript-prod \
  --region us-east-1 \
  --nodegroup-name standard \
  --node-type m5.xlarge \
  --nodes 3 \
  --nodes-min 3 \
  --nodes-max 6 \
  --managed

# Add GPU node group
eksctl create nodegroup \
  --cluster transcript-prod \
  --name gpu-workers \
  --node-type g4dn.xlarge \
  --nodes 2 \
  --nodes-min 1 \
  --nodes-max 4
```

### Google GKE

See [gcp.md](./gcp.md) for detailed GCP deployment guide.

**Quick Start:**
```bash
gcloud container clusters create transcript-prod \
  --region us-central1 \
  --num-nodes 3 \
  --machine-type n1-standard-4 \
  --enable-autoscaling \
  --min-nodes 3 \
  --max-nodes 6

# Add GPU node pool
gcloud container node-pools create gpu-pool \
  --cluster transcript-prod \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --machine-type n1-standard-4 \
  --num-nodes 2 \
  --region us-central1
```

### Azure AKS

See [azure.md](./azure.md) for detailed Azure deployment guide.

**Quick Start:**
```bash
az aks create \
  --resource-group transcript-rg \
  --name transcript-prod \
  --node-count 3 \
  --node-vm-size Standard_D4s_v3 \
  --enable-managed-identity \
  --enable-cluster-autoscaler \
  --min-count 3 \
  --max-count 6

# Add GPU node pool
az aks nodepool add \
  --resource-group transcript-rg \
  --cluster-name transcript-prod \
  --name gpupool \
  --node-count 2 \
  --node-vm-size Standard_NC6s_v3 \
  --node-taints sku=gpu:NoSchedule
```

## Troubleshooting

### Pods Not Starting

```bash
# Describe pod
kubectl describe pod <pod-name> -n transcript-create

# Check events
kubectl get events -n transcript-create --sort-by='.lastTimestamp'

# Check logs
kubectl logs <pod-name> -n transcript-create --previous
```

### GPU Not Available

```bash
# Check GPU nodes
kubectl get nodes -l nvidia.com/gpu.present=true -o wide

# Check GPU device plugin
kubectl get pods -n kube-system | grep nvidia

# Check GPU allocation
kubectl describe node <gpu-node>
```

### Database Connection Issues

```bash
# Test from pod
kubectl exec -it <api-pod> -n transcript-create -- \
  python -c "from app.db import engine; engine.connect(); print('Connected')"

# Check network policy
kubectl get networkpolicy -n transcript-create
```

### Ingress Not Working

```bash
# Check ingress
kubectl describe ingress -n transcript-create

# Check ingress controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx

# Check certificate
kubectl describe certificate -n transcript-create
```

## Performance Tuning

### Resource Optimization

Monitor and adjust:

```bash
# Check resource usage
kubectl top pods -n transcript-create
kubectl top nodes

# Adjust resource requests/limits in values file
```

### Database Connection Pooling

Use PgBouncer:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pgbouncer
spec:
  template:
    spec:
      containers:
      - name: pgbouncer
        image: edoburu/pgbouncer:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: transcript-secrets
              key: database-url
        - name: POOL_MODE
          value: transaction
        - name: MAX_CLIENT_CONN
          value: "1000"
        - name: DEFAULT_POOL_SIZE
          value: "25"
```

## Cost Optimization

### Use Spot/Preemptible Instances

**AWS:**
```bash
eksctl create nodegroup \
  --cluster transcript-prod \
  --name spot-workers \
  --spot \
  --instance-types m5.xlarge,m5a.xlarge \
  --nodes-min 2 \
  --nodes-max 6
```

**GCP:**
```bash
gcloud container node-pools create spot-pool \
  --cluster transcript-prod \
  --preemptible \
  --machine-type n1-standard-4 \
  --num-nodes 3
```

### Right-size Resources

```bash
# Install metrics server
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Monitor actual usage
kubectl top pods -n transcript-create

# Adjust requests/limits based on actual usage
```

## Next Steps

- [ ] Set up monitoring dashboards
- [ ] Configure backup automation
- [ ] Implement disaster recovery plan
- [ ] Set up CI/CD pipeline
- [ ] Configure log aggregation
- [ ] Implement chaos engineering tests
- [ ] Document runbooks

## Additional Resources

- [Helm Chart README](../../charts/transcript-create/README.md)
- [Raw Manifests](../../k8s/README.md)
- [AWS Deployment Guide](./aws.md)
- [GCP Deployment Guide](./gcp.md)
- [Azure Deployment Guide](./azure.md)
- [Troubleshooting Guide](./troubleshooting.md)
