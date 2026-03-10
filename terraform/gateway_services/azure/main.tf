# Terraform configuration for express route circuit on azure
terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.80.0"
    }
  }

  required_version = ">= 1.1.0"
}

# Configure azure Provider
provider "azurerm" {
  features {}
  skip_provider_registration = true
}


locals {
  rg_name   = var.use_existing_rg ? var.rg_name : azurerm_resource_group.rg[0].name
  rg_location = var.use_existing_rg ? data.azurerm_resource_group.existing[0].location : azurerm_resource_group.rg[0].location
  vnet_name = var.use_existing_vnet ? var.vnet_name : azurerm_virtual_network.virtual_network[0].name
  vnet_id   = var.use_existing_vnet ? data.azurerm_virtual_network.existing[0].id : azurerm_virtual_network.virtual_network[0].id
}

# Get existing Resource Group
data "azurerm_resource_group" "existing" {
  count = var.use_existing_rg ? 1 : 0
  name  = var.rg_name
}

# Resource Group
resource "azurerm_resource_group" "rg" {
  count    = var.use_existing_rg ? 0 : 1
  name     = var.rg_name != null ? var.rg_name : "${var.project_name}-rg"
  location = var.azure_region

  tags = {
    Name        = var.rg_name != null ? var.rg_name : "${var.project_name}-rg"
    Environment = var.environment
  }
}

# Get existing Virtual Network
data "azurerm_virtual_network" "existing" {
  count               = var.use_existing_vnet ? 1 : 0
  name                = var.vnet_name
  resource_group_name = local.rg_name
}

# Virtual Network
resource "azurerm_virtual_network" "virtual_network" {
  count               = var.use_existing_vnet ? 0 : 1
  name                = var.vnet_name != null ? var.vnet_name : "${var.project_name}-vnet"
  resource_group_name = local.rg_name
  location            = var.azure_region
  address_space       = [var.vnet_address_prefix]

  tags = {
    Name        = var.vnet_name != null ? var.vnet_name : "${var.project_name}-vnet"
    Environment = var.environment
  }
}

# Public Subnet
resource "azurerm_subnet" "vnet_public_subnet" {
  count               = var.use_existing_vnet ? 0 : 1
  name                 = "${var.project_name}-public-subnet"
  resource_group_name  = local.rg_name
  virtual_network_name = local.vnet_name
  address_prefixes     = [var.vnet_public_address_prefix]
}

# ExpressRoute Circuit
resource "azurerm_express_route_circuit" "express_route" {
  count               = var.enable_expressroute ? 1 : 0
  name                = "${var.project_name}-er-circuit"
  resource_group_name = local.rg_name
  location            = local.rg_location
  service_provider_name = var.expressroute_service_provider
  peering_location    = var.expressroute_peering_location
  bandwidth_in_mbps   = var.expressroute_bandwidth

  sku {
    tier   = var.expressroute_sku
    family = var.expressroute_family
  }

  allow_classic_operations = var.expressroute_allow_classic_operations

  tags = {
    Name        = "${var.project_name}-er-circuit"
    Environment = var.environment
  }
}

# ExpressRoute Circuit Authorization
resource "azurerm_express_route_circuit_authorization" "express_route_auth" {
  count                   = var.enable_expressroute ? 1 : 0
  name                    = "${var.project_name}-er-auth"
  resource_group_name     = local.rg_name
  express_route_circuit_name = azurerm_express_route_circuit.express_route[count.index].name
}

# Secondary ExpressRoute Circuit (for redundancy)
resource "azurerm_express_route_circuit" "express_route_secondary" {
  count               = var.enable_expressroute && var.expressroute_secondary_peering_location != "" ? 1 : 0
  name                = "${var.project_name}-er-circuit-secondary"
  resource_group_name = local.rg_name
  location            = local.rg_location
  service_provider_name = var.expressroute_secondary_service_provider != "" ? var.expressroute_secondary_service_provider : var.expressroute_service_provider
  peering_location    = var.expressroute_secondary_peering_location
  bandwidth_in_mbps   = var.expressroute_secondary_bandwidth

  sku {
    tier   = var.expressroute_sku
    family = var.expressroute_family
  }

  allow_classic_operations = var.expressroute_allow_classic_operations

  tags = {
    Name        = "${var.project_name}-er-circuit-secondary"
    Environment = var.environment
  }
}

