terraform {
  required_version = ">= 1.3.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80.0"
    }
  }
}

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
  skip_provider_registration = true
}

# -----------------------------------------------------------------------------
# Locals
# -----------------------------------------------------------------------------
locals {
  is_create      = var.action == "create"
  is_devtest     = var.mode == "devtest"
  admin_username = local.is_devtest ? "gnos" : "gradmin"

  # Derive flags from whether IDs are provided
  use_existing_rg   = var.resource_group_id != ""
  use_existing_vnet = var.vnet_id != ""
  new_vnet          = !local.use_existing_vnet

  # Parse RG name from ARM resource ID: /subscriptions/<sub>/resourceGroups/<name>
  existing_rg_name = local.use_existing_rg ? element(split("/", var.resource_group_id), 4) : ""
  rg_name          = local.use_existing_rg ? local.existing_rg_name : azurerm_resource_group.rg[0].name
  rg_location      = local.use_existing_rg ? data.azurerm_resource_group.existing[0].location : azurerm_resource_group.rg[0].location

  tags = merge(
    {
      Environment = var.mode
      Vendor      = "Graphiant"
    },
    var.tags
  )

  # VNet name/RG to create subnets in — parsed from vnet_id: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<name>
  vnet_name_resolved = local.use_existing_vnet ? element(split("/", var.vnet_id), 8) : var.vnet_name
  vnet_rg_resolved   = local.use_existing_vnet ? element(split("/", var.vnet_id), 4) : local.rg_name

  # Each component is independent: reuse it when its *_id is set, else create it
  create_subnet_cloud_init = local.is_create && local.is_devtest && var.subnet_cloud_init_id == ""
  create_subnet_mgmt       = local.is_create && var.subnet_mgmt_id == ""
  create_subnet_wan        = local.is_create && var.subnet_wan_id == ""
  create_subnet_lan        = local.is_create && var.subnet_lan_id == ""

  # A route table is only created when a new subnet needs it; existing subnets keep their association
  create_rt_wan = local.is_create && var.route_table_wan_id == "" && (local.create_subnet_mgmt || local.create_subnet_wan)
  create_rt_lan = local.is_create && var.route_table_lan_id == "" && local.create_subnet_lan

  create_nsg_cloud_init = local.is_create && local.is_devtest && var.nsg_cloud_init_id == ""
  create_nsg_mgmt       = local.is_create && var.nsg_mgmt_id == ""
  create_nsg_wan        = local.is_create && var.nsg_wan_id == ""
  create_nsg_lan        = local.is_create && var.nsg_lan_id == ""
  create_nsg_test_vm    = local.is_create && var.deploy_test_vm && var.nsg_test_vm_id == ""

  create_pip_mgmt = local.is_create && var.public_ip_mgmt_id == ""
  create_pip_wan  = local.is_create && var.public_ip_wan_id == ""

  subnet_cloud_init_id = local.create_subnet_cloud_init ? azurerm_subnet.cloud_init[0].id : var.subnet_cloud_init_id
  subnet_mgmt_id       = local.create_subnet_mgmt ? azurerm_subnet.mgmt[0].id : var.subnet_mgmt_id
  subnet_wan_id        = local.create_subnet_wan ? azurerm_subnet.wan[0].id : var.subnet_wan_id
  subnet_lan_id        = local.create_subnet_lan ? azurerm_subnet.lan[0].id : var.subnet_lan_id

  route_table_wan_id = local.create_rt_wan ? azurerm_route_table.wan[0].id : var.route_table_wan_id
  route_table_lan_id = local.create_rt_lan ? azurerm_route_table.lan[0].id : var.route_table_lan_id

  nsg_cloud_init_id = local.create_nsg_cloud_init ? azurerm_network_security_group.cloud_init[0].id : var.nsg_cloud_init_id
  nsg_mgmt_id       = local.create_nsg_mgmt ? azurerm_network_security_group.mgmt[0].id : var.nsg_mgmt_id
  nsg_wan_id        = local.create_nsg_wan ? azurerm_network_security_group.wan[0].id : var.nsg_wan_id
  nsg_lan_id        = local.create_nsg_lan ? azurerm_network_security_group.lan[0].id : var.nsg_lan_id
  nsg_test_vm_id    = local.create_nsg_test_vm ? azurerm_network_security_group.test_vm[0].id : var.nsg_test_vm_id

  public_ip_mgmt_id = local.create_pip_mgmt ? azurerm_public_ip.mgmt[0].id : var.public_ip_mgmt_id
  public_ip_wan_id  = local.create_pip_wan ? azurerm_public_ip.wan[0].id : var.public_ip_wan_id

  # IPv6 is LAN-side only: VNet range, LAN subnet /64, vEdge LAN + test VM NICs, ::/0 route via vEdge.
  # lan_ipv6 drives counts, so it uses only plan-time values (vars + existing VNet/subnet lookups).
  vnet_ipv6_space          = local.new_vnet ? var.vnet_address_space_v6 : try([for p in data.azurerm_virtual_network.existing[0].address_space : p if can(regex(":", p))][0], "")
  existing_lan_subnet_ipv6 = length([for p in try(data.azurerm_subnet.lan_existing[0].address_prefixes, []) : p if can(regex(":", p))]) > 0
  lan_ipv6                 = local.is_create && (local.create_subnet_lan ? local.vnet_ipv6_space != "" : local.existing_lan_subnet_ipv6)
  lan_subnet_ipv6_prefix   = local.create_subnet_lan && local.lan_ipv6 ? try(cidrsubnet(local.vnet_ipv6_space, 64 - tonumber(split("/", local.vnet_ipv6_space)[1]), var.subnet_lan_ipv6_netnum), null) : null
  vedge_lan_ipv6           = local.lan_ipv6 ? try([for c in azurerm_network_interface.lan[0].ip_configuration : c.private_ip_address if c.private_ip_address_version == "IPv6"][0], null) : null

  # cloud-init user data
  cloud_init_production = <<-USERDATA
    #cloud-config

    graphnos:
      token: ${var.token}
  USERDATA

  cloud_init_devtest = <<-USERDATA
    #cloud-config

    graphnos:
      onboarding-gw: ${var.onboarding_gateway}
      onboarding-auth-url: ${var.onboarding_auth_url}
      token: ${var.token}

    users:
      - name: ${var.cloud_init_username}
        plain_text_passwd: '${var.cloud_init_password}'
        sudo: ["ALL=(ALL) NOPASSWD:ALL"]
        lock_passwd: false
        groups: sudo
        shell: /bin/bash
        ssh-authorized-keys:
          - ${var.ssh_public_key}
  USERDATA

  custom_data = base64encode(local.is_devtest ? local.cloud_init_devtest : local.cloud_init_production)

  # Use Shared Image Gallery image when source_image_id is provided (used for private Images not available in Azure marketplace)
  use_gallery_image = var.source_image_id != ""

}

