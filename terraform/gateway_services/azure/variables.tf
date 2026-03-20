# Variables for ExpressRoute circuit configuration on azure
variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "graphiant-express-route"
}

variable "azure_region" {
  description = "Azure region to deploy the infrastructure"
  type        = string
  default     = "East US"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "virtual_hub_address_prefix" {
  description = "Address space for Virtual Hub"
  type        = string
  default     = "10.0.0.0/24"
}

variable "vnet_address_prefix" {
  description = "Address space for Virtual Network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "vnet_public_address_prefix" {
  description = "Virtual Network public subnet"
  type        = string
  default     = "10.0.1.0/28"
}

variable "vnet_gateway_address_prefixes" {
  description = "Virtual Network Gateway subnet list"
  type        = list(string)
  default     = ["10.0.1.16/28"]
}

# Resource Group Configuration
variable "use_existing_rg" {
  description = "Whether to use an existing Resource Group (true) or create a new one (false)"
  type        = bool
  default     = false
}

variable "rg_name" {
  description = "Name of the Resource Group (used for both creating new or referencing existing RG)"
  type        = string
  default     = null
}

# Virtual Network Configuration
variable "use_existing_vnet" {
  description = "Whether to use an existing Virtual Network (true) or create a new one (false)"
  type        = bool
  default     = false
}

variable "vnet_name" {
  description = "Name of the Virtual Network (used for both creating new or referencing existing VNet)"
  type        = string
  default     = null
}

# ExpressRoute Circuit Configuration Variables
variable "enable_expressroute" {
  description = "Whether to create an ExpressRoute circuit"
  type        = bool
  default     = true
}

variable "expressroute_sku" {
  description = "ExpressRoute circuit SKU (Standard, Premium)"
  type        = string
  default     = "Standard"
}

variable "expressroute_family" {
  description = "ExpressRoute circuit family (MeteredData, UnlimitedData)"
  type        = string
  default     = "MeteredData"
}

variable "expressroute_bandwidth" {
  description = "ExpressRoute circuit bandwidth in Mbps (50, 100, 200, 500, 1000, 2000, 5000, 10000)"
  type        = number
  default     = 50
}

variable "expressroute_peering_location" {
  description = "ExpressRoute peering location"
  type        = string
  default     = "Washington DC"
}

variable "expressroute_service_provider" {
  description = "ExpressRoute service provider name"
  type        = string
  default     = "PacketFabric"
}

variable "expressroute_allow_classic_operations" {
  description = "Allow classic operations on ExpressRoute circuit"
  type        = bool
  default     = false
}

variable "expressroute_secondary_peering_location" {
  description = "Secondary ExpressRoute peering location for redundancy"
  type        = string
  default     = ""
}

variable "expressroute_secondary_bandwidth" {
  description = "Secondary ExpressRoute circuit bandwidth in Mbps"
  type        = number
  default     = 50
}

variable "expressroute_secondary_service_provider" {
  description = "Secondary ExpressRoute service provider name"
  type        = string
  default     = "PacketFabric"
}

variable "expressroute_gateway_scale_units" {
  description = "Number of scale units for ExpressRoute Gateway"
  type        = number
  default     = 1
}

# ExpressRoute Peering Configuration Variables
variable "expressroute_shared_key" {
  description = "Shared key for ExpressRoute circuit peering"
  type        = string
  default     = ""
  sensitive   = true
}

variable "expressroute_peer_asn" {
  description = "ASN for ExpressRoute circuit peering"
  type        = number
  default     = 100
}

variable "expressroute_primary_peer_address_prefix" {
  description = "Primary peer address prefix for ExpressRoute peering"
  type        = string
  default     = "192.168.1.0/30"
}

variable "expressroute_secondary_peer_address_prefix" {
  description = "Secondary peer address prefix for ExpressRoute peering"
  type        = string
  default     = "192.168.2.0/30"
}

variable "expressroute_vlan_id" {
  description = "VLAN ID for ExpressRoute circuit peering"
  type        = number
  default     = 100
}

variable "create_expressroute_connection" {
  description = "Whether to create the ExpressRoute connection (set to true after service provider provisions the circuit)"
  type        = bool
  default     = false
}

variable "route_table_disable_bgp_propagation" {
  description = "Whether to disable BGP route propagation on the route table"
  type        = bool
  default     = false
}

variable "route_table_default_route" {
  description = "Default route destination (e.g., 0.0.0.0/0 for all traffic, or specific subnet)"
  type        = string
  default     = "0.0.0.0/0"
}

# VM Configuration Variables for E2E Testing
variable "deploy_test_vm" {
  description = "Whether to deploy a test VM for ExpressRoute connectivity testing"
  type        = bool
  default     = false
}

variable "vm_size" {
  description = "Size of the test VM"
  type        = string
  default     = "Standard_B1s"
}

variable "vm_admin_username" {
  description = "Admin username for the test VM"
  type        = string
  default     = "azureuser"
}

variable "vm_ssh_public_key" {
  description = "SSH public key for the test VM"
  type        = string
  default     = ""
}

variable "vnet_vm_address_prefix" {
  description = "Virtual Network VM subnet"
  type        = string
  default     = "10.0.1.32/28"
}