# ExpressRoute Gateway Subnet
# Note: Gateway Subnet is only created when creating a new VNet
# If using existing VNet, ensure GatewaySubnet exists (required for ExpressRoute Gateway)
resource "azurerm_subnet" "express_route_gateway_subnet" {
  count                = var.enable_expressroute && !var.use_existing_vnet ? 1 : 0
  name                 = "GatewaySubnet"
  resource_group_name  = local.rg_name
  virtual_network_name = local.vnet_name
  address_prefixes     = var.vnet_gateway_address_prefixes
}

# ExpressRoute Gateway Public IP
resource "azurerm_public_ip" "express_route_gateway_ip" {
  count               = var.enable_expressroute ? 1 : 0
  name                = "${var.project_name}-er-gateway-ip"
  resource_group_name = local.rg_name
  location            = local.rg_location
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    Name        = "${var.project_name}-er-gateway-ip"
    Environment = var.environment
  }
}

# Virtual WAN (required for Virtual Hub with ExpressRoute Gateway)
resource "azurerm_virtual_wan" "virtual_wan" {
  count               = var.enable_expressroute ? 1 : 0
  name                = "${var.project_name}-wan"
  resource_group_name = local.rg_name
  location            = local.rg_location

  tags = {
    Name        = "${var.project_name}-wan"
    Environment = var.environment
  }
}

# Virtual Hub (required for ExpressRoute Gateway)
resource "azurerm_virtual_hub" "virtual_hub" {
  count               = var.enable_expressroute ? 1 : 0
  name                = "${var.project_name}-virtual-hub"
  resource_group_name = local.rg_name
  location            = local.rg_location
  virtual_wan_id      = azurerm_virtual_wan.virtual_wan[0].id
  address_prefix      = var.virtual_hub_address_prefix
  sku                 = "Standard"

  tags = {
    Name        = "${var.project_name}-virtual-hub"
    Environment = var.environment
  }
}

# Wait for Virtual Hub to be fully ready
resource "time_sleep" "wait_for_virtual_hub" {
  count = var.enable_expressroute ? 1 : 0

  depends_on = [
    azurerm_virtual_hub.virtual_hub
  ]

  create_duration = "300s"
}


# ExpressRoute Gateway
resource "azurerm_express_route_gateway" "express_route_gateway" {
  count               = var.enable_expressroute ? 1 : 0
  name                = "${var.project_name}-er-gateway"
  resource_group_name = local.rg_name
  location            = local.rg_location
  virtual_hub_id      = azurerm_virtual_hub.virtual_hub[0].id

  scale_units = var.expressroute_gateway_scale_units

  depends_on = [
    time_sleep.wait_for_virtual_hub
  ]

  tags = {
    Name        = "${var.project_name}-er-gateway"
    Environment = var.environment
  }
}



# ExpressRoute Connection (only created after service provider provisions the circuit)
resource "azurerm_express_route_connection" "express_route_connection" {
  count               = var.enable_expressroute && var.create_expressroute_connection ? 1 : 0
  name                = "${var.project_name}-er-connection"
  express_route_gateway_id = azurerm_express_route_gateway.express_route_gateway[0].id
  express_route_circuit_peering_id = azurerm_express_route_circuit_peering.express_route_peering[0].id
  routing_weight      = 1

  routing {
    associated_route_table_id = "${azurerm_virtual_hub.virtual_hub[0].id}/hubRouteTables/defaultRouteTable"

    propagated_route_table {
      labels = ["default"]
      route_table_ids = ["${azurerm_virtual_hub.virtual_hub[0].id}/hubRouteTables/defaultRouteTable"]
    }
  }
}

# VNet Connection to Virtual Hub (required for ExpressRoute connectivity)
resource "azurerm_virtual_hub_connection" "vnet_connection" {
  count                     = var.enable_expressroute ? 1 : 0
  name                      = "${var.project_name}-vnet-connection"
  virtual_hub_id            = azurerm_virtual_hub.virtual_hub[0].id
  remote_virtual_network_id = local.vnet_id
  
  # Disable internet security to allow SSH access
  internet_security_enabled = false

  routing {
    associated_route_table_id = "${azurerm_virtual_hub.virtual_hub[0].id}/hubRouteTables/defaultRouteTable"

    propagated_route_table {
      labels = ["default"]
      route_table_ids = ["${azurerm_virtual_hub.virtual_hub[0].id}/hubRouteTables/defaultRouteTable"]
    }
  }
}

# Route Table
resource "azurerm_route_table" "express_route_route_table" {
  count                         = var.enable_expressroute ? 1 : 0
  name                          = "${var.project_name}-route-table"
  location                      = local.rg_location
  resource_group_name           = local.rg_name
  disable_bgp_route_propagation = var.route_table_disable_bgp_propagation

  tags = {
    Name        = "${var.project_name}-route-table"
    Environment = var.environment
  }
}

