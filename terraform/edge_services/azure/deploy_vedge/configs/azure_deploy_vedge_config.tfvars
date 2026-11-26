# Azure Deploy vEdge Configuration

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

# vm_name: Virtual machine name
vm_name = "graphiant-vedge"

# vm_size: Azure VM size (Standard_D8s_v4, Standard_DS3_v2, Standard_DS4_v2, Standard_F8s_v2)
vm_size = "Standard_D8s_v4"

# source_image_id: Full ARM resource ID of a Shared Image Gallery image version (optional)
# When set, overrides the Marketplace image below
# Example: /subscriptions/<subscription-id>/resourceGroups/<resource-group>/providers/Microsoft.Compute/galleries/<gallery-name>/images/<image-definition>/versions/<version>
# source_image_id = ""

# ================================================================
# Marketplace Image Configuration (not needed when source_image_id is set)
# ================================================================
image_publisher = "graphiantinc1622651764677"
image_offer = "graphiant-edge-vm"
image_sku = "graphiant-edge-vm"
image_version = "latest"

# ssh_public_key: SSH public key (required by Azure)
ssh_public_key = ""

# token: Edge Authentication token for Onboarding the vEdge into a specific Enterprise within Graphiant Portal
# If token is left empty, the vEdge falls back to URL/QR code based onboarding.
# The URL/QR code is shown on the vEdge serial console: Azure Portal -> VM -> Help -> Serial console (press Enter),
# or: az serial-console connect -g <resource_group> -n <vm_name>
token = ""

# ================================================================
# VNet: provide vnet_id to use existing, or vnet_name + vnet_address_space to create new
# Each subnet / route table / NSG / public IP below is independent: set its *_id to reuse it,
# or leave it empty to create it (new subnets can be created in an existing VNet; existing subnets require vnet_id).
# Subnet names default to mgmt/wan/lan; set subnet_*_name when creating a subnet in a VNet that already has one with that name.
# ================================================================
# vnet_id = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet"
vnet_name = "graphiant-vedge-vnet"
vnet_address_space = "10.1.0.0/16"
# vnet_address_space_v6: IPv6 range for a new VNet (used by the LAN subnet only); "" keeps the VNet IPv4-only.
# An existing VNet's own IPv6 range (if any) is used instead.
# vnet_address_space_v6 = "fd00:10:1::/48"

# mgmt subnet: provide subnet_mgmt_id to use existing, or subnet_mgmt_prefix to create new
# subnet_mgmt_id = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet/subnets/mgmt"
subnet_mgmt_prefix = "10.1.1.0/24"

# wan subnet: provide subnet_wan_id to use existing, or subnet_wan_prefix to create new
# subnet_wan_id = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet/subnets/wan"
subnet_wan_prefix = "10.1.2.0/24"

# lan subnet: provide subnet_lan_id to use existing, or subnet_lan_prefix to create new
# subnet_lan_id = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/vnet/subnets/lan"
subnet_lan_prefix = "10.1.3.0/24"
# IPv6 is LAN-side only: a new LAN subnet gets a /64 (index subnet_lan_ipv6_netnum of the VNet IPv6 range)
# and the vEdge LAN + test VM interfaces get an IPv6 address, with a ::/0 route via the vEdge LAN.
# An existing LAN subnet that already has an IPv6 prefix is used as-is. mgmt/wan are always IPv4-only.
# With the default fd00:10:1::/48 and index 3, the LAN subnet gets fd00:10:1:3::/64.
# subnet_lan_ipv6_netnum = 3

# ================================================================
# Route Tables: provide route_table_*_id to use existing, or leave empty to create new.
# Newly created subnets are associated with the (new or existing) route table; existing subnets keep their association.
# route_table_lan_id is required when subnet_lan_id is provided — a default-via-vEdge route is added to it.
# ================================================================
# route_table_wan_id = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/routeTables/wan-rt"
# route_table_lan_id = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/routeTables/lan-rt"

# ================================================================
# Network Security Groups: provide nsg_*_id to use existing, or leave empty to create new
# ================================================================
# nsg_mgmt_id = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/networkSecurityGroups/mgmt-nsg"
# nsg_wan_id  = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/networkSecurityGroups/wan-nsg"
# nsg_lan_id  = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/networkSecurityGroups/lan-nsg"

# ================================================================
# Public IPs: provide public_ip_*_id to use existing Standard SKU IPs, or leave empty to create new.
# A provided public IP must not be associated elsewhere and is not deleted on destroy.
# ================================================================
# public_ip_mgmt_id = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/mgmt-pip"
# public_ip_wan_id  = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/wan-pip"

# ================================================================
# Test VM Configuration (Optional — attached to LAN subnet)
# ================================================================
# deploy_test_vm = true
# test_vm_name = "graphiant-vedge-test-vm"
# test_vm_size = "Standard_B2ts_v2"
# test_vm_admin_username = "azureuser"
# test_vm_admin_password = ""  # 12-123 chars via CLI, must meet 3 of 4 complexity requirements : Have lowercase, Have uppercase, Have a digit, Have a special char
# nsg_test_vm_id = "/subscriptions/xxxx/resourceGroups/rg/providers/Microsoft.Network/networkSecurityGroups/test-vm-nsg"   # only with deploy_test_vm

# ================================================================
# Mgmt VM Configuration (Optional — desktop VM on mgmt subnet to access the vEdge local web server)
# ================================================================
# RDP to mgmt_vm_public_ip (allowed only from allowed_cidr), then browse to the vedge_local_web_server_url output
# deploy_mgmt_vm = true
# mgmt_vm_name = "graphiant-vedge-mgmt-vm"
# mgmt_vm_size = "Standard_B2s_v2"
# mgmt_vm_admin_username = "azureuser"
# mgmt_vm_admin_password = ""  # 12-123 chars via CLI, must meet 3 of 4 complexity requirements : Have lowercase, Have uppercase, Have a digit, Have a special char
# allowed_cidr: Public IPv4 (/32) allowed to RDP to the mgmt VM (required with deploy_mgmt_vm; 0.0.0.0/0 is rejected)
# allowed_cidr = "YOUR_PUBLIC_IP/32"

# tags: Additional tags to apply
# tags = {
#   Owner = "team-network"
# }

# delete_resource_group: Whether to delete the resource group when action is 'delete'
# delete_resource_group = true
