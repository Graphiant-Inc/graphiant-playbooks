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

# -----------------------------------------------------------------------------
# Locals
# -----------------------------------------------------------------------------
data "aws_ssm_parameter" "vedge_ami" {
  count = var.image_id == "" && var.marketplace_product_id != "" ? 1 : 0
  name  = "/aws/service/marketplace/${var.marketplace_product_id}/${var.marketplace_version}"
}

data "aws_ami" "debian_13" {
  count       = var.deploy_test_vm && var.test_vm_ami == "" ? 1 : 0
  most_recent = true
  owners      = ["136693071363"]

  filter {
    name   = "name"
    values = ["debian-13-amd64-*"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

locals {
  is_devtest       = var.mode == "devtest"
  use_existing_vpc = var.vpc_id != ""
  new_vpc          = !local.use_existing_vpc

  # AMI: explicit image_id wins; otherwise resolved via the AWS Marketplace SSM public parameter.
  resolved_image_id = var.image_id != "" ? var.image_id : try(data.aws_ssm_parameter.vedge_ami[0].value, "")

  # Test VM AMI: use test_vm_ami if configured; otherwise auto-derive latest Debian 13 from AWS.
  test_vm_ami_resolved = var.test_vm_ami != "" ? var.test_vm_ami : try(data.aws_ami.debian_13[0].id, "")

  # Per-resource rule: an ID provided -> use it; empty -> create it.
  create_subnet_cloud_init = local.is_devtest && var.subnet_cloud_init_id == ""
  create_subnet_mgmt       = var.subnet_mgmt_id == ""
  create_subnet_wan        = var.subnet_wan_id == ""
  create_subnet_lan        = var.subnet_lan_id == ""

  # WAN RT is only needed to give newly created mgmt/wan/cloud-init subnets an IGW route.
  create_rt_wan = var.route_table_wan_id == "" && (local.create_subnet_cloud_init || local.create_subnet_mgmt || local.create_subnet_wan)
  create_rt_lan = var.route_table_lan_id == ""

  create_sg_cloud_init = local.is_devtest && var.security_group_cloud_init_id == ""
  create_sg_mgmt       = var.security_group_mgmt_id == ""
  create_sg_wan        = var.security_group_wan_id == ""
  create_sg_lan        = var.security_group_lan_id == ""
  create_sg_test_vm    = var.deploy_test_vm && var.security_group_test_vm_id == ""

  # IGW: internet_gateway_id provided -> use it; else create_internet_gateway decides:
  # null (auto) -> create for a new VPC, use the IGW already attached to an existing VPC;
  # true -> create one; false -> no-IGW mode (no IGW routes, no public IPs).
  use_igw    = var.internet_gateway_id != "" || var.create_internet_gateway != false
  create_igw = var.internet_gateway_id == "" && (var.create_internet_gateway == true || (var.create_internet_gateway == null && local.new_vpc))
  lookup_igw = var.internet_gateway_id == "" && var.create_internet_gateway == null && local.use_existing_vpc

  # EIPs need an IGW-attached VPC (AWS rejects the association otherwise with Gateway.NotAttached).
  create_eip_mgmt = local.use_igw && var.eip_mgmt_allocation_id == ""
  create_eip_wan  = local.use_igw && var.eip_wan_allocation_id == ""

  # Test VM ingress: check if explicitly configured (not default allow-all)
  test_vm_ingress_custom = var.deploy_test_vm && !(length(var.test_vm_ingress_allowed_subnets) == 1 && var.test_vm_ingress_allowed_subnets[0] == "0.0.0.0/0")

  # Destination CIDRs routed via the vEdge LAN ENI in the LAN RT
  lan_vedge_routed_cidrs = local.test_vm_ingress_custom ? var.test_vm_ingress_allowed_subnets : ["0.0.0.0/0"]

  test_vm_ssh_via_igw = var.deploy_test_vm && var.test_vm_enable_ssh_public_ip

  vpc_id_resolved = local.use_existing_vpc ? var.vpc_id : aws_vpc.this[0].id

  # CIDRs of subnets to be created in an existing VPC — checked against subnets already there.
  new_subnet_cidrs_in_existing_vpc = local.new_vpc ? {} : {
    for k, v in {
      cloud_init = local.create_subnet_cloud_init ? var.subnet_cloud_init_prefix : ""
      mgmt       = local.create_subnet_mgmt ? var.subnet_mgmt_prefix : ""
      wan        = local.create_subnet_wan ? var.subnet_wan_prefix : ""
      lan        = local.create_subnet_lan ? var.subnet_lan_prefix : ""
    } : k => v if v != ""
  }

  # Per new subnet: subnets with the same CIDR, minus the ones this module already manages.
  subnet_cidr_conflicts = {
    for k, d in data.aws_subnets.cidr_in_use : k => tolist(setsubtract(d.ids, data.aws_subnets.own_cidr[k].ids))
  }

  # IPv6 is LAN-side only: VPC block, new LAN subnet /64, vEdge LAN + test VM NICs.
  # lan_ipv6 drives counts, so it uses only plan-time values (vars + existing VPC lookup).
  existing_vpc_ipv6_cidr = local.new_vpc ? "" : try(coalesce(data.aws_vpc.existing[0].ipv6_cidr_block), "")
  lan_ipv6               = local.create_subnet_lan && (local.new_vpc || local.existing_vpc_ipv6_cidr != "")
  lan_subnet_ipv6_cidr   = local.lan_ipv6 ? cidrsubnet(local.new_vpc ? aws_vpc.this[0].ipv6_cidr_block : local.existing_vpc_ipv6_cidr, 8, var.subnet_lan_ipv6_netnum) : null

  igw_id_resolved = local.create_igw ? aws_internet_gateway.this[0].id : local.lookup_igw ? data.aws_internet_gateway.attached[0].id : var.internet_gateway_id

  subnet_cloud_init_id_resolved = local.create_subnet_cloud_init ? aws_subnet.cloud_init[0].id : var.subnet_cloud_init_id
  subnet_mgmt_id_resolved       = local.create_subnet_mgmt ? aws_subnet.mgmt[0].id : var.subnet_mgmt_id
  subnet_wan_id_resolved        = local.create_subnet_wan ? aws_subnet.wan[0].id : var.subnet_wan_id
  subnet_lan_id_resolved        = local.create_subnet_lan ? aws_subnet.lan[0].id : var.subnet_lan_id

  route_table_wan_id_resolved = local.create_rt_wan ? aws_route_table.wan[0].id : var.route_table_wan_id
  route_table_lan_id_resolved = local.create_rt_lan ? aws_route_table.lan[0].id : var.route_table_lan_id

  sg_cloud_init_id_resolved = local.create_sg_cloud_init ? aws_security_group.cloud_init[0].id : var.security_group_cloud_init_id
  sg_mgmt_id_resolved       = local.create_sg_mgmt ? aws_security_group.mgmt[0].id : var.security_group_mgmt_id
  sg_wan_id_resolved        = local.create_sg_wan ? aws_security_group.wan[0].id : var.security_group_wan_id
  sg_lan_id_resolved        = local.create_sg_lan ? aws_security_group.lan[0].id : var.security_group_lan_id
  sg_test_vm_id_resolved    = local.create_sg_test_vm ? aws_security_group.test_vm[0].id : var.security_group_test_vm_id

  eip_mgmt_allocation_id_resolved = local.create_eip_mgmt ? aws_eip.mgmt[0].id : var.eip_mgmt_allocation_id
  eip_wan_allocation_id_resolved  = local.create_eip_wan ? aws_eip.wan[0].id : var.eip_wan_allocation_id
  eip_mgmt_public_ip              = !local.use_igw ? null : local.create_eip_mgmt ? aws_eip.mgmt[0].public_ip : data.aws_eip.mgmt[0].public_ip
  eip_wan_public_ip               = !local.use_igw ? null : local.create_eip_wan ? aws_eip.wan[0].public_ip : data.aws_eip.wan[0].public_ip

  tags = merge(
    {
      Vendor      = "Graphiant"
      Environment = var.mode
    },
    var.tags,
  )

  # Cloud-init user-data (token is optional; only included if configured)
  cloud_init_production = concat(
    ["#cloud-config\n\ngraphnos:"],
    var.token != "" ? ["  token: ${var.token}"] : []
  )

  cloud_init_devtest = concat(
    [
      "#cloud-config\n\ngraphnos:",
      "  onboarding-gw: ${var.onboarding_gateway}",
      "  onboarding-auth-url: ${var.onboarding_auth_url}",
    ],
    var.token != "" ? ["  token: ${var.token}"] : [],
    [
      "\nusers:",
      "  - name: ${var.cloud_init_username}",
      "    plain_text_passwd: '${var.cloud_init_password}'",
      "    sudo: [\"ALL=(ALL) NOPASSWD:ALL\"]",
      "    lock_passwd: false",
      "    groups: sudo",
      "    shell: /bin/bash",
      "    ssh-authorized-keys:",
      "      - ${var.ssh_public_key}",
    ]
  )

  user_data = join("\n", local.is_devtest ? local.cloud_init_devtest : local.cloud_init_production)
}

# -----------------------------------------------------------------------------
# VPC (new VPC only) — IPv6 block is used by the LAN subnet only. An existing VPC is
# read for its IPv6 block; without one the LAN side stays IPv4-only.
# -----------------------------------------------------------------------------
data "aws_vpc" "existing" {
  count = local.new_vpc ? 0 : 1
  id    = var.vpc_id
}

resource "aws_vpc" "this" {
  count                            = local.new_vpc ? 1 : 0
  cidr_block                       = var.vpc_address_range
  assign_generated_ipv6_cidr_block = true
  enable_dns_support               = true
  enable_dns_hostnames             = true

  tags = merge(local.tags, { Name = var.vpc_name })
}

# IGW — created for a new VPC (or create_internet_gateway = true) when internet_gateway_id is empty.
# AWS allows one IGW per VPC, so an existing VPC uses the IGW already attached to it by default.
data "aws_internet_gateway" "attached" {
  count = local.lookup_igw ? 1 : 0

  filter {
    name   = "attachment.vpc-id"
    values = [var.vpc_id]
  }
}

resource "aws_internet_gateway" "this" {
  count  = local.create_igw ? 1 : 0
  vpc_id = local.vpc_id_resolved

  tags = merge(local.tags, { Name = "${var.project_name}-igw" })
}

# -----------------------------------------------------------------------------
# Subnets — created when subnet_*_id is empty (in the new or existing VPC).
# -----------------------------------------------------------------------------

# Subnets in the existing VPC with exactly the CIDR a new subnet would use. Exact match only:
# partially overlapping CIDRs are still rejected by AWS at apply (InvalidSubnet.Conflict).
data "aws_subnets" "cidr_in_use" {
  for_each = local.new_subnet_cidrs_in_existing_vpc

  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }

  filter {
    name   = "cidr-block"
    values = [each.value]
  }
}

# Same lookup restricted to this module's own Name tag, so subnets it already manages are
# not reported as conflicts on re-plan (a precondition cannot reference its own resource).
data "aws_subnets" "own_cidr" {
  for_each = local.new_subnet_cidrs_in_existing_vpc

  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }

  filter {
    name   = "cidr-block"
    values = [each.value]
  }

  filter {
    name   = "tag:Name"
    values = ["${var.project_name}-${replace(each.key, "_", "")}"]
  }
}

# Cloud-init subnet — devtest only
resource "aws_subnet" "cloud_init" {
  count             = local.create_subnet_cloud_init ? 1 : 0
  vpc_id            = local.vpc_id_resolved
  availability_zone = var.availability_zone
  cidr_block        = var.subnet_cloud_init_prefix

  tags = merge(local.tags, { Name = "${var.project_name}-cloudinit" })

  lifecycle {
    precondition {
      condition     = length(try(local.subnet_cidr_conflicts["cloud_init"], [])) == 0
      error_message = "Subnet ${try(local.subnet_cidr_conflicts["cloud_init"][0], "")} already uses ${var.subnet_cloud_init_prefix} in ${var.vpc_id}: set subnet_cloud_init_id = \"${try(local.subnet_cidr_conflicts["cloud_init"][0], "")}\" to reuse it, or choose a different subnet_cloud_init_prefix."
    }
  }
}

resource "aws_subnet" "mgmt" {
  count             = local.create_subnet_mgmt ? 1 : 0
  vpc_id            = local.vpc_id_resolved
  availability_zone = var.availability_zone
  cidr_block        = var.subnet_mgmt_prefix

  tags = merge(local.tags, { Name = "${var.project_name}-mgmt" })

  lifecycle {
    precondition {
      condition     = length(try(local.subnet_cidr_conflicts["mgmt"], [])) == 0
      error_message = "Subnet ${try(local.subnet_cidr_conflicts["mgmt"][0], "")} already uses ${var.subnet_mgmt_prefix} in ${var.vpc_id}: set subnet_mgmt_id = \"${try(local.subnet_cidr_conflicts["mgmt"][0], "")}\" to reuse it, or choose a different subnet_mgmt_prefix."
    }
  }
}

resource "aws_subnet" "wan" {
  count             = local.create_subnet_wan ? 1 : 0
  vpc_id            = local.vpc_id_resolved
  availability_zone = var.availability_zone
  cidr_block        = var.subnet_wan_prefix

  tags = merge(local.tags, { Name = "${var.project_name}-wan" })

  lifecycle {
    precondition {
      condition     = length(try(local.subnet_cidr_conflicts["wan"], [])) == 0
      error_message = "Subnet ${try(local.subnet_cidr_conflicts["wan"][0], "")} already uses ${var.subnet_wan_prefix} in ${var.vpc_id}: set subnet_wan_id = \"${try(local.subnet_cidr_conflicts["wan"][0], "")}\" to reuse it, or choose a different subnet_wan_prefix."
    }
  }
}

resource "aws_subnet" "lan" {
  count                           = local.create_subnet_lan ? 1 : 0
  vpc_id                          = local.vpc_id_resolved
  availability_zone               = var.availability_zone
  cidr_block                      = var.subnet_lan_prefix
  ipv6_cidr_block                 = local.lan_subnet_ipv6_cidr
  assign_ipv6_address_on_creation = local.lan_ipv6

  tags = merge(local.tags, { Name = "${var.project_name}-lan" })

  lifecycle {
    precondition {
      condition     = length(try(local.subnet_cidr_conflicts["lan"], [])) == 0
      error_message = "Subnet ${try(local.subnet_cidr_conflicts["lan"][0], "")} already uses ${var.subnet_lan_prefix} in ${var.vpc_id}: set subnet_lan_id = \"${try(local.subnet_cidr_conflicts["lan"][0], "")}\" to reuse it, or choose a different subnet_lan_prefix."
    }
  }
}

# -----------------------------------------------------------------------------
# Route Tables — reuse route_table_*_id when provided, else create in the VPC in use.
# Only subnets created here are associated; existing subnets keep their current
# association (re-associating would fail with Resource.AlreadyAssociated).
# -----------------------------------------------------------------------------
# Without an IGW the WAN RT has no default routes; the operator adds egress (e.g. NAT/TGW).
resource "aws_route_table" "wan" {
  count  = local.create_rt_wan ? 1 : 0
  vpc_id = local.vpc_id_resolved

  dynamic "route" {
    for_each = local.use_igw ? [1] : []
    content {
      cidr_block = "0.0.0.0/0"
      gateway_id = local.igw_id_resolved
    }
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-wan-rt" })
}

resource "aws_route_table_association" "cloud_init" {
  count          = local.create_subnet_cloud_init ? 1 : 0
  subnet_id      = aws_subnet.cloud_init[0].id
  route_table_id = local.route_table_wan_id_resolved
}

resource "aws_route_table_association" "mgmt" {
  count          = local.create_subnet_mgmt ? 1 : 0
  subnet_id      = aws_subnet.mgmt[0].id
  route_table_id = local.route_table_wan_id_resolved
}

resource "aws_route_table_association" "wan" {
  count          = local.create_subnet_wan ? 1 : 0
  subnet_id      = aws_subnet.wan[0].id
  route_table_id = local.route_table_wan_id_resolved
}

resource "aws_route_table" "lan" {
  count  = local.create_rt_lan ? 1 : 0
  vpc_id = local.vpc_id_resolved

  tags = merge(local.tags, { Name = "${var.vm_name}-lan-rt" })
}

resource "aws_route_table_association" "lan" {
  count          = local.create_subnet_lan ? 1 : 0
  subnet_id      = aws_subnet.lan[0].id
  route_table_id = local.route_table_lan_id_resolved
}

# Default route via vEdge LAN ENI — only if test VM ingress is not explicitly configured.
# If ingress is custom-configured, only those subnets route via vEdge (see lan_ingress_via_vedge below).
# Wait for the LAN ENI attachment so the route is immediately usable when apply completes.
resource "aws_route" "lan_default_via_vedge" {
  count                  = !local.test_vm_ingress_custom ? 1 : 0
  route_table_id         = local.route_table_lan_id_resolved
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_network_interface.lan.id

  depends_on = [aws_network_interface_attachment.lan]
}

# IPv6 counterpart of lan_default_via_vedge (only when the LAN subnet has IPv6).
resource "aws_route" "lan_default_v6_via_vedge" {
  count                       = local.lan_ipv6 && !local.test_vm_ingress_custom ? 1 : 0
  route_table_id              = local.route_table_lan_id_resolved
  destination_ipv6_cidr_block = "::/0"
  network_interface_id        = aws_network_interface.lan.id

  depends_on = [aws_network_interface_attachment.lan]
}

# Routes for explicitly configured test VM ingress subnets via vEdge LAN ENI.
# Each configured subnet gets its own route to the vEdge LAN interface.
resource "aws_route" "lan_ingress_via_vedge" {
  for_each               = local.test_vm_ingress_custom ? toset(var.test_vm_ingress_allowed_subnets) : []
  route_table_id         = local.route_table_lan_id_resolved
  destination_cidr_block = each.value
  network_interface_id   = aws_network_interface.lan.id

  depends_on = [aws_network_interface_attachment.lan]
}

# Test VM SSH return traffic via IGW — one route per allowed SSH subnet.
# Allows responses to SSH connections from external sources to route back via the Internet Gateway.
resource "aws_route" "lan_ssh_via_igw" {
  for_each               = local.test_vm_ssh_via_igw ? toset(var.test_vm_ssh_allowed_subnets) : []
  route_table_id         = local.route_table_lan_id_resolved
  destination_cidr_block = each.value
  gateway_id             = local.igw_id_resolved

  depends_on = [aws_network_interface_attachment.lan]
}

# -----------------------------------------------------------------------------
# Security Groups — reuse security_group_*_id when provided (must be in the same
# VPC), else create. Cloud-init SG is devtest only.
# -----------------------------------------------------------------------------

# Cloud-init SG — devtest only
resource "aws_security_group" "cloud_init" {
  count       = local.create_sg_cloud_init ? 1 : 0
  name        = "${var.vm_name}-cloudinit-sg"
  description = "Graphiant vEdge cloud-init interface"
  vpc_id      = local.vpc_id_resolved

  ingress {
    description = "SSH from allowed CIDRs"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  egress {
    description = "IMDS HTTP endpoint"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["169.254.169.254/32"]
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-cloudinit-sg" })

  # Renaming vm_name replaces the SG; create the new one first so the in-use ENI
  # can be switched to it before the old SG is deleted (else DependencyViolation).
  lifecycle {
    create_before_destroy = true
  }
}

# Mgmt SG
resource "aws_security_group" "mgmt" {
  count       = local.create_sg_mgmt ? 1 : 0
  name        = "${var.vm_name}-mgmt-sg"
  description = "Graphiant Device Management Interface"
  vpc_id      = local.vpc_id_resolved

  # Devtest: HTTPS from allowed CIDRs. Production: no ingress (operator
  # must open the local web UI explicitly after onboarding if needed).
  dynamic "ingress" {
    for_each = local.is_devtest ? [443] : []
    content {
      description = "Inbound TCP/${ingress.value} from allowed CIDRs (devtest)"
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = [var.allowed_cidr]
    }
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-mgmt-sg" })

  # See aws_security_group.cloud_init.
  lifecycle {
    create_before_destroy = true
  }
}

# WAN SG — outbound rules for Graphiant network services (DNS, HTTPS, IKE, IPsec NAT-T, GRPC/TLS).
resource "aws_security_group" "wan" {
  count       = local.create_sg_wan ? 1 : 0
  name        = "${var.vm_name}-wan-sg"
  description = "Graphiant vEdge WAN Connectivity Interface"
  vpc_id      = local.vpc_id_resolved

  egress {
    description = "DNS"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "HTTPS to Graphiant onboarding services"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "IKEv2"
    from_port   = 500
    to_port     = 500
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "IPsec NAT Traversal"
    from_port   = 4500
    to_port     = 4500
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "TLS to Graphiant onboarding gateway"
    from_port   = 16000
    to_port     = 16000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "NTP"
    from_port   = 123
    to_port     = 123
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-wan-sg" })

  # See aws_security_group.cloud_init.
  lifecycle {
    create_before_destroy = true
  }
}

# LAN SG - Allow all Inbound and Outbound traffic
resource "aws_security_group" "lan" {
  count       = local.create_sg_lan ? 1 : 0
  name        = "${var.vm_name}-lan-sg"
  description = "Graphiant vEdge LAN (customer ingress) interface"
  vpc_id      = local.vpc_id_resolved

  ingress {
    description      = "Allow all ingress"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = local.lan_ipv6 ? ["::/0"] : null
  }

  egress {
    description      = "Allow all egress"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = local.lan_ipv6 ? ["::/0"] : null
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-lan-sg" })

  # See aws_security_group.cloud_init.
  lifecycle {
    create_before_destroy = true
  }
}

# -----------------------------------------------------------------------------
# Network Interfaces
# -----------------------------------------------------------------------------
resource "aws_network_interface" "cloud_init" {
  count           = local.is_devtest ? 1 : 0
  subnet_id       = local.subnet_cloud_init_id_resolved
  security_groups = [local.sg_cloud_init_id_resolved]
  description     = "Graphiant cloud-init"

  tags = merge(local.tags, { Name = "CloudInit" })
}

resource "aws_network_interface" "mgmt" {
  subnet_id       = local.subnet_mgmt_id_resolved
  security_groups = [local.sg_mgmt_id_resolved]
  description     = "Graphiant local management"

  tags = merge(local.tags, { Name = "LocalManagement" })
}

resource "aws_network_interface" "wan" {
  subnet_id         = local.subnet_wan_id_resolved
  security_groups   = [local.sg_wan_id_resolved]
  source_dest_check = false
  description       = "Graphiant Network"

  tags = merge(local.tags, { Name = "WanDefault" })
}

resource "aws_network_interface" "lan" {
  subnet_id         = local.subnet_lan_id_resolved
  security_groups   = [local.sg_lan_id_resolved]
  source_dest_check = false
  description       = "Customer ingress"
  # null on an existing LAN subnet: its own IPv6 auto-assign setting decides.
  ipv6_address_count = local.lan_ipv6 ? 1 : null

  tags = merge(local.tags, { Name = "LanDefault" })
}

# -----------------------------------------------------------------------------
# Elastic IPs (no EIP on the LAN NIC; none at all without an IGW) — mgmt/wan reuse
# eip_*_allocation_id when provided, else allocate. A provided EIP is only disassociated
# on destroy, never released.
# -----------------------------------------------------------------------------
resource "aws_eip" "cloud_init" {
  count  = local.is_devtest && local.use_igw ? 1 : 0
  domain = "vpc"

  tags = merge(local.tags, { Name = "${var.vm_name}-cloudinit-eip" })
}

resource "aws_eip_association" "cloud_init" {
  count                = local.is_devtest && local.use_igw ? 1 : 0
  allocation_id        = aws_eip.cloud_init[0].id
  network_interface_id = aws_network_interface.cloud_init[0].id
}

resource "aws_eip" "mgmt" {
  count  = local.create_eip_mgmt ? 1 : 0
  domain = "vpc"

  tags = merge(local.tags, { Name = "${var.vm_name}-mgmt-eip" })
}

data "aws_eip" "mgmt" {
  count = local.use_igw && !local.create_eip_mgmt ? 1 : 0
  id    = var.eip_mgmt_allocation_id
}

resource "aws_eip_association" "mgmt" {
  count                = local.use_igw ? 1 : 0
  allocation_id        = local.eip_mgmt_allocation_id_resolved
  network_interface_id = aws_network_interface.mgmt.id
}

resource "aws_eip" "wan" {
  count  = local.create_eip_wan ? 1 : 0
  domain = "vpc"

  tags = merge(local.tags, { Name = "${var.vm_name}-wan-eip" })
}

data "aws_eip" "wan" {
  count = local.use_igw && !local.create_eip_wan ? 1 : 0
  id    = var.eip_wan_allocation_id
}

resource "aws_eip_association" "wan" {
  count                = local.use_igw ? 1 : 0
  allocation_id        = local.eip_wan_allocation_id_resolved
  network_interface_id = aws_network_interface.wan.id
}

# -----------------------------------------------------------------------------
# vEdge EC2 instance
# NIC ordering:
#   Production : mgmt=0, wan=1, lan=2
#   Devtest    : cloud-init=0, mgmt=1, wan=2, lan=3
# -----------------------------------------------------------------------------
resource "aws_instance" "vedge" {
  ami           = local.resolved_image_id
  instance_type = var.instance_type
  user_data     = local.user_data
  # Cloud-init only runs on first boot; force re-create when user_data changes
  # so token / onboarding params / SSH key / password updates actually take effect.
  user_data_replace_on_change = true

  # Primary NIC (device_index 0): cloud-init in devtest, mgmt in production.
  # Additional NICs are attached below via aws_network_interface_attachment.
  primary_network_interface {
    network_interface_id = local.is_devtest ? aws_network_interface.cloud_init[0].id : aws_network_interface.mgmt.id
  }

  metadata_options {
    http_endpoint          = "enabled"
    http_tokens            = "required"
    instance_metadata_tags = "enabled"
  }

  tags = merge(local.tags, { Name = var.vm_name })

  depends_on = [
    aws_eip_association.mgmt,
    aws_eip_association.wan,
  ]

  lifecycle {
    precondition {
      condition     = local.resolved_image_id != ""
      error_message = "Set either image_id (explicit AMI) or marketplace_product_id (and optionally marketplace_version)."
    }

    precondition {
      condition = !local.new_vpc || alltrue([
        for id in [
          var.subnet_cloud_init_id, var.subnet_mgmt_id, var.subnet_wan_id, var.subnet_lan_id,
          var.route_table_wan_id, var.route_table_lan_id,
          var.security_group_cloud_init_id, var.security_group_mgmt_id, var.security_group_wan_id, var.security_group_lan_id, var.security_group_test_vm_id,
          var.internet_gateway_id,
        ] : id == ""
      ])
      error_message = "subnet_*_id, route_table_*_id, security_group_*_id and internet_gateway_id must be empty when vpc_id is empty: they cannot belong to the VPC being created (eip_*_allocation_id may be set)."
    }

    # An existing subnet is never re-associated, so a newly created LAN RT would not carry its traffic.
    precondition {
      condition     = var.subnet_lan_id == "" || var.route_table_lan_id != ""
      error_message = "route_table_lan_id is required when subnet_lan_id is provided (the default-via-vEdge route is added to the LAN subnet's existing route table)."
    }

    precondition {
      condition     = !local.test_vm_ssh_via_igw || length(setintersection(toset(var.test_vm_ssh_allowed_subnets), toset(local.lan_vedge_routed_cidrs))) == 0
      error_message = "test_vm_ssh_allowed_subnets must not include CIDRs already routed via the vEdge in the LAN route table (${join(", ", local.lan_vedge_routed_cidrs)})."
    }

    precondition {
      condition     = local.use_igw || (!local.test_vm_ssh_via_igw && var.eip_mgmt_allocation_id == "" && var.eip_wan_allocation_id == "")
      error_message = "Without an IGW (create_internet_gateway = false, no internet_gateway_id), public IPs cannot be used: unset eip_*_allocation_id and test_vm_enable_ssh_public_ip."
    }
  }
}

# Additional NIC attachments (device_index >= 1).
# Devtest: mgmt=1, wan=2, lan=3. Production: wan=1, lan=2 (mgmt is the primary NIC).
resource "aws_network_interface_attachment" "mgmt" {
  count                = local.is_devtest ? 1 : 0
  instance_id          = aws_instance.vedge.id
  network_interface_id = aws_network_interface.mgmt.id
  device_index         = 1
}

resource "aws_network_interface_attachment" "wan" {
  instance_id          = aws_instance.vedge.id
  network_interface_id = aws_network_interface.wan.id
  device_index         = local.is_devtest ? 2 : 1
}

resource "aws_network_interface_attachment" "lan" {
  instance_id          = aws_instance.vedge.id
  network_interface_id = aws_network_interface.lan.id
  device_index         = local.is_devtest ? 3 : 2
}

# -----------------------------------------------------------------------------
# Test VM (optional) — Debian 13, attached to LAN subnet, private IP only.
# Default route is set to the vEdge LAN private IP via cloud-init runcmd.
# -----------------------------------------------------------------------------
resource "aws_security_group" "test_vm" {
  count       = local.create_sg_test_vm ? 1 : 0
  name        = "${var.test_vm_name}-sg"
  description = "Graphiant vEdge test VM"
  vpc_id      = local.vpc_id_resolved

  # IPv6: all when ingress is left at the 0.0.0.0/0 default, else only the LAN /64.
  ingress {
    description      = "Allow ingress from specified subnets"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = var.test_vm_ingress_allowed_subnets
    ipv6_cidr_blocks = local.lan_ipv6 ? (local.test_vm_ingress_custom ? [local.lan_subnet_ipv6_cidr] : ["::/0"]) : null
  }

  dynamic "ingress" {
    for_each = var.test_vm_enable_ssh_public_ip ? var.test_vm_ssh_allowed_subnets : []
    content {
      description = "SSH from allowed subnets (public)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  egress {
    description      = "Allow all egress"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = local.lan_ipv6 ? ["::/0"] : null
  }

  tags = merge(local.tags, { Name = "${var.test_vm_name}-sg" })

  # Renaming test_vm_name replaces the SG; see aws_security_group.cloud_init.
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_network_interface" "test_vm" {
  count              = var.deploy_test_vm ? 1 : 0
  subnet_id          = local.subnet_lan_id_resolved
  security_groups    = [local.sg_test_vm_id_resolved]
  description        = "Graphiant vEdge test VM"
  ipv6_address_count = local.lan_ipv6 ? 1 : null

  tags = merge(local.tags, { Name = "${var.test_vm_name}-nic" })
}

resource "aws_eip" "test_vm" {
  count  = var.deploy_test_vm && var.test_vm_enable_ssh_public_ip ? 1 : 0
  domain = "vpc"

  tags = merge(local.tags, { Name = "${var.test_vm_name}-eip" })
}

resource "aws_eip_association" "test_vm" {
  count                = var.deploy_test_vm && var.test_vm_enable_ssh_public_ip ? 1 : 0
  allocation_id        = aws_eip.test_vm[0].id
  network_interface_id = aws_network_interface.test_vm[0].id
}

resource "aws_instance" "test_vm" {
  count         = var.deploy_test_vm ? 1 : 0
  ami           = local.test_vm_ami_resolved
  instance_type = var.test_vm_instance_type
  key_name      = var.test_vm_key_name != "" ? var.test_vm_key_name : null

  primary_network_interface {
    network_interface_id = aws_network_interface.test_vm[0].id
  }

  tags = merge(local.tags, { Name = var.test_vm_name })

  lifecycle {
    precondition {
      condition     = local.test_vm_ami_resolved != ""
      error_message = "Set test_vm_ami explicitly or ensure Debian 13 AMI is available in the region."
    }
  }
}
