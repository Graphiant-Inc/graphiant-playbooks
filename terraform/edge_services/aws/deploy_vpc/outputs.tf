output "region" {
  description = "AWS region used for the deployment"
  value       = var.aws_region
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.this.id
}

output "vpc_name" {
  description = "VPC Name tag"
  value       = var.vpc_name
}

output "internet_gateway_id" {
  description = "Internet gateway ID (only when create_internet_gateway = true)"
  value       = var.create_internet_gateway ? try(aws_internet_gateway.this[0].id, null) : null
}

output "subnet_mgmt_id" {
  description = "Subnet ID for the mgmt subnet"
  value       = aws_subnet.mgmt.id
}

output "subnet_wan_id" {
  description = "Subnet ID for the WAN subnet"
  value       = aws_subnet.wan.id
}

output "subnet_lan_id" {
  description = "Subnet ID for the LAN subnet"
  value       = aws_subnet.lan.id
}

output "route_table_wan_id" {
  description = "Route table ID associated with mgmt + wan subnets (default route to IGW)"
  value       = aws_route_table.wan.id
}

output "route_table_lan_id" {
  description = "Route table ID associated with the LAN subnet (default-via-vEdge added by deploy_vedge)"
  value       = aws_route_table.lan.id
}
