# KVM Deploy vEdge Configuration - Devtest mode (Internal Use Only)
#
# Devtest differs from production in three ways:
#   - cloud-init creates an SSH user
#   - cloud-init carries the onboarding endpoints, which you must set
#   - a kernel-managed mgmt NIC is attached, so the interface order gains a
#     leading `mgmt` and NIC 0 is no longer the first ISP WAN
#
# It requires a devtest GNOS image; the image decides which build boots, not
# this setting. See the KVM section of terraform/README.md for prerequisites.

mode        = "devtest"
libvirt_uri = "qemu:///system"
vm_name     = "graphiant-vedge-devtest"

# =============================================================================
# Required
# =============================================================================
# image_source: path or URL to a devtest GNOS qcow2. Set base_volume_id instead
# to back onto an image already imported by an earlier deployment, which is much
# faster when redeploying several edges.
image_source = ""
# base_volume_id = ""

# token: Edge Authentication token for onboarding into a specific Enterprise
token = ""

# =============================================================================
# Cloud-init user (devtest only)
# =============================================================================
ssh_public_key      = ""
cloud_init_username = "gnos"
cloud_init_password = ""

# =============================================================================
# Onboarding endpoints (devtest only) - both required
#
# Set these to the environment you are onboarding to.
# =============================================================================
onboarding_auth_url = ""
onboarding_gateway  = ""

# =============================================================================
# Networking
#
# NIC order presented to GNOS in devtest:
#
#   mgmt, wan1, local-mgmt, wan2..wanN, lan1..lanN
#
# Name a host bridge to put an interface on an existing network, or leave it
# empty and this module creates a libvirt network for it. Check what exists
# with: ip link show type bridge
# =============================================================================
mgmt_bridge = ""            # kernel-managed management interface
wan_bridges = []            # e.g. ["br-wan"], or two entries for dual-WAN
lan_bridge  = ""            # shared by all LAN interfaces
lan_count   = 1

# =============================================================================
# Sizing
# =============================================================================
vcpus        = 4
memory_mb    = 8192
disk_size_gb = 20
storage_pool = "default"

# Expose VNC beyond loopback only on a trusted management network.
vnc_listen_address = "127.0.0.1"
