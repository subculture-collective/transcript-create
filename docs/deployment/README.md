# Deployment Documentation Summary

This directory contains comprehensive production deployment documentation and Infrastructure as Code for transcript-create.

## Documentation

### Core Deployment Guides

1. **[Production Checklist](production-checklist.md)** - Complete pre-deployment and post-deployment checklist
2. **[Docker Compose Guide](docker-compose.md)** - Single-node production deployment with Docker Compose
3. **[Kubernetes Guide](kubernetes.md)** - Production Kubernetes deployment with Helm
4. **[Self-Hosted Guide](self-hosted.md)** - Bare-metal/VM deployment with systemd
5. **[Troubleshooting](troubleshooting.md)** - Common issues and solutions
6. **[Upgrade Guide](upgrade-guide.md)** - Zero-downtime upgrade procedures

### Cloud Provider Guides

1. **[AWS Deployment](aws.md)** - ECS/Fargate, EC2 with GPU, RDS, S3
2. **[GCP Deployment](gcp.md)** - GKE, Cloud SQL, Cloud Storage
3. **Azure Deployment** (coming soon) - AKS, Azure DB, Blob Storage

## Infrastructure as Code

### Terraform

Located in `/terraform/`:

- **AWS Module** (`terraform/aws/`) - Complete AWS infrastructure
  - VPC and networking
  - RDS PostgreSQL
  - ElastiCache Redis
  - ECS Fargate for API
  - EC2 Auto Scaling for GPU workers
  - S3 storage
  - Application Load Balancer
  - Secrets Manager

### Ansible

Located in `/ansible/`:

- **Roles:**
  - `base` - System configuration
  - `docker` - Docker installation
  - `gpu-drivers` - NVIDIA/AMD GPU drivers
  - `app` - Application deployment
  - `monitoring` - Prometheus/Grafana setup

- **Playbooks:**
  - `site.yml` - Full server setup
  - `deploy.yml` - Application deployment
  - `update.yml` - Application updates

## Deployment Options Comparison

| Method | Complexity | Best For | Downtime | GPU Support |
|--------|-----------|----------|----------|-------------|
| Docker Compose | Low | Small deployments, dev/staging | Minutes | Yes (ROCm/CUDA) |
| Kubernetes | Medium | Production, scalability | None | Yes (device plugins) |
| Self-Hosted | Medium | Maximum control, bare metal | Minutes | Yes (native) |
| AWS ECS | Low | Serverless, no GPU | None | Limited |
| AWS EKS | Medium | Production with GPU | None | Yes |
| GCP GKE | Medium | Production with GPU | None | Yes |

## Quick Start by Use Case

### Small Production (< 100 users)

**Recommended:** Docker Compose on single server

```bash
# Follow: docs/deployment/docker-compose.md
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Cost:** ~$200-400/month (dedicated server with GPU)

### Medium Production (100-1000 users)

**Recommended:** Kubernetes with Helm

```bash
# Follow: docs/deployment/kubernetes.md
helm install transcript-create ./charts/transcript-create \
  -f production-values.yaml \
  --namespace transcript-create
```

**Cost:** $500-1500/month (managed Kubernetes + GPU nodes)

### Large Production (1000+ users)

**Recommended:** Cloud provider with Terraform

```bash
# Follow: docs/deployment/aws.md or gcp.md
cd terraform/aws
terraform init
terraform apply
```

**Cost:** $1500-5000/month (auto-scaling, multi-region)

### Development/Testing

**Recommended:** Docker Compose (local)

```bash
# Use default docker-compose.yml
docker compose up
```

**Cost:** Free (local machine)

## Architecture Decision Tree

```
Start
  │
  ├─ Need GPU processing?
  │   ├─ Yes
  │   │   ├─ Cloud deployment?
  │   │   │   ├─ Yes → Use Kubernetes (EKS/GKE) with GPU nodes
  │   │   │   └─ No → Use Self-Hosted or Docker Compose
  │   │   │
  │   │   └─ High availability required?
  │   │       ├─ Yes → Kubernetes
  │   │       └─ No → Docker Compose
  │   │
  │   └─ No → Consider ECS Fargate (simplest cloud option)
  │
  ├─ Team Kubernetes experience?
  │   ├─ Yes → Kubernetes (most flexible)
  │   ├─ No → Docker Compose or managed services
  │   │
  │   └─ Want to learn? → Start with Docker Compose, migrate to K8s
  │
  └─ Budget constraints?
      ├─ Limited → Self-hosted on dedicated server
      ├─ Medium → Managed Kubernetes
      └─ No constraints → Multi-cloud with auto-scaling
```

## Common Patterns

### Pattern 1: Hybrid Deployment
- API on managed Kubernetes (auto-scaling)
- Workers on dedicated GPU servers (cost-effective)
- Database on managed service (RDS/Cloud SQL)

### Pattern 2: All-Cloud
- Everything on one cloud provider
- Use managed services where possible
- Terraform for infrastructure
- CI/CD for deployments

### Pattern 3: Self-Hosted
- Own servers or colocation
- Maximum control and cost optimization
- Ansible for automation
- Manual scaling

## Security Considerations

All deployment methods include:

- ✅ SSL/TLS encryption
- ✅ Secrets management (Vault, Secrets Manager, K8s Secrets)
- ✅ Network isolation (VPC, security groups, network policies)
- ✅ Database encryption at rest
- ✅ Automated backups
- ✅ Health checks and monitoring
- ✅ Rate limiting
- ✅ OAuth authentication

## Monitoring and Observability

All deployments support:

- **Metrics:** Prometheus + Grafana
- **Logging:** CloudWatch / Cloud Logging / ELK
- **Tracing:** OpenTelemetry / X-Ray
- **Alerts:** PagerDuty / Slack / Email

See [Production Checklist](production-checklist.md#monitoring-and-observability) for details.

## Support and Resources

### Documentation
- [Main README](../../README.md)
- [Getting Started](../getting-started.md)
- [API Reference](../api-reference.md)
- [Operations Guide](../operations/)

### External Resources
- [Terraform Documentation](https://www.terraform.io/docs)
- [Ansible Documentation](https://docs.ansible.com/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Docker Documentation](https://docs.docker.com/)

### Community
- GitHub Issues: https://github.com/subculture-collective/transcript-create/issues
- Discussions: https://github.com/subculture-collective/transcript-create/discussions

## Contributing

Improvements to deployment documentation are welcome! Please:

1. Test changes in a staging environment
2. Update relevant documentation
3. Submit PR with clear description
4. Include any new dependencies or requirements

## License

See [LICENSE](../../LICENSE) for details.
