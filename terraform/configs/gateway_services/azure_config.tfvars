# Azure ExpressRoute Configuration
# Copy this file to terraform.tfvars and modify the values as needed

# -----------------------
#    Azure Configuration
# -----------------------
# azure_region :To get Azure region : https://learn.microsoft.com/en-us/azure/reliability/regions-list 
azure_region = "East US"

# -----------------------
#    Environment Configuration
# -----------------------
environment   = "dev"

# project_name : All the resources created in this project will have project_name as prefix
project_name  = "your-project" 

# -----------------------
#    Network Configuration
# -----------------------
# use_existing_rg : Use existing Resource Group (set to true to use existing, false to create new)
use_existing_rg = false
# rg_name : Name of the Resource Group (used for both creating new or referencing existing)
# If use_existing_rg = true, this must be the name of an existing Resource Group
# If use_existing_rg = false, this will be used as the name for the new Resource Group (or leave null to auto-generate)
rg_name = null  # e.g., "your-resource-group-name"

# use_existing_vnet : Use existing Virtual Network (set to true to use existing, false to create new)
use_existing_vnet = false
# vnet_name : Name of the Virtual Network (used for both creating new or referencing existing)
# If use_existing_vnet = true, this must be the name of an existing VNet
# If use_existing_vnet = false, this will be used as the name for the new VNet (or leave null to auto-generate)
vnet_name = null  # e.g., "your-vnet-name"

# -----------------------
#    Virtual Hub Configuration
# -----------------------
virtual_hub_address_prefix    = "10.0.0.0/24"

# -----------------------
#    Virtual Network Configuration
# -----------------------
vnet_address_prefix    = "10.0.1.0/24"
vnet_public_address_prefix  = "10.0.1.0/28"
vnet_gateway_address_prefixes = ["10.0.1.16/28"]

# -----------------------
#    ExpressRoute Configuration
# -----------------------
enable_expressroute = true
expressroute_sku = "Standard"  # Valid values: Standard, Premium
expressroute_family = "MeteredData"  # Valid values: MeteredData, UnlimitedData
expressroute_bandwidth = 50  # Valid values: 50, 100, 200, 500, 1000, 2000, 5000, 10000
# expressroute_peering_location : Use the below command to see available Packet Fabric peering locations
# az network express-route list-service-providers --query "[?name=='PacketFabric'].{name:name, peeringLocations:peeringLocations}" -o json
expressroute_peering_location = "Washington DC"
expressroute_service_provider = "PacketFabric"
expressroute_allow_classic_operations = false

# -----------------------
#    ExpressRoute Gateway Configuration
# -----------------------
expressroute_gateway_scale_units = 1

# -----------------------
#    Secondary ExpressRoute (Optional - for redundancy)
# -----------------------
expressroute_secondary_peering_location = ""  # Leave empty to disable secondary circuit
expressroute_secondary_bandwidth = 50
expressroute_secondary_service_provider = "PacketFabric"

# -----------------------
#    ExpressRoute Peering Configuration
# -----------------------
expressroute_shared_key = ""  # BGP authentication key
expressroute_peer_asn = 30656  # Graphiant's ASN
expressroute_primary_peer_address_prefix = "169.254.50.0/30"  # Link-local /30 CIDR
expressroute_secondary_peer_address_prefix = "169.254.60.0/30"  # Link-local /30 CIDR
# expressroute_vlan_id : Contact Graphiant Customer Support to get the VLAN ID allocated for the ExpressRoute circuit.
expressroute_vlan_id = 11

# -----------------------
#    ExpressRoute Connection
# -----------------------
# create_expressroute_connection : Set to false for the initial terraform apply. This creates all Azure resources except the ExpressRoute connection.
# Once you have expressroute_circuit_service_key, Create the Gateway Service request in Graphiant Portal and share the service key.
# After Graphiant provisions the Packet Fabric, set create_expressroute_connection to true and run terraform again to create the ExpressRoute connection.
create_expressroute_connection = false

# -----------------------
#    Route Table Configuration
# -----------------------
route_table_disable_bgp_propagation = false
route_table_default_route = "0.0.0.0/0"

# -----------------------
#    VM Configuration (Optional - for E2E Testing)
# -----------------------
deploy_test_vm = false  # Set to true to deploy a test VM
# vm_size = "Standard_B1s"
# vm_admin_username = "azureuser"
# vm_ssh_public_key = ""  # Replace with your SSH public key
# vnet_vm_address_prefix = "10.0.1.32/28" # Address space from vnet_address_prefix for VM subnet
