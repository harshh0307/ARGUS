variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "instance_type" {
  description = "EC2 instance type (free tier: t4g.micro / t3.micro)"
  type        = string
  default     = "t4g.micro"
}

variable "ssh_cidr" {
  description = "CIDR allowed to SSH (use your public IP: <ip>/32)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "ssm_prefix" {
  description = "Prefix where Argus secrets live in SSM Parameter Store"
  type        = string
  default     = "/argus"
}

variable "git_repo" {
  description = "Public GitHub repo to clone on the instance"
  type        = string
  default     = "https://github.com/harshh0307/ARGUS.git"
}
