variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev/staging/prod)"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "image_tag" {
  description = "Container image tag to deploy (must already exist in ECR)"
  type        = string
  default     = "latest"
}

variable "api_desired_count" {
  description = "Desired number of API tasks"
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Desired number of Celery worker tasks"
  type        = number
  default     = 1
}

variable "beat_desired_count" {
  description = "Desired number of Celery beat tasks"
  type        = number
  default     = 1
}

variable "db_password" {
  description = "RDS postgres password (fallback if SSM secret missing)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ssm_prefix" {
  description = "Prefix under which Argus secrets live in SSM Parameter Store"
  type        = string
  default     = "/argus"
}

variable "snapshot_bucket_name" {
  description = "Name of the S3 bucket for spec snapshots (default: auto-generated)"
  type        = string
  default     = ""
}