# Note: Routes will be learned via BGP from ExpressRoute peering
# No static routes needed - BGP will handle routing to on-premises networks

# Associate Route Table with Public Subnet
resource "azurerm_subnet_route_table_association" "public_subnet_route_table" {
  count          = var.enable_expressroute && !var.use_existing_vnet ? 1 : 0
  subnet_id      = azurerm_subnet.vnet_public_subnet[0].id
  route_table_id = azurerm_route_table.express_route_route_table[0].id
}

# ExpressRoute Circuit Peering
resource "azurerm_express_route_circuit_peering" "express_route_peering" {
  count                   = var.enable_expressroute ? 1 : 0
  peering_type            = "AzurePrivatePeering"
  express_route_circuit_name = azurerm_express_route_circuit.express_route[count.index].name
  resource_group_name     = local.rg_name
  shared_key              = var.expressroute_shared_key != "" ? var.expressroute_shared_key : null
  peer_asn                = var.expressroute_peer_asn
  primary_peer_address_prefix = var.expressroute_primary_peer_address_prefix
  secondary_peer_address_prefix = var.expressroute_secondary_peer_address_prefix
  vlan_id                 = var.expressroute_vlan_id

  depends_on = [
    azurerm_express_route_circuit_authorization.express_route_auth
  ]
}

# VM Subnet for E2E Testing
resource "azurerm_subnet" "vm_subnet" {
  count                = var.deploy_test_vm ? 1 : 0
  name                 = "${var.project_name}-vm-subnet"
  resource_group_name  = local.rg_name
  virtual_network_name = local.vnet_name
  address_prefixes     = [var.vnet_vm_address_prefix]
}

# Network Security Group for VM
resource "azurerm_network_security_group" "vm_nsg" {
  count               = var.deploy_test_vm ? 1 : 0
  name                = "${var.project_name}-vm-nsg"
  location            = local.rg_location
  resource_group_name = local.rg_name

  # Allow SSH access
  security_rule {
    name                       = "SSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # Allow ICMP for ping tests
  security_rule {
    name                       = "ICMP"
    priority                   = 1002
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Icmp"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = {
    Name        = "${var.project_name}-vm-nsg"
    Environment = var.environment
  }
}

# Associate NSG with VM Subnet
resource "azurerm_subnet_network_security_group_association" "vm_nsg_association" {
  count                     = var.deploy_test_vm ? 1 : 0
  subnet_id                 = azurerm_subnet.vm_subnet[0].id
  network_security_group_id = azurerm_network_security_group.vm_nsg[0].id
}

# Public IP for VM (for initial access)
resource "azurerm_public_ip" "vm_public_ip" {
  count               = var.deploy_test_vm ? 1 : 0
  name                = "${var.project_name}-vm-public-ip"
  resource_group_name = local.rg_name
  location            = local.rg_location
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    Name        = "${var.project_name}-vm-public-ip"
    Environment = var.environment
  }
}

# Network Interface for VM
resource "azurerm_network_interface" "vm_nic" {
  count               = var.deploy_test_vm ? 1 : 0
  name                = "${var.project_name}-vm-nic"
  location            = local.rg_location
  resource_group_name = local.rg_name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.vm_subnet[0].id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.vm_public_ip[0].id
  }

  tags = {
    Name        = "${var.project_name}-vm-nic"
    Environment = var.environment
  }
}

# Virtual Machine for E2E Testing
resource "azurerm_linux_virtual_machine" "test_vm" {
  count               = var.deploy_test_vm ? 1 : 0
  name                = "${var.project_name}-test-vm"
  computer_name       = "${replace(var.project_name, "_", "-")}-test-vm"
  resource_group_name = local.rg_name
  location            = local.rg_location
  size                = var.vm_size
  admin_username      = var.vm_admin_username

  disable_password_authentication = true

  network_interface_ids = [
    azurerm_network_interface.vm_nic[0].id,
  ]

  admin_ssh_key {
    username   = var.vm_admin_username
    public_key = var.vm_ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  tags = {
    Name        = "${var.project_name}-test-vm"
    Environment = var.environment
  }
}

# Associate Route Table with VM Subnet
resource "azurerm_subnet_route_table_association" "vm_subnet_route_table" {
  count          = var.enable_expressroute && var.deploy_test_vm ? 1 : 0
  subnet_id      = azurerm_subnet.vm_subnet[0].id
  route_table_id = azurerm_route_table.express_route_route_table[0].id
}
