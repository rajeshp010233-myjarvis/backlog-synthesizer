terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Optional: store state in S3 so the team shares it.
  # Uncomment after running `terraform init` once locally.
  #
  # backend "s3" {
  #   bucket = "backlog-synthesizer-tfstate"
  #   key    = "infra/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region
}

# ── Data sources ──────────────────────────────────────────────────────────────

data "aws_caller_identity" "current" {}

# Auto-select the latest Amazon Linux 2023 AMI when var.ami_id is empty
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  ami       = var.ami_id != "" ? var.ami_id : data.aws_ami.al2023.id
  account_id = data.aws_caller_identity.current.account_id
}

# ── VPC / default networking ──────────────────────────────────────────────────

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ── Security Group ────────────────────────────────────────────────────────────

resource "aws_security_group" "app" {
  name        = "${var.app_name}-sg"
  description = "Allow inbound traffic for ${var.app_name}"
  vpc_id      = data.aws_vpc.default.id

  # Frontend (nginx)
  ingress {
    description = "Frontend"
    from_port   = var.app_port_frontend
    to_port     = var.app_port_frontend
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Backend API
  ingress {
    description = "Backend API"
    from_port   = var.app_port_backend
    to_port     = var.app_port_backend
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # MCP server
  ingress {
    description = "MCP server"
    from_port   = var.app_port_mcp
    to_port     = var.app_port_mcp
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # SSH (restrict to your IP in production via var.allowed_ssh_cidr)
  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # All outbound (needed for ECR pulls, package installs, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.app_name}-sg"
    App  = var.app_name
  }
}

# ── IAM instance profile (allows EC2 to call SSM + ECR without credentials) ──

resource "aws_iam_role" "ec2_role" {
  name = "${var.app_name}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { App = var.app_name }
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.app_name}-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

# ── Key pair (optional — SSM is the primary access method) ───────────────────
# If you want SSH access, generate a key pair locally:
#   ssh-keygen -t ed25519 -f ~/.ssh/backlog-synthesizer
# Then set TF_VAR_public_key="$(cat ~/.ssh/backlog-synthesizer.pub)" before apply.

variable "public_key" {
  description = "SSH public key material. Leave empty to skip key pair creation."
  type        = string
  default     = ""
}

resource "aws_key_pair" "deployer" {
  count      = var.public_key != "" ? 1 : 0
  key_name   = "${var.app_name}-deployer"
  public_key = var.public_key
}

# ── EC2 instance ──────────────────────────────────────────────────────────────

resource "aws_instance" "app" {
  ami                    = local.ami
  instance_type          = var.instance_type
  subnet_id              = tolist(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name
  key_name               = var.public_key != "" ? aws_key_pair.deployer[0].key_name : null

  # 20 GB gp3 root volume — free tier allows 30 GB total
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 20
    delete_on_termination = true
    encrypted             = true
  }

  user_data = file("${path.module}/user_data.sh")

  # Prevent accidental termination
  disable_api_termination = false

  tags = {
    Name = var.app_name
    App  = var.app_name
  }

  lifecycle {
    # Don't replace the instance when AMI changes — update manually
    ignore_changes = [ami, user_data]
  }
}

# ── Elastic IP ────────────────────────────────────────────────────────────────

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"

  tags = {
    Name = "${var.app_name}-eip"
    App  = var.app_name
  }
}
