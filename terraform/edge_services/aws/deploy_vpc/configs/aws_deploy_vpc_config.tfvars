# AWS Deploy VPC Configuration

# Pre-requisite:
# ============================================================================
# 1. AWS regions and availability zones:
#    To find the AWS region ID:
#      https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html#available-regions
#    To find available availability zones for your region:
#      aws ec2 describe-availability-zones --region us-east-1

# aws_region: AWS region to deploy resources into
aws_region = "us-east-1"

# availability_zone: AWS availability zone to create network resources in
availability_zone = "us-east-1a"

# project_name: Project name used for default resource names
project_name = "graphiant-vedge"

# vpc_name: Name tag for the new VPC
vpc_name = "graphiant-vedge-vpc"

# vpc_address_range: CIDR block for the new VPC (IPv4). An Amazon-provided IPv6 block is associated automatically.
vpc_address_range = "10.0.0.0/16"

# subnet_mgmt_prefix: CIDR for the mgmt subnet
subnet_mgmt_prefix = "10.0.1.0/24"

# subnet_wan_prefix: CIDR for the WAN subnet
subnet_wan_prefix = "10.0.2.0/24"

# subnet_lan_prefix: CIDR for the LAN subnet
subnet_lan_prefix = "10.0.3.0/24"

# create_internet_gateway: Whether to create an Internet Gateway for the VPC
# create_internet_gateway = true

# tags: Additional tags to apply
# tags = {
#   Owner = "team-network"
# }
