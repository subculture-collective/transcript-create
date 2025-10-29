# Google Cloud Platform (GCP) Deployment Guide

Complete guide for deploying transcript-create on Google Cloud Platform using GKE, Cloud SQL, and other managed services.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [GKE Deployment](#gke-deployment)
4. [Cloud SQL Setup](#cloud-sql-setup)
5. [Storage Configuration](#storage-configuration)
6. [Networking](#networking)
7. [Monitoring](#monitoring)
8. [Cost Optimization](#cost-optimization)
9. [Terraform Automation](#terraform-automation)

## Architecture Overview

### Production Architecture

```
Internet
    │
    ↓
Cloud Load Balancing
    │
    ├──→ GKE (API) ──→ Cloud SQL PostgreSQL
    │        │
    │        └──→ Memorystore Redis
    │
    └──→ GKE GPU (Workers) ──→ Cloud Storage
```

### Components

- **Compute**: GKE with GPU node pools
- **Database**: Cloud SQL for PostgreSQL
- **Cache**: Memorystore for Redis
- **Storage**: Cloud Storage buckets
- **Networking**: VPC, Cloud Load Balancing
- **Monitoring**: Cloud Monitoring, Cloud Logging
- **Security**: IAM, Secret Manager, KMS

## Prerequisites

### Install gcloud CLI

```bash
# Install gcloud SDK
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Initialize gcloud
gcloud init

# Set project
gcloud config set project transcript-prod-12345

# Enable required APIs
gcloud services enable \
  container.googleapis.com \
  compute.googleapis.com \
  sqladmin.googleapis.com \
  storage-api.googleapis.com \
  redis.googleapis.com \
  secretmanager.googleapis.com
```

### Set Environment Variables

```bash
export PROJECT_ID="transcript-prod-12345"
export REGION="us-central1"
export ZONE="us-central1-a"
export CLUSTER_NAME="transcript-prod"
```

## GKE Deployment

### 1. Create GKE Cluster

```bash
# Create VPC network
gcloud compute networks create transcript-vpc \
  --subnet-mode=custom

# Create subnet
gcloud compute networks subnets create transcript-subnet \
  --network=transcript-vpc \
  --region=$REGION \
  --range=10.0.0.0/24 \
  --secondary-range pods=10.1.0.0/16,services=10.2.0.0/16

# Create GKE cluster
gcloud container clusters create $CLUSTER_NAME \
  --region=$REGION \
  --num-nodes=3 \
  --machine-type=n1-standard-4 \
  --disk-size=100 \
  --disk-type=pd-standard \
  --network=transcript-vpc \
  --subnetwork=transcript-subnet \
  --cluster-secondary-range-name=pods \
  --services-secondary-range-name=services \
  --enable-ip-alias \
  --enable-autoscaling \
  --min-nodes=3 \
  --max-nodes=10 \
  --enable-autorepair \
  --enable-autoupgrade \
  --addons=HorizontalPodAutoscaling,HttpLoadBalancing,GcePersistentDiskCsiDriver \
  --workload-pool=$PROJECT_ID.svc.id.goog \
  --enable-stackdriver-kubernetes

# Get credentials
gcloud container clusters get-credentials $CLUSTER_NAME --region=$REGION
```

### 2. Add GPU Node Pool

```bash
# Create GPU node pool (NVIDIA T4)
gcloud container node-pools create gpu-pool \
  --cluster=$CLUSTER_NAME \
  --region=$REGION \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=2 \
  --min-nodes=1 \
  --max-nodes=4 \
  --enable-autoscaling \
  --disk-size=100 \
  --node-taints=nvidia.com/gpu=present:NoSchedule \
  --node-labels=gpu=nvidia

# Install NVIDIA GPU device plugin
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded.yaml

# Verify GPU nodes
kubectl get nodes -l gpu=nvidia
kubectl describe node <gpu-node-name> | grep nvidia.com/gpu
```

### 3. Install Ingress and Cert Manager

```bash
# Install nginx ingress controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml

# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer for Let's Encrypt
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

## Cloud SQL Setup

### 1. Create Cloud SQL Instance

```bash
# Create Cloud SQL instance
gcloud sql instances create transcript-db \
  --database-version=POSTGRES_16 \
  --tier=db-custom-4-16384 \
  --region=$REGION \
  --network=projects/$PROJECT_ID/global/networks/transcript-vpc \
  --no-assign-ip \
  --storage-type=SSD \
  --storage-size=100 \
  --storage-auto-increase \
  --availability-type=REGIONAL \
  --backup-start-time=03:00 \
  --enable-bin-log \
  --maintenance-window-day=SUN \
  --maintenance-window-hour=4 \
  --database-flags=max_connections=200,shared_buffers=1024MB

# Create database
gcloud sql databases create transcripts --instance=transcript-db

# Create user
gcloud sql users create transcript-user \
  --instance=transcript-db \
  --password=$(openssl rand -base64 32)

# Get connection name
gcloud sql instances describe transcript-db \
  --format="value(connectionName)"
```

### 2. Enable Private IP

```bash
# Enable Private Service Access
gcloud compute addresses create google-managed-services-transcript-vpc \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network=transcript-vpc

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-transcript-vpc \
  --network=transcript-vpc
```

### 3. Configure Cloud SQL Proxy (for GKE)

```bash
# Create service account for Cloud SQL
gcloud iam service-accounts create cloudsql-proxy \
  --display-name="Cloud SQL Proxy"

# Grant permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:cloudsql-proxy@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

# Create Workload Identity binding
kubectl create serviceaccount cloudsql-proxy -n transcript-create

gcloud iam service-accounts add-iam-policy-binding \
  cloudsql-proxy@$PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:$PROJECT_ID.svc.id.goog[transcript-create/cloudsql-proxy]"

kubectl annotate serviceaccount cloudsql-proxy -n transcript-create \
  iam.gke.io/gcp-service-account=cloudsql-proxy@$PROJECT_ID.iam.gserviceaccount.com
```

## Storage Configuration

### 1. Create Cloud Storage Bucket

```bash
# Create bucket
gsutil mb -p $PROJECT_ID \
  -c STANDARD \
  -l $REGION \
  -b on \
  gs://transcript-media-prod-$PROJECT_ID/

# Enable versioning
gsutil versioning set on gs://transcript-media-prod-$PROJECT_ID/

# Set lifecycle policy
cat > lifecycle.json <<EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
        "condition": {"age": 30}
      },
      {
        "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
        "condition": {"age": 90}
      },
      {
        "action": {"type": "Delete"},
        "condition": {"age": 365}
      }
    ]
  }
}
EOF

gsutil lifecycle set lifecycle.json gs://transcript-media-prod-$PROJECT_ID/

# Set CORS for web access (if needed)
cat > cors.json <<EOF
[
  {
    "origin": ["https://app.example.com"],
    "method": ["GET", "HEAD"],
    "responseHeader": ["Content-Type"],
    "maxAgeSeconds": 3600
  }
]
EOF

gsutil cors set cors.json gs://transcript-media-prod-$PROJECT_ID/
```

### 2. Configure Filestore (for shared storage)

```bash
# Create Filestore instance for persistent volumes
gcloud filestore instances create transcript-filestore \
  --zone=$ZONE \
  --tier=STANDARD \
  --file-share=name=data,capacity=1TB \
  --network=name=transcript-vpc

# Get Filestore IP
FILESTORE_IP=$(gcloud filestore instances describe transcript-filestore \
  --zone=$ZONE \
  --format="value(networks[0].ipAddresses[0])")
```

## Memorystore Redis

```bash
# Create Memorystore Redis instance
gcloud redis instances create transcript-redis \
  --size=5 \
  --region=$REGION \
  --tier=standard-ha \
  --redis-version=redis_7_0 \
  --network=projects/$PROJECT_ID/global/networks/transcript-vpc \
  --redis-config maxmemory-policy=allkeys-lru

# Get Redis host
REDIS_HOST=$(gcloud redis instances describe transcript-redis \
  --region=$REGION \
  --format="value(host)")
```

## Secrets Management

```bash
# Create secrets in Secret Manager
echo -n "postgresql+psycopg://transcript-user:password@10.x.x.x:5432/transcripts" | \
  gcloud secrets create database-url --data-file=-

echo -n "$(openssl rand -hex 32)" | \
  gcloud secrets create session-secret --data-file=-

echo -n "hf_your_token" | \
  gcloud secrets create hf-token --data-file=-

# Grant access to GKE service account
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud secrets add-iam-policy-binding database-url \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# For Workload Identity
gcloud secrets add-iam-policy-binding database-url \
  --member="serviceAccount:$PROJECT_ID.svc.id.goog[transcript-create/transcript-api]" \
  --role="roles/secretmanager.secretAccessor"
```

## Deploy Application

### 1. Create Kubernetes Secrets

```bash
kubectl create namespace transcript-create

# Create secret from GCP Secret Manager
kubectl create secret generic transcript-secrets \
  --from-literal=database-url="$(gcloud secrets versions access latest --secret=database-url)" \
  --from-literal=session-secret="$(gcloud secrets versions access latest --secret=session-secret)" \
  --from-literal=hf-token="$(gcloud secrets versions access latest --secret=hf-token)" \
  --namespace=transcript-create
```

### 2. Deploy with Helm

```bash
# Clone repository
git clone https://github.com/subculture-collective/transcript-create.git
cd transcript-create

# Create values file
cat > gcp-values.yaml <<EOF
global:
  environment: production
  domain: api.example.com

image:
  repository: gcr.io/$PROJECT_ID/transcript-create
  tag: "1.0.0"

api:
  replicaCount: 5
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 2000m
      memory: 4Gi
  ingress:
    enabled: true
    className: nginx
    annotations:
      cert-manager.io/cluster-issuer: letsencrypt-prod
    hosts:
      - host: api.example.com
        paths:
          - path: /
            pathType: Prefix
    tls:
      - secretName: transcript-tls
        hosts:
          - api.example.com

worker:
  replicaCount: 2
  gpu:
    enabled: true
    type: nvidia
    count: 1
  resources:
    requests:
      cpu: 2000m
      memory: 8Gi
    limits:
      cpu: 4000m
      memory: 16Gi
      nvidia.com/gpu: 1

persistence:
  data:
    enabled: true
    storageClass: "standard-rwo"
    size: 500Gi

secrets:
  existingSecret: transcript-secrets

monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
EOF

# Install
helm install transcript-create ./charts/transcript-create \
  -f gcp-values.yaml \
  --namespace transcript-create \
  --create-namespace
```

## Monitoring

### 1. Cloud Monitoring

```bash
# Enable Cloud Monitoring
gcloud services enable monitoring.googleapis.com

# Create notification channel (email)
gcloud alpha monitoring channels create \
  --display-name="Admin Email" \
  --type=email \
  --channel-labels=email_address=admin@example.com

# Create alert policy for high CPU
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="High CPU Alert" \
  --condition-display-name="CPU usage > 80%" \
  --condition-threshold-value=0.8 \
  --condition-threshold-duration=300s \
  --condition-filter='resource.type="k8s_container" AND metric.type="kubernetes.io/container/cpu/core_usage_time"'
```

### 2. Cloud Logging

```bash
# View logs
gcloud logging read "resource.type=k8s_container AND resource.labels.namespace_name=transcript-create" \
  --limit 50 \
  --format json

# Create log-based metric
gcloud logging metrics create error_count \
  --description="Count of error logs" \
  --log-filter='resource.type="k8s_container" AND jsonPayload.level="ERROR"'
```

## Cost Optimization

### Monthly Cost Estimates

**Small Deployment:**
- GKE cluster (3 n1-standard-4 nodes): $270
- GPU node pool (1 n1-standard-4 + T4): $450
- Cloud SQL (db-custom-4-16384): $400
- Memorystore Redis (5GB HA): $140
- Cloud Storage (500GB): $10
- Networking: $50
- **Total: ~$1,320/month**

**Medium Deployment:**
- GKE cluster (5 n1-standard-4 nodes): $450
- GPU node pool (2 nodes with T4): $900
- Cloud SQL (db-custom-8-32768): $800
- Memorystore Redis (10GB HA): $280
- Cloud Storage (2TB): $41
- Networking: $100
- **Total: ~$2,571/month**

### Cost Saving Tips

1. **Use Committed Use Discounts** (save 37-57%)
2. **Enable Cluster Autoscaler** to scale down during low usage
3. **Use Preemptible VMs** for non-critical workloads (save 70-80%)
4. **Right-size your instances** using GCP recommender
5. **Use Cloud Storage lifecycle policies** to move data to cheaper tiers
6. **Set budget alerts** to monitor spending

### Enable Preemptible GPU Nodes

```bash
gcloud container node-pools create gpu-pool-preemptible \
  --cluster=$CLUSTER_NAME \
  --region=$REGION \
  --preemptible \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --num-nodes=1 \
  --enable-autoscaling \
  --min-nodes=0 \
  --max-nodes=3
```

## Terraform Automation

See [terraform/gcp/](../../terraform/gcp/) for complete Terraform modules.

### Quick Start

```bash
cd terraform/gcp

# Initialize
terraform init

# Create terraform.tfvars
cat > terraform.tfvars <<EOF
project_id = "transcript-prod-12345"
region = "us-central1"
zone = "us-central1-a"
environment = "production"

# GKE
gke_node_count = 3
gke_machine_type = "n1-standard-4"
gpu_node_count = 2
gpu_machine_type = "n1-standard-4"
gpu_accelerator_type = "nvidia-tesla-t4"

# Cloud SQL
cloudsql_tier = "db-custom-4-16384"
cloudsql_disk_size = 100

# Redis
redis_memory_size_gb = 5

# Storage
storage_bucket_location = "US"

domain_name = "api.example.com"
EOF

# Apply
terraform plan
terraform apply
```

## Backup and Disaster Recovery

### Automated Backups

```bash
# Cloud SQL backups are automatic
# Manual backup
gcloud sql backups create \
  --instance=transcript-db \
  --description="Manual backup before upgrade"

# List backups
gcloud sql backups list --instance=transcript-db

# Restore from backup
gcloud sql backups restore BACKUP_ID \
  --backup-instance=transcript-db \
  --backup-instance=transcript-db-restore
```

### GKE Backup

```bash
# Install Velero with Google Cloud Storage
velero install \
  --provider gcp \
  --plugins velero/velero-plugin-for-gcp:v1.8.0 \
  --bucket transcript-velero-backups-$PROJECT_ID \
  --secret-file ./credentials-velero

# Create backup
velero backup create transcript-backup --include-namespaces transcript-create

# Schedule daily backups
velero schedule create transcript-daily \
  --schedule="0 2 * * *" \
  --include-namespaces transcript-create
```

## Troubleshooting

### Check GKE Cluster

```bash
# Check cluster status
gcloud container clusters describe $CLUSTER_NAME --region=$REGION

# Check node pools
gcloud container node-pools list --cluster=$CLUSTER_NAME --region=$REGION

# Check GPU nodes
kubectl get nodes -l gpu=nvidia
kubectl describe node <gpu-node> | grep -A 10 Allocatable
```

### Cloud SQL Connection Issues

```bash
# Test connection
gcloud sql connect transcript-db --user=transcript-user --database=transcripts

# Check Cloud SQL proxy
kubectl logs -n transcript-create deployment/transcript-api -c cloudsql-proxy
```

### Storage Issues

```bash
# Check bucket permissions
gsutil iam get gs://transcript-media-prod-$PROJECT_ID/

# Test access
gsutil ls gs://transcript-media-prod-$PROJECT_ID/
```

## Next Steps

- [ ] Set up Cloud Build for CI/CD
- [ ] Configure Cloud CDN for static assets
- [ ] Implement Cloud Armor for DDoS protection
- [ ] Set up Cloud NAT for outbound traffic
- [ ] Configure Cloud DNS for domain management
- [ ] Implement VPC Service Controls for enhanced security

## Additional Resources

- [Terraform GCP Module](../../terraform/gcp/README.md)
- [GKE Best Practices](https://cloud.google.com/kubernetes-engine/docs/best-practices)
- [Cloud SQL Best Practices](https://cloud.google.com/sql/docs/postgres/best-practices)
- [GCP Architecture Center](https://cloud.google.com/architecture)