# -----------------------------------------------------------------------------
# Resource Group
# -----------------------------------------------------------------------------
data "azurerm_resource_group" "existing" {
  count = local.use_existing_rg ? 1 : 0
  name  = local.existing_rg_name
}

resource "azurerm_resource_group" "rg" {
  count    = local.use_existing_rg || !local.is_create ? 0 : 1
  name     = var.resource_group_name != "" ? var.resource_group_name : "${var.project_name}-rg"
  location = var.azure_region

  tags = local.tags
}

# -----------------------------------------------------------------------------
# Virtual Network & Subnets — subnets are created in the new or existing VNet
# -----------------------------------------------------------------------------
resource "azurerm_virtual_network" "vnet" {
  count               = local.is_create && local.new_vnet ? 1 : 0
  name                = var.vnet_name
  resource_group_name = local.rg_name
  location            = local.rg_location
  address_space       = compact([var.vnet_address_space, var.vnet_address_space_v6])

  tags = local.tags
}

resource "azurerm_subnet" "cloud_init" {
  count                = local.create_subnet_cloud_init ? 1 : 0
  name                 = var.subnet_cloud_init_name
  resource_group_name  = local.vnet_rg_resolved
  virtual_network_name = local.new_vnet ? azurerm_virtual_network.vnet[0].name : local.vnet_name_resolved
  address_prefixes     = [var.subnet_cloud_init_prefix]
}

