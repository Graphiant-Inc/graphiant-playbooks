# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------
variable "mode" {
  description = "Deployment mode: 'production' for customer-facing, 'devtest' for internal use with SSH access"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "devtest"], var.mode)
    error_message = "Mode must be either 'production' or 'devtest'."
  }
}

variable "aws_region" {
  description = "AWS region to deploy resources into"
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "Availability zone to create network resources in"
  type        = string
}

variable "project_name" {
  description = "Project name used as a prefix for default resource names"
  type        = string
  default     = "graphiant-vedge"
}

variable "vm_name" {
  description = "EC2 Name tag for the vEdge instance"
  type        = string
  default     = "graphiant-vedge"
}

variable "instance_type" {
  description = "EC2 instance type (allowed values depend on mode)"
  type        = string
  default     = "c5.large"

  validation {
    condition = contains([
      "c5.large", "c5.xlarge",
      "m5.large", "m5.xlarge",
      "r5.large", "r5.xlarge",
      "c6i.4xlarge", "c6i.8xlarge", "c6in.8xlarge",
    ], var.instance_type)
    error_message = "Instance type must be one of: c5.large, c5.xlarge, m5.large, m5.xlarge, r5.large, r5.xlarge, c6i.4xlarge, c6i.8xlarge, c6in.8xlarge."
  }
}

variable "image_id" {
  description = "Explicit AMI ID for the Graphiant vEdge instance. When empty, marketplace_product_id is used to resolve the AMI via the AWS Marketplace SSM public parameter. Exactly one of image_id or marketplace_product_id must be set."
  type        = string
  default     = ""
}

variable "marketplace_product_id" {
  description = "AWS Marketplace product ID (e.g. 'prod-tjdlkbawxqsyg'). Used with marketplace_version to resolve the vEdge AMI via /aws/service/marketplace/<product_id>/<version>. Used only when image_id is empty."
  type        = string
  default     = ""
}

variable "marketplace_version" {
  description = "Marketplace AMI version. Use 'latest' to auto-bump to the newest version, or pin to a specific version string (e.g. '2512.20260119.1808')."
  type        = string
  default     = "latest"
}

variable "token" {
  description = "Graphiant vEdge onboarding authentication token"
  type        = string
  sensitive   = true
  default     = ""
}

# -----------------------------------------------------------------------------
# Devtest-specific
# -----------------------------------------------------------------------------
variable "ssh_public_key" {
  description = "SSH public key for the cloud-init user (devtest only)"
  type        = string
  default     = ""
}

variable "cloud_init_username" {
  description = "Username for the cloud-init user created in devtest mode"
  type        = string
  default     = "gnos"
}

variable "cloud_init_password" {
  description = "Password for the cloud-init user created in devtest mode"
  type        = string
  sensitive   = true
  default     = ""
}

variable "onboarding_auth_url" {
  description = "Internal Graphiant OAuth authentication endpoint (devtest only)"
  type        = string
  default     = ""
}

variable "onboarding_gateway" {
  description = "Internal Graphiant onboarding service hostname and port (devtest only)"
  type        = string
  default     = ""
}

variable "allowed_cidr" {
  description = "Public IPv4 (/32) allowed to connect to the devtest mgmt/SSH ports"
  type        = string
  default     = "127.0.0.1/32"
}

# -----------------------------------------------------------------------------
# VPC (existing or new)
# -----------------------------------------------------------------------------
variable "vpc_id" {
  description = "Existing VPC ID. When set, uses the existing VPC (new subnets/route tables can still be created in it). When empty, creates a new VPC using vpc_name + vpc_address_range."
  type        = string
  default     = ""
}

variable "vpc_name" {
  description = "Name tag for the new VPC (only used when vpc_id is empty)"
  type        = string
  default     = "graphiant-vedge-vpc"
}

variable "vpc_address_range" {
  description = "CIDR block for the new VPC (only used when vpc_id is empty)"
  type        = string
  default     = "10.1.0.0/16"
}

# -----------------------------------------------------------------------------
# Internet Gateway (existing, new, or none)
# -----------------------------------------------------------------------------
variable "internet_gateway_id" {
  description = "Existing Internet Gateway ID attached to the VPC. When set, it is used and create_internet_gateway is ignored."
  type        = string
  default     = ""
}

variable "create_internet_gateway" {
  description = "When internet_gateway_id is empty: null (default) creates an IGW for a new VPC and uses the IGW attached to an existing VPC; true creates a new IGW (existing VPC without one); false deploys without an IGW (no IGW routes, no mgmt/WAN/cloud-init EIPs; the WAN route table needs operator-provided egress such as NAT/TGW)."
  type        = bool
  default     = null
}

# -----------------------------------------------------------------------------
# Subnets — each subnet_*_id provided is reused; empty creates a new subnet from
# subnet_*_prefix in the VPC in use (IPv4 only).
# -----------------------------------------------------------------------------
variable "subnet_cloud_init_id" {
  description = "Existing cloud-init subnet ID (devtest only). When empty, a new subnet is created from subnet_cloud_init_prefix."
  type        = string
  default     = ""
}

variable "subnet_cloud_init_prefix" {
  description = "CIDR for the new cloud-init subnet (devtest only; used when subnet_cloud_init_id is empty)"
  type        = string
  default     = "10.1.0.0/24"
}

variable "subnet_mgmt_id" {
  description = "Existing mgmt subnet ID. When empty, a new subnet is created from subnet_mgmt_prefix."
  type        = string
  default     = ""
}

