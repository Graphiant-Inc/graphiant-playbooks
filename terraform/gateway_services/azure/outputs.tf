# Outputs for Express.js Terraform configuration on azure

output "resource_group_name" {
  description = "Name of the resource group"
  value       = var.use_existing_rg ? data.azurerm_resource_group.existing[0].name : azurerm_resource_group.rg[0].name
}

#Virtual Network output
output "vnet_id" {
  description = "ID of the Virtual Network"
  value       = var.use_existing_vnet ? data.azurerm_virtual_network.existing[0].id : azurerm_virtual_network.virtual_network[0].id
}

output "vnet_name" {
  description = "Name of the Virtual Network"
  value       = var.use_existing_vnet ? data.azurerm_virtual_network.existing[0].name : azurerm_virtual_network.virtual_network[0].name
}

# ExpressRoute Circuit Outputs
output "expressroute_circuit_id" {
  description = "ID of the ExpressRoute Circuit"
  value       = var.enable_expressroute ? azurerm_express_route_circuit.express_route[0].id : "ExpressRoute not enabled"
}

output "expressroute_circuit_name" {
  description = "Name of the ExpressRoute Circuit"
  value       = var.enable_expressroute ? azurerm_express_route_circuit.express_route[0].name : "ExpressRoute not enabled"
}

output "expressroute_circuit_service_key" {
  description = "Service key of the ExpressRoute Circuit"
  value       = var.enable_expressroute ? azurerm_express_route_circuit.express_route[0].service_key : "ExpressRoute not enabled"
  sensitive   = true
}

output "expressroute_circuit_bandwidth" {
  description = "Bandwidth of the ExpressRoute Circuit"
  value       = var.enable_expressroute ? azurerm_express_route_circuit.express_route[0].bandwidth_in_mbps : "ExpressRoute not enabled"
}

output "expressroute_gateway_id" {
  description = "ID of the ExpressRoute Gateway"
  value       = var.enable_expressroute ? azurerm_express_route_gateway.express_route_gateway[0].id : "ExpressRoute not enabled"
}

output "expressroute_gateway_name" {
  description = "Name of the ExpressRoute Gateway"
  value       = var.enable_expressroute ? azurerm_express_route_gateway.express_route_gateway[0].name : "ExpressRoute not enabled"
}

output "expressroute_connection_id" {
  description = "ID of the ExpressRoute Connection"
  value       = var.enable_expressroute && var.create_expressroute_connection ? azurerm_express_route_connection.express_route_connection[0].id : "Connection not created yet - set create_expressroute_connection = true after service provider provisions the circuit"
}

output "expressroute_peering_id" {
  description = "ID of the ExpressRoute Circuit Peering"
  value       = var.enable_expressroute ? azurerm_express_route_circuit_peering.express_route_peering[0].id : "ExpressRoute not enabled"
}

output "virtual_hub_id" {
  description = "ID of the Virtual Hub"
  value       = var.enable_expressroute ? azurerm_virtual_hub.virtual_hub[0].id : "ExpressRoute not enabled"
}

output "virtual_hub_name" {
  description = "Name of the Virtual Hub"
  value       = var.enable_expressroute ? azurerm_virtual_hub.virtual_hub[0].name : "ExpressRoute not enabled"
}

output "secondary_expressroute_circuit_id" {
  description = "ID of the Secondary ExpressRoute Circuit"
  value       = var.enable_expressroute && var.expressroute_secondary_peering_location != "" ? azurerm_express_route_circuit.express_route_secondary[0].id : "Secondary ExpressRoute not enabled"
}

output "deployment_status" {
  description = "Current deployment status and next steps"
  value = var.enable_expressroute ? "✅ Azure infrastructure is ready! The physical connection needs to be provisioned by the service provider (${var.expressroute_service_provider}). Contact them to complete the circuit provisioning." : "ExpressRoute not enabled"
}

output "service_provider_contact_info" {
  description = "Information about service provider provisioning"
  value = var.enable_expressroute ? "Contact ${var.expressroute_service_provider} to provision the physical circuit. Once provisioned, run 'terraform apply' again to create the ExpressRoute connection." : "N/A"
}

# Route Table Outputs
output "route_table_id" {
  description = "ID of the Route Table"
  value       = var.enable_expressroute ? azurerm_route_table.express_route_route_table[0].id : "ExpressRoute not enabled"
}

output "route_table_name" {
  description = "Name of the Route Table"
  value       = var.enable_expressroute ? azurerm_route_table.express_route_route_table[0].name : "ExpressRoute not enabled"
}

output "route_table_default_route" {
  description = "Configured default route destination"
  value       = var.enable_expressroute ? var.route_table_default_route : "ExpressRoute not enabled"
}

# VM Outputs for E2E Testing
output "test_vm_public_ip" {
  description = "Public IP address of the test VM for SSH access"
  value       = var.deploy_test_vm ? azurerm_public_ip.vm_public_ip[0].ip_address : "Test VM not deployed"
}

output "test_vm_private_ip" {
  description = "Private IP address of the test VM"
  value       = var.deploy_test_vm ? azurerm_network_interface.vm_nic[0].private_ip_address : "Test VM not deployed"
}

output "test_vm_ssh_command" {
  description = "SSH command to connect to the test VM"
  value       = var.deploy_test_vm ? "ssh ${var.vm_admin_username}@${azurerm_public_ip.vm_public_ip[0].ip_address}" : "Test VM not deployed"
}
