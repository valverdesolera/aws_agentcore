variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used as prefix for resource naming"
  type        = string
  default     = "teilur-stock-agent"
}

variable "langfuse_secret_key" {
  description = "Langfuse secret key (sk-lf-...)"
  type        = string
  sensitive   = true
}

variable "langfuse_public_key" {
  description = "Langfuse public key (pk-lf-...)"
  type        = string
  sensitive   = true
}

variable "langfuse_base_url" {
  description = "Langfuse base URL"
  type        = string
  default     = "https://us.cloud.langfuse.com"
}
