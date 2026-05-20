# Graphiant Playbooks Terraform Infrastructure as Code

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](../LICENSE)
[![Terraform](https://img.shields.io/badge/terraform-1.3+-blue.svg)](https://www.terraform.io/)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)

Production-ready Terraform modules for deploying cloud networking infrastructure that seamlessly integrates with Graphiant Gateway devices.

## Description

This Terraform configuration provides modules to automate:

**Edge Services** — Deploy Graphiant Virtual Edge appliances in the cloud:
- AWS vEdge deployment and VPC provisioning with subnets, route tables and security groups
- Azure vEdge deployment and VNet provisioning with subnets, route tables and security groups

**Gateway Services** — Connect cloud networks to the Graphiant backbone:
- Azure ExpressRoute circuit and VNet configuration
- AWS Direct Connect gateway and VPC configuration
- GCP InterConnect VLAN attachments and VPC configuration

## Terraform Version Compatibility

This configuration requires **Terraform >= 1.14.0**.

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
│   ├── aws/                       # AWS edge modules
│   │   ├── deploy_vedge/          # Deploy Graphiant vEdge EC2
│   │   │   ├── configs/           # aws_deploy_vedge_config.tfvars, devtest tfvars
│   │   │   ├── main.tf
│   │   │   ├── variables.tf
│   │   │   └── outputs.tf
│   │   └── deploy_vpc/            # Deploy AWS VPC, subnets, route tables
│   │       ├── configs/           # aws_deploy_vpc_config.tfvars
│   │       ├── main.tf
│   │       ├── variables.tf
│   │       └── outputs.tf
│   └── azure/                     # Azure edge modules
│       ├── deploy_vedge/          # Deploy Graphiant vEdge VM
│       │   ├── configs/           # azure_deploy_vedge_config.tfvars, devtest tfvars
│       │   ├── main.tf
│       │   ├── variables.tf
│       │   └── outputs.tf
│       └── deploy_vnet/           # Deploy Azure VNet, subnets, route tables
│           ├── configs/           # azure_deploy_vnet_config.tfvars
│           ├── main.tf
│           ├── variables.tf
│           └── outputs.tf
│
└── gateway_services/              # Cloud gateway service modules
    ├── azure/                    # Azure ExpressRoute modules
    │   ├── configs/              # Configuration files
    │   │   └── azure_config.tfvars
    │   ├── main.tf              # Main Terraform configuration
    │   ├── variables.tf         # Variable definitions
    │   └── outputs.tf           # Output values
    ├── aws/                     # AWS Direct Connect modules
    │   ├── configs/             # Configuration files
    │   │   └── aws_config.tfvars
    │   ├── main.tf              # Main Terraform configuration
    │   ├── variables.tf         # Variable definitions
    │   └── outputs.tf          # Output values
    └── gcp/                     # GCP InterConnect modules
        ├── configs/              # Configuration files
        │   └── gcp_config.tfvars
        ├── main.tf              # Main Terraform configuration
        ├── variables.tf         # Variable definitions
        └── outputs.tf           # Output values
```

## Installation

### Install Terraform (Required for all providers)

For supported install methods, current commands, and all operating systems, refer to the official HashiCorp documentation: **[Install Terraform](https://developer.hashicorp.com/terraform/install)**.

**macOS** (example; if this differs from the docs, follow the link above):

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

**Windows** and **Linux**: use the official install guide above for package managers, binaries, and supported distributions.

### Verify Terraform Installation

```bash
terraform version  # Should be >= 1.14.0
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
terraform plan -var-file="config/<cloud>_config.tfvars" -out=tfplan

# Apply
terraform apply tfplan

# Show outputs
terraform output

# Destroy
terraform destroy -var-file="config/<cloud>_config.tfvars"
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

# AWS — Graphiant Virtual Edge

Two Terraform modules are provided:
- **`deploy_vpc`** — creates the networking layer only (VPC, IGW, mgmt/wan/lan subnets, mgmt/wan and lan route tables). Use this to pre-provision infrastructure before deploying the vEdge.
- **`deploy_vedge`** — deploys the Graphiant vEdge EC2 instance. It can either create a new VPC and networking (Option A), or deploy into an existing VPC (Option B) — such as one created by `deploy_vpc` or already present in your AWS account.

Two deployment modes are supported:
- **Production** — Use `edge_services/aws/deploy_vedge/configs/aws_deploy_vedge_config.tfvars`
- **Devtest** (Only for Internal Usage) - Use `edge_services/aws/deploy_vedge/configs/aws_deploy_vedge_devtest_config.tfvars`

### Prerequisites

#### Verify AWS CLI:

Configure the **AWS CLI** for the target account and region, then verify:

```bash
aws --version
aws sts get-caller-identity
```

#### Pre-requisite Setup:

1. **AWS regions and availability zones:**
   - To find the AWS region ID: https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html#available-regions
   - To find available availability zones for your region:
     ```bash
     aws ec2 describe-availability-zones --region us-east-1
     ```

2. **Subscribe to the Graphiant Virtual Edge AWS Marketplace listing** in your account (required for `marketplace_product_id` to resolve):
   https://aws.amazon.com/marketplace/pp/prodview-xngq36gyfhpv2
   
   **To get `marketplace_product_id` :**
   - Open the Marketplace product page and check AMI details: https://aws.amazon.com/marketplace/launch?ref_=aws_mp_pw&productId=ef19ce00-3544-4c76-af98-2001d39fdfd9
   - The product ID for Graphiant vEdge is `ef19ce00-3544-4c76-af98-2001d39fdfd9`
   - The marketplace_product_id for Graphiant vEdge is `prod-tjdlkbawxqsyg`

3. **(Only if you plan to launch a test VM)** Create an EC2 SSH key pair in the target region. From AWS CloudShell:
   ```bash
   aws ec2 create-key-pair --key-name aws_ec2_ssh_keypair --region us-east-1 \
     --query 'KeyMaterial' --output text > aws_ec2_ssh_keypair_privatekey.pem
   chmod 400 aws_ec2_ssh_keypair_privatekey.pem
   ```
   Then set `test_vm_key_name` to the key pair name.

4. **(Optional: Only if you plan to launch a test VM with a specific Debian AMI)** Find the Debian 13 AMI ID for your region and set as `test_vm_ami`:
   ```bash
   aws ec2 describe-images --owners 136693071363 \
     --filters "Name=name,Values=debian-13-amd64-*" "Name=state,Values=available" \
     --region us-east-1 \
     --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text
   ```
   If `test_vm_ami` is not set, Terraform will automatically discover the latest Debian 13 AMI for your region.


### Onboarding and local management UI

- Prefer onboarding with the **Graphiant Portal token** (`token` in tfvars) when you use token-based onboarding.
- If you are **not** using the token flow, onboard using the **onboarding URL** from the **serial console** or from the VM **local web UI**.
- To use the local web UI at `https://<mgmt-public-address>`, add an **inbound rule allowing HTTPS (TCP 443)** on the **mgmt** security group (`<vm_name>-mgmt-sg`) attached to the Graphiant local management interface. Production deployments deny all inbound by default.
- After the edge is onboarded, **lock down** the local web server using edge configuration as appropriate for your security policy.

### Option A: Deploy vEdge with a new VPC

Everything (VPC, IGW, subnets, route tables, SGs, NICs, EIPs, EC2 instance) is created in one step.

1. Edit `edge_services/aws/deploy_vedge/configs/aws_deploy_vedge_config.tfvars`:
   - `mode` — deployment mode (`production` or `devtest`)
   - `aws_region` / `availability_zone` — target AWS region and AZ
   - `project_name` — prefix used for default resource names (IGW, subnets, EIPs, SGs)
   - `vm_name` — Name tag for the vEdge EC2 instance
   - `instance_type` — EC2 instance type (see allowed values in `variables.tf`)
   - **AMI** — set exactly one of:
     - `image_id` — explicit AMI ID, or
     - `marketplace_product_id` (+ optional `marketplace_version`, default `"latest"`) — resolves the AMI via the AWS Marketplace SSM public parameter `/aws/service/marketplace/<product_id>/<version>`. Requires your account to be subscribed to the Graphiant Marketplace listing.
   - `token` — Graphiant Portal onboarding token
   - `vpc_name` / `vpc_address_range` — VPC name + CIDR for the new VPC
   - `subnet_mgmt_prefix`, `subnet_wan_prefix`, `subnet_lan_prefix` — subnet CIDRs within the VPC
   - **Test VM (optional)** — `deploy_test_vm`, `test_vm_name`, `test_vm_instance_type`, `test_vm_key_name`, `test_vm_ami`, `test_vm_ingress_allowed_subnets`, `test_vm_enable_ssh_public_ip`, `test_vm_ssh_allowed_subnets` (see [Optional: Test VM on LAN subnet](#optional-test-vm-on-lan-subnet))

2. Deploy:

```bash
cd terraform/edge_services/aws/deploy_vedge
terraform init
terraform plan -var-file="configs/aws_deploy_vedge_config.tfvars" -out=tfplan
terraform apply tfplan
```

### Option B: Deploy vEdge into an existing VPC

Use this when you already have a VPC, subnets, and route tables pre-existing in your AWS account.

#### Optional: To provision the new VPC, subnets and route tables first via `deploy_vpc`

```bash
cd terraform/edge_services/aws/deploy_vpc
terraform init
terraform plan -var-file="configs/aws_deploy_vpc_config.tfvars" -out=tfplan
terraform apply tfplan
terraform output    # capture vpc_id, subnet_*_id, route_table_*_id
```

#### Deploy the vEdge into the existing VPC

1. Edit `edge_services/aws/deploy_vedge/configs/aws_deploy_vedge_config.tfvars`:
   - `mode` — deployment mode (`production` or `devtest`)
   - `aws_region` / `availability_zone` — same region/AZ as the existing VPC
   - `project_name` — prefix used for default resource names (EIPs, SGs)
   - `vm_name` — Name tag for the vEdge EC2 instance
   - `instance_type` — EC2 instance type (see allowed values in `variables.tf`)
   - **AMI** — set exactly one of `image_id` or `marketplace_product_id` (+ optional `marketplace_version`) — same as Option A
   - `token` — Graphiant Portal onboarding token
   - `vpc_id` — existing VPC ID
   - `subnet_mgmt_id`, `subnet_wan_id`, `subnet_lan_id` — existing subnet IDs
   - `subnet_cloud_init_id` — required for **devtest** only
   - `route_table_lan_id` — existing LAN route table; a `0.0.0.0/0` route via the vEdge LAN ENI will be added to it
   - `route_table_wan_id` — existing WAN route table (the mgmt+wan subnets you supply must already be associated with an IGW-routed RT)
   - **Test VM (optional)** — `deploy_test_vm`, `test_vm_name`, `test_vm_instance_type`, `test_vm_key_name`, `test_vm_ami`, `test_vm_ingress_allowed_subnets`, `test_vm_enable_ssh_public_ip`, `test_vm_ssh_allowed_subnets` (see [Optional: Test VM on LAN subnet](#optional-test-vm-on-lan-subnet))

2. Deploy:

```bash
cd terraform/edge_services/aws/deploy_vedge
terraform init
terraform plan -var-file="configs/aws_deploy_vedge_config.tfvars" -out=tfplan
terraform apply tfplan
```

### Post-deployment: Configure the vEdge in Graphiant Portal

After the vEdge instance is deployed and onboarded:

1. Go to the **Graphiant Portal**
2. Navigate to **Configure** -> **Devices** -> select the vEdge
3. Update the following:
   - **Site Name** — assign the vEdge to a site
   - **Edge LAN Segment** — select the LAN segment for interface `GigabitEthernet0/7/0` for customer workload traffic
   - **IP Address** — set to the `lan_private_ip` output from Terraform (`terraform output lan_private_ip`)

### Optional: Test VM on LAN subnet

A Debian 13 test VM can be deployed on the LAN subnet to verify connectivity through the vEdge. The test VM is attached to the LAN subnet with all traffic routed through the vEdge by default. Optionally, you can allocate a public Elastic IP for SSH access from external sources.

**Configuration:**

```hcl
deploy_test_vm                  = true
test_vm_name                    = "graphiant-vedge-test-vm"
test_vm_instance_type           = "t3.micro"
test_vm_key_name                = "aws_ec2_ssh_keypair"    # EC2 key pair name (must exist in aws_region)
test_vm_ami                     = ""                       # Leave empty to auto-discover latest Debian 13
test_vm_ingress_allowed_subnets = ["0.0.0.0/0"]           # CIDR blocks allowed ingress to test VM (all protocols)
test_vm_enable_ssh_public_ip    = true                     # Allocate Elastic IP for public SSH access
test_vm_ssh_allowed_subnets     = ["YOUR_LAPTOP_IP/32"]    # List of CIDR blocks allowed SSH (only if public IP enabled; e.g., ["203.0.113.45/32"])
```

**Security Note:** When `test_vm_enable_ssh_public_ip = true`, it is recommended to restrict both `test_vm_ingress_allowed_subnets` and `test_vm_ssh_allowed_subnets` to trusted CIDR blocks only, rather than `0.0.0.0/0`.

**SSH access examples:**

- **Private IP (within VPC)**: 
  ```bash
  ssh -i ~/aws_ec2_ssh_keypair_privatekey.pem admin@<test_vm_private_ip>
  ```
  Retrieve with: `terraform output test_vm_private_ip`

- **Public IP (from external sources, if enabled)**: 
  ```bash
  ssh -i ~/aws_ec2_ssh_keypair_privatekey.pem admin@<test_vm_public_ip>
  ```
  Retrieve with: `terraform output test_vm_public_ip`

### Destroy

```bash
cd terraform/edge_services/aws/deploy_vedge
terraform destroy -var-file="configs/aws_deploy_vedge_config.tfvars"

# If deploy_vpc was used:
cd ../deploy_vpc
terraform destroy -var-file="configs/aws_deploy_vpc_config.tfvars"
```

Tear down `deploy_vedge` before `deploy_vpc` so nothing still references the VPC.

### Dev/test mode (internal use only)

Use `configs/aws_deploy_vedge_devtest_config.tfvars` with `mode = "devtest"`. This adds a cloud-init NIC + EIP for SSH access, opens TCP 22/443 on the mgmt SG from `allowed_cidr`/`allowed_cidr_v6`, and seeds a `cloud_init_username` user via cloud-init with `ssh_public_key` and `cloud_init_password`.

---

# Azure — Graphiant Virtual Edge

Two Terraform modules are provided:
- **`deploy_vnet`** — creates the networking layer only (Resource Group, VNet, subnets, route tables). Use this to pre-provision infrastructure before deploying the vEdge.
- **`deploy_vedge`** — deploys the Graphiant vEdge VM. It can either create its own VNet and networking (Option A), or deploy into an existing VNet (Option B) — such as one created by `deploy_vnet` or already present in your Azure subscription.

Two deployment modes are supported:
- **Production** — 3 NICs (mgmt, wan, lan), Marketplace image or Shared Image Gallery Image, no SSH access (onboard via token)
- **Devtest** (internal) — 4 NICs (+cloud-init for SSH), Shared Image Gallery image, SSH + password access

### Prerequisites

Install and authenticate the Azure CLI:

```bash
az version
az login
az account set --subscription "your-subscription-id"
az account show
```

### Find available image versions

```bash
# Marketplace (production) — list all versions, latest is last
az vm image list --publisher graphiantinc1622651764677 --offer graphiant-edge-vm --sku graphiant-edge-vm --all --query "[].version" -o tsv | sort -V

# Shared Image Gallery (devtest, internal)
az sig image-version list --gallery-name gnosimages --gallery-image-definition GNOS-dev --resource-group gnos-images --subscription 3aad0757-65c3-4f82-82c1-9bb05af8134c -o table
```

### Option A: Deploy vEdge with a new VNet

Everything (RG, VNet, subnets, route tables, NSGs, VM) is created in one step.

1. Edit `edge_services/azure/deploy_vedge/configs/azure_deploy_vedge_config.tfvars`:
   - `mode` — deployment mode (`production` or `devtest`)
   - `resource_group_name` — name for the new Azure resource group
   - `azure_region` — Azure region to deploy into (e.g. `eastus`)
   - `vm_name` — name for the vEdge virtual machine
   - `vm_size` — VM size (`Standard_DS3_v2`, `Standard_DS4_v2`, `Standard_F8s_v2`)
   - `image_version` — Marketplace image version (or `source_image_id` for Shared Image Gallery)
   - `ssh_public_key` — SSH public key (required by Azure)
   - `token` — Graphiant Portal onboarding token
   - `vnet_name` — name for the new virtual network
   - `vnet_address_space` — VNet CIDR block (e.g. `10.1.0.0/16`)
   - `subnet_mgmt_prefix`, `subnet_wan_prefix`, `subnet_lan_prefix` — subnet CIDRs within the VNet

2. Deploy:

```bash
cd terraform/edge_services/azure/deploy_vedge
terraform init
terraform plan -var-file="configs/azure_deploy_vedge_config.tfvars" -out=tfplan
terraform apply tfplan
```

### Option B: Deploy vEdge into an existing VNet

Use this when you already have a VNet, subnets, and route tables — either created by `deploy_vnet` or pre-existing in your Azure subscription.

1. Edit `edge_services/azure/deploy_vedge/configs/azure_deploy_vedge_config.tfvars`:
   - `mode` — deployment mode (`production` or `devtest`)
   - `resource_group_id` — existing resource group ID from Azure Portal
   - `vm_name` — name for the vEdge virtual machine
   - `vm_size` — VM size (`Standard_DS3_v2`, `Standard_DS4_v2`, `Standard_F8s_v2`)
   - `image_version` — Marketplace image version (or `source_image_id` for Shared Image Gallery)
   - `ssh_public_key` — SSH public key (required by Azure)
   - `token` — Graphiant Portal onboarding token
   - `vnet_id` — existing VNet ID
   - `subnet_mgmt_id` — existing mgmt subnet ID
   - `subnet_wan_id` — existing WAN subnet ID
   - `subnet_lan_id` — existing LAN subnet ID
   - `route_table_wan_id` — existing WAN route table ID (optional)
   - `route_table_lan_id` — existing LAN route table ID (optional)

2. Deploy the vEdge:

```bash
cd terraform/edge_services/azure/deploy_vedge
terraform init
terraform plan -var-file="configs/azure_deploy_vedge_config.tfvars" -out=tfplan
terraform apply tfplan
```

### Post-deployment: Configure the vEdge in Graphiant Portal

After the vEdge VM is deployed and onboarded:

1. Go to the **Graphiant Portal**
2. Navigate to **Configure** -> **Devices** -> select the vEdge
3. Update the following:
   - **Site Name** — assign the vEdge to a site
   - **Edge LAN Segment** — select the LAN segment for customer workload traffic
   - **IP Address** — set to the `lan_private_ip` output from Terraform (`terraform output lan_private_ip`)

### Optional: Test VM on LAN subnet

A Debian 12 test VM can be deployed on the LAN subnet to verify connectivity. It has a private IP only (no public IP) and a default route via the vEdge LAN interface.

```hcl
deploy_test_vm         = true
test_vm_name           = "graphiant-vedge-test-vm"
test_vm_size           = "Standard_B1s"
test_vm_admin_username = "azureuser"
test_vm_admin_password = "<password>"  # 12-123 chars, must meet 3 of 4: lowercase, uppercase, digit, special char
```

### Destroy

```bash
# Destroy vEdge
cd terraform/edge_services/azure/deploy_vedge
terraform destroy -var-file="configs/azure_deploy_vedge_config.tfvars"

```

### Dev/test mode (internal use only)

Use `configs/azure_deploy_vedge_devtest_config.tfvars` with `mode = "devtest"`.

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

> **💡 Tip:** This module supports using existing Resource Group and Virtual Network. If you have existing resources, set `use_existing_rg = true` and/or `use_existing_vnet = true` and provide the resource names.


## Azure Configuration

> **⚠️ Required:** You must update `terraform/gateway_services/azure/configs/azure_config.tfvars` with your specific values before running Terraform commands.

### Step 1: Deploy Azure resources (without ExpressRoute connection)

1. Update `terraform/gateway_services/azure/configs/azure_config.tfvars` and set:
   - `create_expressroute_connection = false`
2. Optional reference commands:
   - Azure regions: [Azure regions list](https://learn.microsoft.com/en-us/azure/reliability/regions-list)
   - PacketFabric ExpressRoute peering locations:

```bash
az network express-route list-service-providers --query "[?name=='PacketFabric'].{name:name, peeringLocations:peeringLocations}" -o json
```

3. Run Terraform:

```bash
cd graphiant-playbooks/terraform/gateway_services/azure
terraform init
terraform plan -var-file="config/azure_config.tfvars" -out=tfplan
terraform apply tfplan
```

### Step 2: Create Gateway Service request in Graphiant Portal

For detailed steps, see the [Graphiant Documentation](https://docs.graphiant.com/docs/creating-the-graphiant-gateway-service-for-azure-graphiant-support) section on "Gateway Service for Azure Connectivity in the Graphiant Portal".

### Step 3: Graphiant Support provisioning

Graphiant Customer Support configures the sub-interface, fabric, and BGP peering.

### Step 4: Create the ExpressRoute connection

After Graphiant confirms circuit provisioning, set `create_expressroute_connection = true` in `terraform/gateway_services/azure/configs/azure_config.tfvars`, then rerun:

```bash
terraform plan -var-file="config/azure_config.tfvars" -out=tfplan
terraform apply tfplan
```

**Verification:**
- The **Gateway Status** in the Graphiant Portal will change to **"Live"**
- BGP peering will be established between Azure and Graphiant Core

> **Note:** The status of "Live" indicates that the Gateway has been provisioned. It does not reflect the current status of the connection.

**Important:** All manual steps (Steps 2 and 3) are required to complete the Gateway Service setup. The Terraform module creates the Azure infrastructure, but the Gateway Service request in Graphiant Portal and BGP peering configuration must be completed manually with Graphiant Support.


## Azure Troubleshooting

**Common Issues:**
- Verify the peering location matches your Azure region
- Contact Graphiant Support for the express route Peering vlan(expressroute_vlan_id) to be used

**BGP Peering Issues:**
- Ensure you've provided the ExpressRoute Circuit Service Key to Graphiant Support
- Verify BGP peering is configured correctly (coordinate with Graphiant Support)
- Check that the Gateway Status in Graphiant Portal shows "Live"


## Azure Cleanup

To destroy all Azure Terraform-managed resources:

```bash
cd terraform/gateway_services/azure
terraform destroy -var-file="config/azure_config.tfvars"
```

**⚠️ Warning:** This command will permanently delete all created Azure resources!

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

> **⚠️ Important:** Before running Terraform commands, you must request the Gateway Service in Graphiant Portal first, then update `terraform/gateway_services/aws/configs/aws_config.tfvars` with your specific values. See the [AWS Configuration](#aws-configuration) section below.

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

**Step 2: Accept the Connection**

After Graphiant provisions the Direct Connect connection, you'll receive the connection request in AWS Portal.

To accept the Direct Connect Connection request and to get Direct Connect connection ID
1. Go to AWS Console → **Direct Connect** → **Connections**
2. Find the connection provisioned by Graphiant (it will show as "ordering")
3. Click on the connection and note the **VLAN ID** (you'll need this to update the config file)
4. Click **"Accept"** to accept the connection
5. A confirmation modal will appear - click **"Confirm"** to proceed
6. Wait for the connection state to change to "available" or "pending"
7. After acceptance, update `dx_connection_id` and `dx_connection_vlan` in `aws_config.tfvars`

> **Note:** If using LAG, create a LAG manually in AWS Console → **Direct Connect** → **LAGs**, and attach the Direct Connect connections to it. Set `dx_connection_id` to the LAG ID (`dxlag-xxxxx`) and `dx_connection_vlan` to the LAG VLAN in `aws_config.tfvars`. Enable MACsec as part of lag created if needed.

**Step 3: Update the Configuration**

Update `terraform/gateway_services/aws/configs/aws_config.tfvars` with your AWS-specific values:
- **Project name, region, environment**
- **Existing VPC/subnet/route table names** (if `use_existing_* = true`)
- **Direct Connect connection ID** (Direct Connect connection ID after the Connection is accepted)
- **VLAN ID** (VLAN used for the direct connection between Graphaint Gateway and AWS Direct Connect)
- **BGP ASN, MTU settings**


**Step 4: Deploy**

```bash
cd terraform/gateway_services/aws
terraform init
terraform plan -var-file="configs/aws_config.tfvars" -out=tfplan
terraform apply tfplan
```

**Step 5 - Provide BGP Peering Information to Graphiant Support**

After the Virtual Interface is created, you need to provide the following information to Graphiant Customer Support:

1. Go to AWS Console → **Direct Connect** → **Virtual Interfaces**
2. Select the Transit Virtual Interface created by Terraform
3. Collect the following information:
   - **Amazon side ASN** (from Direct Connect Gateway)
   - **BGP Authentication Key** (if configured)
   - **Your router peer IP** (from the virtual interface)
   - **Amazon router peer IP** (from the virtual interface)
4. Provide this information to Graphiant Customer Support

**Step 6: Graphiant Provisions the Gateway Service**

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
- Transit Gateway Association with DirectConnect Gateway
- Transit Virtual Interface
- Route Table with default route to Transit Gateway

**Optional resources** (if `use_existing_* = false`):
- VPC (if `use_existing_vpc = false`)
- Private Subnet (if `use_existing_subnet = false`)
- Route Table (if `use_existing_route_table = false`)
- VM Instance (if `deploy_vm = true`)

**Configuration Example:**
```hcl
# Use Existing VPC
use_existing_vpc         = true
existing_vpc_name        = "your-vpc-name"  # Name of existing VPC

# Use Existing Subnet
use_existing_subnet      = true
existing_subnet_name     = "your-subnet-name"  # Name of existing subnet

# Use Existing Route Table
use_existing_route_table = true
existing_route_table_name = "your-route-table-name"  # Name of existing route table
```

### Creating New VPC and Subnet (Default)

If you need to create new VPC and subnet resources:

```hcl
# To deploy new VPC 
use_existing_vpc = false
cidr_block      = "10.10.0.0/16"
tenancy         = "default"

# To create new Private Subnet
use_existing_subnet   = false
private_subnet_cidr = "10.10.0.0/24"
aws_az          = "us-east-1a"

# To create new Route Table
use_existing_route_table   = false
```

### Required Configuration

Regardless of whether you use existing or new resources, you must configure:

```hcl
# Project Configuration
project_name = "your-project-name"
aws_region   = "us-east-1"
environment  = "prod"

# Transit Gateway
tgw_description = "transit gateway description"
tgw_asn_number = 64512  # Must be different from DirectConnect Gateway ASN

# DirectConnect Gateway
dx_gateway_name = "your-dx-gateway-name"
dx_gateway_asn  = 64513  # Must be different from Transit Gateway ASN
dxgw_allowed_prefixes = ["10.10.0.0/16"]  # Prefixes to advertise to Graphiant

# DirectConnect Connection
dx_connection_id = "dx-xxxxx" # Get the direct connect connection ID from AWS after the Graphiant connection is accepted, Incase of LAG the dx_connection_id would be "dxlag-xxxxx"

# DirectConnect Virtual Interface
dx_vif_name      = "graphiant-transit-vif"
dx_connection_vlan = 100      # VLAN tag for this VIF on the connection/LAG, should match the vlan on Graphiant Gateway Interface
customer_bgp_asn = 30656  # Graphiant's ASN
transit_vif_mtu   = 8500   # Valid values: 1500 or 8500 (jumbo frames)

# VM Instance (Optional)
deploy_vm       = true  # Set to true to deploy a test VM
ami             = "ami-0f9fc25dd2506cf6d"   # Amazon Linux 2023 (us-east-1) - update for your region
instance_type   = "t3.micro"
key_name        = "aws_ec2_ssh_keypair"
ssh_allowed_cidr = "0.0.0.0/0"
```

> **Note:** To Generate SSH Keypair from AWS cloudshell, 
```bash
aws ec2 create-key-pair --key-name aws_ec2_ssh_keypair --region us-east-1 --query 'KeyMaterial' --output text > aws_ec2_ssh_keypair_privatekey.pem
```

See the full configuration file (`terraform/gateway_services/aws/configs/aws_config.tfvars`) for all available options.

## AWS Cleanup

To destroy all AWS Terraform-managed resources:

```bash
cd terraform/gateway_services/aws
terraform destroy -var-file="configs/aws_config.tfvars"
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

> **⚠️ Important:** Before running Terraform commands, you must update `terraform/gateway_services/gcp/configs/gcp_config.tfvars` with your specific values. See the [GCP Configuration](#gcp-configuration) section below.

> **💡 Tip:** This module is designed to work with your existing VPC and subnet (default). Make sure you have the exact names of your existing VPC and subnet before configuring.

**Step 1: Verify Existing Resources (if using existing VPC/subnet)**

If you're using existing VPC and subnet (default), verify they exist:

```bash
# Optional: If you have gcloud CLI installed
gcloud compute networks list --project=your-project-id
gcloud compute networks subnets list --project=your-project-id --filter="region:us-central1"
```

**Step 2: Update Configuration**

Edit `terraform/gateway_services/gcp/configs/gcp_config.tfvars` with your GCP-specific values:
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
terraform plan -var-file="config/gcp_config.tfvars" -out=tfplan

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

> **⚠️ Required:** You must update `terraform/gateway_services/gcp/configs/gcp_config.tfvars` with your specific values before running Terraform commands.

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

See the full configuration file (`terraform/gateway_services/gcp/configs/gcp_config.tfvars`) for all available options.

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
terraform destroy -var-file="config/gcp_config.tfvars"
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
