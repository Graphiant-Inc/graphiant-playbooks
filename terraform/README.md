# Graphiant Playbooks Terraform Infrastructure as Code

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](../LICENSE)
[![Terraform](https://img.shields.io/badge/terraform-1.3+-blue.svg)](https://www.terraform.io/)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)

Production-ready Terraform modules for deploying cloud networking infrastructure that seamlessly integrates with Graphiant Gateway devices.

## Description

This Terraform configuration provides modules to automate:
- Azure ExpressRoute circuit and gateway setup
- AWS Direct Connect gateway and virtual interface configuration
- GCP InterConnect VLAN attachments and BGP peering
- Cloud networking infrastructure (VPCs, subnets, routers)
- BGP peering configuration for all cloud providers

## Terraform Version Compatibility

This configuration requires **Terraform >= 1.3.0**.

Provider versions are specified in each module's `terraform {}` block and are installed automatically via `terraform init`.

## Prerequisites

| Requirement | Purpose |
|-------------|---------|
| **Terraform CLI** | Infrastructure provisioning (required for all providers) |
| **Cloud Account** | Active cloud subscription (Azure/AWS/GCP) |
| **Permissions** | Resource creation and management rights |

## Directory Structure

```
terraform/
├── edge_services/                 # Cloud edge service modules
│   └── aws/                       # AWS edge modules
│       ├── deploy_vedge/          # Deploy Graphiant vEdge
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   ├── outputs.tf
│       │   └── templates/
│       └── deploy_vpc/            # Deploy AWS VPC (for edge connectivity)
│           ├── main.tf
│           ├── variables.tf
│           ├── outputs.tf
│           └── templates/
│
├── gateway_services/              # Cloud gateway service modules
│   ├── azure/                    # Azure ExpressRoute modules
│   │   ├── main.tf              # Main Terraform configuration
│   │   ├── variables.tf         # Variable definitions
│   │   └── outputs.tf           # Output values
│   ├── aws/                     # AWS Direct Connect modules
│   │   ├── main.tf              # Main Terraform configuration
│   │   ├── variables.tf         # Variable definitions
│   │   └── outputs.tf          # Output values
│   └── gcp/                     # GCP InterConnect modules
│       ├── main.tf              # Main Terraform configuration
│       ├── variables.tf         # Variable definitions
│       └── outputs.tf           # Output values
│
└── configs/
    ├── edge_services/            # Edge service configuration files
    │   ├── aws_deploy_vedge_config.tfvars
    │   └── aws_deploy_vpc_config.tfvars
    └── gateway_services/        # Configuration files
        ├── azure_config.tfvars  # Azure variable configuration
        ├── aws_config.tfvars    # AWS variable configuration
        └── gcp_config.tfvars    # GCP variable configuration
```

## Installation

### Install Terraform (Required for all providers)

**macOS:**
```bash
brew install terraform
```

**Windows:**
```bash
choco install terraform
```

**Linux:**
```bash
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -
sudo apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
sudo apt-get update && sudo apt-get install terraform
```

### Verify Terraform Installation

```bash
terraform version  # Should be >= 1.3.0
```

---

# Common Sections

## Important: Terraform State File Management

> **⚠️ Important:** Customers are responsible for saving and managing their Terraform state file (`terraform.tfstate`). The state file contains sensitive information about your infrastructure and is required for Terraform to manage your resources.

**Best Practices:**
- **Backup your state file** regularly, especially before making changes
- **Store state files securely** - consider using remote state backends (S3, Azure Blob Storage, GCS, Terraform Cloud)
- **Never commit state files to version control** - they may contain sensitive data
- **Keep state files safe** - losing the state file can make it difficult to manage or destroy resources

## Terraform Commands

### Common Commands

```bash
# Initialize
terraform init

# Validate
terraform validate

# Plan
terraform plan -var-file="../../configs/gateway_services/<cloud>_config.tfvars" -out=tfplan

# Apply
terraform apply tfplan

# Show outputs
terraform output

# Destroy
terraform destroy -var-file="../../configs/gateway_services/<cloud>_config.tfvars"
```

### View Outputs

```bash
# All outputs
terraform output

# Specific output
terraform output vpc_id
terraform output cloud_router_id
```

---

# Edge Services 

# AWS

These modules deploy Graphiant edge components in AWS by launching AWS CloudFormation stacks.

**Workflow**
- **Create/update**: set `action = "create"` (default)
- **Delete**: set `action = "delete"` (uses the AWS CLI to delete the CloudFormation stack)

## AWS Deploy VPC (`edge_services/aws/deploy_vpc`)

1. Update the config file: `terraform/configs/edge_services/aws_deploy_vpc_config.tfvars`
2. Deploy:

```bash
cd terraform/edge_services/aws/deploy_vpc
terraform init
terraform plan -var-file="../../../configs/edge_services/aws_deploy_vpc_config.tfvars" -out=tfplan
terraform apply tfplan
```

3. Destroy:

```bash
cd terraform/edge_services/aws/deploy_vpc
terraform apply -var-file="../../../configs/edge_services/aws_deploy_vpc_config.tfvars" -var="action=delete"
```

## AWS Deploy vEdge (`edge_services/aws/deploy_vedge`)

1. Update the config file: `terraform/configs/edge_services/aws_deploy_vedge_config.tfvars`
   - Choose a CloudFormation template via `template_path`:
     - `templates/template-aws-vedge-production-new-vpc.yml`
     - `templates/template-aws-vedge-production-existing-vpc.yml`
     - Dev/test templates are for internal use
2. Deploy:

```bash
cd terraform/edge_services/aws/deploy_vedge
terraform init
terraform plan -var-file="../../../configs/edge_services/aws_deploy_vedge_config.tfvars" -out=tfplan
terraform apply tfplan
```

3. Destroy:

```bash
cd terraform/edge_services/aws/deploy_vedge
terraform apply -var-file="../../../configs/edge_services/aws_deploy_vedge_config.tfvars" -var="action=delete"
```

## Notes

- These modules create CloudFormation stacks and may shell out to `aws cloudformation delete-stack` for deletion.
- Ensure your AWS credentials and region are configured so the AWS CLI can delete the stack successfully.

---


# Gateway Services

# Azure ExpressRoute

## Azure Prerequisites

| Requirement | Purpose |
|-------------|---------|
| **Azure CLI** | Azure authentication and management |
| **Azure Subscription** | Active Azure subscription with appropriate permissions |

## Azure Installation

### Install Azure CLI

**macOS:**
```bash
brew install azure-cli
```

**Windows:**
```bash
choco install azure-cli
```

**Linux:**
```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### Verify Azure CLI Installation

```bash
az version
```

## Azure Authentication

```bash
az login
az account set --subscription "your-subscription-id"
az account show  # Verify
```

## Azure Quick Start

> **📚 Documentation:** For a step-by-step guide on creating the Graphiant Gateway Service for Azure, see the [Graphiant Documentation](https://docs.graphiant.com/docs/creating-the-graphiant-gateway-service-for-azure-graphiant-support). This guide provides step-by-step instructions to accomplish the same setup.

> **⚠️ Important:** Before running Terraform commands, you must request the Gateway Service in Graphiant Portal first, then update `terraform/configs/gateway_services/azure_config.tfvars` with your specific values. See the [Azure Configuration](#azure-configuration) section below.

> **💡 Tip:** This module supports using existing Resource Group and Virtual Network. If you have existing resources, set `use_existing_rg = true` and/or `use_existing_vnet = true` and provide the resource names.

**Step 1: Request Gateway Service in Graphiant Portal (Manual Step - Required)**

Before running Terraform, you need to request the Gateway Service in the Graphiant Portal. This will provision the ExpressRoute circuit.

1. Log into the **Graphiant Portal**
2. Navigate to **Gateway Services**:
   - From Home screen: Click **"Setup Gateway Service"** under Quickstart
   - Or: Click **"Services"** → **"Gateway"**
3. Click **"Create New"**
4. Select the Graphiant region corresponding to your Azure region
5. Choose **"Azure"** as the cloud provider
6. Configure Gateway details:
   - **Speed**: Desired speed for the connection
   - **Microsoft Peering VLAN ID**: Enter a VLAN ID between 101-200 (Note: This VLAN ID may change during provisioning based on availability)
   - **Routing Policy**: Provide the subnets of the ExpressRoute BGP neighbor (in the form of "169.254.___.___" /30 Link-Local Only CIDR) and any BGP policies you wish to apply
7. Click **"Next"** to review, then **"Confirm"** to submit the request

> **📚 Documentation:** For detailed step-by-step instructions, see the [Graphiant Documentation](https://docs.graphiant.com/docs/creating-the-graphiant-gateway-service-for-azure-graphiant-support) section on "Gateway Service for Azure Connectivity in the Graphiant Portal".

**Note:** After submitting the request, Graphiant Customer Support will contact you to discuss the details and assist with provisioning the Gateway Service. The ExpressRoute circuit will be provisioned.

**Step 2: Verify Existing Resources (if using existing Resource Group/VNet)**

If you're using existing Resource Group and/or Virtual Network, verify they exist:

```bash
# List Resource Groups
az group list --query "[].{Name:name, Location:location}" --output table

# List Virtual Networks
az network vnet list --query "[].{Name:name, ResourceGroup:resourceGroup, AddressSpace:addressSpace.addressPrefixes}" --output table

# Get specific VNet details
az network vnet show --resource-group <resource-group-name> --name <vnet-name> --query "{Name:name, AddressSpace:addressSpace.addressPrefixes, Subnets:subnets[*].{Name:name, AddressPrefix:addressPrefix}}" --output json
```

**Step 3: Update Configuration**

After Graphiant provisions the ExpressRoute circuit, update `terraform/configs/gateway_services/azure_config.tfvars` with your Azure-specific values:
- **Project name, Azure region**
- **Existing Resource Group name** (if `use_existing_rg = true`)
- **Existing Virtual Network name** (if `use_existing_vnet = true`)
- **ExpressRoute peering location, service provider, bandwidth**
- **BGP settings** (shared key, peer ASN)
- **VNet and subnet configuration** (if creating new VNet)

**Step 4: Deploy with Terraform**

```bash
cd terraform/gateway_services/azure

# Initialize Terraform
terraform init

# Review plan
terraform plan -var-file="../../configs/gateway_services/azure_config.tfvars" -out=tfplan

# Apply configuration
terraform apply tfplan
```

**Step 5: Provide Information to Graphiant Support (Manual Step - Required)**

After Terraform successfully creates the ExpressRoute Circuit and Gateway, you need to provide information to Graphiant Customer Support to complete the BGP peering configuration.

1. Get the **ExpressRoute Circuit Service Key** from Azure:
   - Go to Azure Portal → **ExpressRoute circuits**
   - Select the circuit created by Terraform
   - Copy the **Service Key** from the Overview page

2. Provide the following information to Graphiant Customer Support:
   - **ExpressRoute Circuit Service Key** (from Azure Portal)
   - **BGP peering configuration details** (if needed)
   - Any additional information requested by Graphiant Support

> **📚 Documentation:** For detailed information on what needs to be provided to Graphiant Support, see the [Graphiant Documentation](https://docs.graphiant.com/docs/creating-the-graphiant-gateway-service-for-azure-graphiant-support).

**Step 6: Graphiant Completes Provisioning**

After providing the information, Graphiant Customer Support will:
- Configure the ExpressRoute BGP private peering
- Establish the peering between Azure and the Graphiant Gateway
- Complete the provisioning of your Gateway Service

**Verification:**
- The **Gateway Status** in the Graphiant Portal will change to **"Live"**
- BGP peering will be established between Azure and Graphiant Core

> **Note:** The status of "Live" indicates that the Gateway has been provisioned. It does not reflect the current status of the connection.

**Important:** All manual steps (Steps 1 and 4) are required to complete the Gateway Service setup. The Terraform module creates the Azure infrastructure, but the Gateway Service request in Graphiant Portal and BGP peering configuration must be completed manually with Graphiant Support.

## What Azure Terraform Creates

**By default, this module can create new Resource Group and Virtual Network, or use your existing resources.** It will create:

- ExpressRoute Circuit (primary and optionally secondary for redundancy)
- ExpressRoute Gateway (Virtual Network Gateway)
- Virtual Hub (optional)
- ExpressRoute Connection
- Route Table with BGP propagation

**Optional resources** (if `use_existing_* = false`):
- Resource Group (if `use_existing_rg = false`)
- Virtual Network with subnets (if `use_existing_vnet = false`)
  - **Note:** If using existing VNet, ensure it has a GatewaySubnet (required for ExpressRoute Gateway)

**What Terraform does NOT create (requires manual steps):**
- Gateway Service request in Graphiant Portal (must be done first - Step 1)
- ExpressRoute Circuit provisioning (done by Graphiant after Gateway Service request)
- BGP peering configuration (completed by Graphiant Support after you provide the Service Key)

## Azure Configuration

> **⚠️ Required:** You must update `terraform/configs/gateway_services/azure_config.tfvars` with your specific values before running Terraform commands.

**Note:** The Azure module always creates a new Virtual Network. It does not support using existing VNets like the AWS and GCP modules.

**Required Configuration:**

```hcl
# Project Configuration
project_name = "your-project"
azure_region = "East US"
environment  = "dev"

# Network Configuration
vnet_address_space    = "10.0.0.0/16"
public_subnet_prefix  = "10.0.1.0/24"

# ExpressRoute Configuration
expressroute_peering_location = "Washington DC"  # Use: az network express-route list-service-providers
expressroute_service_provider = "PacketFabric"
expressroute_bandwidth = 50  # Valid: 50, 100, 200, 500, 1000, 2000, 5000, 10000
expressroute_sku = "Standard"  # Valid: Standard, Premium

# ExpressRoute Gateway
expressroute_gateway_sku = "Standard"  # Valid: Standard, HighPerformance, UltraPerformance
expressroute_gateway_scale_units = 1

# BGP Peering Configuration
expressroute_peer_asn = 30656  # Graphiant's ASN
expressroute_shared_key = "your-bgp-key"
expressroute_primary_peer_address_prefix = "169.254.50.0/30"  # Link-local /30 CIDR
expressroute_secondary_peer_address_prefix = "169.254.60.0/30"  # Link-local /30 CIDR
expressroute_vlan_id = 11
```

See the full configuration file (`terraform/configs/gateway_services/azure_config.tfvars`) for all available options.

## Azure Troubleshooting

**Authentication Errors:**
- Run `az login` and verify subscription
- Check subscription: `az account show`

**Common Issues:**

**ExpressRoute Circuit Not Provisioned:**
- Ensure you've requested the Gateway Service in Graphiant Portal first (Step 1)
- Contact Graphiant Support if the circuit is not appearing in Azure
- Verify the peering location matches your Azure region

**Gateway Subnet Issues:**
- If using existing VNet, ensure it has a GatewaySubnet (required for ExpressRoute Gateway)
- Ensure the Gateway Subnet is /27 or larger
- Verify the subnet name is exactly "GatewaySubnet"
- Check that there's sufficient address space in your VNet
- If GatewaySubnet doesn't exist in your existing VNet, you'll need to create it manually or use a new VNet

**BGP Peering Issues:**
- Ensure you've provided the ExpressRoute Circuit Service Key to Graphiant Support
- Verify BGP peering is configured correctly (coordinate with Graphiant Support)
- Check that the Gateway Status in Graphiant Portal shows "Live"

**Resource Creation Failures:**
- Verify Azure account permissions
- Check resource quotas/limits
- Verify network CIDR ranges don't conflict
- Ensure subscription has ExpressRoute provider registered

**Useful Commands:**
```bash
# Verify Azure subscription
az account show

# List Resource Groups
az group list --query "[].{Name:name, Location:location}" --output table

# List Virtual Networks
az network vnet list --query "[].{Name:name, ResourceGroup:resourceGroup, AddressSpace:addressSpace.addressPrefixes}" --output table

# Get VNet details including subnets
az network vnet show --resource-group <resource-group> --name <vnet-name> --query "{Name:name, AddressSpace:addressSpace.addressPrefixes, Subnets:subnets[*].{Name:name, AddressPrefix:addressPrefix}}" --output json

# Check if GatewaySubnet exists
az network vnet subnet show --resource-group <resource-group> --vnet-name <vnet-name> --name GatewaySubnet

# List available ExpressRoute service providers and peering locations
az network express-route list-service-providers

# Get ExpressRoute circuit details
az network express-route show --resource-group <resource-group> --name <circuit-name>

# Get ExpressRoute circuit service key
az network express-route show --resource-group <resource-group> --name <circuit-name> --query serviceKey -o tsv

# List ExpressRoute circuits
az network express-route list --resource-group <resource-group>

# Check Virtual Network Gateway status
az network vnet-gateway show --resource-group <resource-group> --name <gateway-name>
```

## Azure Cleanup

To destroy all Azure Terraform-managed resources:

```bash
cd terraform/gateway_services/azure
terraform destroy -var-file="../../configs/gateway_services/azure_config.tfvars"
```

**⚠️ Warning:** This command will permanently delete all created resources!

---

# AWS Direct Connect

## AWS Prerequisites

| Requirement | Purpose |
|-------------|---------|
| **AWS CLI** | AWS resource management |
| **AWS Account** | Active AWS account with appropriate permissions |

## AWS Installation

### Install AWS CLI

**macOS:**
```bash
brew install awscli
```

**Windows:**
```bash
choco install awscli
```

**Linux:**
```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install
```

### Verify AWS CLI Installation

```bash
aws --version
```

## AWS Authentication

```bash
aws configure
# Or use environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="your-region"
aws sts get-caller-identity  # Verify
```

## AWS Quick Start

> **📚 Documentation:** For a step-by-step guide on creating the Graphiant Gateway Service for AWS, see the [Graphiant Documentation](https://docs.graphiant.com/docs/creating-the-graphiant-gateway-service-for-aws-graphiant-support). This guide provides step-by-step instructions to accomplish the same setup.

> **⚠️ Important:** Before running Terraform commands, you must request the Gateway Service in Graphiant Portal first, then update `terraform/configs/gateway_services/aws_config.tfvars` with your specific values. See the [AWS Configuration](#aws-configuration) section below.

> **💡 Tip:** This module supports using existing VPC, subnet, and route table. If you have existing resources, set `use_existing_* = true` and provide the resource names.

**Step 1: Request Gateway Service in Graphiant Portal (Manual Step - Required)**

Before running Terraform, you need to request the Gateway Service in the Graphiant Portal. This will provision the Direct Connect connection that you'll accept in AWS.

1. Log into the **Graphiant Portal**
2. Navigate to **Gateway Services**:
   - From Home screen: Click **"Setup Gateway Service"** under Quickstart
   - Or: Click **"Services"** → **"Gateway"**
3. Click **"Create New"**
4. Select the Graphiant region corresponding to your AWS region
5. Choose **"Amazon Web Services"** as the cloud provider
6. Configure Gateway details:
   - **Speed**: Speed of the circuit from the Gateway to AWS
   - **LAN Segment**: The desired LAN segment to connect
   - **Amazon Account ID**: Enter your AWS Account ID where the connection will appear
   - **Description** (optional)
7. Click **"Next"** to review, then **"Confirm"** to submit the request

> **📚 Documentation:** For detailed step-by-step instructions, see the [Graphiant Documentation](https://docs.graphiant.com/docs/creating-the-graphiant-gateway-service-for-aws-graphiant-support) section on "Gateway Service for AWS Connectivity in the Graphiant Portal".

**Note:** After submitting the request, Graphiant Customer Support will schedule a call to discuss the details. The Direct Connect connection will be provisioned and will appear in your AWS account.

**Step 2: Verify Existing Resources (if using existing VPC/subnet)**

If you're using existing VPC, subnet, or route table, verify they exist:

```bash
# List VPCs
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0],CidrBlock]' --output table

