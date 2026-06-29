variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name — used as a prefix for all resource names"
  type        = string
  default     = "backlog-synthesizer"
}

variable "instance_type" {
  description = "EC2 instance type. t2.micro is free-tier eligible (750 h/month)"
  type        = string
  default     = "t2.micro"
}

variable "ami_id" {
  description = "Amazon Linux 2023 AMI. Leave empty to auto-select latest for the region."
  type        = string
  default     = ""
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to reach port 22. Set to your IP e.g. 1.2.3.4/32. Use 0.0.0.0/0 only for testing."
  type        = string
  default     = "0.0.0.0/0"
}

variable "app_port_backend" {
  type    = number
  default = 8000
}

variable "app_port_frontend" {
  type    = number
  default = 80
}

variable "app_port_mcp" {
  type    = number
  default = 8002
}
