terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# --------- Get latest Ubuntu 22.04 LTS (Jammy) AMI ----------
data "aws_ami" "ubuntu_2204" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# --------- Security Group: no inbound, all outbound ----------
resource "aws_security_group" "ec2_no_inbound" {
  name        = "${var.project_name}-sg"
  description = "No inbound; allow all egress (SSM uses outbound only)"
  vpc_id      = var.vpc_id

  # No ingress rules -> denies all inbound
  egress {
    description = "allow all egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name = "${var.project_name}-sg"
  }
}

# --------- IAM Role for SSM ----------
data "aws_iam_policy" "ssm_core" {
  arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role" "ec2_ssm_role" {
  name               = "${var.project_name}-ec2-ssm-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags = {
    Project = var.project_name
  }
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "attach_ssm_core" {
  role       = aws_iam_role.ec2_ssm_role.name
  policy_arn = data.aws_iam_policy.ssm_core.arn
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "${var.project_name}-ec2-profile"
  role = aws_iam_role.ec2_ssm_role.name
}

# --------- EC2 Instance ----------
resource "aws_instance" "ir_ec2" {
  ami                         = data.aws_ami.ubuntu_2204.id
  instance_type               = "t3.micro"
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.ec2_no_inbound.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2_profile.name
  monitoring                  = true

  # No key pair (we’ll use SSM Session Manager)
  key_name                    = null

  # Enforce IMDSv2 (security best practice)
  metadata_options {
    http_tokens = "required"
  }

  # Optional: Pre-install CloudWatch Agent (uncomment if desired)
  # user_data = <<-EOF
  #   #!/usr/bin/env bash
  #   set -eux
  #   apt-get update -y
  #   apt-get install -y curl unzip
  #   cd /tmp
  #   curl -fsSLo amazon-cloudwatch-agent.deb \
  #     https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
  #   dpkg -i amazon-cloudwatch-agent.deb
  #   # Minimal config could be pushed later via SSM; start service anyway:
  #   systemctl enable amazon-cloudwatch-agent || true
  #   systemctl start amazon-cloudwatch-agent || true
  # EOF

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  tags = merge(
    {
      Name    = "${var.project_name}-ec2"
      Project = var.project_name
      Role    = "incident-response-target"
    },
    var.additional_tags
  )
}