# List subnets
aws ec2 describe-subnets --filters "Name=vpc-id,Values=vpc-xxxxx" --query 'Subnets[*].[SubnetId,Tags[?Key==`Name`].Value|[0],CidrBlock]' --output table

# List route tables
aws ec2 describe-route-tables --filters "Name=vpc-id,Values=vpc-xxxxx" --query 'RouteTables[*].[RouteTableId,Tags[?Key==`Name`].Value|[0]]' --output table
```

**Step 3: Update Configuration**

After Graphiant provisions the Direct Connect connection, you'll receive the connection ID. Update `terraform/configs/gateway_services/aws_config.tfvars` with your AWS-specific values:
- **Project name, region, environment**
- **Existing VPC/subnet/route table names** (if `use_existing_* = true`)
- **Direct Connect connection ID** (provided by Graphiant after Gateway Service request)
- **VLAN ID** (you'll get this when you accept the connection in Step 4)
- **BGP ASN, MTU settings**

**Step 4: Deploy**

**Note:** AWS Direct Connect requires a multi-step deployment process with manual steps between Terraform runs.

**Step 4a: Initial Terraform Deployment (skip_manual_steps = false)**
```bash
cd terraform/gateway_services/aws
terraform init
terraform plan -var-file="../../configs/gateway_services/aws_config.tfvars" -out=tfplan
terraform apply tfplan
```

**Step 4b - Manual Step: Accept Direct Connect Connection**

After Terraform creates the Transit Gateway and DirectConnect Gateway, you need to accept the Direct Connect connection:

1. Go to AWS Console → **Direct Connect** → **Connections**
2. Find the connection provisioned by Graphiant (it will show as "ordering")
3. Click on the connection and note the **VLAN ID** (you'll need this to update the config file)
4. Click **"Accept"** to accept the connection
5. A confirmation modal will appear - click **"Confirm"** to proceed
6. Wait for the connection state to change to "available" or "pending"
7. After acceptance, update `dx_connection_vlan` with the VLAN ID and set `skip_manual_steps = true` in `aws_config.tfvars`

**Step 4c: Final Terraform Deployment (skip_manual_steps = true)**
```bash
terraform plan -var-file="../../configs/gateway_services/aws_config.tfvars" -out=tfplan2
terraform apply tfplan2
```

**Step 4d - Manual Step: Associate Transit Gateway with DirectConnect Gateway**

After accepting the connection, you need to associate the Transit Gateway with the DirectConnect Gateway:

1. Go to AWS Console → **Direct Connect** → **Direct Connect Gateways**
2. Select the DirectConnect Gateway created by Terraform
3. Click on **"Gateway associations"** tab
4. Click **"Associate gateway"**
5. Configure the association:
   - **Gateways**: Select the Transit Gateway created by Terraform
   - **Allowed prefixes**: Enter the prefixes you want to advertise from AWS to Graphiant (e.g., `["10.0.0.0/16"]`)
6. Click **"Associate gateway"**

**Step 4e - Manual Step: Provide Information to Graphiant Support**

After the Virtual Interface is created, you need to provide the following information to Graphiant Customer Support:

1. Go to AWS Console → **Direct Connect** → **Virtual Interfaces**
2. Select the Transit Virtual Interface created by Terraform
3. Collect the following information:
   - **Amazon side ASN** (from Direct Connect Gateway)
   - **BGP Authentication Key** (if configured)
   - **Your router peer IP** (from the virtual interface)
   - **Amazon router peer IP** (from the virtual interface)
4. Provide this information to Graphiant Customer Support

> **💡 Tip:** You can download a sample configuration file from the Virtual Interface **Actions** menu → **"Sample configuration"** to get all required fields in one file.

**Step 4f: Graphiant Provisions the Gateway Service**

After providing the information, Graphiant Customer Support will enable the BGP Peer connection to the Graphiant Core and complete the provisioning of your Gateway Service. 

**Verification:**
- The AWS portal will show the BGP status as **"UP"** (green)
- The Gateway Status in the Graphiant Portal will change to **"Live"**

> **Note:** The status of "Live" indicates that the Gateway has been provisioned. It does not reflect the current status of the connection.

## What AWS Terraform Creates

**By default, this module can create new VPC and subnet, or use your existing resources.** It will create:

- Transit Gateway
- DirectConnect Gateway
- Transit Gateway Attachment (to VPC)
- Transit Virtual Interface
- Route Table with default route to Transit Gateway

**Optional resources** (if `use_existing_* = false`):
- VPC (if `use_existing_vpc = false`)
- Private Subnet (if `use_existing_subnet = false`)
- Route Table (if `use_existing_route_table = false`)
- VM Instance (if `deploy_vm = true`)

**What Terraform does NOT create (requires manual steps):**
- Gateway Service request in Graphiant Portal (must be done first - Step 1)
- Direct Connect Connection (provisioned by Graphiant after Gateway Service request)
- Transit Gateway Association with DirectConnect Gateway (Step 4d)
- BGP peering configuration (completed by Graphiant Support after you provide the required information)

## AWS Configuration

> **⚠️ Required:** You must update `terraform/configs/gateway_services/aws_config.tfvars` with your specific values before running Terraform commands.

### Using Existing VPC, Subnet, and Route Table (Optional)

**If you already have a VPC, subnet, and route table**, you can use them instead of creating new ones:

**Prerequisites:**
- Your VPC must already exist in the specified AWS region
- Your subnet must be in the specified VPC and Availability Zone
- Your route table must be associated with the subnet

**Configuration Example:**
```hcl
# Use existing resources
use_existing_vpc         = true
existing_vpc_name        = "your-vpc-name"  # Name of existing VPC

