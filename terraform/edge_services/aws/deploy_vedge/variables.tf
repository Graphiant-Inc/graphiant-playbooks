variable "action" {
  description = "Action to perform: 'create' to deploy the CloudFormation stack, 'delete' to destroy it"
  type        = string
  default     = "create"

  validation {
    condition     = contains(["create", "delete"], var.action)
    error_message = "Action must be either 'create' or 'delete'."
  }
}

variable "mode" {
  description = "Mode name (production, devtest)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "devtest"], var.mode)
    error_message = "Mode must be either 'production' or 'devtest'."
  }
}

variable "aws_region" {
  description = "AWS region to deploy the CloudFormation stack into"
  type        = string
  default     = "us-east-1"
}

variable "stack_name" {
  description = "CloudFormation stack name"
  type        = string
  default     = "vedge_vpc_production"
}

variable "template_path" {
  description = "Path to the CloudFormation template file (only used for create action)"
  type        = string
  default     = "templates/vEdge-production.yml"
}

variable "image_id" {
  description = "AMI ID used by the vEdge instance (CloudFormation: ImageId) (only used for create action)"
  type        = string
  default     = "ami-0e6c9aef7f9c78d0e"
}

variable "instance_type" {
  description = "EC2 instance type (CloudFormation: InstanceType) (only used for create action)"
  type        = string
  default     = "c5.large"
}

variable "instance_name" {
  description = "Name of the instance (CloudFormation: InstanceName) (only used for create action)"
  type        = string
  default     = "vEdgeEC2"
}

variable "vpc_address_range" {
  description = "CIDR block for VPC (CloudFormation: VPCAddressRange) (only used for create action)"
  type        = string
  default     = "10.0.0.0/16"
}

variable "onboarding_gateway" {
  description = "Graphiant onboarding gateway address & port (CloudFormation: OnboardingGateway) (only used for create action)"
  type        = string
  default     = ""
}

variable "onboarding_auth_url" {
  description = "Graphiant onboarding authentication URL (CloudFormation: OnboardingAuthUrl) (only used for create action)"
  type        = string
  default     = ""
}

variable "ssh_public_key" {
  description = "Public ssh key for accessing the instance (CloudFormation: SSHPublicKey) (only used for create action)"
  type        = string
  default     = ""
}

variable "allowed_cidr" {
  description = "Public IPv4 (/32) allowed to connect to the local web UI (CloudFormation: AllowedCidr) (only used for create action)"
  type        = string
  default     = "127.0.0.1/32"
}

variable "allowed_cidr_v6" {
  description = "Public IPv6 (/128) allowed to connect to the local web UI (CloudFormation: AllowedCidrV6) (only used for create action)"
  type        = string
  default     = "::1/128"
}

variable "availability_zone" {
  description = "Availability zone to create network resources in (CloudFormation: AvailabilityZone) (only used for create action)"
  type        = string
}

variable "token" {
  description = "Graphiant vEdge onboarding authentication token (CloudFormation: Token) (only used for create action)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "customer_vpc" {
  description = "The VPC to deploy the vEdge instance into (CloudFormation: CustomerVPC) (only used for create action)"
  type        = string
  default     = ""
}

variable "customer_vpc_route_table" {
  description = "An existing route table in the VPC to use for internet access (CloudFormation: CustomerVPCRouteTable) (only used for create action)"
  type        = string
  default     = ""
}

variable "subnet_cloud_init" {
  description = "Subnet within the VPC to use for ssh access (CloudFormation: SubnetCloudInit) (only used for create action)"
  type        = string
  default     = ""
}

variable "subnet_mgmt" {
  description = "Subnet within the VPC to use for mgmt access (CloudFormation: SubnetMgmt) (only used for create action)"
  type        = string
  default     = ""
}

variable "subnet_wan" {
  description = "Subnet within the VPC to use for WAN access (CloudFormation: SubnetWan) (only used for create action)"
  type        = string
  default     = ""
}

variable "subnet_lan" {
  description = "Subnet within the VPC to use for customer workload access (CloudFormation: SubnetLan) (only used for create action)"
  type        = string
  default     = ""
}