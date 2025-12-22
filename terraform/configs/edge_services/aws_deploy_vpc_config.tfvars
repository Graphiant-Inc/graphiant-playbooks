# AWS Deploy vEdge Configuration
# Copy this file to terraform.tfvars and modify the values as needed

# action: Terraform action to perform ('create' or 'delete')
action = "create"

# mode: Deployment mode ('production' or 'devtest'(Internal Use Only))
mode = "production"

# template_path: Path to the CloudFormation template file
template_path = "templates/template-aws-vpc.yml"

# aws_region: AWS region for CloudFormation stack deployment
aws_region = "us-east-1"

# availability_zone: AWS data center location for resource deployment
availability_zone = "us-east-1a"

# vpc_address_range: The block of addresses that the deployed VPC owns
vpc_address_range = "10.0.0.0/16"

# stack_name: Unique CloudFormation stack identifier in AWS
stack_name = "graphiant-vpc"