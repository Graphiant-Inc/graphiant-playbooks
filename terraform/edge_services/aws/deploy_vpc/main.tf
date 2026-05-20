terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      "aws-apn-id" = "pc:${var.aws_partner_product_code}"
    }
  }
}

locals {
  tags = merge({ Vendor = "Graphiant" }, var.tags)
}

# -----------------------------------------------------------------------------
# VPC (IPv4 + Amazon-provided IPv6)
# -----------------------------------------------------------------------------
resource "aws_vpc" "this" {
  cidr_block                       = var.vpc_address_range
  assign_generated_ipv6_cidr_block = true
  enable_dns_support               = true
  enable_dns_hostnames             = true

  tags = merge(local.tags, { Name = var.vpc_name })
}

# -----------------------------------------------------------------------------
# Internet Gateway (optional)
# -----------------------------------------------------------------------------
resource "aws_internet_gateway" "this" {
  count  = var.create_internet_gateway ? 1 : 0
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, { Name = "${var.project_name}-igw" })
}

# -----------------------------------------------------------------------------
# Subnets — IPv4 from var prefixes; IPv6 /64s carved from the VPC /56 block
# -----------------------------------------------------------------------------
resource "aws_subnet" "mgmt" {
  vpc_id                          = aws_vpc.this.id
  availability_zone               = var.availability_zone
  cidr_block                      = var.subnet_mgmt_prefix
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.this.ipv6_cidr_block, 8, 1)
  assign_ipv6_address_on_creation = true

  tags = merge(local.tags, { Name = "${var.project_name}-mgmt" })
}

resource "aws_subnet" "wan" {
  vpc_id                          = aws_vpc.this.id
  availability_zone               = var.availability_zone
  cidr_block                      = var.subnet_wan_prefix
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.this.ipv6_cidr_block, 8, 2)
  assign_ipv6_address_on_creation = true

  tags = merge(local.tags, { Name = "${var.project_name}-wan" })
}

resource "aws_subnet" "lan" {
  vpc_id                          = aws_vpc.this.id
  availability_zone               = var.availability_zone
  cidr_block                      = var.subnet_lan_prefix
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.this.ipv6_cidr_block, 8, 3)
  assign_ipv6_address_on_creation = true

  tags = merge(local.tags, { Name = "${var.project_name}-lan" })
}

# -----------------------------------------------------------------------------
# Route Tables — Azure-style split:
#   WAN RT: default route to IGW (associates mgmt + wan subnets)
#   LAN RT: empty; default-via-vEdge is added by deploy_vedge after the vEdge NIC exists
# -----------------------------------------------------------------------------
resource "aws_route_table" "wan" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, { Name = "${var.project_name}-wan-rt" })
}

# Routes to IGW (only if IGW is created)
resource "aws_route" "wan_default_ipv4" {
  count              = var.create_internet_gateway ? 1 : 0
  route_table_id     = aws_route_table.wan.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id         = aws_internet_gateway.this[0].id
}

resource "aws_route" "wan_default_ipv6" {
  count               = var.create_internet_gateway ? 1 : 0
  route_table_id      = aws_route_table.wan.id
  destination_ipv6_cidr_block = "::/0"
  gateway_id          = aws_internet_gateway.this[0].id
}

resource "aws_route_table_association" "mgmt" {
  subnet_id      = aws_subnet.mgmt.id
  route_table_id = aws_route_table.wan.id
}

resource "aws_route_table_association" "wan" {
  subnet_id      = aws_subnet.wan.id
  route_table_id = aws_route_table.wan.id
}

resource "aws_route_table" "lan" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.tags, { Name = "${var.project_name}-lan-rt" })
}

resource "aws_route_table_association" "lan" {
  subnet_id      = aws_subnet.lan.id
  route_table_id = aws_route_table.lan.id
}