use_existing_subnet      = true
existing_subnet_name     = "your-subnet-name"  # Name of existing subnet

use_existing_route_table = true
existing_route_table_name = "your-route-table-name"  # Name of existing route table
```

**Important:** Make sure the resource names match exactly the `Name` tags of your existing resources in AWS.

### Creating New VPC and Subnet (Default)

If you need to create new VPC and subnet resources:

```hcl
# Create new resources
use_existing_vpc         = false
cidr_block               = "10.0.0.0/16"

use_existing_subnet      = false
private_subnet_cidr      = "10.0.1.0/24"
aws_az                   = "us-east-1a"

use_existing_route_table = false
```

### Required Configuration

Regardless of whether you use existing or new resources, you must configure:

```hcl
# Project Configuration
project_name = "your-project"
aws_region   = "us-east-1"

# Deployment Control
skip_manual_steps = false  # Set to true after accepting Direct Connect connection

# Transit Gateway
tgw_asn_number = 64512  # Must be different from DirectConnect Gateway ASN

# DirectConnect Gateway
dx_gateway_name = "graphiant-dx-gateway"
dx_gateway_asn  = 64513  # Must be different from Transit Gateway ASN
dxgw_allowed_prefixes = ["10.0.0.0/16"]  # Prefixes to advertise to Graphiant