resource "azurerm_subnet" "mgmt" {
  count                = local.create_subnet_mgmt ? 1 : 0
  name                 = var.subnet_mgmt_name
  resource_group_name  = local.vnet_rg_resolved
  virtual_network_name = local.new_vnet ? azurerm_virtual_network.vnet[0].name : local.vnet_name_resolved
  address_prefixes     = [var.subnet_mgmt_prefix]
}

resource "azurerm_subnet" "wan" {
  count                = local.create_subnet_wan ? 1 : 0
  name                 = var.subnet_wan_name
  resource_group_name  = local.vnet_rg_resolved
  virtual_network_name = local.new_vnet ? azurerm_virtual_network.vnet[0].name : local.vnet_name_resolved
  address_prefixes     = [var.subnet_wan_prefix]
}

resource "azurerm_subnet" "lan" {
  count                = local.create_subnet_lan ? 1 : 0
  name                 = var.subnet_lan_name
  resource_group_name  = local.vnet_rg_resolved
  virtual_network_name = local.new_vnet ? azurerm_virtual_network.vnet[0].name : local.vnet_name_resolved
  address_prefixes     = local.lan_ipv6 ? [var.subnet_lan_prefix, local.lan_subnet_ipv6_prefix] : [var.subnet_lan_prefix]

  lifecycle {
    precondition {
      condition     = !local.lan_ipv6 || local.lan_subnet_ipv6_prefix != null
      error_message = "subnet_lan_ipv6_netnum (${var.subnet_lan_ipv6_netnum}) has no /64 in the VNet IPv6 range ${local.vnet_ipv6_space}: use a shorter prefix or a smaller index."
    }
  }
}

# Existing VNet / LAN subnet — read only to detect an IPv6 range (LAN side stays IPv4-only without one)
data "azurerm_virtual_network" "existing" {
  count               = local.is_create && local.use_existing_vnet ? 1 : 0
  name                = local.vnet_name_resolved
  resource_group_name = local.vnet_rg_resolved
}

# Subnet ID: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<name>
data "azurerm_subnet" "lan_existing" {
  count                = local.is_create && var.subnet_lan_id != "" ? 1 : 0
  name                 = element(split("/", var.subnet_lan_id), 10)
  virtual_network_name = element(split("/", var.subnet_lan_id), 8)
  resource_group_name  = element(split("/", var.subnet_lan_id), 4)
}

# -----------------------------------------------------------------------------
# Route Tables — create new or use existing (e.g. from deploy_vnet).
# Newly created subnets are associated with the new or existing route table.
# -----------------------------------------------------------------------------

# WAN route table — default route to Internet, BGP propagation disabled
resource "azurerm_route_table" "wan" {
  count                         = local.create_rt_wan ? 1 : 0
  name                          = "${var.vm_name}-wan-rt"
  location                      = local.rg_location
  resource_group_name           = local.rg_name
  disable_bgp_route_propagation = true

  route {
    name           = "default-to-igw"
    address_prefix = "0.0.0.0/0"
    next_hop_type  = "Internet"
  }

  tags = local.tags
}

resource "azurerm_subnet_route_table_association" "mgmt" {
  count          = local.create_subnet_mgmt ? 1 : 0
  subnet_id      = azurerm_subnet.mgmt[0].id
  route_table_id = local.route_table_wan_id
}

