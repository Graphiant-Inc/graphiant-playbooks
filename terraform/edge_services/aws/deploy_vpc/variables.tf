variable "aws_region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "Availability zone to create subnets in"
  type        = string
}

variable "project_name" {
  description = "Project name used as a prefix for default resource names"
  type        = string
  default     = "graphiant-vedge"
}

variable "vpc_name" {
  description = "Name tag for the created VPC"
  type        = string
  default     = "graphiant-vedge-vpc"
}

variable "vpc_address_range" {
  description = "CIDR block for the VPC (IPv4). An Amazon-provided IPv6 block is associated automatically."
  type        = string
  default     = "10.1.0.0/16"
}

variable "subnet_mgmt_prefix" {
  description = "CIDR for the mgmt subnet (must fit inside vpc_address_range)"
  type        = string
  default     = "10.1.1.0/24"
}

variable "subnet_wan_prefix" {
  description = "CIDR for the WAN subnet (must fit inside vpc_address_range)"
  type        = string
  default     = "10.1.2.0/24"
}

variable "subnet_lan_prefix" {
  description = "CIDR for the LAN subnet (must fit inside vpc_address_range)"
  type        = string
  default     = "10.1.3.0/24"
}

variable "create_internet_gateway" {
  description = "Whether to create an Internet Gateway for the VPC"
  type        = bool
  default     = true
}

# -----------------------------------------------------------------------------
# AWS Partner Product Code
# -----------------------------------------------------------------------------
variable "aws_partner_product_code" {
  description = "AWS Partner product code for resource tagging. Used to track AWS consumption driven by the Graphiant product."
  type        = string
  default     = "e5lbtnbqh6hbtcvn329gzonh5"
}

variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