# DirectConnect Connection (from Graphiant - provided after Gateway Service request)
dx_connection_id   = "dx-xxxxx"  # Provided by Graphiant after Step 1
dx_connection_vlan = 100         # VLAN ID from the connection (obtained when accepting connection in Step 4b)

# Transit Virtual Interface
dx_vif_name      = "graphiant-transit-vif"
customer_bgp_asn = 30656  # Graphiant's ASN
transit_vif_mtu   = 8500   # Valid values: 1500 or 8500 (jumbo frames)
```

See the full configuration file (`terraform/configs/gateway_services/aws_config.tfvars`) for all available options.

## AWS Troubleshooting

**Authentication Errors:**
- Run `aws configure` or set environment variables
- Verify credentials: `aws sts get-caller-identity`

**Common Issues:**

**VPC/Subnet/Route Table Not Found (when using existing resources):**
- Verify resource names match exactly the `Name` tags in AWS
- Ensure resources exist in the specified region
- Verify subnet is in the specified VPC
- Verify route table is associated with the subnet
- Check that you're using the correct AWS region

**Direct Connect Connection Issues:**
- Ensure you've requested the Gateway Service in Graphiant Portal first (Step 1)
- Verify `dx_connection_id` is correct (provided by Graphiant after Gateway Service request)
- Ensure connection is accepted in AWS Console before Step 4c
- Check connection state: `aws directconnect describe-connections --connection-id <id>`
- Verify the VLAN ID in config matches the connection's VLAN ID
- Wait for connection state to be "available" or "pending" before proceeding

**ASN Configuration Issues:**
- Ensure Direct Connect Gateway ASN is different from Transit Gateway ASN
- Verify customer BGP ASN is set to Graphiant's ASN (30656)
- Check that ASN values are within valid ranges

**BGP Peering Issues:**
- If BGP status is not "UP", verify you've provided all required information to Graphiant Support
- Ensure Virtual Interface is in "available" state
- Verify all information provided to Graphiant Support is correct

**Resource Creation Failures:**
- Verify AWS account permissions
- Check resource quotas/limits
- Ensure network CIDR ranges don't conflict (when creating new resources)

**Useful Commands:**
```bash
# Verify AWS credentials
aws sts get-caller-identity

