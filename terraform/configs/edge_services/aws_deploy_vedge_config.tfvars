# AWS Deploy vEdge Configuration
# Copy this file to terraform.tfvars and modify the values as needed

# action: Terraform action to perform ('create' or 'delete')
action = "create"

# mode: Deployment mode ('production' or 'devtest'(Internal Use Only))
mode = "production"

# template_path: Path to the CloudFormation template file
# ================================================================
# To create a new VPC and deploy the vEdge into it,
# For Production mode : template-aws-vedge-production-new-vpc.yml
# For Devtest mode(Internal Use Only) : template-aws-vedge-devtest-new-vpc.yml
# ================================================================
# To deploy the vEdge into an existing VPC,
# For Production mode : template-aws-vedge-production-existing-vpc.yml
# For Devtest mode(Internal Use Only) : template-aws-vedge-devtest-existing-vpc.yml
# ================================================================
template_path = "templates/template-aws-vedge-production-existing-vpc.yml"

# aws_region: AWS region for CloudFormation stack deployment
aws_region = "us-east-1"

# stack_name: Unique CloudFormation stack identifier in AWS
stack_name = "graphiant-vedge-stack"

# image_id: AWS EC2 AMI ID for Recommended Graphiant-NOS Image
image_id = "ami-0bbb585f10c4ef72d"

# instance_name: Human-readable name tag for the EC2 instance
instance_name = "graphiant-vedge"

# instance_type: AWS EC2 instance size (CPU, memory, network capacity)
# Recommended values: production: c5.large, devtest(Internal Use Only): c5.xlarge
instance_type = "c5.xlarge"

# allowed_cidr : Remote Public /32 IPv4 address allowed to SSH into vEdge instance (Internal Use Only)
allowed_cidr = "127.0.0.1/32"

# allowed_cidr_v6: Public /128 IPv6 address allowed to SSH into vEdge instance (Internal Use Only)
allowed_cidr_v6 = "::1/128"

# availability_zone: AWS data center location for resource deployment
availability_zone = "us-east-1a"

# token: Edge Authentication token for Onboarding the vEdge into a specific Enterprise within Graphiant Portal
token = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# ================================================================
# vEdge Deployment configuration parameters in an existing VPC
# Applicable when the template_path is template-aws-vedge-production-existing-vpc.yml
# or template-aws-vedge-devtest-existing-vpc.yml
# ================================================================
# customer_vpc: The VPC-ID to deploy the vEdge instance into
customer_vpc = "vpc-xxxxxxx"

# customer_vpc_route_table: An existing route table id in the VPC to use for internet access
customer_vpc_route_table = "rtb-xxxxxxx"

# subnet_cloud_init: Subnet within the VPC to use for ssh access (Applicable for devtest mode, Internal Use only)
subnet_cloud_init = "subnet-xxxxxxx"

# subnet_management: Subnet within the VPC to use for management access
subnet_management = "subnet-xxxxxxx"

# subnet_wan: Subnet within the VPC to use for WAN access
subnet_wan = "subnet-xxxxxxx"

# subnet_lan: Subnet within the VPC to use for customer workload access
subnet_lan = "subnet-xxxxxxx"

# =============================================================================
# Edge Onboarding Configuration Parameters (For Internal Use Only)
# =============================================================================

# onboarding_auth_url: Graphiant OAuth authentication endpoint (Applicable for devtest mode only)
# For Tisiphone env: onboarding_auth_url = "https://api.tisiphone.graphiant.io/v1/devices/oauth"
# For Megaera env: onboarding_auth_url = "https://api.megaera.graphiant.io/v1/devices/oauth"
# For Systest env: onboarding_auth_url = "https://api.test.graphiant.io/v1/devices/oauth"

# onboarding_gateway: Graphiant onboarding service hostname and port (Applicable for devtest mode only)
# For Tisiphone env: onboarding_gateway = "onboarding-gateway.tisiphone.graphiant.io:16000"
# For Megaera env: onboarding_gateway = "onboarding-gateway.megaera.graphiant.io:16000"
# For Systest env: onboarding_gateway = "onboarding-gateway.test.graphiant.io:16000"

# ssh_public_key: SSH public key for accessing the vedge (Applicable for devtest mode only)
# ssh_public_key = "ssh-rsa xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

