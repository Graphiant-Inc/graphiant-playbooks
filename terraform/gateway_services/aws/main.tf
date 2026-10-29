# Terraform configuration for direct connect circuit on aws.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0.0"
    }
  }

  required_version = ">= 1.1.0"
}

# Configure aws Provider
provider "aws" {
  region = var.aws_region
}

locals {
  vpc_id                 = var.use_existing_vpc ? data.aws_vpc.existing[0].id : aws_vpc.main[0].id
  subnet_ids             = var.use_existing_subnet ? [data.aws_subnet.existing[0].id] : [aws_subnet.private_subnet[0].id]
  private_route_table_id = var.use_existing_route_table ? data.aws_route_table.existing_private[0].id : aws_route_table.private[0].id
}

# Create VPC 
resource "aws_vpc" "main" {
  count            = var.use_existing_vpc ? 0 : 1
  cidr_block       = var.cidr_block
  instance_tenancy = var.tenancy

  tags = {
    Name        = "${var.project_name}-vpc"
    Environment = var.environment
    Project     = var.project_name
  }
}

# get existing VPC ID by VPC name
data "aws_vpc" "existing" {
  count = var.use_existing_vpc ? 1 : 0

  filter {
    name   = "tag:Name"
    values = [var.existing_vpc_name]
  }
}

# Private Subnet
resource "aws_subnet" "private_subnet" {
  count                   = var.use_existing_subnet ? 0 : 1
  vpc_id                  = local.vpc_id
  cidr_block              = var.private_subnet_cidr
  availability_zone       = var.aws_az
  map_public_ip_on_launch = false # This makes it a private subnet

  tags = {
    Name        = "${var.project_name}-private-subnet"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Get existing Subnet by Name
data "aws_subnet" "existing" {
  count = var.use_existing_subnet ? 1 : 0

  filter {
    name   = "tag:Name"
    values = [var.existing_subnet_name]
  }
}

# Create new route table if not using existing
resource "aws_route_table" "private" {
  count  = var.use_existing_route_table ? 0 : 1
  vpc_id = local.vpc_id

  tags = {
    Name        = "${var.project_name}-private-rt"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Use existing route table if specified
data "aws_route_table" "existing_private" {
  count = var.use_existing_route_table ? 1 : 0

  filter {
    name   = "tag:Name"
    values = [var.existing_route_table_name]
  }
}

# Associates a subnet with a route table so routing (like TGW) works correctly
resource "aws_route_table_association" "private_subnet_assoc" {
  count          = var.use_existing_route_table ? 0 : length(local.subnet_ids)
  subnet_id      = local.subnet_ids[count.index]
  route_table_id = local.private_route_table_id
}

# Create a VM and Security group within VPC
resource "aws_security_group" "vm_sg" {
  count = var.deploy_vm ? 1 : 0

  name        = "${var.project_name}-sg"
  description = "Security group for EC2 instance"
  vpc_id      = local.vpc_id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  ingress {
    from_port   = -1
    to_port     = -1
    protocol    = "icmp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "vm" {
  count = var.deploy_vm ? 1 : 0

  ami                         = var.ami
  instance_type               = var.instance_type
  subnet_id                   = local.subnet_ids[0]
  vpc_security_group_ids      = [aws_security_group.vm_sg[0].id]
  key_name                    = var.key_name
  associate_public_ip_address = false # Private subnet

  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }

  tags = {
    Name = "${var.project_name}-vm"
  }
}

# EC2 Instance Connect Endpoint
resource "aws_security_group" "connect_endpoint_sg" {
  count       = var.deploy_connect_endpoint ? 1 : 0
  name        = "${var.project_name}-connect-endpoint-sg"
  description = "SG for EC2 Instance Connect Endpoint"
  vpc_id      = local.vpc_id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  ingress {
    from_port   = -1
    to_port     = -1
    protocol    = "icmp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-connect-endpoint-sg"
    Environment = var.environment
  }
}

resource "aws_ec2_instance_connect_endpoint" "connect_endpoint" {
  count              = var.deploy_connect_endpoint ? 1 : 0
  subnet_id          = local.subnet_ids[0]
  security_group_ids = [aws_security_group.connect_endpoint_sg[0].id]

  tags = {
    Name        = "${var.project_name}-connect-endpoint"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Create a Transit Gateway
resource "aws_ec2_transit_gateway" "tgw" {
  description = var.tgw_description
  # Options (all optional)
  amazon_side_asn                 = var.tgw_asn_number
  default_route_table_association = "enable"
  default_route_table_propagation = "enable"
  dns_support                     = "enable"
  vpn_ecmp_support                = "enable"

  tags = {
    Name        = "${var.project_name}-tgw"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Transit Gateway VPC Attachment
resource "aws_ec2_transit_gateway_vpc_attachment" "tgw_vpc_attachment" {
  vpc_id                 = local.vpc_id
  transit_gateway_id     = aws_ec2_transit_gateway.tgw.id
  dns_support            = "enable" # can also use "disable"
  ipv6_support           = "disable"
  appliance_mode_support = "disable"
  subnet_ids             = local.subnet_ids

  tags = {
    Name        = "${var.project_name}-tgw-attachment"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Create Default Route to the transit gateway for the VPC
resource "aws_route" "tgw_route" {
  route_table_id         = local.private_route_table_id
  destination_cidr_block = var.tgw_route_cidr
  transit_gateway_id     = aws_ec2_transit_gateway.tgw.id

  depends_on = [
    aws_ec2_transit_gateway_vpc_attachment.tgw_vpc_attachment
  ]
}

# Create a DirectConnect Gateway
# Note: The LAG (and connection associations) are created manually outside Terraform
# due to MACsec constraints in the AWS provider. Set dx_connection_id to the LAG ID.
resource "aws_dx_gateway" "dxgw" {
  name            = var.dx_gateway_name
  amazon_side_asn = var.dx_gateway_asn
}

# Associate Transit Gateway to Direct Connect Gateway
resource "aws_dx_gateway_association" "tgw_dxgw_association" {
  dx_gateway_id         = aws_dx_gateway.dxgw.id
  associated_gateway_id = aws_ec2_transit_gateway.tgw.id
  # Optional: restrict advertised prefixes
  allowed_prefixes = var.dxgw_allowed_prefixes # e.g., ["10.0.0.0/16", "192.168.1.0/24"]

  depends_on = [
    aws_dx_gateway.dxgw,
    aws_ec2_transit_gateway.tgw,
  ]
}

# Create a Transit Virtual Interface
resource "aws_dx_transit_virtual_interface" "transit_vif" {
  # When using a LAG, set dx_connection_id to the LAG ID (e.g. dxlag-xxxxxxxx)
  connection_id = var.dx_connection_id
  dx_gateway_id = aws_dx_gateway.dxgw.id

  name           = var.dx_vif_name
  address_family = "ipv4"
  vlan           = var.dx_connection_vlan
  bgp_asn        = var.customer_bgp_asn
  mtu            = var.transit_vif_mtu

  lifecycle {
    precondition {
      condition     = var.dx_connection_id != null
      error_message = "dx_connection_id must be set. Use the LAG ID when connecting via a LAG."
    }
  }

  tags = {
    Name        = var.dx_vif_name
    Environment = var.environment
  }
}