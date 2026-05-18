# AWS Direct Connect Configuration
# Copy this file to terraform.tfvars and modify the values as needed

# Pre-requisite: 
# ============================================================================                                                                                                          
# 1. You MUST manually accept the Direct Connect connection in the aws Console before running terraform:
# 	1. Go to aws Console -> Direct Connect -> Connections                                                                                                                                 
# 	2. Find the connection with ID: ${var.dx_connection_id}                                                                                                                               
# 	3. Check the connection state:                                                                                                                                                        
#    		- If state is "ordering": Click "Accept" button                                                                                                                                    
#    		- If state is "requested": Connection may need approval from provider                                                                                                              
#    		- If state is "available": Connection is already accepted, proceed to Step 2                                                                                                       
# 	4. Wait until connection state changes to "available" or "pending"
# 	You can verify the connection state using:                                                                                                                                            
#   		aws directconnect describe-connections --connection-id ${var.dx_connection_id}   
#    	Once the connection state is available, Set dx_connection_id.
# 2. Create SSH Key pair for the accessing the EC2 Instance
# 	To Generate SSH Keypair from AWS cloudshell,
	  # aws ec2 create-key-pair --key-name aws_ec2_ssh_keypair --region us-east-1 --query 'KeyMaterial' --output text > aws_ec2_ssh_keypair_privatekey.pem
# 3. AWS regions and availability zones: 
#    To find the AWS region Id:	
#	https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html#available-regions
#    To find available availability zones for your region:
#     aws ec2 describe-availability-zones --region us-east-1
# 4. In case of LAG, Create the Direct Connect LAG manually and asoociate the connections to the LAG before running Terraform.
#    	Set dx_connection_id below to the LAG ID (dxlag-xxxxx) and dx_connection_vlan to the LAG VLAN.

# -----------------------
#    Project Configuration
# -----------------------
project_name = "your-project-name"
aws_region   = "us-east-1"
environment  = "prod"

# -----------------------
#    VPC Configuration
# -----------------------

# To deploy new VPC 
use_existing_vpc = false
cidr_block      = "10.10.0.0/16"
tenancy         = "default"

# Use Existing VPC
# use_existing_vpc      = true
# existing_vpc_name = "your-existing-vpc-name"

# -----------------------
#    Private Subnet
# -----------------------

# To create new Private Subnet
use_existing_subnet   = false
private_subnet_cidr = "10.10.0.0/24"
aws_az          = "us-east-1a"

# Use Existing Subnet
# use_existing_subnet = true
# existing_subnet_name = "your-existing-subnet-name"

# -----------------------
#    Route Table
# -----------------------

# To create new Route Table
use_existing_route_table   = false

# Use Existing Route Table
# use_existing_route_table = true
# existing_route_table_name = "your-existing-route-table-name"

# --------------------------------
#    VM Instance (Optional)
# --------------------------------
deploy_vm       = false  # Set to true to deploy a test VM
# ami             = "ami-0f9fc25dd2506cf6d"   # Amazon Linux 2023 (us-east-1) - update for your region
# instance_type   = "t3.micro"
# key_name        = "aws_ec2_ssh_keypair"
# ssh_allowed_cidr = "0.0.0.0/0"

# -----------------------
#    Transit Gateway
# -----------------------

tgw_description     = "transit gateway description"
tgw_asn_number      = 64512  # Amazon side ASN (must be different from DirectConnect Gateway ASN)
tgw_route_cidr      = "0.0.0.0/0"  # Destination CIDR for the TGW route. Use a specific CIDR to limit traffic (e.g. "10.0.0.0/8")

# ------------------------------
#    DirectConnect Gateway
# ------------------------------

dx_gateway_name     = "your-dx-gateway-name"
dx_gateway_asn      = 64513  # Amazon side ASN (must be different from Transit Gateway ASN)
dxgw_allowed_prefixes = ["10.10.0.0/16"]  # Prefixes to advertise from AWS to Graphiant

# ------------------------------
#    DirectConnect Connection
# ------------------------------
dx_connection_id = "dx-xxxxx" # Get the direct connect connection ID from AWS after the Graphiant connection is accepted

# -----------------------------------
#   DirectConnect Virtual Interfaces
# ------------------------------------

dx_vif_name        = "dx-virtual-interface-name"
dx_connection_vlan = 100      # VLAN tag for this VIF on the connection/LAG, should match the vlan on Graphiant Gateway Interface
customer_bgp_asn   = 30656   # Graphiant's ASN
transit_vif_mtu    = 8500    # Valid values: 1500 or 8500 (jumbo frames)
