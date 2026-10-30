variable "action" {
  description = "Action to perform: 'create' to deploy resources, 'delete' to remove the resource group (optional)"
  type        = string
  default     = "create"

  validation {
    condition     = contains(["create", "delete"], var.action)
    error_message = "Action must be either 'create' or 'delete'."
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

variable "vnet_name" {
  description = "Virtual network name"
  type        = string
  default     = "graphiant-vedge-vnet"
}

variable "vnet_address_space" {
  description = "CIDR block for the virtual network"
  type        = string
  default     = "10.1.0.0/16"
}

variable "vnet_address_space_v6" {
  description = "IPv6 CIDR (/48 to /64) added to the VNet; only the LAN subnet uses it (index 3 /64). Empty keeps the VNet IPv4-only."
  type        = string
  default     = "fd00:10:1::/48"

  validation {
    condition     = var.vnet_address_space_v6 == "" || (can(regex(":", var.vnet_address_space_v6)) && can(cidrsubnet(var.vnet_address_space_v6, 64 - tonumber(split("/", var.vnet_address_space_v6)[1]), 3)))
    error_message = "vnet_address_space_v6 must be empty or an IPv6 CIDR with a prefix length of /62 or shorter (e.g. fd00:10:1::/48)."
  }
}

variable "subnet_mgmt_prefix" {
  description = "CIDR for the mgmt subnet"
  type        = string
  default     = "10.1.1.0/24"
}

variable "subnet_wan_prefix" {
  description = "CIDR for the WAN subnet"
  type        = string
  default     = "10.1.2.0/24"
}

variable "subnet_lan_prefix" {
  description = "CIDR for the LAN subnet"
  type        = string
  default     = "10.1.3.0/24"
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
