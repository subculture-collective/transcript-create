# Kubernetes Manifests

This directory contains raw Kubernetes manifests for deploying transcript-create without Helm.

## Files

- **api-deployment.yaml** - API service deployment with 3 replicas, health checks, and autoscaling support
- **worker-deployment.yaml** - GPU-enabled worker deployment for transcription processing
- **api-service.yaml** - ClusterIP service exposing the API
- **configmap.yaml** - Application configuration (non-sensitive)
- **secrets.yaml** - Secret template (DO NOT commit actual secrets)
- **data-pvc.yaml** - Persistent volume claims for data and cache storage
- **ingress.yaml** - Ingress configuration with TLS and rate limiting
- **hpa.yaml** - Horizontal Pod Autoscaler for API and Worker
- **poddisruptionbudget.yaml** - Pod disruption budgets for high availability
- **migrations-job.yaml** - Pre-install database migration job
- **servicemonitor.yaml** - Prometheus ServiceMonitor for metrics collection
- **networkpolicy.yaml** - Network policies for security

## Quick Start

### Prerequisites

1. Kubernetes cluster (v1.25+)
2. kubectl configured
3. Storage class with ReadWriteMany support
4. GPU nodes (for workers)
5. Ingress controller installed

### Deployment Steps

1. **Create namespace**:
   ```bash
   kubectl create namespace transcript-create
   ```

2. **Update configuration**:
   - Edit `configmap.yaml` with your settings
   - Edit `secrets.yaml` with your credentials (or use kubectl create secret)
   - Edit `data-pvc.yaml` to match your storage class
   - Edit `ingress.yaml` with your domain

3. **Create secrets** (recommended over editing secrets.yaml):
   ```bash
   kubectl create secret generic transcript-secrets \
     --from-literal=database-url='postgresql+psycopg://user:pass@host:5432/db' \
     --from-literal=session-secret="$(openssl rand -hex 32)" \
     --from-literal=hf-token='your-hf-token' \
     -n transcript-create
   ```

4. **Apply manifests**:
   ```bash
   # Apply in order
   kubectl apply -f secrets.yaml -n transcript-create  # Or skip if using kubectl create secret
   kubectl apply -f configmap.yaml -n transcript-create
   kubectl apply -f data-pvc.yaml -n transcript-create
   kubectl apply -f migrations-job.yaml -n transcript-create
   
   # Wait for migrations
   kubectl wait --for=condition=complete job/transcript-migrations -n transcript-create --timeout=300s
   
   # Deploy services
   kubectl apply -f api-deployment.yaml -n transcript-create
   kubectl apply -f worker-deployment.yaml -n transcript-create
   kubectl apply -f api-service.yaml -n transcript-create
   kubectl apply -f ingress.yaml -n transcript-create
   
   # Apply autoscaling and policies
   kubectl apply -f hpa.yaml -n transcript-create
   kubectl apply -f poddisruptionbudget.yaml -n transcript-create
   
   # Optional: monitoring and network policies
   kubectl apply -f servicemonitor.yaml -n transcript-create
   kubectl apply -f networkpolicy.yaml -n transcript-create
   ```

5. **Verify deployment**:
   ```bash
   kubectl get pods -n transcript-create
   kubectl get svc -n transcript-create
   kubectl get ingress -n transcript-create
   ```

## Configuration

### GPU Type

The worker deployment is configured for AMD ROCm GPUs by default. To use NVIDIA GPUs:

1. Update `worker-deployment.yaml`:
   - Change `amd.com/gpu: 1` to `nvidia.com/gpu: 1`
   - Update tolerations from `amd.com/gpu` to `nvidia.com/gpu`
   - Remove ROCm device mounts (`/dev/kfd`, `/dev/dri`)

### Storage Class

Update the `storageClassName` in `data-pvc.yaml` to match your cluster:
- GKE: `standard-rwo` or use Filestore
- EKS: `gp2` or use EFS
- AKS: `default` or `azurefile`

### Resource Limits

Adjust resource requests/limits in deployment files based on your needs:
- API: Default is 500m-2000m CPU, 1-4Gi memory
- Worker: Default is 2000m CPU, 8Gi memory, 1 GPU

## Validation

Validate manifests before applying:

```bash
# Dry-run validation
kubectl apply --dry-run=client -f api-deployment.yaml
kubectl apply --dry-run=client -f worker-deployment.yaml

# Full validation
for f in *.yaml; do
  echo "Validating $f..."
  kubectl apply --dry-run=client -f "$f"
done
```

## Monitoring

If you have Prometheus Operator installed:

```bash
kubectl apply -f servicemonitor.yaml -n transcript-create
```

This will configure Prometheus to scrape metrics from:
- API: `http://transcript-api:8000/metrics`
- Worker: Pod metrics via PodMonitor

## Security

### Network Policies

Apply network policies to restrict traffic:

```bash
kubectl apply -f networkpolicy.yaml -n transcript-create
```

This configures:
- Default deny all traffic
- Allow API ingress from ingress controller
- Allow API/Worker egress to database, Redis, OpenSearch
- Allow Prometheus to scrape metrics

### Pod Security

Deployments follow Pod Security Standards:
- Run as non-root user (UID 1000)
- Read-only root filesystem where possible
- Drop all capabilities
- No privilege escalation

## Troubleshooting

### Pods not starting

```bash
kubectl describe pod <pod-name> -n transcript-create
kubectl logs <pod-name> -n transcript-create
```

### Database connection issues

Test connectivity:
```bash
kubectl run -it --rm debug --image=postgres:16 --restart=Never -n transcript-create -- \
  psql "postgresql://user:pass@host:5432/db"
```

### GPU not available

Check GPU resources:
```bash
kubectl describe node <gpu-node-name>
kubectl get pod <worker-pod> -n transcript-create -o yaml | grep -A 5 resources
```

## Upgrades

To update the deployment:

1. Update the image tag in deployment files
2. Apply the updated manifests:
   ```bash
   kubectl apply -f api-deployment.yaml -n transcript-create
   kubectl apply -f worker-deployment.yaml -n transcript-create
   ```

3. Monitor rollout:
   ```bash
   kubectl rollout status deployment/transcript-api -n transcript-create
   kubectl rollout status deployment/transcript-worker -n transcript-create
   ```

## Cleanup

To remove the deployment:

```bash
kubectl delete namespace transcript-create
```

Or delete individual resources:

```bash
kubectl delete -f . -n transcript-create
```

## Next Steps

For a more flexible deployment, consider using the Helm chart:
- See `charts/transcript-create/` directory
- Refer to `docs/kubernetes/README.md` for detailed guide

## Support

For issues and questions:
- GitHub Issues: https://github.com/subculture-collective/transcript-create/issues
- Full documentation: https://github.com/subculture-collective/transcript-create/tree/main/docs/kubernetes
