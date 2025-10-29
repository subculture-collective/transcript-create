# Terraform AWS Infrastructure for Transcript Create

This directory contains Terraform modules for deploying transcript-create on AWS.

## Architecture

The Terraform configuration creates:

- **VPC**: Custom VPC with public and private subnets
- **RDS**: PostgreSQL 16 database with automated backups
- **ElastiCache**: Redis cluster for caching
- **ECS**: Fargate cluster for API
- **EC2**: GPU instances for workers (optional)
- **ALB**: Application Load Balancer with SSL
- **S3**: Media storage bucket
- **Secrets Manager**: Secure credential storage
- **CloudWatch**: Monitoring and logging

## Prerequisites

```bash
# Install Terraform
terraform version  # Should be 1.5+

# Configure AWS credentials
aws configure

# Or use environment variables
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="us-east-1"
```

## Quick Start

```bash
# Initialize Terraform
terraform init

# Copy and edit variables
cp terraform.tfvars.example terraform.tfvars
vim terraform.tfvars

# Plan deployment
terraform plan

# Apply configuration
terraform apply

# Get outputs
terraform output
```

## Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `aws_region` | AWS region | `us-east-1` |
| `environment` | Environment name | `production` |
| `domain_name` | Domain for API | `api.example.com` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `vpc_cidr` | `10.0.0.0/16` | VPC CIDR block |
| `db_instance_class` | `db.t3.medium` | RDS instance type |
| `redis_node_type` | `cache.t3.medium` | ElastiCache node type |
| `ecs_api_count` | `3` | Number of API tasks |
| `ec2_worker_instance_type` | `g4dn.xlarge` | GPU instance type |
| `ec2_worker_count` | `2` | Number of worker instances |

See `variables.tf` for complete list.

## Modules

### VPC Module
Creates VPC, subnets, NAT gateways, and route tables.

### Database Module
Provisions RDS PostgreSQL with automated backups and monitoring.

### Cache Module
Sets up ElastiCache Redis cluster with automatic failover.

### ECS Module
Deploys API on ECS Fargate with auto-scaling.

### EC2 Module
Launches GPU instances for workers with auto-scaling group.

### Storage Module
Creates S3 bucket with lifecycle policies and encryption.

### Load Balancer Module
Configures ALB with SSL termination and health checks.

## Outputs

After successful deployment:

```bash
# Get all outputs
terraform output

# Get specific output
terraform output database_endpoint
terraform output redis_endpoint
terraform output alb_dns_name
```

## Customization

### Use Spot Instances

Edit `terraform.tfvars`:
```hcl
ec2_worker_spot_enabled = true
ec2_worker_spot_max_price = "0.40"
```

### Enable Multi-AZ

```hcl
db_multi_az = true
redis_num_cache_clusters = 2
```

### Adjust Resources

```hcl
db_instance_class = "db.m5.large"
redis_node_type = "cache.m5.large"
ecs_api_cpu = 2048
ecs_api_memory = 4096
```

## Cost Estimation

Use AWS Pricing Calculator or:

```bash
# Install infracost
brew install infracost

# Get cost estimate
infracost breakdown --path .
```

**Approximate Monthly Costs:**

- Small setup: $600-800
- Medium setup: $1,500-2,000
- Large setup: $3,000-5,000

## Deployment Workflow

### 1. Plan

```bash
terraform plan -out=tfplan
```

### 2. Review

Check the plan carefully, especially:
- Resource creations/deletions
- Security group changes
- Database modifications

### 3. Apply

```bash
terraform apply tfplan
```

### 4. Verify

```bash
# Check resources
aws ecs list-tasks --cluster transcript-prod
aws rds describe-db-instances --db-instance-identifier transcript-db

# Test API
curl https://$(terraform output -raw alb_dns_name)/health
```

## State Management

### Local State (Development)

State is stored locally in `terraform.tfstate`.

**⚠️ Warning**: Local state is not suitable for production.

### Remote State (Production)

Use S3 backend:

```hcl
# backend.tf
terraform {
  backend "s3" {
    bucket = "transcript-terraform-state"
    key    = "production/terraform.tfstate"
    region = "us-east-1"
    encrypt = true
    dynamodb_table = "terraform-locks"
  }
}
```

Create S3 bucket and DynamoDB table first:

```bash
# Create S3 bucket
aws s3 mb s3://transcript-terraform-state
aws s3api put-bucket-versioning \
  --bucket transcript-terraform-state \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for locks
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

## Maintenance

### Updates

```bash
# Update Terraform providers
terraform init -upgrade

# Plan changes
terraform plan

# Apply updates
terraform apply
```

### Backups

Terraform state is critical:

```bash
# Backup state
terraform state pull > terraform.tfstate.backup

# For S3 backend, enable versioning (already done above)
```

### Cleanup

```bash
# Destroy all resources
terraform destroy

# Destroy specific resource
terraform destroy -target=module.ec2_workers
```

## Troubleshooting

### State Lock

```bash
# If state is locked
terraform force-unlock <lock-id>
```

### Import Existing Resources

```bash
# Import existing resource
terraform import aws_s3_bucket.media transcript-media-prod
```

### Debug

```bash
# Enable debug logging
export TF_LOG=DEBUG
terraform plan
```

## Security Best Practices

1. **Never commit secrets** to version control
2. **Use Secrets Manager** for credentials
3. **Enable encryption** at rest and in transit
4. **Restrict security groups** to minimum required
5. **Enable CloudTrail** for audit logging
6. **Use IAM roles** instead of access keys where possible
7. **Regular security updates** via automated patching

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Terraform Deploy
on:
  push:
    branches: [main]

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        
      - name: Terraform Init
        run: terraform init
        
      - name: Terraform Plan
        run: terraform plan
        
      - name: Terraform Apply
        if: github.ref == 'refs/heads/main'
        run: terraform apply -auto-approve
```

## Support

- GitHub Issues: https://github.com/subculture-collective/transcript-create/issues
- AWS Deployment Guide: [../../docs/deployment/aws.md](../../docs/deployment/aws.md)
- Terraform Documentation: https://www.terraform.io/docs
