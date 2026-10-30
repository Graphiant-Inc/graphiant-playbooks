# AWS Deploy vEdge Configuration - Production

# Pre-requisite:
# ============================================================================
# (Replace <aws_region> in the commands below with the aws_region you set in this file.)
# 0. Tooling and access:
#    - Terraform >= 1.3
#    - AWS credentials with EC2/VPC permissions in the target account
#    - An onboarding token from the Graphiant Portal (set as token below)
# 1. AWS regions and availability zones:
#    To find the AWS region ID:
#      https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html#available-regions
#    To find available availability zones for your region:
#      aws ec2 describe-availability-zones --region <aws_region>
# 2. Subscribe to the Graphiant Virtual Edge AWS Marketplace listing in your
#    account (required for marketplace_product_id to resolve):
#      https://aws.amazon.com/marketplace/pp/prodview-xngq36gyfhpv2
#    **To get `marketplace_product_id` :**
#    - Open the Marketplace product page and check AMI details: https://aws.amazon.com/marketplace/launch?ref_=aws_mp_pw&productId=ef19ce00-3544-4c76-af98-2001d39fdfd9
#    - The product ID for Graphiant vEdge is `ef19ce00-3544-4c76-af98-2001d39fdfd9`
#    - The marketplace_product_id for Graphiant vEdge is `prod-tjdlkbawxqsyg`
# 3. (Only if you want to SSH into the test VM)
#    Create an EC2 SSH key pair in the target region.
#    From AWS CloudShell or any authenticated host:
#      aws ec2 create-key-pair --key-name aws_ec2_ssh_keypair --region <aws_region> \
#        --query 'KeyMaterial' --output text > aws_ec2_ssh_keypair_privatekey.pem
#      chmod 400 aws_ec2_ssh_keypair_privatekey.pem
#    Then set test_vm_key_name to the key pair name.
# 4. (Optional: Only if you plan to launch a test VM with a specific Debian AMI)
#    Find the Debian 13 AMI ID for your region and set as test_vm_ami:
#      aws ec2 describe-images --owners 136693071363 \
#        --filters "Name=name,Values=debian-13-amd64-*" "Name=state,Values=available" \
#        --region <aws_region> \
#        --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text
#    If test_vm_ami is not set, Terraform will automatically discover the latest
#    Debian 13 AMI for your region.

# mode: Deployment mode
mode = "production"

# aws_region: AWS region to deploy resources into
aws_region = "us-east-1"

# availability_zone: AWS availability zone to create network resources in
availability_zone = "us-east-1a"

# project_name: Project name used for default resource names
project_name = "graphiant-vedge"

# vm_name: EC2 Name tag for the vEdge instance
vm_name = "graphiant-vedge"

# instance_type: AWS EC2 instance type (c5.large, c5.xlarge, m5.large, m5.xlarge, r5.large, r5.xlarge, c6i.4xlarge, c6i.8xlarge, c6in.8xlarge)
instance_type = "c5.large"

# ================================================================
# AMI: Configure the AMI id in image_id or set marketplace_product_id and marketplace_version.
# Refer Pre-requisite #2 to get the marketplace_product_id.
# ================================================================
# image_id = "ami-xxxxxxxx"
marketplace_product_id = "prod-tjdlkbawxqsyg"
marketplace_version    = "latest"

# token: Edge Authentication token for Onboarding the vEdge into a specific Enterprise within Graphiant Portal
token = ""

# ================================================================
# VPC: provide vpc_id to use an existing VPC, or vpc_name + vpc_address_range to create new
# Each subnet / route table / security group / EIP below is independent: set its *_id to reuse it,
# or leave it empty to create it.
# ================================================================
# vpc_id = ""
vpc_name          = "graphiant-vedge-vpc"
vpc_address_range = "10.0.0.0/16"

# mgmt subnet: provide subnet_mgmt_id to use existing, or subnet_mgmt_prefix to create new
# subnet_mgmt_id = ""
subnet_mgmt_prefix = "10.0.1.0/24"

