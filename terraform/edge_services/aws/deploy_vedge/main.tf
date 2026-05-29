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

  create_rt_wan = local.new_vpc && var.route_table_wan_id == ""
  create_rt_lan = local.new_vpc && var.route_table_lan_id == ""

  # Test VM ingress: check if explicitly configured (not default allow-all)
  test_vm_ingress_custom = var.deploy_test_vm && !(length(var.test_vm_ingress_allowed_subnets) == 1 && var.test_vm_ingress_allowed_subnets[0] == "0.0.0.0/0")

  vpc_id_resolved = local.use_existing_vpc ? var.vpc_id : aws_vpc.this[0].id

  subnet_cloud_init_id_resolved = (
    local.new_vpc && local.is_devtest
    ? aws_subnet.cloud_init[0].id
    : var.subnet_cloud_init_id
  )
  subnet_mgmt_id_resolved = local.new_vpc ? aws_subnet.mgmt[0].id : var.subnet_mgmt_id
  subnet_wan_id_resolved  = local.new_vpc ? aws_subnet.wan[0].id : var.subnet_wan_id
  subnet_lan_id_resolved  = local.new_vpc ? aws_subnet.lan[0].id : var.subnet_lan_id

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
# VPC + IGW + Subnets (new VPC only)
# -----------------------------------------------------------------------------
resource "aws_vpc" "this" {
  count                            = local.new_vpc ? 1 : 0
  cidr_block                       = var.vpc_address_range
  assign_generated_ipv6_cidr_block = true
  enable_dns_support               = true
  enable_dns_hostnames             = true

  tags = merge(local.tags, { Name = var.vpc_name })
}

resource "aws_internet_gateway" "this" {
  count  = local.new_vpc ? 1 : 0
  vpc_id = aws_vpc.this[0].id

  tags = merge(local.tags, { Name = "${var.project_name}-igw" })
}

# Cloud-init subnet — only created for devtest in new VPC mode
resource "aws_subnet" "cloud_init" {
  count                           = local.new_vpc && local.is_devtest ? 1 : 0
  vpc_id                          = aws_vpc.this[0].id
  availability_zone               = var.availability_zone
  cidr_block                      = var.subnet_cloud_init_prefix
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.this[0].ipv6_cidr_block, 8, 0)
  assign_ipv6_address_on_creation = true

  tags = merge(local.tags, { Name = "${var.project_name}-cloudinit" })
}

resource "aws_subnet" "mgmt" {
  count                           = local.new_vpc ? 1 : 0
  vpc_id                          = aws_vpc.this[0].id
  availability_zone               = var.availability_zone
  cidr_block                      = var.subnet_mgmt_prefix
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.this[0].ipv6_cidr_block, 8, 1)
  assign_ipv6_address_on_creation = true

  tags = merge(local.tags, { Name = "${var.project_name}-mgmt" })
}

resource "aws_subnet" "wan" {
  count                           = local.new_vpc ? 1 : 0
  vpc_id                          = aws_vpc.this[0].id
  availability_zone               = var.availability_zone
  cidr_block                      = var.subnet_wan_prefix
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.this[0].ipv6_cidr_block, 8, 2)
  assign_ipv6_address_on_creation = true

  tags = merge(local.tags, { Name = "${var.project_name}-wan" })
}

resource "aws_subnet" "lan" {
  count                           = local.new_vpc ? 1 : 0
  vpc_id                          = aws_vpc.this[0].id
  availability_zone               = var.availability_zone
  cidr_block                      = var.subnet_lan_prefix
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.this[0].ipv6_cidr_block, 8, 3)
  assign_ipv6_address_on_creation = true

  tags = merge(local.tags, { Name = "${var.project_name}-lan" })
}

