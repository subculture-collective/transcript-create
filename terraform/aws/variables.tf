# General Variables
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "transcript"
}

variable "environment" {
  description = "Environment name (production, staging, development)"
  type        = string
  default     = "production"
}

# Networking Variables
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

# Database Variables
variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
  default     = "transcripts"
}

variable "db_username" {
  description = "PostgreSQL master username"
  type        = string
  default     = "transcript_admin"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS in GB"
  type        = number
  default     = 100
}

variable "db_multi_az" {
  description = "Enable Multi-AZ deployment for RDS"
  type        = bool
  default     = true
}

# Redis Variables
variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.medium"
}

variable "redis_num_clusters" {
  description = "Number of cache clusters (1 or 2 for HA)"
  type        = number
  default     = 2
}

# ECS Variables
variable "ecr_repository_url" {
  description = "ECR repository URL for container images"
  type        = string
}

variable "image_tag" {
  description = "Container image tag"
  type        = string
  default     = "latest"
}

variable "ecs_api_cpu" {
  description = "CPU units for API task (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "ecs_api_memory" {
  description = "Memory for API task in MB"
  type        = number
  default     = 2048
}

variable "ecs_api_count" {
  description = "Desired number of API tasks"
  type        = number
  default     = 3
}

variable "ecs_api_min_count" {
  description = "Minimum number of API tasks for auto-scaling"
  type        = number
  default     = 2
}

variable "ecs_api_max_count" {
  description = "Maximum number of API tasks for auto-scaling"
  type        = number
  default     = 10
}

# EC2 Worker Variables
variable "ec2_worker_enabled" {
  description = "Enable EC2 workers for GPU processing"
  type        = bool
  default     = true
}

variable "ec2_worker_instance_type" {
  description = "EC2 instance type for workers (GPU instances)"
  type        = string
  default     = "g4dn.xlarge"
}

variable "ec2_worker_ami_id" {
  description = "AMI ID for worker instances (should have GPU drivers)"
  type        = string
  # Deep Learning AMI with NVIDIA drivers
  # Update based on region
  default     = "ami-0c55b159cbfafe1f0"
}

variable "ec2_key_name" {
  description = "EC2 key pair name for SSH access"
  type        = string
  default     = ""
}

variable "ec2_worker_count" {
  description = "Desired number of worker instances"
  type        = number
  default     = 2
}

variable "ec2_worker_min_count" {
  description = "Minimum number of worker instances"
  type        = number
  default     = 1
}

variable "ec2_worker_max_count" {
  description = "Maximum number of worker instances"
  type        = number
  default     = 4
}

# Load Balancer Variables
variable "certificate_arn" {
  description = "ARN of SSL certificate for ALB (from ACM)"
  type        = string
}

# DNS Variables
variable "domain_name" {
  description = "Domain name for the API"
  type        = string
}

variable "create_dns_record" {
  description = "Create Route53 DNS record"
  type        = bool
  default     = false
}

variable "route53_zone_id" {
  description = "Route53 hosted zone ID (required if create_dns_record is true)"
  type        = string
  default     = ""
}

# Logging Variables
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

# Tags
variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
