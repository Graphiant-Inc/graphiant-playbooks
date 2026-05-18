# Azure Deploy VPC Configuration

# Pre-requisite:
# ============================================================================
# 1. Azure regions: https://learn.microsoft.com/en-us/azure/reliability/regions-list
#    To find available Azure regions:
#     az account list-locations --query "[].{Region:name, Location:displayName, PairedRegion:metadata.pairedRegion[0].name, Geography:metadata.geography, ProgrammaticName:name}" --output table

# action: Terraform action to perform ('create' or 'delete')
action = "create"

# ================================================================
# Resource Group: provide resource_group_id to use existing, or resource_group_name to create new
# ================================================================
# resource_group_id = "/subscriptions/xxxx/resourceGroups/graphiant-vedge-rg"
resource_group_name = "graphiant-vedge-rg"

# azure_region: Azure region (used when creating a new resource group)
azure_region = "eastus"

# project_name: Project name used for default resource names
project_name = "graphiant-vedge"

# vnet_name: Virtual network name
vnet_name = "graphiant-vedge-vnet"

# vnet_address_space: CIDR block for the virtual network
vnet_address_space = "10.1.0.0/16"

# subnet_mgmt_prefix: CIDR for the mgmt subnet
subnet_mgmt_prefix = "10.1.1.0/24"

# subnet_wan_prefix: CIDR for the WAN subnet
subnet_wan_prefix = "10.1.2.0/24"

# subnet_lan_prefix: CIDR for the LAN subnet
subnet_lan_prefix = "10.1.3.0/24"

# tags: Additional tags to apply
# tags = {
#   Owner = "team-network"
# }

# delete_resource_group: Whether to delete the resource group when action is 'delete'
# delete_resource_group = true
