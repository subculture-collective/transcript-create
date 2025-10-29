# AWS Deployment Guide

Complete guide for deploying transcript-create on Amazon Web Services (AWS) using ECS/Fargate, EC2 with GPU, RDS, and other managed services.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Deployment Options](#deployment-options)
4. [ECS/Fargate Deployment](#ecsfargate-deployment)
5. [EKS with GPU Nodes](#eks-with-gpu-nodes)
6. [EC2 Self-Managed](#ec2-self-managed)
7. [Database Setup (RDS)](#database-setup-rds)
8. [Storage (S3)](#storage-s3)
9. [Networking](#networking)
10. [Monitoring and Logging](#monitoring-and-logging)
11. [Security](#security)
12. [Cost Optimization](#cost-optimization)
13. [Terraform Automation](#terraform-automation)

## Architecture Overview

### Production Architecture

```
Internet
    │
    ↓
Route53 (DNS)
    │
    ↓
ALB/CloudFront
    │
    ├──→ ECS/EKS (API) ──→ RDS PostgreSQL
    │        │               │
    │        └──→ ElastiCache Redis
    │
    └──→ EC2/EKS (Workers) ──→ S3 (Media)
              │
              └──→ GPU Processing
```

### Components

- **Compute**: ECS Fargate (API), EC2 GPU instances (Workers)
- **Database**: RDS PostgreSQL
- **Cache**: ElastiCache Redis
- **Storage**: S3 for media files
- **Networking**: VPC, ALB, Route53
- **Monitoring**: CloudWatch, X-Ray
- **Security**: IAM, Secrets Manager, KMS

## Prerequisites

### AWS Account Setup

```bash
# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure AWS credentials
aws configure
# AWS Access Key ID: your-key-id
# AWS Secret Access Key: your-secret-key
# Default region: us-east-1
# Default output format: json

# Verify configuration
aws sts get-caller-identity
```

### Install Required Tools

```bash
# eksctl (for EKS)
curl --silent --location "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin

# Terraform
wget https://releases.hashicorp.com/terraform/1.6.0/terraform_1.6.0_linux_amd64.zip
unzip terraform_1.6.0_linux_amd64.zip
sudo mv terraform /usr/local/bin/

# Verify installations
aws --version
eksctl version
terraform version
```

### Required AWS Services

Enable these services in your AWS account:
- EC2
- ECS or EKS
- RDS
- ElastiCache
- S3
- VPC
- Route53
- CloudWatch
- Secrets Manager
- Systems Manager

## Deployment Options

| Option | Best For | Pros | Cons | Monthly Cost* |
|--------|----------|------|------|---------------|
| ECS Fargate | Simple deployments, API-only | Serverless, no server management | Limited GPU support | $200-400 |
| EKS + EC2 GPU | Production with GPU | Full control, scalable | More complex | $500-1000 |
| EC2 Self-Managed | Custom requirements | Maximum flexibility | Manual management | $400-800 |

*Estimated costs for small-medium workloads

## ECS/Fargate Deployment

### 1. Create VPC and Networking

```bash
# Create VPC with public and private subnets
aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=transcript-vpc}]'

# Get VPC ID
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=tag:Name,Values=transcript-vpc" \
  --query 'Vpcs[0].VpcId' --output text)

# Create subnets
aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.1.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=transcript-public-1a}]'

aws ec2 create-subnet \
  --vpc-id $VPC_ID \
  --cidr-block 10.0.2.0/24 \
  --availability-zone us-east-1b \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=transcript-public-1b}]'

# Create Internet Gateway
aws ec2 create-internet-gateway \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=transcript-igw}]'

IGW_ID=$(aws ec2 describe-internet-gateways \
  --filters "Name=tag:Name,Values=transcript-igw" \
  --query 'InternetGateways[0].InternetGatewayId' --output text)

aws ec2 attach-internet-gateway --vpc-id $VPC_ID --internet-gateway-id $IGW_ID
```

### 2. Create RDS Database

```bash
# Create DB subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name transcript-db-subnet \
  --db-subnet-group-description "Transcript DB subnet group" \
  --subnet-ids subnet-xxx subnet-yyy

# Create security group for RDS
aws ec2 create-security-group \
  --group-name transcript-db-sg \
  --description "Security group for transcript RDS" \
  --vpc-id $VPC_ID

DB_SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=transcript-db-sg" \
  --query 'SecurityGroups[0].GroupId' --output text)

# Allow PostgreSQL from VPC
aws ec2 authorize-security-group-ingress \
  --group-id $DB_SG_ID \
  --protocol tcp \
  --port 5432 \
  --cidr 10.0.0.0/16

# Create RDS instance
aws rds create-db-instance \
  --db-instance-identifier transcript-db \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --engine-version 16.1 \
  --master-username postgres \
  --master-user-password "$(openssl rand -base64 32)" \
  --allocated-storage 100 \
  --storage-type gp3 \
  --storage-encrypted \
  --db-subnet-group-name transcript-db-subnet \
  --vpc-security-group-ids $DB_SG_ID \
  --backup-retention-period 7 \
  --preferred-backup-window "03:00-04:00" \
  --preferred-maintenance-window "sun:04:00-sun:05:00" \
  --enable-cloudwatch-logs-exports '["postgresql"]' \
  --multi-az

# Wait for database to be available
aws rds wait db-instance-available --db-instance-identifier transcript-db

# Get database endpoint
DB_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier transcript-db \
  --query 'DBInstances[0].Endpoint.Address' --output text)

echo "Database endpoint: $DB_ENDPOINT"
```

### 3. Create ElastiCache Redis

```bash
# Create cache subnet group
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name transcript-redis-subnet \
  --cache-subnet-group-description "Transcript Redis subnet group" \
  --subnet-ids subnet-xxx subnet-yyy

# Create security group for Redis
aws ec2 create-security-group \
  --group-name transcript-redis-sg \
  --description "Security group for transcript Redis" \
  --vpc-id $VPC_ID

REDIS_SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=transcript-redis-sg" \
  --query 'SecurityGroups[0].GroupId' --output text)

# Allow Redis from VPC
aws ec2 authorize-security-group-ingress \
  --group-id $REDIS_SG_ID \
  --protocol tcp \
  --port 6379 \
  --cidr 10.0.0.0/16

# Create Redis cluster
aws elasticache create-replication-group \
  --replication-group-id transcript-redis \
  --replication-group-description "Transcript Redis cluster" \
  --engine redis \
  --cache-node-type cache.t3.medium \
  --num-cache-clusters 2 \
  --automatic-failover-enabled \
  --cache-subnet-group-name transcript-redis-subnet \
  --security-group-ids $REDIS_SG_ID \
  --at-rest-encryption-enabled \
  --transit-encryption-enabled

# Get Redis endpoint
REDIS_ENDPOINT=$(aws elasticache describe-replication-groups \
  --replication-group-id transcript-redis \
  --query 'ReplicationGroups[0].NodeGroups[0].PrimaryEndpoint.Address' --output text)

echo "Redis endpoint: $REDIS_ENDPOINT"
```

### 4. Create S3 Bucket

```bash
# Create S3 bucket
aws s3 mb s3://transcript-media-prod-${AWS_ACCOUNT_ID}

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket transcript-media-prod-${AWS_ACCOUNT_ID} \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket transcript-media-prod-${AWS_ACCOUNT_ID} \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      },
      "BucketKeyEnabled": true
    }]
  }'

# Set lifecycle policy
aws s3api put-bucket-lifecycle-configuration \
  --bucket transcript-media-prod-${AWS_ACCOUNT_ID} \
  --lifecycle-configuration file://s3-lifecycle.json
```

**s3-lifecycle.json:**
```json
{
  "Rules": [
    {
      "Id": "DeleteOldMedia",
      "Status": "Enabled",
      "Filter": {},
      "Expiration": {
        "Days": 90
      }
    },
    {
      "Id": "TransitionToIA",
      "Status": "Enabled",
      "Filter": {},
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        }
      ]
    }
  ]
}
```

### 5. Store Secrets

```bash
# Create secrets in Secrets Manager
aws secretsmanager create-secret \
  --name transcript/database-url \
  --secret-string "postgresql+psycopg://postgres:password@${DB_ENDPOINT}:5432/transcripts"

aws secretsmanager create-secret \
  --name transcript/session-secret \
  --secret-string "$(openssl rand -hex 32)"

aws secretsmanager create-secret \
  --name transcript/stripe-api-key \
  --secret-string "sk_live_..."

aws secretsmanager create-secret \
  --name transcript/hf-token \
  --secret-string "hf_..."
```

### 6. Create ECS Cluster

```bash
# Create ECS cluster
aws ecs create-cluster \
  --cluster-name transcript-prod \
  --capacity-providers FARGATE FARGATE_SPOT \
  --default-capacity-provider-strategy \
    capacityProvider=FARGATE,weight=1,base=2 \
    capacityProvider=FARGATE_SPOT,weight=4

# Create ECR repository
aws ecr create-repository \
  --repository-name transcript-create \
  --encryption-configuration encryptionType=AES256

# Get ECR login
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com

# Build and push image
docker build -t transcript-create .
docker tag transcript-create:latest ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/transcript-create:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/transcript-create:latest
```

### 7. Create Task Definition

**task-definition.json:**
```json
{
  "family": "transcript-api",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/transcriptTaskRole",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/transcript-create:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "ENVIRONMENT", "value": "production"},
        {"name": "LOG_LEVEL", "value": "INFO"},
        {"name": "REDIS_URL", "value": "redis://${REDIS_ENDPOINT}:6379/0"}
      ],
      "secrets": [
        {
          "name": "DATABASE_URL",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:${AWS_ACCOUNT_ID}:secret:transcript/database-url"
        },
        {
          "name": "SESSION_SECRET",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:${AWS_ACCOUNT_ID}:secret:transcript/session-secret"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/transcript-api",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "api"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

```bash
# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

### 8. Create Application Load Balancer

```bash
# Create ALB
aws elbv2 create-load-balancer \
  --name transcript-alb \
  --subnets subnet-xxx subnet-yyy \
  --security-groups sg-xxx \
  --scheme internet-facing \
  --type application

ALB_ARN=$(aws elbv2 describe-load-balancers \
  --names transcript-alb \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

# Create target group
aws elbv2 create-target-group \
  --name transcript-api-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-path /health \
  --health-check-interval-seconds 30 \
  --health-check-timeout-seconds 5 \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3

TG_ARN=$(aws elbv2 describe-target-groups \
  --names transcript-api-tg \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

# Create listener with SSL
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:us-east-1:${AWS_ACCOUNT_ID}:certificate/xxx \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN

# Redirect HTTP to HTTPS
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTP \
  --port 80 \
  --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'
```

### 9. Create ECS Service

```bash
# Create ECS service
aws ecs create-service \
  --cluster transcript-prod \
  --service-name transcript-api \
  --task-definition transcript-api \
  --desired-count 3 \
  --launch-type FARGATE \
  --platform-version LATEST \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx,subnet-yyy],securityGroups=[sg-xxx],assignPublicIp=DISABLED}" \
  --load-balancers targetGroupArn=$TG_ARN,containerName=api,containerPort=8000 \
  --health-check-grace-period-seconds 60 \
  --deployment-configuration "maximumPercent=200,minimumHealthyPercent=100,deploymentCircuitBreaker={enable=true,rollback=true}"

# Enable auto-scaling
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/transcript-prod/transcript-api \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 3 \
  --max-capacity 10

aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/transcript-prod/transcript-api \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name transcript-api-cpu-scaling \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

**scaling-policy.json:**
```json
{
  "TargetValue": 70.0,
  "PredefinedMetricSpecification": {
    "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
  },
  "ScaleInCooldown": 300,
  "ScaleOutCooldown": 60
}
```

## EKS with GPU Nodes

### 1. Create EKS Cluster

```bash
# Create EKS cluster with managed node group
eksctl create cluster \
  --name transcript-prod \
  --region us-east-1 \
  --version 1.28 \
  --nodegroup-name standard-workers \
  --node-type m5.xlarge \
  --nodes 3 \
  --nodes-min 3 \
  --nodes-max 6 \
  --managed \
  --with-oidc \
  --ssh-access \
  --ssh-public-key ~/.ssh/id_rsa.pub

# Add GPU node group
eksctl create nodegroup \
  --cluster transcript-prod \
  --name gpu-workers \
  --node-type g4dn.xlarge \
  --nodes 2 \
  --nodes-min 1 \
  --nodes-max 4 \
  --node-labels gpu=nvidia \
  --node-taints nvidia.com/gpu=:NoSchedule

# Install NVIDIA device plugin
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/v0.14.0/nvidia-device-plugin.yml

# Verify GPU nodes
kubectl get nodes -l gpu=nvidia
```

### 2. Install AWS Load Balancer Controller

```bash
# Download IAM policy
curl -o iam-policy.json https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json

# Create IAM policy
aws iam create-policy \
  --policy-name AWSLoadBalancerControllerIAMPolicy \
  --policy-document file://iam-policy.json

# Create service account
eksctl create iamserviceaccount \
  --cluster=transcript-prod \
  --namespace=kube-system \
  --name=aws-load-balancer-controller \
  --attach-policy-arn=arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy \
  --approve

# Install controller
helm repo add eks https://aws.github.io/eks-charts
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=transcript-prod \
  --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller
```

### 3. Deploy Application

Follow the [Kubernetes deployment guide](./kubernetes.md) with AWS-specific configurations.

## EC2 Self-Managed

### 1. Launch GPU Instance

```bash
# Launch g4dn.xlarge instance with NVIDIA T4 GPU
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type g4dn.xlarge \
  --key-name my-key-pair \
  --security-group-ids sg-xxx \
  --subnet-id subnet-xxx \
  --iam-instance-profile Name=TranscriptWorkerRole \
  --block-device-mappings '[
    {
      "DeviceName": "/dev/sda1",
      "Ebs": {
        "VolumeSize": 100,
        "VolumeType": "gp3",
        "DeleteOnTermination": true
      }
    }
  ]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=transcript-worker}]' \
  --user-data file://user-data.sh
```

**user-data.sh:**
```bash
#!/bin/bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install NVIDIA drivers and Docker runtime
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  tee /etc/apt/sources.list.d/nvidia-docker.list

apt-get update
apt-get install -y nvidia-driver-535 nvidia-container-toolkit
systemctl restart docker

# Pull and run worker
docker pull ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/transcript-create:latest
docker run -d \
  --name transcript-worker \
  --gpus all \
  --restart unless-stopped \
  -v /data:/data \
  -e DATABASE_URL="$(aws secretsmanager get-secret-value --secret-id transcript/database-url --query SecretString --output text)" \
  ${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/transcript-create:latest \
  python -m worker.loop
```

### 2. Create Auto Scaling Group

```bash
# Create launch template
aws ec2 create-launch-template \
  --launch-template-name transcript-worker-template \
  --version-description "v1" \
  --launch-template-data file://launch-template.json

# Create auto scaling group
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name transcript-workers \
  --launch-template LaunchTemplateName=transcript-worker-template \
  --min-size 1 \
  --max-size 4 \
  --desired-capacity 2 \
  --vpc-zone-identifier "subnet-xxx,subnet-yyy" \
  --health-check-type EC2 \
  --health-check-grace-period 300 \
  --tags Key=Name,Value=transcript-worker,PropagateAtLaunch=true
```

## Database Setup (RDS)

### Performance Optimization

```bash
# Create parameter group
aws rds create-db-parameter-group \
  --db-parameter-group-name transcript-postgres16 \
  --db-parameter-group-family postgres16 \
  --description "Optimized parameters for transcript-create"

# Modify parameters
aws rds modify-db-parameter-group \
  --db-parameter-group-name transcript-postgres16 \
  --parameters \
    "ParameterName=max_connections,ParameterValue=200,ApplyMethod=immediate" \
    "ParameterName=shared_buffers,ParameterValue='{DBInstanceClassMemory/4}',ApplyMethod=pending-reboot" \
    "ParameterName=effective_cache_size,ParameterValue='{DBInstanceClassMemory*3/4}',ApplyMethod=immediate" \
    "ParameterName=maintenance_work_mem,ParameterValue=524288,ApplyMethod=immediate" \
    "ParameterName=checkpoint_completion_target,ParameterValue=0.9,ApplyMethod=immediate" \
    "ParameterName=wal_buffers,ParameterValue=2048,ApplyMethod=pending-reboot"

# Apply parameter group
aws rds modify-db-instance \
  --db-instance-identifier transcript-db \
  --db-parameter-group-name transcript-postgres16 \
  --apply-immediately
```

### Automated Backups

```bash
# Enable automated backups with 30-day retention
aws rds modify-db-instance \
  --db-instance-identifier transcript-db \
  --backup-retention-period 30 \
  --preferred-backup-window "03:00-04:00" \
  --apply-immediately

# Create manual snapshot
aws rds create-db-snapshot \
  --db-instance-identifier transcript-db \
  --db-snapshot-identifier transcript-manual-$(date +%Y%m%d)
```

## Storage (S3)

### Configure S3 Integration

Update application to use S3 for media storage:

```python
# In .env or environment variables
MEDIA_STORAGE_BACKEND=s3
S3_BUCKET=transcript-media-prod-${AWS_ACCOUNT_ID}
S3_REGION=us-east-1
```

### S3 Lifecycle Policies

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket transcript-media-prod-${AWS_ACCOUNT_ID} \
  --lifecycle-configuration file://s3-lifecycle.json
```

## Networking

### VPC Best Practices

- Public subnets for ALB
- Private subnets for ECS/EKS, RDS, ElastiCache
- Use NAT Gateways for outbound internet access
- Enable VPC Flow Logs
- Use Security Groups and NACLs

### Route53 Configuration

```bash
# Create hosted zone
aws route53 create-hosted-zone \
  --name api.example.com \
  --caller-reference $(date +%s)

# Get ALB DNS
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --names transcript-alb \
  --query 'LoadBalancers[0].DNSName' --output text)

# Create A record
aws route53 change-resource-record-sets \
  --hosted-zone-id Z1234567890ABC \
  --change-batch file://route53-change.json
```

**route53-change.json:**
```json
{
  "Changes": [{
    "Action": "CREATE",
    "ResourceRecordSet": {
      "Name": "api.example.com",
      "Type": "A",
      "AliasTarget": {
        "HostedZoneId": "Z35SXDOTRQ7X7K",
        "DNSName": "${ALB_DNS}",
        "EvaluateTargetHealth": true
      }
    }
  }]
}
```

## Monitoring and Logging

### CloudWatch Dashboards

```bash
# Create dashboard
aws cloudwatch put-dashboard \
  --dashboard-name transcript-prod \
  --dashboard-body file://dashboard.json
```

### CloudWatch Alarms

```bash
# CPU alarm
aws cloudwatch put-metric-alarm \
  --alarm-name transcript-api-high-cpu \
  --alarm-description "Alert when API CPU exceeds 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/ECS \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=ServiceName,Value=transcript-api Name=ClusterName,Value=transcript-prod

# RDS storage alarm
aws cloudwatch put-metric-alarm \
  --alarm-name transcript-db-low-storage \
  --alarm-description "Alert when RDS free storage is low" \
  --metric-name FreeStorageSpace \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 10737418240 \
  --comparison-operator LessThanThreshold \
  --dimensions Name=DBInstanceIdentifier,Value=transcript-db
```

### X-Ray Tracing

Enable X-Ray in task definition:

```json
{
  "containerDefinitions": [{
    "environment": [
      {"name": "AWS_XRAY_TRACING_NAME", "value": "transcript-api"},
      {"name": "AWS_XRAY_DAEMON_ADDRESS", "value": "xray-daemon:2000"}
    ]
  }]
}
```

## Security

### IAM Roles

**ECS Task Execution Role:**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "secretsmanager:GetSecretValue"
    ],
    "Resource": "*"
  }]
}
```

**Task Role:**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject"
    ],
    "Resource": "arn:aws:s3:::transcript-media-prod-*/*"
  }]
}
```

### Secrets Rotation

```bash
# Enable automatic rotation
aws secretsmanager rotate-secret \
  --secret-id transcript/database-password \
  --rotation-lambda-arn arn:aws:lambda:us-east-1:${AWS_ACCOUNT_ID}:function:SecretsManagerRDSPostgreSQLRotationSingleUser \
  --rotation-rules AutomaticallyAfterDays=30
```

## Cost Optimization

### Monthly Cost Estimates

**Small Deployment:**
- ECS Fargate (API): 3 tasks × 1 vCPU, 2GB = $100
- EC2 g4dn.xlarge (Worker): 1 instance = $350
- RDS db.t3.medium: $80
- ElastiCache cache.t3.medium: $50
- S3: 500GB = $12
- Data transfer: $20
- **Total: ~$600/month**

**Medium Deployment:**
- ECS Fargate (API): 5 tasks × 1 vCPU, 2GB = $167
- EC2 g4dn.xlarge (Workers): 2 instances = $700
- RDS db.m5.large: $300
- ElastiCache cache.m5.large: $180
- S3: 2TB = $48
- ALB: $25
- Data transfer: $100
- **Total: ~$1,520/month**

### Cost Saving Tips

1. **Use Spot Instances** for workers (60-70% savings)
2. **Right-size RDS** based on actual usage
3. **Use S3 Intelligent-Tiering** for automatic cost optimization
4. **Enable ECS Fargate Spot** for non-critical tasks
5. **Use Reserved Instances** for predictable workloads (save 30-50%)
6. **Set up S3 lifecycle policies** to move old data to Glacier
7. **Use CloudWatch alarms** to scale down during low usage

## Terraform Automation

See [terraform/aws/](../../terraform/aws/) for complete Terraform modules.

### Quick Start

```bash
cd terraform/aws

# Initialize Terraform
terraform init

# Create terraform.tfvars
cat > terraform.tfvars <<EOF
aws_region = "us-east-1"
environment = "production"
vpc_cidr = "10.0.0.0/16"
db_instance_class = "db.t3.medium"
redis_node_type = "cache.t3.medium"
ecs_api_count = 3
ec2_worker_instance_type = "g4dn.xlarge"
ec2_worker_count = 2
domain_name = "api.example.com"
EOF

# Plan
terraform plan

# Apply
terraform apply
```

## Troubleshooting

### ECS Task Failures

```bash
# View task logs
aws logs tail /ecs/transcript-api --follow

# Describe stopped tasks
aws ecs describe-tasks \
  --cluster transcript-prod \
  --tasks task-id
```

### RDS Connection Issues

```bash
# Test connection from ECS task
aws ecs execute-command \
  --cluster transcript-prod \
  --task task-id \
  --container api \
  --interactive \
  --command "/bin/bash"

# Then in container:
psql $DATABASE_URL
```

### GPU Not Available

```bash
# SSH to EC2 instance
ssh -i key.pem ubuntu@instance-ip

# Check GPU
nvidia-smi

# Check Docker
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

## Next Steps

- [ ] Set up CI/CD pipeline with CodePipeline
- [ ] Configure AWS Backup for automated backups
- [ ] Implement AWS WAF for API protection
- [ ] Set up AWS CloudTrail for audit logging
- [ ] Configure AWS Config for compliance
- [ ] Implement disaster recovery to second region

## Additional Resources

- [Terraform AWS Module](../../terraform/aws/README.md)
- [ECS Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/)
- [RDS Best Practices](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_BestPractices.html)
- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