resource "azurerm_subnet_route_table_association" "wan" {
  count          = local.create_subnet_wan ? 1 : 0
  subnet_id      = azurerm_subnet.wan[0].id
  route_table_id = local.route_table_wan_id
}

# LAN route table — default route via vEdge LAN IP (Virtual Appliance)
resource "azurerm_route_table" "lan" {
  count                         = local.create_rt_lan ? 1 : 0
  name                          = "${var.vm_name}-lan-rt"
  location                      = local.rg_location
  resource_group_name           = local.rg_name
  disable_bgp_route_propagation = false

  route {
    name                   = "default-via-vedge"
    address_prefix         = "0.0.0.0/0"
    next_hop_type          = "VirtualAppliance"
    next_hop_in_ip_address = azurerm_network_interface.lan[0].private_ip_address
  }

  dynamic "route" {
    for_each = local.lan_ipv6 ? [1] : []
    content {
      name                   = "default-v6-via-vedge"
      address_prefix         = "::/0"
      next_hop_type          = "VirtualAppliance"
      next_hop_in_ip_address = local.vedge_lan_ipv6
    }
  }

  tags = local.tags
}

resource "azurerm_subnet_route_table_association" "lan" {
  count          = local.create_subnet_lan ? 1 : 0
  subnet_id      = azurerm_subnet.lan[0].id
  route_table_id = local.route_table_lan_id
}

# Add default route via vEdge LAN IP to an existing LAN route table (e.g. from deploy_vnet)
# RG and name parsed from route_table_lan_id: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/routeTables/<name>
resource "azurerm_route" "default_via_vedge" {
  count                  = local.is_create && var.route_table_lan_id != "" ? 1 : 0
  name                   = "default-via-vedge"
  resource_group_name    = element(split("/", var.route_table_lan_id), 4)
  route_table_name       = element(split("/", var.route_table_lan_id), 8)
  address_prefix         = "0.0.0.0/0"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = azurerm_network_interface.lan[0].private_ip_address
}

# IPv6 counterpart of default_via_vedge (only when the LAN subnet has IPv6)
resource "azurerm_route" "default_v6_via_vedge" {
  count                  = local.lan_ipv6 && var.route_table_lan_id != "" ? 1 : 0
  name                   = "default-v6-via-vedge"
  resource_group_name    = element(split("/", var.route_table_lan_id), 4)
  route_table_name       = element(split("/", var.route_table_lan_id), 8)
  address_prefix         = "::/0"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = local.vedge_lan_ipv6
}

# -----------------------------------------------------------------------------
# Network Security Groups
# -----------------------------------------------------------------------------

# Cloud-init NSG — devtest only: SSH inbound from allowed CIDRs
resource "azurerm_network_security_group" "cloud_init" {
  count               = local.create_nsg_cloud_init ? 1 : 0
  name                = "${var.vm_name}-cloudinit-nsg"
  location            = local.rg_location
  resource_group_name = local.rg_name

  security_rule {
    name                       = "AllowSSHIPv4"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.allowed_cidr
    destination_address_prefix = "*"
  }

  tags = local.tags
}