# -----------------------------------------------------------------------------
# Route Tables — create new (new VPC, no route_table_*_id provided) or reuse existing
# -----------------------------------------------------------------------------
resource "aws_route_table" "wan" {
  count  = local.create_rt_wan ? 1 : 0
  vpc_id = aws_vpc.this[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this[0].id
  }

  route {
    ipv6_cidr_block = "::/0"
    gateway_id      = aws_internet_gateway.this[0].id
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-wan-rt" })
}

resource "aws_route_table_association" "cloud_init" {
  count          = local.create_rt_wan && local.is_devtest ? 1 : 0
  subnet_id      = aws_subnet.cloud_init[0].id
  route_table_id = aws_route_table.wan[0].id
}

resource "aws_route_table_association" "mgmt" {
  count          = local.create_rt_wan ? 1 : 0
  subnet_id      = aws_subnet.mgmt[0].id
  route_table_id = aws_route_table.wan[0].id
}

resource "aws_route_table_association" "wan" {
  count          = local.create_rt_wan ? 1 : 0
  subnet_id      = aws_subnet.wan[0].id
  route_table_id = aws_route_table.wan[0].id
}

resource "aws_route_table" "lan" {
  count  = local.create_rt_lan ? 1 : 0
  vpc_id = aws_vpc.this[0].id

  tags = merge(local.tags, { Name = "${var.vm_name}-lan-rt" })
}

resource "aws_route_table_association" "lan" {
  count          = local.create_rt_lan ? 1 : 0
  subnet_id      = aws_subnet.lan[0].id
  route_table_id = aws_route_table.lan[0].id
}

# Default route via vEdge LAN ENI — only if test VM ingress is not explicitly configured.
# If ingress is custom-configured, only those subnets route via vEdge (see lan_ingress_via_vedge below).
# Wait for the LAN ENI attachment so the route is immediately usable when apply completes.
resource "aws_route" "lan_default_via_vedge" {
  count                  = !local.test_vm_ingress_custom ? 1 : 0
  route_table_id         = local.create_rt_lan ? aws_route_table.lan[0].id : var.route_table_lan_id
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_network_interface.lan.id

  depends_on = [aws_network_interface_attachment.lan]
}

# Routes for explicitly configured test VM ingress subnets via vEdge LAN ENI.
# Each configured subnet gets its own route to the vEdge LAN interface.
resource "aws_route" "lan_ingress_via_vedge" {
  for_each               = local.test_vm_ingress_custom ? toset(var.test_vm_ingress_allowed_subnets) : []
  route_table_id         = local.create_rt_lan ? aws_route_table.lan[0].id : var.route_table_lan_id
  destination_cidr_block = each.value
  network_interface_id   = aws_network_interface.lan.id

  depends_on = [aws_network_interface_attachment.lan]
}

# Test VM SSH return traffic via IGW — one route per allowed SSH subnet.
# Allows responses to SSH connections from external sources to route back via the Internet Gateway.
resource "aws_route" "lan_ssh_via_igw" {
  for_each               = var.test_vm_enable_ssh_public_ip ? toset(var.test_vm_ssh_allowed_subnets) : []
  route_table_id         = local.create_rt_lan ? aws_route_table.lan[0].id : var.route_table_lan_id
  destination_cidr_block = each.value
  gateway_id             = local.new_vpc ? aws_internet_gateway.this[0].id : data.aws_internet_gateway.existing[0].id

  depends_on = [aws_network_interface_attachment.lan]
}

# Data source to fetch existing IGW when reusing an existing VPC
data "aws_internet_gateway" "existing" {
  count = var.test_vm_enable_ssh_public_ip && !local.new_vpc ? 1 : 0

  filter {
    name   = "attachment.vpc-id"
    values = [local.vpc_id_resolved]
  }
}

# -----------------------------------------------------------------------------
# Security Groups (all VPC-scoped; SG creation is conditional on mode)
# -----------------------------------------------------------------------------

# Cloud-init SG — devtest only
resource "aws_security_group" "cloud_init" {
  count       = local.is_devtest ? 1 : 0
  name        = "${var.vm_name}-cloudinit-sg"
  description = "Graphiant vEdge cloud-init interface"
  vpc_id      = local.vpc_id_resolved

  ingress {
    description      = "SSH from allowed CIDRs"
    from_port        = 22
    to_port          = 22
    protocol         = "tcp"
    cidr_blocks      = [var.allowed_cidr]
    ipv6_cidr_blocks = [var.allowed_cidr_v6]
  }

  egress {
    description = "IMDS HTTP endpoint"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["169.254.169.254/32"]
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-cloudinit-sg" })
}

# Mgmt SG
resource "aws_security_group" "mgmt" {
  name        = "${var.vm_name}-mgmt-sg"
  description = "Graphiant Device Management Interface"
  vpc_id      = local.vpc_id_resolved

  # Devtest: HTTPS from allowed CIDRs. Production: no ingress (operator
  # must open the local web UI explicitly after onboarding if needed).
  dynamic "ingress" {
    for_each = local.is_devtest ? [443] : []
    content {
      description      = "Inbound TCP/${ingress.value} from allowed CIDRs (devtest)"
      from_port        = ingress.value
      to_port          = ingress.value
      protocol         = "tcp"
      cidr_blocks      = [var.allowed_cidr]
      ipv6_cidr_blocks = [var.allowed_cidr_v6]
    }
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-mgmt-sg" })
}

# WAN SG — outbound rules for Graphiant network services (DNS, HTTPS, IKE, IPsec NAT-T, GRPC/TLS).
resource "aws_security_group" "wan" {
  name        = "${var.vm_name}-wan-sg"
  description = "Graphiant vEdge WAN Connectivity Interface"
  vpc_id      = local.vpc_id_resolved

  egress {
    description      = "DNS"
    from_port        = 53
    to_port          = 53
    protocol         = "udp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description      = "HTTPS to Graphiant onboarding services"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description      = "IKEv2"
    from_port        = 500
    to_port          = 500
    protocol         = "udp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description      = "IPsec NAT Traversal"
    from_port        = 4500
    to_port          = 4500
    protocol         = "udp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description      = "TLS to Graphiant onboarding gateway"
    from_port        = 16000
    to_port          = 16000
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description      = "NTP"
    from_port        = 123
    to_port          = 123
    protocol         = "udp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-wan-sg" })
}

# LAN SG - Allow all Inbound and Outbound traffic
resource "aws_security_group" "lan" {
  name        = "${var.vm_name}-lan-sg"
  description = "Graphiant vEdge LAN (customer ingress) interface"
  vpc_id      = local.vpc_id_resolved

  ingress {
    description      = "Allow all ingress"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description      = "Allow all egress"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = merge(local.tags, { Name = "${var.vm_name}-lan-sg" })
}

# -----------------------------------------------------------------------------
# Network Interfaces
# -----------------------------------------------------------------------------
resource "aws_network_interface" "cloud_init" {
  count           = local.is_devtest ? 1 : 0
  subnet_id       = local.subnet_cloud_init_id_resolved
  security_groups = [aws_security_group.cloud_init[0].id]
  description     = "Graphiant cloud-init"

  tags = merge(local.tags, { Name = "CloudInit" })
}

resource "aws_network_interface" "mgmt" {
  subnet_id       = local.subnet_mgmt_id_resolved
  security_groups = [aws_security_group.mgmt.id]
  description     = "Graphiant local management"

  tags = merge(local.tags, { Name = "LocalManagement" })
}

resource "aws_network_interface" "wan" {
  subnet_id         = local.subnet_wan_id_resolved
  security_groups   = [aws_security_group.wan.id]
  source_dest_check = false
  description       = "Graphiant Network"

  tags = merge(local.tags, { Name = "WanDefault" })
}

resource "aws_network_interface" "lan" {
  subnet_id         = local.subnet_lan_id_resolved
  security_groups   = [aws_security_group.lan.id]
  source_dest_check = false
  description       = "Customer ingress"

  tags = merge(local.tags, { Name = "LanDefault" })
}

# -----------------------------------------------------------------------------
# Elastic IPs (no EIP on the LAN NIC)
# -----------------------------------------------------------------------------
resource "aws_eip" "cloud_init" {
  count  = local.is_devtest ? 1 : 0
  domain = "vpc"

  tags = merge(local.tags, { Name = "${var.vm_name}-cloudinit-eip" })
}

resource "aws_eip_association" "cloud_init" {
  count                = local.is_devtest ? 1 : 0
  allocation_id        = aws_eip.cloud_init[0].id
  network_interface_id = aws_network_interface.cloud_init[0].id
}

resource "aws_eip" "mgmt" {
  domain = "vpc"

  tags = merge(local.tags, { Name = "${var.vm_name}-mgmt-eip" })
}

resource "aws_eip_association" "mgmt" {
  allocation_id        = aws_eip.mgmt.id
  network_interface_id = aws_network_interface.mgmt.id
}

resource "aws_eip" "wan" {
  domain = "vpc"

  tags = merge(local.tags, { Name = "${var.vm_name}-wan-eip" })
}

resource "aws_eip_association" "wan" {
  allocation_id        = aws_eip.wan.id
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
  count       = var.deploy_test_vm ? 1 : 0
  name        = "${var.test_vm_name}-sg"
  description = "Graphiant vEdge test VM"
  vpc_id      = local.vpc_id_resolved

  ingress {
    description = "Allow ingress from specified subnets"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = var.test_vm_ingress_allowed_subnets
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
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = merge(local.tags, { Name = "${var.test_vm_name}-sg" })
}

resource "aws_network_interface" "test_vm" {
  count           = var.deploy_test_vm ? 1 : 0
  subnet_id       = local.subnet_lan_id_resolved
  security_groups = [aws_security_group.test_vm[0].id]
  description     = "Graphiant vEdge test VM"

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
