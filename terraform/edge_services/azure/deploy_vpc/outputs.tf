output "action_performed" {
  description = "The action that was performed (create or delete)"
  value       = var.action
}

output "resource_group_id" {
  description = "Resource group ID"
  value       = local.use_existing_rg ? var.resource_group_id : try(azurerm_resource_group.rg[0].id, null)
}

output "resource_group_name" {
  description = "Resource group name used for the deployment"
  value       = local.use_existing_rg ? local.existing_rg_name : try(azurerm_resource_group.rg[0].name, null)
}

# VNet outputs
output "vnet_id" {
  description = "Virtual network ID"
  value       = var.action == "create" ? try(azurerm_virtual_network.vnet[0].id, null) : null
}

output "vnet_name" {
  description = "Virtual network name"
  value       = var.action == "create" ? try(azurerm_virtual_network.vnet[0].name, null) : null
}

# Subnet outputs
output "subnet_mgmt_id" {
  description = "Subnet ID for mgmt subnet"
  value       = var.action == "create" ? try(azurerm_subnet.mgmt[0].id, null) : null
}

output "subnet_wan_id" {
  description = "Subnet ID for WAN subnet"
  value       = var.action == "create" ? try(azurerm_subnet.wan[0].id, null) : null
}

output "subnet_lan_id" {
  description = "Subnet ID for LAN subnet"
  value       = var.action == "create" ? try(azurerm_subnet.lan[0].id, null) : null
}

# Route table outputs
output "route_table_wan_id" {
  description = "Route table ID for WAN/mgmt subnets"
  value       = var.action == "create" ? try(azurerm_route_table.wan[0].id, null) : null
}

output "route_table_lan_id" {
  description = "Route table ID for LAN subnet"
  value       = var.action == "create" ? try(azurerm_route_table.lan[0].id, null) : null
}

output "resource_group_deleted" {
  description = "Confirmation that resource group deletion was requested (only available when action is 'delete')"
  value       = var.action == "delete" && var.delete_resource_group ? "Resource group ${var.resource_group_name} deletion requested" : null
}
