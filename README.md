# Graphiant-Playbooks

Playbooks for [Graphiant NaaS](https://www.graphiant.com). 

Refer [Graphiant Documentation](https://docs.graphiant.com/) to get started with our services.

Graphiant Playbooks are a collection of automated scripts that are designed to streamline 
and manage network infrastructure and policies. These playbooks are built using Python and 
Jinja2 templates to create and apply configurations for multiple Graphiant Edge Devices 
concurrently using GCSDK API. 

```sh
graphiant-playbooks/
├── LICENSE               # Project License file
├── README.md             # Project overview/documentation
├── requirements.txt      # Python dependencies
├── configs/              # Input YAML configuration files
├── libs/                 # Python libraries and modules required by the playbooks
├── templates/            # Jinja2 configuration template
├── test/                 # Sample Python test scripts and Config file 
└── scripts/              # Standalone scripts e.g. cloud-init interactive generator 

# configs/
Contains input configuration YAML files used to drive the execution of various playbooks.

# libs/
Includes all necessary Python libraries and helper modules required by the playbooks.

# logs/
Stores all log files generated during execution. Each run creates a timestamped log 
for auditability and debugging purposes.

# templates/
Contains Jinja2 config templates. These templates are dynamically rendered using the 
input from the configs/ directory to produce finalized configuration artifacts.

# test/
Contains Sample Python test files to validate the packages are installed correctly.

# scripts/
Standalone scripts e.g. cloud-init interactive generator.
```

## Pre-requisites

```sh
cd graphiant-playbooks/
```

### 1. Install Python 3.12+

### 2. Create and activate python virtual environment
```sh
python3 -m venv venv
source venv/bin/activate
```

### 3. Install the requirement packages
```sh
pip3 install -r requirements.txt
```

## Testing virtual environment

### 1. Update the PYTHONPATH env variable
```sh
export PYTHONPATH=$PYTHONPATH:$(pwd)
```

### 2. Enter the host URL and credentials under test.ini
```sh
[credentials]
username = username
password = password
[host]
url = https://api.graphiant.com
```

### 3. Run the sample test and verify the enterprise ID is fetched
```sh
python3 test/test.py
```

## Getting Started

### Step 1: Define Configurations

All input configs should be placed in the configs/ folder.

- sample_bgp_peering.yaml
- sample_interface_config.yaml
- sample_global_routing_policies.yaml

Note : Also refer the templates under templates/ dir for more details on the supported arguments.

### Step 2: Import and Use graphiant-playbooks
```sh
from libs.edge import Edge

host = "https://api.graphiant.com"
username = 'username'
password = 'password'
edge = Edge(base_url=host, username=username, password=password)
```
### Step 3: 
### To Configure the interfaces defined in sample_interface_config.yaml
```sh
Configure Interfaces: edge.configure_interfaces("sample_interface_config.yaml")
```

### To Deconfigure the interfaces defined in sample_interface_config.yaml
```sh
Deconfigure Interfaces: edge.deconfigure_interfaces("sample_interface_config.yaml")
```

### To configure the Global Prefixes, Routing Policies and BGP Peering
```sh
Configure Global Prefixes: edge.configure_global_prefix("sample_global_routing_policies.yaml")
Configure Global Routing Policies: edge.configure_global_bgp_routing_policies("sample_global_routing_policies.yaml")
Configure BGP Peering: edge.configure_bgp_peers("sample_bgp_peering.yaml")
```

### To unlink and deconfigure the BGP Peers
```sh
edge.detach_policies_from_bgp_peers("sample_bgp_peering.yaml")
edge.deconfigure_bgp_peers("sample_bgp_peering.yaml")
```

### To Deconfigure the Global BGP Routing Policies
```sh
edge.deconfigure_global_bgp_routing_policies("sample_global_routing_policies.yaml")

Note: Make sure the routing policies are not attached to any BGP peering configs before deconfigure
```

### To Deconfigure the Global Prefixes
```sh
edge.deconfigure_global_prefix("sample_global_routing_policies.yaml")

Note: Make sure the Global Prefixes are not attached before deconfigure
```

### Release Notes:
- Double Deletion Not Supported: Attempting to delete a configuration that does not exist is not supported.
- IPv6 BGP Peers : Only IPv4 BGP peer configurations are currently validated.