# List VPCs
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0],CidrBlock]' --output table

# List subnets in a VPC
aws ec2 describe-subnets --filters "Name=vpc-id,Values=vpc-xxxxx" --query 'Subnets[*].[SubnetId,Tags[?Key==`Name`].Value|[0],CidrBlock,AvailabilityZone]' --output table

# List route tables
aws ec2 describe-route-tables --filters "Name=vpc-id,Values=vpc-xxxxx" --query 'RouteTables[*].[RouteTableId,Tags[?Key==`Name`].Value|[0]]' --output table

# Check Direct Connect connections
aws directconnect describe-connections --query 'connections[*].[connectionId,connectionState,vlan]' --output table

# Check Direct Connect virtual interfaces
aws directconnect describe-virtual-interfaces --query 'virtualInterfaces[*].[virtualInterfaceId,virtualInterfaceState,virtualInterfaceType]' --output table

# Get Transit Gateway details
aws ec2 describe-transit-gateways --query 'TransitGateways[*].[TransitGatewayId,State,AmazonSideAsn]' --output table

# Get Direct Connect Gateway details
aws directconnect describe-direct-connect-gateways --query 'directConnectGateways[*].[directConnectGatewayId,directConnectGatewayName,amazonSideAsn]' --output table
```

## AWS Cleanup

To destroy all AWS Terraform-managed resources:

```bash
cd terraform/gateway_services/aws
terraform destroy -var-file="../../configs/gateway_services/aws_config.tfvars"
```

**⚠️ Warning:** This command will permanently delete all created resources!

---

# GCP InterConnect

## GCP Prerequisites

| Requirement | Purpose |
|-------------|---------|
| **GCP Service Account Key** | GCP authentication (no CLI required) |
| **GCP Project** | Active GCP project with appropriate permissions |
| **Google Cloud SDK** | Optional - for easier authentication and verification |

## GCP Installation

### Install Google Cloud SDK (Optional)

GCP authentication primarily uses service account keys, but you can optionally install the Google Cloud SDK for easier authentication and verification.

**macOS:**
```bash
brew install --cask google-cloud-sdk
```

**Windows:**
```bash
choco install gcloudsdk
```

**Linux:**
```bash
# See https://cloud.google.com/sdk/docs/install for installation instructions
```

**Note:** The Google Cloud SDK is optional. Terraform can authenticate using service account keys without the CLI.

### Verify GCP Installation (Optional)

```bash
gcloud --version  # Only if you installed Google Cloud SDK
```

## GCP Authentication

The Terraform Google provider authenticates using service account keys. No CLI installation required.

```bash
# Set the service account key file path
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"

