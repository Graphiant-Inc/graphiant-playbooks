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

output "internet_gateway_id" {
  description = "Internet Gateway ID (new or existing); null when deployed without an IGW"
  value       = local.use_igw ? local.igw_id_resolved : null
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
  description = "Public IP of the cloud-init interface (devtest only; null without an IGW)"
  value       = local.is_devtest ? try(aws_eip.cloud_init[0].public_ip, null) : null
}

output "mgmt_public_ip" {
  description = "Public IP of the mgmt interface (null without an IGW)"
  value       = local.eip_mgmt_public_ip
}

output "wan_public_ip" {
  description = "Public IP of the WAN interface (null without an IGW)"
  value       = local.eip_wan_public_ip
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

output "lan_ipv6_address" {
  description = "IPv6 address of the LAN interface (null when the LAN subnet has no IPv6)"
  value       = try(tolist(aws_network_interface.lan.ipv6_addresses)[0], null)
}

output "test_vm_private_ip" {
  description = "Private IP of the test VM on the LAN subnet (only when deploy_test_vm = true)"
  value       = var.deploy_test_vm ? try(aws_instance.test_vm[0].private_ip, null) : null
}

output "test_vm_ipv6_address" {
  description = "IPv6 address of the test VM (only when deploy_test_vm = true and the LAN subnet has IPv6)"
  value       = var.deploy_test_vm ? try(tolist(aws_network_interface.test_vm[0].ipv6_addresses)[0], null) : null
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
  value       = local.route_table_wan_id_resolved
}

output "route_table_lan_id" {
  description = "LAN route table ID (new or existing)"
  value       = local.route_table_lan_id_resolved
}

output "security_group_mgmt_id" {
  description = "Mgmt security group ID (new or existing)"
  value       = local.sg_mgmt_id_resolved
}

output "security_group_wan_id" {
  description = "WAN security group ID (new or existing)"
  value       = local.sg_wan_id_resolved
}

output "security_group_lan_id" {
  description = "LAN security group ID (new or existing)"
  value       = local.sg_lan_id_resolved
}

output "security_group_test_vm_id" {
  description = "Test VM security group ID (new or existing; only when deploy_test_vm = true)"
  value       = var.deploy_test_vm ? local.sg_test_vm_id_resolved : null
}
