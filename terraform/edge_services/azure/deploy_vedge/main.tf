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

  # Resolve subnet IDs — new VNet creates subnets, existing VNet uses provided IDs
  subnet_cloud_init_id = local.new_vnet && local.is_devtest ? azurerm_subnet.cloud_init[0].id : var.subnet_cloud_init_id
  subnet_mgmt_id       = local.new_vnet ? azurerm_subnet.mgmt[0].id : var.subnet_mgmt_id
  subnet_wan_id        = local.new_vnet ? azurerm_subnet.wan[0].id : var.subnet_wan_id
  subnet_lan_id        = local.new_vnet ? azurerm_subnet.lan[0].id : var.subnet_lan_id


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
# Virtual Network & Subnets (new VNet only)
# -----------------------------------------------------------------------------
resource "azurerm_virtual_network" "vnet" {
  count               = local.is_create && local.new_vnet ? 1 : 0
  name                = var.vnet_name
  resource_group_name = local.rg_name
  location            = local.rg_location
  address_space       = [var.vnet_address_space]

  tags = local.tags
}

resource "azurerm_subnet" "cloud_init" {
  count                = local.is_create && local.new_vnet && local.is_devtest ? 1 : 0
  name                 = "cloud-init"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.vnet[0].name
  address_prefixes     = [var.subnet_cloud_init_prefix]
}

resource "azurerm_subnet" "mgmt" {
  count                = local.is_create && local.new_vnet ? 1 : 0
  name                 = "mgmt"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.vnet[0].name
  address_prefixes     = [var.subnet_mgmt_prefix]
}

resource "azurerm_subnet" "wan" {
  count                = local.is_create && local.new_vnet ? 1 : 0
  name                 = "wan"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.vnet[0].name
  address_prefixes     = [var.subnet_wan_prefix]
}

resource "azurerm_subnet" "lan" {
  count                = local.is_create && local.new_vnet ? 1 : 0
  name                 = "lan"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.vnet[0].name
  address_prefixes     = [var.subnet_lan_prefix]
}

# -----------------------------------------------------------------------------
# Route Tables — create new or use existing from deploy_vpc
# -----------------------------------------------------------------------------
locals {
  create_rt_wan = var.route_table_wan_id == ""
  create_rt_lan = var.route_table_lan_id == ""
}

# WAN route table — default route to Internet, BGP propagation disabled
resource "azurerm_route_table" "wan" {
  count                         = local.is_create && local.new_vnet && local.create_rt_wan ? 1 : 0
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
  count          = local.is_create && local.new_vnet && local.create_rt_wan ? 1 : 0
  subnet_id      = azurerm_subnet.mgmt[0].id
  route_table_id = azurerm_route_table.wan[0].id
}

resource "azurerm_subnet_route_table_association" "wan" {
  count          = local.is_create && local.new_vnet && local.create_rt_wan ? 1 : 0
  subnet_id      = azurerm_subnet.wan[0].id
  route_table_id = azurerm_route_table.wan[0].id
}

# LAN route table — default route via vEdge LAN IP (Virtual Appliance)
resource "azurerm_route_table" "lan" {
  count                         = local.is_create && local.new_vnet && local.create_rt_lan ? 1 : 0
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

  tags = local.tags
}

resource "azurerm_subnet_route_table_association" "lan" {
  count          = local.is_create && local.new_vnet && local.create_rt_lan ? 1 : 0
  subnet_id      = azurerm_subnet.lan[0].id
  route_table_id = azurerm_route_table.lan[0].id
}

# Add default route via vEdge LAN IP to an existing LAN route table (from deploy_vpc)
resource "azurerm_route" "default_via_vedge" {
  count                  = local.is_create && !local.create_rt_lan ? 1 : 0
  name                   = "default-via-vedge"
  resource_group_name    = local.rg_name
  route_table_name       = element(split("/", var.route_table_lan_id), length(split("/", var.route_table_lan_id)) - 1)
  address_prefix         = "0.0.0.0/0"
  next_hop_type          = "VirtualAppliance"
  next_hop_in_ip_address = azurerm_network_interface.lan[0].private_ip_address
}

# -----------------------------------------------------------------------------
# Network Security Groups
# -----------------------------------------------------------------------------

# Cloud-init NSG — devtest only: SSH inbound from allowed CIDRs
resource "azurerm_network_security_group" "cloud_init" {
  count               = local.is_create && local.is_devtest ? 1 : 0
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

  security_rule {
    name                       = "AllowSSHIPv6"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.allowed_cidr_v6
    destination_address_prefix = "*"
  }

  tags = local.tags
}

# Mgmt NSG — HTTPS(443) denied inbound by default (customer modifies in portal to allow access)
resource "azurerm_network_security_group" "mgmt" {
  count               = local.is_create ? 1 : 0
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
  count               = local.is_create ? 1 : 0
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
  count               = local.is_create ? 1 : 0
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
  count               = local.is_create ? 1 : 0
  name                = "${var.vm_name}-mgmt-pip"
  location            = local.rg_location
  resource_group_name = local.rg_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = local.tags
}

resource "azurerm_public_ip" "wan" {
  count               = local.is_create ? 1 : 0
  name                = "${var.vm_name}-wan-pip"
  location            = local.rg_location
  resource_group_name = local.rg_name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = local.tags
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
    public_ip_address_id          = azurerm_public_ip.mgmt[0].id
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
    public_ip_address_id          = azurerm_public_ip.wan[0].id
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

  enable_accelerated_networking = true
  enable_ip_forwarding          = true

  tags = local.tags
}

# -----------------------------------------------------------------------------
# NSG Associations
# -----------------------------------------------------------------------------
resource "azurerm_network_interface_security_group_association" "cloud_init" {
  count                     = local.is_create && local.is_devtest ? 1 : 0
  network_interface_id      = azurerm_network_interface.cloud_init[0].id
  network_security_group_id = azurerm_network_security_group.cloud_init[0].id
}

resource "azurerm_network_interface_security_group_association" "mgmt" {
  count                     = local.is_create ? 1 : 0
  network_interface_id      = azurerm_network_interface.mgmt[0].id
  network_security_group_id = azurerm_network_security_group.mgmt[0].id
}

resource "azurerm_network_interface_security_group_association" "wan" {
  count                     = local.is_create ? 1 : 0
  network_interface_id      = azurerm_network_interface.wan[0].id
  network_security_group_id = azurerm_network_security_group.wan[0].id
}

resource "azurerm_network_interface_security_group_association" "lan" {
  count                     = local.is_create ? 1 : 0
  network_interface_id      = azurerm_network_interface.lan[0].id
  network_security_group_id = azurerm_network_security_group.lan[0].id
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
  count               = local.is_create && var.deploy_test_vm ? 1 : 0
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

  tags = local.tags
}

resource "azurerm_network_interface_security_group_association" "test_vm" {
  count                     = local.is_create && var.deploy_test_vm ? 1 : 0
  network_interface_id      = azurerm_network_interface.test_vm[0].id
  network_security_group_id = azurerm_network_security_group.test_vm[0].id
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