# Verify authentication (optional - requires gcloud CLI)
# gcloud auth activate-service-account --key-file=$GOOGLE_APPLICATION_CREDENTIALS
```

**Note:** You can also use Application Default Credentials if you have gcloud CLI installed, but it's not required.

## GCP Quick Start

> **📚 Documentation:** For a step-by-step guide on creating the Graphiant Gateway Service for GCP, see the [Graphiant Documentation](https://docs.graphiant.com/docs/creating-the-graphiant-gateway-service-for-google-cloud-platform-graphiant-support). This guide provides step-by-step instructions to accomplish the same setup.

> **⚠️ Important:** Before running Terraform commands, you must update `terraform/configs/gateway_services/gcp_config.tfvars` with your specific values. See the [GCP Configuration](#gcp-configuration) section below.

> **💡 Tip:** This module is designed to work with your existing VPC and subnet (default). Make sure you have the exact names of your existing VPC and subnet before configuring.

**Step 1: Verify Existing Resources (if using existing VPC/subnet)**

If you're using existing VPC and subnet (default), verify they exist:

```bash
# Optional: If you have gcloud CLI installed
gcloud compute networks list --project=your-project-id
gcloud compute networks subnets list --project=your-project-id --filter="region:us-central1"
```

**Step 2: Update Configuration**

Edit `terraform/configs/gateway_services/gcp_config.tfvars` with your GCP-specific values:
- **Project ID, region, zone**
- **Existing VPC name** (if `use_existing_vpc = true`)
- **Existing subnet name** (if `use_existing_subnet = true`)
- **Router ASN, VLAN names, MTU**

**Step 3: Deploy with Terraform**

```bash
cd terraform/gateway_services/gcp

