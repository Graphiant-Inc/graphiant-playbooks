# AWS Deploy vEdge Configuration - Devtest mode (Internal Use Only)

# Pre-requisite:
# ============================================================================
# 1. AWS regions and availability zones:
#    To find the AWS region ID:
#      https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html#available-regions
#    To find available availability zones for your region:
#      aws ec2 describe-availability-zones --region us-east-1
# 2. (Only if you plan to launch a test VM) 
#    Create an EC2 SSH key pair in the target region. 
#    From AWS CloudShell or any authenticated host:
#      aws ec2 create-key-pair --key-name aws_ec2_ssh_keypair --region us-east-1 \
#        --query 'KeyMaterial' --output text > aws_ec2_ssh_keypair_privatekey.pem
#      chmod 400 aws_ec2_ssh_keypair_privatekey.pem
#    Then set test_vm_key_name to the key pair name.
# 3. (Optional: Only if you plan to launch a test VM with a specific Debian AMI)
#    Find the Debian 13 AMI ID for your region and set as test_vm_ami:
#      aws ec2 describe-images --owners 136693071363 \
#        --filters "Name=name,Values=debian-13-amd64-*" "Name=state,Values=available" \
#        --region us-east-1 \
#        --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text
#    If test_vm_ami is not set, Terraform will automatically discover the latest
#    Debian 13 AMI for your region.

# mode: Deployment mode
mode = "devtest"

# aws_region: AWS region to deploy resources into
aws_region = "us-east-1"

# availability_zone: AWS availability zone to create network resources in
availability_zone = "us-east-1a"

# project_name: Project name used for default resource names
project_name = "graphiant-vedge-devtest"

# vm_name: EC2 Name tag for the vEdge instance
vm_name = "graphiant-vedge-devtest"

# instance_type: AWS EC2 instance type
instance_type = "c5.xlarge"

# ================================================================
# AMI: Configure the AMI id in image_id or set marketplace_product_id and marketplace_version.
# Refer Pre-requisite #4 to get the marketplace_product_id.
# ================================================================
image_id = ""
# marketplace_product_id = "prod-tjdlkbawxqsyg"
# marketplace_version    = "latest"

# token: Edge Authentication token for Onboarding the vEdge into a specific Enterprise within Graphiant Portal
token = ""

# =============================================================================
# Cloud-init User Configuration (devtest only)
# =============================================================================
# ssh_public_key: SSH public key for the cloud-init user
ssh_public_key = ""

# cloud_init_username: Username for the cloud-init user
cloud_init_username = ""

# cloud_init_password: Password for the cloud-init user
cloud_init_password = ""

# ================================================================
# VPC: provide vpc_id to use an existing VPC, or vpc_name + vpc_address_range to create new
# ================================================================
# vpc_id = "vpc-xxxxxxxx"
vpc_name          = "graphiant-vedge-devtest-vpc"
vpc_address_range = "10.0.0.0/16"

# cloud-init subnet (devtest only): provide subnet_cloud_init_id when using an existing VPC,
# or subnet_cloud_init_prefix to create new (new VPC only).
# subnet_cloud_init_id = "subnet-xxxxxxxx"
subnet_cloud_init_prefix = "10.0.0.0/24"

# mgmt subnet: provide subnet_mgmt_id to use existing, or subnet_mgmt_prefix to create new
# subnet_mgmt_id = "subnet-xxxxxxxx"
subnet_mgmt_prefix = "10.0.1.0/24"

# wan subnet: provide subnet_wan_id to use existing, or subnet_wan_prefix to create new
# subnet_wan_id = "subnet-xxxxxxxx"
subnet_wan_prefix = "10.0.2.0/24"

# lan subnet: provide subnet_lan_id to use existing, or subnet_lan_prefix to create new
# subnet_lan_id = "subnet-xxxxxxxx"
subnet_lan_prefix = "10.0.3.0/24"

# ================================================================
# Route Tables: provide route_table_*_id to use existing (e.g. from deploy_vpc), or leave empty to create new
# ================================================================
# route_table_wan_id = "rtb-xxxxxxxx"
# route_table_lan_id = "rtb-xxxxxxxx"

# =============================================================================
# Edge Onboarding Configuration Parameters (For Internal Use Only)
# =============================================================================
# onboarding_auth_url: Internal Graphiant OAuth authentication endpoint (devtest only)
onboarding_auth_url = ""

# onboarding_gateway: Internal Graphiant onboarding service hostname and port (devtest only)
onboarding_gateway = ""

# allowed_cidr: Public IPv4 allowed to connect to the devtest cloud-init SSH ports
allowed_cidr = "0.0.0.0/0"

# allowed_cidr_v6: Public IPv6 allowed to connect to the devtest cloud-init SSH ports
allowed_cidr_v6 = "::/0"

# ================================================================
# Test VM Configuration (Optional — attached to LAN subnet, default route via vEdge)
# ================================================================
# deploy_test_vm                    = true
# test_vm_name                      = "graphiant-vedge-devtest-test-vm"
# test_vm_instance_type             = "t3.micro"
# test_vm_key_name                  = "aws_ec2_ssh_keypair"   # EC2 key pair name (must exist in aws_region; see pre-requisite step 2). SSH in as the AMI's default user (e.g. 'admin' on Debian).
# test_vm_ami                       = ""   # (Optional) Configure only if you want the specific Debian AMI avialable for your region. Default, the latest Debain 13 is picked.

# By default, all ingress traffic is allowed to the test VM.
# When test_vm_enable_ssh_public_ip is true(which enables internet access to the test VM), it is recommended torestrict test_vm_ingress_allowed_subnets and test_vm_ssh_allowed_subnets to trusted CIDRs only.
# test_vm_enable_ssh_public_ip      = true
# test_vm_ingress_allowed_subnets   = ["0.0.0.0/0"]   # List of allowed CIDR blocks for the traffic ingressing to the test VM
# test_vm_ssh_allowed_subnets       = []   # List of CIDR blocks allowed for SSH access (only when test_vm_enable_ssh_public_ip = true) (eg : ["Your Laptop IP/32"])

# tags: Additional tags to apply
# tags = {
#   Owner = "team-network"
# }