# Mgmt NSG — HTTPS(443) denied inbound by default (customer modifies in portal to allow access)
resource "azurerm_network_security_group" "mgmt" {
  count               = local.create_nsg_mgmt ? 1 : 0
  name                = "${var.vm_name}-mgmt-nsg"
  location            = local.rg_location
  resource_group_name = local.rg_name

  security_rule {
    name                       = "DenyHTTPS"
    priority                   = 101
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = local.tags
}

# WAN NSG — outbound rules for Graphiant network services
resource "azurerm_network_security_group" "wan" {
  count               = local.create_nsg_wan ? 1 : 0
  name                = "${var.vm_name}-wan-nsg"
  location            = local.rg_location
  resource_group_name = local.rg_name

  security_rule {
    name                       = "DNS"
    priority                   = 100
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "53"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "HTTPS"
    priority                   = 101
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "IKE"
    priority                   = 110
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "500"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "IPSec-NAT-T"
    priority                   = 111
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "4500"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "GCS-Onboarding-TLS"
    priority                   = 121
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "16000"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = local.tags
}

# LAN NSG — allow all inbound and outbound traffic
resource "azurerm_network_security_group" "lan" {
  count               = local.create_nsg_lan ? 1 : 0
  name                = "${var.vm_name}-lan-nsg"
  location            = local.rg_location
  resource_group_name = local.rg_name

  security_rule {
    name                       = "AllowAllInbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowAllOutbound"
    priority                   = 100
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = local.tags
}

# -----------------------------------------------------------------------------
# Public IPs
# -----------------------------------------------------------------------------
resource "azurerm_public_ip" "cloud_init" {
  count               = local.is_create && local.is_devtest ? 1 : 0
  name                = "${var.vm_name}-cloudinit-pip"
  location            = local.rg_location
  resource_group_name = local.rg_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = local.tags
}

resource "azurerm_public_ip" "mgmt" {
  count               = local.create_pip_mgmt ? 1 : 0
  name                = "${var.vm_name}-mgmt-pip"
  location            = local.rg_location
  resource_group_name = local.rg_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = local.tags
}

resource "azurerm_public_ip" "wan" {
  count               = local.create_pip_wan ? 1 : 0
  name                = "${var.vm_name}-wan-pip"
  location            = local.rg_location
  resource_group_name = local.rg_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = local.tags
}

# Existing public IPs (public_ip_*_id) — read for their address outputs; not deleted on destroy
data "azurerm_public_ip" "mgmt" {
  count               = local.is_create && !local.create_pip_mgmt ? 1 : 0
  name                = element(split("/", var.public_ip_mgmt_id), 8)
  resource_group_name = element(split("/", var.public_ip_mgmt_id), 4)
}

data "azurerm_public_ip" "wan" {
  count               = local.is_create && !local.create_pip_wan ? 1 : 0
  name                = element(split("/", var.public_ip_wan_id), 8)
  resource_group_name = element(split("/", var.public_ip_wan_id), 4)
}

# -----------------------------------------------------------------------------
# Network Interfaces
# -----------------------------------------------------------------------------

# Cloud-init NIC — devtest only
resource "azurerm_network_interface" "cloud_init" {
  count               = local.is_create && local.is_devtest ? 1 : 0
  name                = "${var.vm_name}-cloudinit-nic"
  location            = local.rg_location
  resource_group_name = local.rg_name

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = local.subnet_cloud_init_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.cloud_init[0].id
    primary                       = true
  }

  tags = local.tags
}

resource "azurerm_network_interface" "mgmt" {
  count               = local.is_create ? 1 : 0
  name                = "${var.vm_name}-mgmt-nic"
  location            = local.rg_location
  resource_group_name = local.rg_name

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = local.subnet_mgmt_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = local.public_ip_mgmt_id
    primary                       = true
  }

  enable_accelerated_networking = true
  enable_ip_forwarding          = true

  tags = local.tags
}

resource "azurerm_network_interface" "wan" {
  count               = local.is_create ? 1 : 0
  name                = "${var.vm_name}-wan-nic"
  location            = local.rg_location
  resource_group_name = local.rg_name

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = local.subnet_wan_id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = local.public_ip_wan_id
    primary                       = true
  }

  enable_accelerated_networking = true
  enable_ip_forwarding          = true

  tags = local.tags
}