# Initialize Terraform
terraform init

# Review plan
terraform plan -var-file="../../configs/gateway_services/gcp_config.tfvars" -out=tfplan

# Apply configuration
terraform apply tfplan
```

**Step 4: Get Pairing Keys from GCP (Manual Step - Required)**

After Terraform successfully creates the VLAN Attachments, you need to retrieve the Pairing Keys from GCP Console.

1. Go to GCP Console → **Interconnect** → **VLAN Attachments**
2. Select each VLAN Attachment created by Terraform (VLAN A and VLAN B)
3. **Note the Pairing Keys** displayed for each attachment
   - You'll need these Pairing Keys for the next step

**Step 5: Configure Gateway Service in Graphiant Portal (Manual Step - Required)**

1. Log into the **Graphiant Portal**
2. Navigate to **Gateway Services**:
   - From Home screen: Click **"Setup Gateway Service"** under Quickstart
   - Or: Click **"Services"** → **"Gateway"**
3. Click **"Create New"**
4. Select the Graphiant region corresponding to your GCP region
5. Choose **"Google Cloud Platform"** as the cloud provider
6. Configure Gateway details:
   - **LAN Segment**: Select your desired LAN segment
   - **Speed**: Set the circuit speed
   - **Peering Key**: Enter the Pairing Keys obtained from GCP (Step 4)
   - **Routing Policy**: Specify subnets and BGP policies if needed
7. Click **"Next"** to review, then **"Confirm"** to submit the request

> **📚 Documentation:** For detailed step-by-step instructions, see the [Graphiant Documentation](https://docs.graphiant.com/docs/creating-the-graphiant-gateway-service-for-google-cloud-platform-graphiant-support) section on "Configuring Gateway Service in Graphiant Portal".

**Step 6: Configure BGP Peering (Manual Step - Required)**

After configuring the Gateway Service in Graphiant Portal, configure BGP peering in GCP:

1. Go to GCP Console → **Interconnect** → **VLAN Attachments**
2. Select a VLAN Attachment (start with VLAN A)
3. Click **"Edit BGP Session"**
4. Configure BGP settings:
   - **Peer ASN**: Enter Graphiant's ASN: **30656**
   - Configure other BGP settings as needed
5. Click **"Save and Continue"**
6. Repeat for the second VLAN Attachment (VLAN B)

> **📚 Documentation:** For detailed step-by-step instructions on configuring Interconnect BGP Peering with Graphiant, see the [Graphiant Documentation](https://docs.graphiant.com/docs/creating-the-graphiant-gateway-service-for-google-cloud-platform-graphiant-support) section on "Configuring Interconnect BGP Peering with Graphiant".

**Step 7: Graphiant Completes Provisioning**

After you've completed the manual steps above, Graphiant Support will finalize the provisioning:

- The **Gateway Service status** in the Graphiant Portal will change to **"Live"**
- BGP peering will be established between GCP and Graphiant Core

> **Note:** The status of "Live" indicates that the Gateway has been provisioned. It does not reflect the current status of the connection.

**Important:** All manual steps (Steps 4-6) are required to complete the Gateway Service setup. The Terraform module creates the infrastructure with `admin_enabled = true`, so VLAN Attachments are automatically enabled. However, the Gateway Service configuration in Graphiant Portal and BGP peering must be completed manually.

## What GCP Terraform Creates

**By default, this module uses your existing VPC and subnet** (most common use case). It will create:

- Cloud Router (attached to your existing VPC)
- InterConnect VLAN Attachments (A and B) - **Note:** These are automatically enabled (`admin_enabled = true`) but will be in "Unpaired" state until configured in Graphiant Portal

**Optional resources** (if `use_existing_* = false`):
- VPC network (if `use_existing_vpc = false`)
- Subnet (if `use_existing_subnet = false`)
- VM Instance (if `use_existing_vm = false`)

**What Terraform does NOT create (requires manual steps):**
- Gateway Service configuration in Graphiant Portal
- BGP peering configuration (must be configured manually in GCP Console)

**Note:** VLAN Attachments are automatically enabled (`admin_enabled = true`) when created by Terraform, so no manual activation is required.

## GCP Configuration

> **⚠️ Required:** You must update `terraform/configs/gateway_services/gcp_config.tfvars` with your specific values before running Terraform commands.

### Using Existing VPC and Subnet (Recommended - Default)

**Most customers already have a VPC and subnet.** This is the default configuration. You only need to provide the names of your existing resources.

**Prerequisites:**
- Your VPC must already exist in the specified GCP project
- Your subnet must already exist in the specified region
- The subnet must be in the VPC you're using

**Configuration Example:**
```hcl
# GCP Project Configuration
project_id = "your-project-id"
region     = "us-central1"
zone       = "us-central1-a"

