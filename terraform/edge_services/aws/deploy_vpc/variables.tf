variable "action" {
  description = "Action to perform: 'create' to deploy the CloudFormation stack, 'delete' to destroy it"
  type        = string
  default     = "create"

  validation {
    condition     = contains(["create", "delete"], var.action)
    error_message = "Action must be either 'create' or 'delete'."
  }
}

variable "aws_region" {
  description = "AWS region to deploy the CloudFormation stack into"
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "Availability zone to create network resources"
  type        = string
}

variable "stack_name" {
  description = "CloudFormation stack name"
  type        = string
  default     = "graphiant-vpc"
}

variable "template_path" {
  description = "Path to the CloudFormation template file (only used for create action)"
  type        = string
  default     = "templates/template-aws-vpc.yml"
}

variable "vpc_address_range" {
  description = "CIDR block for VPC (CloudFormation: VPCAddressRange) (only used for create action)"
  type        = string
  default     = "10.0.0.0/16"
}