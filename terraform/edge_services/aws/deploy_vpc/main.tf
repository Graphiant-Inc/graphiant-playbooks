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
  params = {
    VPCAddressRange  = var.vpc_address_range
    AvailabilityZone = var.availability_zone
  }
}

# ------------------------------------------------------------------------------
# VPC and Graphiant vEdge instance
# ------------------------------------------------------------------------------
# Create VPC and Graphiant vEdge instance
resource "aws_cloudformation_stack" "graphiant_stack" {
  count = var.action == "create" ? 1 : 0

  name          = var.stack_name
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