# wan subnet: provide subnet_wan_id to use existing, or subnet_wan_prefix to create new
# subnet_wan_id = ""
subnet_wan_prefix = "10.0.2.0/24"

# lan subnet: provide subnet_lan_id to use existing, or subnet_lan_prefix to create new
# subnet_lan_id = ""
subnet_lan_prefix = "10.0.3.0/24"

# IPv6 is LAN-side only: a new LAN subnet gets a /64 (index subnet_lan_ipv6_netnum of the VPC /56)
# AWS gives a VPC a /56, If the VPC got 2600:1f1c:e90:a900::/56, and with index 3, the LAN subnet will get 2600:1f1c:e90:a903::/64.
# subnet_lan_ipv6_netnum = 3

# ================================================================
# Internet Gateway: provide internet_gateway_id to use existing, else create_internet_gateway decides.
# Note: AWS allows one IGW per VPC
#   unset (default) — new VPC: create an IGW; existing VPC: use the IGW attached to it (plan fails if none).
#   true            — create a new IGW (existing VPC without one); mgmt/WAN get EIPs and the new WAN route table gets default routes to it.
#   false           — no IGW: no EIPs and no IGW routes; add egress (e.g. NAT/TGW) to the WAN route table yourself.
# The LAN route table always gets 0.0.0.0/0 via the vEdge LAN interface.
# ================================================================
# internet_gateway_id     = "igw-xxxxxxxx"
# create_internet_gateway = false

# ================================================================
# Route Tables: provide route_table_*_id to use existing, or leave empty to create new.
# Newly created subnets are associated with the (new or existing) route table; existing subnets keep their association.
# route_table_lan_id is required when subnet_lan_id is provided — a default-via-vEdge route is added to it.
# ================================================================
# route_table_wan_id = ""
# route_table_lan_id = ""

# ================================================================
# Security Groups: provide security_group_*_id to use existing (same VPC), or leave empty to create new
# ================================================================
# security_group_mgmt_id = "sg-xxxxxxxx"
# security_group_wan_id  = "sg-xxxxxxxx"
# security_group_lan_id  = "sg-xxxxxxxx"

# ================================================================
# Elastic IPs: provide eip_*_allocation_id to use pre-allocated EIPs, or leave empty to allocate new (requires an IGW).
# A provided EIP must not be associated elsewhere and is not released on destroy.
# ================================================================
# eip_mgmt_allocation_id = "eipalloc-xxxxxxxx"
# eip_wan_allocation_id  = "eipalloc-xxxxxxxx"

# ================================================================
# Test VM Configuration (Optional — attached to LAN subnet, default route via vEdge)
# ================================================================
deploy_test_vm                    = true
test_vm_name                      = "graphiant-vedge-test-vm"
test_vm_instance_type             = "t3.micro"
test_vm_key_name                  = "aws_ec2_ssh_keypair"   # EC2 key pair name (must exist in aws_region; see pre-requisite step 3). SSH in as the AMI's default user (e.g. 'admin' on Debian).
# test_vm_ami                       = ""   # (Optional) Configure only if you want the specific Debian AMI avialable for your region. Default, the latest Debain 13 is picked.
# security_group_test_vm_id         = "sg-xxxxxxxx"   # only with deploy_test_vm

# By default, all ingress traffic is allowed to the test VM.
# When test_vm_enable_ssh_public_ip is true(which enables internet access to the test VM), it is recommended to restrict test_vm_ingress_allowed_subnets and test_vm_ssh_allowed_subnets to trusted CIDRs only.
test_vm_enable_ssh_public_ip      = true
test_vm_ingress_allowed_subnets   = ["0.0.0.0/0"]   # List of allowed CIDR blocks for the traffic ingressing to the test VM
test_vm_ssh_allowed_subnets       = []   # List of CIDR blocks allowed for SSH access (only when test_vm_enable_ssh_public_ip = true) (eg : ["Your Laptop IP/32"]). Must not include CIDRs routed via the vEdge (0.0.0.0/0, or test_vm_ingress_allowed_subnets when customised)

# tags: Additional tags to apply
tags = {
   Owner = "team-network"
 }