variable "subnet_mgmt_prefix" {
  description = "CIDR for the new mgmt subnet (used when subnet_mgmt_id is empty)"
  type        = string
  default     = "10.1.1.0/24"
}

variable "subnet_wan_id" {
  description = "Existing WAN subnet ID. When empty, a new subnet is created from subnet_wan_prefix."
  type        = string
  default     = ""
}

variable "subnet_wan_prefix" {
  description = "CIDR for the new WAN subnet (used when subnet_wan_id is empty)"
  type        = string
  default     = "10.1.2.0/24"
}

variable "subnet_lan_id" {
  description = "Existing LAN subnet ID. When set, route_table_lan_id is required. When empty, a new subnet is created from subnet_lan_prefix."
  type        = string
  default     = ""
}

variable "subnet_lan_prefix" {
  description = "CIDR for the new LAN subnet (used when subnet_lan_id is empty)"
  type        = string
  default     = "10.1.3.0/24"
}

variable "subnet_lan_ipv6_netnum" {
  description = "Index of the IPv6 /64 carved from the VPC /56 for a new LAN subnet (only the LAN side gets IPv6; pick an unused index in an existing VPC)"
  type        = number
  default     = 3
}

# -----------------------------------------------------------------------------
# Route tables (existing or new)
# -----------------------------------------------------------------------------
variable "route_table_wan_id" {
  description = "Existing WAN route table ID. Newly created mgmt/wan/cloud-init subnets are associated with it; existing subnets keep their current association. When empty, a new WAN RT is created if any of those subnets is new (default routes to the IGW, or no routes without an IGW)."
  type        = string
  default     = ""
}

variable "route_table_lan_id" {
  description = "Existing LAN route table ID. The default-via-vEdge route is added to it, and a newly created LAN subnet is associated with it. When empty, a new LAN RT is created (required when subnet_lan_id is set)."
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Security groups (existing or new) — must belong to the VPC in use
# -----------------------------------------------------------------------------
variable "security_group_cloud_init_id" {
  description = "Existing security group ID for the cloud-init NIC (devtest only). When empty, a new SG is created."
  type        = string
  default     = ""
}

variable "security_group_mgmt_id" {
  description = "Existing security group ID for the mgmt NIC. When empty, a new SG is created."
  type        = string
  default     = ""
}

variable "security_group_wan_id" {
  description = "Existing security group ID for the WAN NIC. When empty, a new SG with the Graphiant WAN egress rules is created."
  type        = string
  default     = ""
}

variable "security_group_lan_id" {
  description = "Existing security group ID for the LAN NIC. When empty, a new allow-all SG is created."
  type        = string
  default     = ""
}

variable "security_group_test_vm_id" {
  description = "Existing security group ID for the test VM NIC (only with deploy_test_vm). When empty, a new SG is created from test_vm_ingress_allowed_subnets / test_vm_ssh_allowed_subnets; when set, those no longer shape SG rules (test_vm_ssh_allowed_subnets still drives the LAN SSH routes)."
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Elastic IPs (existing or new)
# -----------------------------------------------------------------------------
variable "eip_mgmt_allocation_id" {
  description = "Existing Elastic IP allocation ID (eipalloc-...) for the mgmt NIC. When empty, a new EIP is allocated (none without an IGW). A provided EIP must not be associated elsewhere and is not released on destroy."
  type        = string
  default     = ""
}

variable "eip_wan_allocation_id" {
  description = "Existing Elastic IP allocation ID (eipalloc-...) for the WAN NIC. When empty, a new EIP is allocated (none without an IGW). A provided EIP must not be associated elsewhere and is not released on destroy."
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Test VM (optional)
# -----------------------------------------------------------------------------
variable "deploy_test_vm" {
  description = "Whether to deploy a test VM on the LAN subnet"
  type        = bool
  default     = false
}

variable "test_vm_name" {
  description = "Name tag for the test VM"
  type        = string
  default     = "graphiant-vedge-test-vm"
}

variable "test_vm_instance_type" {
  description = "EC2 instance type for the test VM"
  type        = string
  default     = "t3.micro"
}

variable "test_vm_ami" {
  description = "AMI ID for the test VM (Debian 13 recommended; required when deploy_test_vm = true)"
  type        = string
  default     = ""
}

variable "test_vm_key_name" {
  description = "EC2 key pair name attached to the test VM. SSH in as the AMI's default cloud user (e.g. 'admin' on Debian, 'ec2-user' on Amazon Linux). The key pair must already exist in the target AWS region — create it as a pre-requisite (see configs/*.tfvars header)."
  type        = string
  default     = ""
}

variable "test_vm_enable_ssh_public_ip" {
  description = "Whether to allocate and attach an Elastic IP to the test VM for public SSH access"
  type        = bool
  default     = false
}

variable "test_vm_ingress_allowed_subnets" {
  description = "List of CIDR blocks allowed ingress to the test VM (all protocols/ports)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "test_vm_ssh_allowed_subnets" {
  description = "List of CIDR blocks allowed SSH access (TCP 22) to the test VM's public IP. Only used when test_vm_enable_ssh_public_ip = true. Must not include CIDRs routed via the vEdge (0.0.0.0/0, or test_vm_ingress_allowed_subnets when customised)."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# -----------------------------------------------------------------------------
# AWS Partner Product Code
# -----------------------------------------------------------------------------
variable "aws_partner_product_code" {
  description = "AWS Partner product code for resource tagging. Used to track AWS consumption driven by the Graphiant product."
  type        = string
  default     = "e5lbtnbqh6hbtcvn329gzonh5"
}

# -----------------------------------------------------------------------------
# Tags
# -----------------------------------------------------------------------------
variable "tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}
