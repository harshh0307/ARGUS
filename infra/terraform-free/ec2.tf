resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "aws_key_pair" "ssh" {
  key_name   = "argus-${var.environment}"
  public_key = tls_private_key.ssh.public_key_openssh

  tags = local.tags
}

resource "local_file" "ssh_private_key" {
  filename        = "${path.module}/keys/argus-${var.environment}.pem"
  content         = tls_private_key.ssh.private_key_pem
  file_permission = "0600"
}

resource "aws_iam_role" "instance" {
  name = "argus-${var.environment}-ec2"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ec2.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = local.tags
}

resource "aws_iam_role_policy" "ssm_read" {
  name = "argus-secrets-read"
  role = aws_iam_role.instance.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_prefix}/*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "instance" {
  name = "argus-${var.environment}-ec2"
  role = aws_iam_role.instance.name
}

resource "aws_security_group" "argus" {
  name        = "argus-${var.environment}"
  description = "Argus free-tier: SSH + API"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_cidr]
  }

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.tags
}

data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"]
}

resource "aws_instance" "argus" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = data.aws_subnet.default.id
  vpc_security_group_ids      = [aws_security_group.argus.id]
  key_name                    = aws_key_pair.ssh.key_name
  iam_instance_profile        = aws_iam_instance_profile.instance.name
  user_data                   = templatefile("${path.module}/user_data.sh.tpl", { ssm_prefix = var.ssm_prefix, git_repo = var.git_repo })
  user_data_replace_on_change = true

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
  }

  tags = merge(local.tags, { Name = "argus-${var.environment}" })
}

resource "aws_eip" "argus" {
  domain = "vpc"

  tags = local.tags
}

resource "aws_eip_association" "argus" {
  instance_id   = aws_instance.argus.id
  allocation_id = aws_eip.argus.id
}
