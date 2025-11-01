# VPC Outputs
output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = module.vpc.vpc_cidr
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = module.vpc.private_subnet_ids
}

# Database Outputs
output "database_endpoint" {
  description = "RDS database endpoint"
  value       = module.database.db_endpoint
}

output "database_name" {
  description = "Database name"
  value       = module.database.db_name
}

output "database_port" {
  description = "Database port"
  value       = module.database.db_port
}

# Redis Outputs
output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = module.redis.redis_endpoint
}

output "redis_port" {
  description = "Redis port"
  value       = module.redis.redis_port
}

# Storage Outputs
output "s3_bucket_name" {
  description = "S3 bucket name for media storage"
  value       = module.storage.bucket_name
}

output "s3_bucket_arn" {
  description = "S3 bucket ARN"
  value       = module.storage.bucket_arn
}

# Load Balancer Outputs
output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.alb.alb_dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the Application Load Balancer"
  value       = module.alb.alb_zone_id
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = module.alb.alb_arn
}

# ECS Outputs
output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = module.ecs_api.cluster_name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = module.ecs_api.service_name
}

output "ecs_task_definition_arn" {
  description = "ARN of the ECS task definition"
  value       = module.ecs_api.task_definition_arn
}

# EC2 Worker Outputs
output "worker_asg_name" {
  description = "Name of the worker Auto Scaling Group"
  value       = var.ec2_worker_enabled ? module.ec2_workers[0].asg_name : null
}

output "worker_launch_template_id" {
  description = "ID of the worker launch template"
  value       = var.ec2_worker_enabled ? module.ec2_workers[0].launch_template_id : null
}

# Security Group Outputs
output "alb_security_group_id" {
  description = "Security group ID for ALB"
  value       = module.security_groups.alb_sg_id
}

output "ecs_api_security_group_id" {
  description = "Security group ID for ECS API tasks"
  value       = module.security_groups.ecs_api_sg_id
}

output "worker_security_group_id" {
  description = "Security group ID for workers"
  value       = module.security_groups.worker_sg_id
}

output "database_security_group_id" {
  description = "Security group ID for database"
  value       = module.security_groups.database_sg_id
}

output "redis_security_group_id" {
  description = "Security group ID for Redis"
  value       = module.security_groups.redis_sg_id
}

# Secrets Outputs
output "secret_arns" {
  description = "ARNs of secrets in Secrets Manager"
  value       = module.secrets.secret_arns
  sensitive   = true
}

# DNS Output
output "api_url" {
  description = "API URL (if DNS record was created)"
  value       = var.create_dns_record ? "https://${var.domain_name}" : "https://${module.alb.alb_dns_name}"
}

# Connection Strings (for convenience)
output "database_connection_string" {
  description = "Database connection string (retrieve password from Secrets Manager)"
  value       = "postgresql+psycopg://${var.db_username}:PASSWORD@${module.database.db_endpoint}/${var.db_name}"
  sensitive   = true
}

output "redis_connection_string" {
  description = "Redis connection string"
  value       = "redis://${module.redis.redis_endpoint}:${module.redis.redis_port}/0"
}

# Helpful Commands
output "helpful_commands" {
  description = "Helpful commands for managing the deployment"
  value = {
    view_api_logs = "aws logs tail /ecs/${var.project_name}-${var.environment}/api --follow --region ${var.aws_region}"
    view_worker_logs = var.ec2_worker_enabled ? "aws logs tail /ec2/${var.project_name}-${var.environment}/worker --follow --region ${var.aws_region}" : "N/A"
    list_ecs_tasks = "aws ecs list-tasks --cluster ${module.ecs_api.cluster_name} --region ${var.aws_region}"
    describe_asg = var.ec2_worker_enabled ? "aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names ${module.ec2_workers[0].asg_name} --region ${var.aws_region}" : "N/A"
    get_db_password = "aws secretsmanager get-secret-value --secret-id ${module.secrets.secret_arns["database_url"]} --query SecretString --output text --region ${var.aws_region}"
  }
}