# Use existing VPC (default: true)
use_existing_vpc = true
vpc_name         = "your-existing-vpc-name"

# Use existing subnet (default: true)
use_existing_subnet = true
subnet_name         = "your-existing-subnet-name"

# Cloud Router Configuration
router_name = "graphiant-cloud-router"
router_asn  = 16550

# InterConnect Configuration
vlan_a_name = "vlan-attachment-a"
vlan_b_name = "vlan-attachment-b"
mtu         = 1440  # Valid values: 1440 or 1500
```

**Important:** Make sure the `vpc_name` and `subnet_name` match exactly the names of your existing resources in GCP.

### Creating New VPC and Subnet (Optional)

If you need to create new VPC and subnet resources:

```hcl
# Use new VPC
use_existing_vpc = false
vpc_name         = "new-vpc-name"

# Use new subnet
use_existing_subnet = false
subnet_name         = "new-subnet-name"
subnet_cidr         = "10.0.1.0/24"  # Required when creating new subnet
```

See the full configuration file (`terraform/configs/gateway_services/gcp_config.tfvars`) for all available options.

## GCP Troubleshooting

**Authentication Errors:**
- Verify `GOOGLE_APPLICATION_CREDENTIALS` environment variable points to valid service account key file
- Check service account permissions

**Common Issues:**

**VPC/Subnet Not Found (when using existing resources):**
- Verify `vpc_name` matches exactly the name of your existing VPC in GCP
- Verify `subnet_name` matches exactly the name of your existing subnet
- Ensure the subnet exists in the specified `region`
- Ensure the subnet is in the specified VPC
- Check that you're using the correct `project_id`
- Verify your service account has permissions to read VPC/subnet resources

**Resource Creation Failures:**
- Verify project ID and region are correct
- Check Cloud Router is ready before creating BGP peers
- Verify GCP project permissions
- Check resource quotas/limits
- Ensure network CIDR ranges don't conflict (when creating new resources)

**BGP Peering Not Working:**
- **Important:** After Terraform deployment, you must complete all manual steps (Steps 4-6 in Quick Start)
- Verify you've retrieved Pairing Keys from VLAN Attachments and configured Gateway Service in Graphiant Portal
- Verify BGP peering is configured with Graphiant's ASN (30656) in GCP Console
- Check that BGP session shows as established in both GCP Console and Graphiant Portal
- Verify Gateway Service status is "Live" in Graphiant Portal
- Ensure VLAN Attachments show `admin_enabled = true` (automatically set by Terraform)

**Useful Commands:**
```bash
# Verify service account key is set
echo $GOOGLE_APPLICATION_CREDENTIALS

# Optional: If you have gcloud CLI installed
# Verify existing VPC
gcloud compute networks list --project=your-project-id

# Verify existing subnet (replace with your region)
gcloud compute networks subnets list --project=your-project-id --filter="region:us-central1"

# Get subnet details (to verify it's in the correct VPC)
gcloud compute networks subnets describe subnet-name --region=us-central1 --project=your-project-id

# Verify project and region
gcloud config get-value project
```

## GCP Cleanup

To destroy all GCP Terraform-managed resources:

```bash
cd terraform/gateway_services/gcp
terraform destroy -var-file="../../configs/gateway_services/gcp_config.tfvars"
```

**⚠️ Warning:** This command will permanently delete all created resources!

---

## Additional Resources

- **Version Requirements**: Provider versions are specified in each module's `terraform {}` block
- [Terraform Azure Provider Documentation](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Terraform AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform Google Provider Documentation](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Azure ExpressRoute Documentation](https://docs.microsoft.com/en-us/azure/expressroute/)
- [AWS Direct Connect Documentation](https://docs.aws.amazon.com/directconnect/)
- [GCP InterConnect Documentation](https://cloud.google.com/network-connectivity/docs/interconnect)
- [Graphiant Playbooks Main Documentation](../README.md)

## Support

- **Documentation**: [docs.graphiant.com](https://docs.graphiant.com/)
- **Issues**: [GitHub Issues](https://github.com/Graphiant-Inc/graphiant-playbooks/issues)
- **Email**: [support@graphiant.com](mailto:support@graphiant.com)

## License

MIT License - see [LICENSE](../LICENSE) for details.
