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
  value       = var.action == "create" ? try(azurerm_public_ip.mgmt[0].ip_address, null) : null
}

output "wan_public_ip" {
  description = "Public IP address of the WAN interface (only available when action is 'create')"
  value       = var.action == "create" ? try(azurerm_public_ip.wan[0].ip_address, null) : null
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

# Test VM outputs
output "test_vm_private_ip" {
  description = "Private IP address of the test VM on LAN subnet (only available when deploy_test_vm is true)"
  value       = var.deploy_test_vm ? try(azurerm_network_interface.test_vm[0].private_ip_address, null) : null
}

output "resource_group_deleted" {
  description = "Confirmation that resource group deletion was requested (only available when action is 'delete')"
  value       = var.action == "delete" && var.delete_resource_group ? "Resource group deletion requested" : null
}