resource "azurerm_network_interface" "lan" {
  count               = local.is_create ? 1 : 0
  name                = "${var.vm_name}-lan-nic"
  location            = local.rg_location
  resource_group_name = local.rg_name

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = local.subnet_lan_id
    private_ip_address_allocation = "Dynamic"
    primary                       = true
  }

  dynamic "ip_configuration" {
    for_each = local.lan_ipv6 ? [1] : []
    content {
      name                          = "ipconfig-v6"
      subnet_id                     = local.subnet_lan_id
      private_ip_address_allocation = "Dynamic"
      private_ip_address_version    = "IPv6"
    }
  }

  enable_accelerated_networking = true
  enable_ip_forwarding          = true

  tags = local.tags

  lifecycle {
    precondition {
      condition     = local.use_existing_vnet || alltrue([for id in [var.subnet_cloud_init_id, var.subnet_mgmt_id, var.subnet_wan_id, var.subnet_lan_id] : id == ""])
      error_message = "Existing subnet IDs (subnet_*_id) require vnet_id of the VNet they belong to."
    }
    # An existing LAN subnet keeps its route table, so the default-via-vEdge route needs to know which one it is
    precondition {
      condition     = var.subnet_lan_id == "" || var.route_table_lan_id != ""
      error_message = "route_table_lan_id is required when subnet_lan_id is provided (the default route via the vEdge LAN IP is added to it)."
    }
  }
}

# -----------------------------------------------------------------------------
# NSG Associations
# -----------------------------------------------------------------------------
resource "azurerm_network_interface_security_group_association" "cloud_init" {
  count                     = local.is_create && local.is_devtest ? 1 : 0
  network_interface_id      = azurerm_network_interface.cloud_init[0].id
  network_security_group_id = local.nsg_cloud_init_id
}

resource "azurerm_network_interface_security_group_association" "mgmt" {
  count                     = local.is_create ? 1 : 0
  network_interface_id      = azurerm_network_interface.mgmt[0].id
  network_security_group_id = local.nsg_mgmt_id
}

resource "azurerm_network_interface_security_group_association" "wan" {
  count                     = local.is_create ? 1 : 0
  network_interface_id      = azurerm_network_interface.wan[0].id
  network_security_group_id = local.nsg_wan_id
}

resource "azurerm_network_interface_security_group_association" "lan" {
  count                     = local.is_create ? 1 : 0
  network_interface_id      = azurerm_network_interface.lan[0].id
  network_security_group_id = local.nsg_lan_id
}

# -----------------------------------------------------------------------------
# Graphiant vEdge Virtual Machine
# -----------------------------------------------------------------------------
resource "azurerm_linux_virtual_machine" "vedge" {
  count               = local.is_create ? 1 : 0
  name                = var.vm_name
  computer_name       = var.vm_name
  resource_group_name = local.rg_name
  location            = local.rg_location
  size                = var.vm_size
  admin_username      = local.admin_username
  custom_data         = local.custom_data

  # Trusted Launch required by Shared Image Gallery images
  # Gallery images require TrustedLaunch with secure boot; Marketplace uses vTPM only (no secure boot)
  secure_boot_enabled = local.use_gallery_image
  vtpm_enabled        = true

  # NIC ordering: devtest has cloud-init as primary (4 NICs), production has mgmt as primary (3 NICs)
  network_interface_ids = local.is_devtest ? [
    azurerm_network_interface.cloud_init[0].id,
    azurerm_network_interface.mgmt[0].id,
    azurerm_network_interface.wan[0].id,
    azurerm_network_interface.lan[0].id,
    ] : [
    azurerm_network_interface.mgmt[0].id,
    azurerm_network_interface.wan[0].id,
    azurerm_network_interface.lan[0].id,
  ]

  # Marketplace image: plan + source_image_reference (production, or devtest without gallery image)
  dynamic "plan" {
    for_each = local.use_gallery_image ? [] : [1]
    content {
      publisher = var.image_publisher
      product   = var.image_offer
      name      = var.image_sku
    }
  }

  source_image_id = local.use_gallery_image ? var.source_image_id : null

  dynamic "source_image_reference" {
    for_each = local.use_gallery_image ? [] : [1]
    content {
      publisher = var.image_publisher
      offer     = var.image_offer
      sku       = var.image_sku
      version   = var.image_version
    }
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Premium_LRS"
  }

  # Password auth disabled; SSH key required by Azure API
  # Devtest: cloud-init creates gnos user with SSH key; Production: no SSH access, onboarding via token
  disable_password_authentication = true

  admin_ssh_key {
    username   = local.admin_username
    public_key = var.ssh_public_key
  }

  # Boot diagnostics with managed storage account (enables Serial Console)
  boot_diagnostics {}

  tags = local.tags

  depends_on = [
    azurerm_network_interface_security_group_association.cloud_init,
    azurerm_network_interface_security_group_association.mgmt,
    azurerm_network_interface_security_group_association.wan,
    azurerm_network_interface_security_group_association.lan,
  ]
}

