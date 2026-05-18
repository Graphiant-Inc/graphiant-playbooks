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

locals {
  is_create        = var.action == "create"
  use_existing_rg  = var.resource_group_id != ""
  existing_rg_name = local.use_existing_rg ? element(split("/", var.resource_group_id), 4) : ""
  rg_name          = local.use_existing_rg ? local.existing_rg_name : azurerm_resource_group.rg[0].name
  rg_location      = local.use_existing_rg ? data.azurerm_resource_group.existing[0].location : azurerm_resource_group.rg[0].location
  tags = merge(
    {
      Vendor = "Graphiant"
    },
    var.tags
  )
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
# Virtual Network & Subnets
# -----------------------------------------------------------------------------
resource "azurerm_virtual_network" "vnet" {
  count               = local.is_create ? 1 : 0
  name                = var.vnet_name
  resource_group_name = local.rg_name
  location            = local.rg_location
  address_space       = [var.vnet_address_space]

  tags = local.tags
}

resource "azurerm_subnet" "mgmt" {
  count                = local.is_create ? 1 : 0
  name                 = "mgmt"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.vnet[0].name
  address_prefixes     = [var.subnet_mgmt_prefix]
}

resource "azurerm_subnet" "wan" {
  count                = local.is_create ? 1 : 0
  name                 = "wan"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.vnet[0].name
  address_prefixes     = [var.subnet_wan_prefix]
}

resource "azurerm_subnet" "lan" {
  count                = local.is_create ? 1 : 0
  name                 = "lan"
  resource_group_name  = local.rg_name
  virtual_network_name = azurerm_virtual_network.vnet[0].name
  address_prefixes     = [var.subnet_lan_prefix]
}

# -----------------------------------------------------------------------------
# Route Tables
# -----------------------------------------------------------------------------

# WAN route table — default route to Internet, BGP propagation disabled
resource "azurerm_route_table" "wan" {
  count                         = local.is_create ? 1 : 0
  name                          = "${var.project_name}-wan-rt"
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
  count          = local.is_create ? 1 : 0
  subnet_id      = azurerm_subnet.mgmt[0].id
  route_table_id = azurerm_route_table.wan[0].id
}

resource "azurerm_subnet_route_table_association" "wan" {
  count          = local.is_create ? 1 : 0
  subnet_id      = azurerm_subnet.wan[0].id
  route_table_id = azurerm_route_table.wan[0].id
}

# LAN route table — empty (vEdge route added after vEdge deployment), BGP propagation enabled
resource "azurerm_route_table" "lan" {
  count                         = local.is_create ? 1 : 0
  name                          = "${var.project_name}-lan-rt"
  location                      = local.rg_location
  resource_group_name           = local.rg_name
  disable_bgp_route_propagation = false

  tags = local.tags
}

resource "azurerm_subnet_route_table_association" "lan" {
  count          = local.is_create ? 1 : 0
  subnet_id      = azurerm_subnet.lan[0].id
  route_table_id = azurerm_route_table.lan[0].id
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
