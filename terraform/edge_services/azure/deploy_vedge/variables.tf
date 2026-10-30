variable "action" {
  description = "Action to perform: 'create' to deploy resources, 'delete' to remove the resource group (optional)"
  type        = string
  default     = "create"

  validation {
    condition     = contains(["create", "delete"], var.action)
    error_message = "Action must be either 'create' or 'delete'."
  }
}

variable "mode" {
  description = "Deployment mode: 'production' for customer-facing, 'devtest' for internal use with SSH access"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "devtest"], var.mode)
    error_message = "Mode must be either 'production' or 'devtest'."
  }
}

variable "resource_group_id" {
  description = "Existing resource group ID. When set, uses existing RG. When empty, creates a new RG using resource_group_name."
  type        = string
  default     = ""
}

variable "resource_group_name" {
  description = "Resource group name for creating a new RG (only used when resource_group_id is empty)"
  type        = string
  default     = ""
}

variable "azure_region" {
  description = "Azure region to deploy resources into (used when creating a new resource group)"
  type        = string
  default     = "eastus"
}

variable "project_name" {
  description = "Project name used for default resource names"
  type        = string
  default     = "graphiant-vedge"
}

variable "vm_name" {
  description = "Virtual machine name"
  type        = string
  default     = "graphiant-vedge"
}

variable "vm_size" {
  description = "Virtual machine size"
  type        = string
  default     = "Standard_DS3_v2"

  validation {
    condition     = contains(["Standard_DS3_v2", "Standard_DS4_v2", "Standard_F8s_v2"], var.vm_size)
    error_message = "VM size must be one of: Standard_DS3_v2, Standard_DS4_v2, Standard_F8s_v2."
  }
}

variable "source_image_id" {
  description = "Full ARM resource ID of a Shared Image Gallery image version (overrides Marketplace image when set)"
  type        = string
  default     = ""
}

variable "image_publisher" {
  description = "Azure Marketplace image publisher"
  type        = string
  default     = "graphiantinc1622651764677"
}

variable "image_offer" {
  description = "Azure Marketplace image offer"
  type        = string
  default     = "graphiant-edge-vm"
}

variable "image_sku" {
  description = "Azure Marketplace image SKU"
  type        = string
  default     = "graphiant-edge-vm"
}

variable "image_version" {
  description = "Azure Marketplace image version (use 'latest' for newest)"
  type        = string
  default     = "latest"
}

variable "ssh_public_key" {
  description = "SSH public key for the VM (required by Azure; used for interactive SSH access in devtest mode)"
  type        = string
}

variable "token" {
  description = "Graphiant vEdge onboarding authentication token"
  type        = string
  sensitive   = true
}

variable "cloud_init_username" {
  description = "Username for the cloud-init user created in devtest mode"
  type        = string
  default     = "gnos"
}

variable "cloud_init_password" {
  description = "Password for the cloud-init user created in devtest mode"
  type        = string
  sensitive   = true
  default     = ""
}

variable "onboarding_gateway" {
  description = "Graphiant onboarding gateway address & port"
  type        = string
  default     = "onboarding-gateway.graphiant.com:16000"
}

variable "onboarding_auth_url" {
  description = "Graphiant onboarding authentication URL"
  type        = string
  default     = "https://api.graphiant.com/v1/devices/oauth"
}

variable "allowed_cidr" {
  description = "Public IPv4 (/32) allowed to connect to the devtest management ports"
  type        = string
  default     = "127.0.0.1/32"
}

# --- VNet configuration ---

variable "vnet_id" {
  description = "Existing VNet ID. When set, uses existing VNet (new subnets are created in it). When empty, creates a new VNet using vnet_name and vnet_address_space."
  type        = string
  default     = ""

  validation {
    condition     = var.vnet_id == "" || can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/virtualNetworks/[^/]+$", var.vnet_id))
    error_message = "vnet_id must be a full ARM ID: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<name>."
  }
}

variable "vnet_name" {
  description = "Virtual network name (only used when vnet_id is empty to create a new VNet)"
  type        = string
  default     = "graphiant-vedge-vnet"
}

variable "vnet_address_space" {
  description = "CIDR block for the virtual network (new VNet mode)"
  type        = string
  default     = "10.1.0.0/16"
}

variable "vnet_address_space_v6" {
  description = "IPv6 CIDR (/48 to /64) added to a new VNet; only the LAN subnet uses it. Empty keeps the VNet IPv4-only. An existing VNet's own IPv6 range (if any) is used instead."
  type        = string
  default     = "fd00:10:1::/48"

  validation {
    condition     = var.vnet_address_space_v6 == "" || (can(regex(":", var.vnet_address_space_v6)) && can(cidrsubnet(var.vnet_address_space_v6, 64 - tonumber(split("/", var.vnet_address_space_v6)[1]), 0)))
    error_message = "vnet_address_space_v6 must be empty or an IPv6 CIDR with a prefix length of /64 or shorter (e.g. fd00:10:1::/48)."
  }
}

variable "subnet_cloud_init_prefix" {
  description = "CIDR for the cloud-init subnet when subnet_cloud_init_id is empty (devtest only)"
  type        = string
  default     = "10.1.0.0/24"
}

variable "subnet_mgmt_prefix" {
  description = "CIDR for the mgmt subnet when subnet_mgmt_id is empty"
  type        = string
  default     = "10.1.1.0/24"
}

variable "subnet_wan_prefix" {
  description = "CIDR for the WAN subnet when subnet_wan_id is empty"
  type        = string
  default     = "10.1.2.0/24"
}

