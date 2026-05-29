output "region" {
  description = "AWS region used for the deployment"
  value       = var.aws_region
}

output "mode" {
  description = "Deployment mode (production or devtest)"
  value       = var.mode
}

output "vpc_id" {
  description = "VPC ID used for the deployment (new or existing)"
  value       = local.vpc_id_resolved
}

output "vpc_name" {
  description = "VPC Name tag (new VPC) or empty when reusing an existing VPC"
  value       = local.new_vpc ? var.vpc_name : ""
}

output "instance_id" {
  description = "vEdge EC2 instance ID"
  value       = aws_instance.vedge.id
}

output "instance_name" {
  description = "vEdge EC2 Name tag"
  value       = var.vm_name
}

output "cloud_init_public_ip" {
  description = "Public IP of the cloud-init interface (devtest only)"
  value       = local.is_devtest ? try(aws_eip.cloud_init[0].public_ip, null) : null
}

output "mgmt_public_ip" {
  description = "Public IP of the mgmt interface"
  value       = aws_eip.mgmt.public_ip
}

output "wan_public_ip" {
  description = "Public IP of the WAN interface"
  value       = aws_eip.wan.public_ip
}

output "mgmt_private_ip" {
  description = "Private IP of the mgmt interface"
  value       = aws_network_interface.mgmt.private_ip
}

output "wan_private_ip" {
  description = "Private IP of the WAN interface"
  value       = aws_network_interface.wan.private_ip
}

output "lan_private_ip" {
  description = "Private IP of the LAN interface (use this when configuring the vEdge in Graphiant Portal)"
  value       = aws_network_interface.lan.private_ip
}

output "test_vm_private_ip" {
  description = "Private IP of the test VM on the LAN subnet (only when deploy_test_vm = true)"
  value       = var.deploy_test_vm ? try(aws_instance.test_vm[0].private_ip, null) : null
}

output "test_vm_public_ip" {
  description = "Elastic IP of the test VM (only when test_vm_enable_ssh_public_ip = true)"
  value       = var.deploy_test_vm && var.test_vm_enable_ssh_public_ip ? try(aws_eip.test_vm[0].public_ip, null) : null
}

output "test_vm_public_dns" {
  description = "Public DNS name of the test VM (only when test_vm_enable_ssh_public_ip = true)"
  value       = var.deploy_test_vm && var.test_vm_enable_ssh_public_ip ? try(aws_eip.test_vm[0].public_dns, null) : null
}

output "subnet_mgmt_id" {
  description = "Mgmt subnet ID (new or existing)"
  value       = local.subnet_mgmt_id_resolved
}

output "subnet_wan_id" {
  description = "WAN subnet ID (new or existing)"
  value       = local.subnet_wan_id_resolved
}

output "subnet_lan_id" {
  description = "LAN subnet ID (new or existing)"
  value       = local.subnet_lan_id_resolved
}

output "route_table_wan_id" {
  description = "WAN route table ID (new or existing)"
  value       = local.create_rt_wan ? try(aws_route_table.wan[0].id, null) : var.route_table_wan_id
}

output "route_table_lan_id" {
  description = "LAN route table ID (new or existing)"
  value       = local.create_rt_lan ? try(aws_route_table.lan[0].id, null) : var.route_table_lan_id
}
