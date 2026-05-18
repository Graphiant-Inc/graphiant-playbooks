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

variable "allowed_cidr_v6" {
  description = "Public IPv6 (/128) allowed to connect to the devtest management ports"
  type        = string
  default     = "::1/128"
}

# --- VNet configuration ---

variable "vnet_id" {
  description = "Existing VNet ID. When set, uses existing VNet. When empty, creates a new VNet using vnet_name and vnet_address_space."
  type        = string
  default     = ""
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

variable "subnet_cloud_init_prefix" {
  description = "CIDR for the cloud-init subnet (new VNet, devtest only)"
  type        = string
  default     = "10.1.0.0/24"
}

variable "subnet_mgmt_prefix" {
  description = "CIDR for the mgmt subnet (new VNet mode)"
  type        = string
  default     = "10.1.1.0/24"
}

variable "subnet_wan_prefix" {
  description = "CIDR for the WAN subnet (new VNet mode)"
  type        = string
  default     = "10.1.2.0/24"
}

variable "subnet_lan_prefix" {
  description = "CIDR for the LAN subnet (new VNet mode)"
  type        = string
  default     = "10.1.3.0/24"
}

# --- Existing VNet references ---

variable "subnet_cloud_init_id" {
  description = "Cloud-init subnet ID (existing VNet, devtest only)"
  type        = string
  default     = ""
}

variable "subnet_mgmt_id" {
  description = "Mgmt subnet ID (existing VNet mode)"
  type        = string
  default     = ""
}

variable "subnet_wan_id" {
  description = "WAN subnet ID (existing VNet mode)"
  type        = string
  default     = ""
}

variable "subnet_lan_id" {
  description = "LAN subnet ID (existing VNet mode)"
  type        = string
  default     = ""
}

# --- Existing route table references ---

variable "route_table_wan_id" {
  description = "Existing WAN route table ID. When set, uses existing. When empty, creates a new one."
  type        = string
  default     = ""
}

variable "route_table_lan_id" {
  description = "Existing LAN route table ID. When set, uses existing. When empty, creates a new one."
  type        = string
  default     = ""
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