# -----------------------------------------------------------------------------
# Test VM (optional) — attached to LAN subnet
# -----------------------------------------------------------------------------
resource "azurerm_network_security_group" "test_vm" {
  count               = local.create_nsg_test_vm ? 1 : 0
  name                = "${var.test_vm_name}-nsg"
  location            = local.rg_location
  resource_group_name = local.rg_name

  security_rule {
    name                       = "AllowAllInbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowAllOutbound"
    priority                   = 100
    direction                  = "Outbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = local.tags
}

resource "azurerm_network_interface" "test_vm" {
  count               = local.is_create && var.deploy_test_vm ? 1 : 0
  name                = "${var.test_vm_name}-nic"
  location            = local.rg_location
  resource_group_name = local.rg_name

  ip_configuration {
    name                          = "ipconfig1"
    subnet_id                     = local.subnet_lan_id
    private_ip_address_allocation = "Dynamic"
    primary                       = true
  }

  dynamic "ip_configuration" {
    for_each = local.lan_ipv6 ? [1] : []
    content {
      name                          = "ipconfig-v6"
      subnet_id                     = local.subnet_lan_id
      private_ip_address_allocation = "Dynamic"
      private_ip_address_version    = "IPv6"
    }
  }

  tags = local.tags
}

resource "azurerm_network_interface_security_group_association" "test_vm" {
  count                     = local.is_create && var.deploy_test_vm ? 1 : 0
  network_interface_id      = azurerm_network_interface.test_vm[0].id
  network_security_group_id = local.nsg_test_vm_id
}

resource "azurerm_linux_virtual_machine" "test_vm" {
  count               = local.is_create && var.deploy_test_vm ? 1 : 0
  name                = var.test_vm_name
  computer_name       = replace(var.test_vm_name, "_", "-")
  resource_group_name = local.rg_name
  location            = local.rg_location
  size                = var.test_vm_size
  admin_username      = var.test_vm_admin_username

  network_interface_ids = [
    azurerm_network_interface.test_vm[0].id,
  ]

  admin_password                  = var.test_vm_admin_password
  disable_password_authentication = false

  # Set default route via vEdge LAN IP and remove DHCP default route
  custom_data = base64encode(<<-USERDATA
    #cloud-config

    runcmd:
      - ip route del default via $(ip route | grep 'default.*dhcp' | awk '{print $3}') || true
      - ip route add default via ${azurerm_network_interface.lan[0].private_ip_address}
  USERDATA
  )

  source_image_reference {
    publisher = "Debian"
    offer     = "debian-12"
    sku       = "12-gen2"
    version   = "latest"
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  boot_diagnostics {}

  tags = local.tags

  depends_on = [
    azurerm_network_interface_security_group_association.test_vm,
  ]
}

# -----------------------------------------------------------------------------
# Delete action
# -----------------------------------------------------------------------------
resource "null_resource" "delete_graphiant_stack" {
  count = var.action == "delete" && var.delete_resource_group ? 1 : 0

  provisioner "local-exec" {
    command = "az group delete --name ${local.rg_name} --yes --no-wait"
  }
}
