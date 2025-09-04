variable "project_name" {
  description = "Project/name prefix for resources"
  type        = string
  default     = "aws-incident-response"
}

variable "region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "ap-southeast-1"
}

variable "vpc_id" {
  description = "VPC ID where the instance will live"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID (prefer a public subnet if you need public IP, or private with NAT/VPC endpoints)"
  type        = string
}

variable "root_volume_size" {
  description = "Root volume size (GB)"
  type        = number
  default     = 16
}

variable "additional_tags" {
  description = "Extra tags to apply to resources"
  type        = map(string)
  default     = {}
}