variable "subnet_lan_prefix" {
  description = "CIDR for the LAN subnet when subnet_lan_id is empty"
  type        = string
  default     = "10.1.3.0/24"
}

variable "subnet_lan_ipv6_netnum" {
  description = "Index of the IPv6 /64 carved from the VNet IPv6 range for a new LAN subnet (only the LAN side gets IPv6; pick an unused index in an existing VNet)"
  type        = number
  default     = 3
}

# Subnet names — must be unique within the VNet (set them when creating subnets in a VNet that already has these names)
variable "subnet_cloud_init_name" {
  description = "Name of the new cloud-init subnet (devtest only)"
  type        = string
  default     = "cloud-init"
}

variable "subnet_mgmt_name" {
  description = "Name of the new mgmt subnet"
  type        = string
  default     = "mgmt"
}

variable "subnet_wan_name" {
  description = "Name of the new WAN subnet"
  type        = string
  default     = "wan"
}

variable "subnet_lan_name" {
  description = "Name of the new LAN subnet"
  type        = string
  default     = "lan"
}

# --- Existing component references (each independent: set to reuse, leave empty to create) ---

variable "subnet_cloud_init_id" {
  description = "Existing cloud-init subnet ID (devtest only; requires vnet_id). When empty, a new subnet is created from subnet_cloud_init_prefix."
  type        = string
  default     = ""
}

variable "subnet_mgmt_id" {
  description = "Existing mgmt subnet ID (requires vnet_id). When empty, a new subnet is created from subnet_mgmt_prefix."
  type        = string
  default     = ""
}

variable "subnet_wan_id" {
  description = "Existing WAN subnet ID (requires vnet_id). When empty, a new subnet is created from subnet_wan_prefix."
  type        = string
  default     = ""
}

variable "subnet_lan_id" {
  description = "Existing LAN subnet ID (requires vnet_id and route_table_lan_id). When empty, a new subnet is created from subnet_lan_prefix."
  type        = string
  default     = ""
}

variable "route_table_wan_id" {
  description = "Existing WAN route table ID; new mgmt/WAN subnets are associated with it. When empty, a new one is created (only if a mgmt/WAN subnet is created)."
  type        = string
  default     = ""

  validation {
    condition     = var.route_table_wan_id == "" || can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/routeTables/[^/]+$", var.route_table_wan_id))
    error_message = "route_table_wan_id must be a full ARM ID: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/routeTables/<name>."
  }
}

variable "route_table_lan_id" {
  description = "Existing LAN route table ID; a default route via the vEdge LAN IP is added to it and a new LAN subnet is associated with it. When empty, a new one is created (only if the LAN subnet is created)."
  type        = string
  default     = ""

  validation {
    condition     = var.route_table_lan_id == "" || can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/routeTables/[^/]+$", var.route_table_lan_id))
    error_message = "route_table_lan_id must be a full ARM ID: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/routeTables/<name>."
  }
}

variable "nsg_cloud_init_id" {
  description = "Existing NSG ID for the cloud-init NIC (devtest only). When empty, a new NSG is created."
  type        = string
  default     = ""
}

variable "nsg_mgmt_id" {
  description = "Existing NSG ID for the mgmt NIC. When empty, a new NSG is created."
  type        = string
  default     = ""
}

variable "nsg_wan_id" {
  description = "Existing NSG ID for the WAN NIC. When empty, a new NSG is created."
  type        = string
  default     = ""
}

variable "nsg_lan_id" {
  description = "Existing NSG ID for the LAN NIC. When empty, a new NSG is created."
  type        = string
  default     = ""
}

variable "nsg_test_vm_id" {
  description = "Existing NSG ID for the test VM NIC (only with deploy_test_vm). When empty, a new NSG is created."
  type        = string
  default     = ""
}

variable "public_ip_mgmt_id" {
  description = "Existing Standard SKU public IP ID for the mgmt NIC (must not be associated elsewhere; not deleted on destroy). When empty, a new one is created."
  type        = string
  default     = ""

  validation {
    condition     = var.public_ip_mgmt_id == "" || can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/publicIPAddresses/[^/]+$", var.public_ip_mgmt_id))
    error_message = "public_ip_mgmt_id must be a full ARM ID: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/publicIPAddresses/<name>."
  }
}

variable "public_ip_wan_id" {
  description = "Existing Standard SKU public IP ID for the WAN NIC (must not be associated elsewhere; not deleted on destroy). When empty, a new one is created."
  type        = string
  default     = ""

  validation {
    condition     = var.public_ip_wan_id == "" || can(regex("(?i)^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/Microsoft.Network/publicIPAddresses/[^/]+$", var.public_ip_wan_id))
    error_message = "public_ip_wan_id must be a full ARM ID: /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Network/publicIPAddresses/<name>."
  }
}

# --- Test VM (optional) ---

variable "deploy_test_vm" {
  description = "Whether to deploy a test VM attached to the LAN subnet"
  type        = bool
  default     = false
}

variable "test_vm_name" {
  description = "Name of the test VM"
  type        = string
  default     = "graphiant-vedge-test-vm"
}

variable "test_vm_size" {
  description = "Azure VM size for the test VM"
  type        = string
  default     = "Standard_B1s"
}

variable "test_vm_admin_username" {
  description = "Admin username for the test VM"
  type        = string
  default     = "azureuser"
}

variable "test_vm_admin_password" {
  description = "Admin password for the test VM (12-123 chars via CLI, must meet 3 of 4 complexity requirements : Have lowercase, Have uppercase, Have a digit, Have a special char)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "delete_resource_group" {
  description = "Whether to delete the resource group when action is 'delete'"
  type        = bool
  default     = false
}
