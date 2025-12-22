terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  aws_vedge_devtest_new_vpc = {
    AvailabilityZone = var.availability_zone
    VPCAddressRange = var.vpc_address_range
    ImageId = var.image_id
    InstanceType = var.instance_type
    InstanceName = var.instance_name
    AllowedCidr = var.allowed_cidr
    AllowedCidrV6 = var.allowed_cidr_v6
    Token = var.token
    OnboardingAuthUrl = var.onboarding_auth_url
    OnboardingGateway = var.onboarding_gateway
    SSHPublicKey = var.ssh_public_key
  }
  aws_vedge_production_new_vpc = {
    AvailabilityZone = var.availability_zone
    VPCAddressRange = var.vpc_address_range
    ImageId = var.image_id
    InstanceType = var.instance_type
    InstanceName = var.instance_name
    Token = var.token
  }
  aws_vedge_devtest_existing_vpc = {
    AvailabilityZone = var.availability_zone
    ImageId = var.image_id
    InstanceType = var.instance_type
    InstanceName = var.instance_name
    AllowedCidr = var.allowed_cidr
    AllowedCidrV6 = var.allowed_cidr_v6
    Token = var.token
    OnboardingAuthUrl = var.onboarding_auth_url
    OnboardingGateway = var.onboarding_gateway
    SSHPublicKey = var.ssh_public_key
    CustomerVPC = var.customer_vpc
    CustomerVPCRouteTable = var.customer_vpc_route_table
    SubnetCloudInit = var.subnet_cloud_init
    SubnetMgmt = var.subnet_mgmt
    SubnetWan = var.subnet_wan
    SubnetLan = var.subnet_lan
  }
  aws_vedge_production_existing_vpc = {
    AvailabilityZone = var.availability_zone
    ImageId = var.image_id
    InstanceType = var.instance_type
    InstanceName = var.instance_name
    Token = var.token
    CustomerVPC = var.customer_vpc
    CustomerVPCRouteTable = var.customer_vpc_route_table
    SubnetMgmt = var.subnet_mgmt
    SubnetWan = var.subnet_wan
    SubnetLan = var.subnet_lan
  }
  params = (
    strcontains(lower(var.template_path), "aws-vedge-devtest-new-vpc") ? local.aws_vedge_devtest_new_vpc :
    strcontains(lower(var.template_path), "aws-vedge-production-new-vpc") ? local.aws_vedge_production_new_vpc :
    strcontains(lower(var.template_path), "aws-vedge-devtest-existing-vpc") ? local.aws_vedge_devtest_existing_vpc :
    strcontains(lower(var.template_path), "aws-vedge-production-existing-vpc") ? local.aws_vedge_production_existing_vpc :
    {}
  )
}

# Create CloudFormation stack
resource "aws_cloudformation_stack" "graphiant_stack" {
  count = var.action == "create" ? 1 : 0
  name = var.stack_name
  template_body = file(var.template_path)
  parameters = local.params
}

# Data source to check if the stack exists - used for deletion
data "aws_cloudformation_stack" "graphiant_stack_data" {
  count = var.action == "delete" && var.stack_name != "" ? 1 : 0
  name  = var.stack_name
}

# Resource to delete the CloudFormation stack
resource "null_resource" "delete_graphiant_stack" {
  count = var.action == "delete" && var.stack_name != "" ? 1 : 0

  provisioner "local-exec" {
    command = "aws cloudformation delete-stack --stack-name ${var.stack_name} --region ${var.aws_region}"
  }

  depends_on = [data.aws_cloudformation_stack.graphiant_stack_data]
}
