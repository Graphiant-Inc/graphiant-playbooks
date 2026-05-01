# AWS Deploy vEdge Configuration
# Copy this file to terraform.tfvars and modify the values as needed

# action: Terraform action to perform ('create' or 'delete')
action = "create"

# ================================================================
# template_path: Path to the CloudFormation template file

# To create a new VPC and deploy the vEdge into it,
template_path = "templates/template-aws-vedge-production-new-vpc.yml"

# To deploy the vEdge into an existing VPC,
# template_path = "templates/template-aws-vedge-production-existing-vpc.yml"
# ================================================================

# aws_region: AWS region for CloudFormation stack deployment
aws_region = "us-east-1"

# stack_name: Unique CloudFormation stack identifier in AWS
stack_name = "graphiant-vedge-stack"

# image_id: AWS EC2 AMI ID for Recommended Graphiant-NOS Image
image_id = "ami-0b1e33617da2b2975"

# instance_name: Human-readable name tag for the EC2 instance
instance_name = "graphiant-vedge"

# vpc_name: Name tag for the VPC when using new-VPC templates (CloudFormation: VPCName)
vpc_name = "graphiant-vedge-vpc"

# vpc_address_range: The block of addresses that the newly deployed VPC owns
vpc_address_range = "10.0.0.0/16"

# instance_type: AWS EC2 instance size (CPU, memory, network capacity)
instance_type = "c5.xlarge"

# availability_zone: AWS data center location for resource deployment
availability_zone = "us-east-1a"

# token: Edge Authentication token for Onboarding the vEdge into a specific Enterprise within Graphiant Portal (Optional)
# token = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# ================================================================
# vEdge Deployment configuration parameters in an existing VPC
# Applicable when the template_path is template-aws-vedge-production-existing-vpc.yml
# ================================================================
# customer_vpc: The VPC-ID to deploy the vEdge instance into
customer_vpc = "vpc-xxxxxxx"

# customer_vpc_route_table: An existing route table id in the VPC to use for internet access
customer_vpc_route_table = "rtb-xxxxxxx"

# subnet_management: Subnet within the VPC to use for management access
subnet_mgmt = "subnet-xxxxxxx"

# subnet_wan: Subnet within the VPC to use for WAN access
subnet_wan = "subnet-xxxxxxx"

# subnet_lan: Subnet within the VPC to use for customer workload access
subnet_lan = "subnet-xxxxxxx"
