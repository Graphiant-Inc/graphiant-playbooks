output "action_performed" {
  description = "The action that was performed (create or delete)"
  value       = var.action
}

output "mode" {
  description = "The deployment mode (production or devtest)"
  value       = var.mode
}

output "resource_group_id" {
  description = "Resource group ID used for the deployment"
  value       = local.use_existing_rg ? var.resource_group_id : try(azurerm_resource_group.rg[0].id, null)
}

output "resource_group_name" {
  description = "Resource group name used for the deployment"
  value       = local.use_existing_rg ? local.existing_rg_name : try(azurerm_resource_group.rg[0].name, null)
}

# Resolved network component IDs (created or reused)
output "vnet_id" {
  description = "VNet ID used for the deployment"
  value       = local.use_existing_vnet ? var.vnet_id : try(azurerm_virtual_network.vnet[0].id, null)
}

output "subnet_ids" {
  description = "Subnet IDs used by the vEdge NICs (cloud_init is devtest only)"
  value = var.action == "create" ? {
    cloud_init = local.is_devtest ? local.subnet_cloud_init_id : null
    mgmt       = local.subnet_mgmt_id
    wan        = local.subnet_wan_id
    lan        = local.subnet_lan_id
  } : null
}

output "route_table_ids" {
  description = "WAN/LAN route table IDs (null when not created and not provided)"
  value = var.action == "create" ? {
    wan = local.route_table_wan_id != "" ? local.route_table_wan_id : null
    lan = local.route_table_lan_id != "" ? local.route_table_lan_id : null
  } : null
}

output "nsg_ids" {
  description = "NSG IDs attached to the NICs (cloud_init is devtest only, test_vm only with deploy_test_vm)"
  value = var.action == "create" ? {
    cloud_init = local.is_devtest ? local.nsg_cloud_init_id : null
    mgmt       = local.nsg_mgmt_id
    wan        = local.nsg_wan_id
    lan        = local.nsg_lan_id
    test_vm    = var.deploy_test_vm ? local.nsg_test_vm_id : null
  } : null
}

output "vm_id" {
  description = "vEdge VM ID (only available when action is 'create')"
  value       = var.action == "create" ? try(azurerm_linux_virtual_machine.vedge[0].id, null) : null
}

output "cloud_init_public_ip" {
  description = "Public IP address of the cloud-init interface (devtest only, only available when action is 'create')"
  value       = var.action == "create" && var.mode == "devtest" ? try(azurerm_public_ip.cloud_init[0].ip_address, null) : null
}

output "mgmt_public_ip" {
  description = "Public IP address of the mgmt interface (only available when action is 'create')"
  value       = var.action == "create" ? try(azurerm_public_ip.mgmt[0].ip_address, data.azurerm_public_ip.mgmt[0].ip_address, null) : null
}

output "wan_public_ip" {
  description = "Public IP address of the WAN interface (only available when action is 'create')"
  value       = var.action == "create" ? try(azurerm_public_ip.wan[0].ip_address, data.azurerm_public_ip.wan[0].ip_address, null) : null
}

output "mgmt_private_ip" {
  description = "Private IP address of the mgmt interface (only available when action is 'create')"
  value       = var.action == "create" ? try(azurerm_network_interface.mgmt[0].private_ip_address, null) : null
}

output "wan_private_ip" {
  description = "Private IP address of the WAN interface (only available when action is 'create')"
  value       = var.action == "create" ? try(azurerm_network_interface.wan[0].private_ip_address, null) : null
}

output "lan_private_ip" {
  description = "Private IP address of the LAN interface (only available when action is 'create')"
  value       = var.action == "create" ? try(azurerm_network_interface.lan[0].private_ip_address, null) : null
}

output "lan_ipv6_address" {
  description = "IPv6 address of the LAN interface (null when the LAN subnet has no IPv6)"
  value       = local.vedge_lan_ipv6
}

# Test VM outputs
output "test_vm_private_ip" {
  description = "Private IP address of the test VM on LAN subnet (only available when deploy_test_vm is true)"
  value       = var.deploy_test_vm ? try(azurerm_network_interface.test_vm[0].private_ip_address, null) : null
}

output "test_vm_ipv6_address" {
  description = "IPv6 address of the test VM (only when deploy_test_vm = true and the LAN subnet has IPv6)"
  value       = var.deploy_test_vm && local.lan_ipv6 ? try([for c in azurerm_network_interface.test_vm[0].ip_configuration : c.private_ip_address if c.private_ip_address_version == "IPv6"][0], null) : null
}

output "resource_group_deleted" {
  description = "Confirmation that resource group deletion was requested (only available when action is 'delete')"
  value       = var.action == "delete" && var.delete_resource_group ? "Resource group deletion requested" : null
}
