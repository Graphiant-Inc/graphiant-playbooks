# KVM Deploy vEdge Configuration - Production
#
# Only image_source and token are required. Everything below them has a working
# default; see the KVM section of terraform/README.md for the full list and for
# hypervisor prerequisites (libvirt, OVMF, swtpm, xsltproc).

# =============================================================================
# Required
# =============================================================================
# image_source: path or URL to the GNOS qcow2 from Graphiant support. Must be a
# production image - the image decides which GNOS build boots, not `mode`.
image_source = ""

# token: onboarding token for your Enterprise in the Graphiant Portal
token = ""

# =============================================================================
# Networking
#
# NIC order presented to GNOS in production:
#
#   wan1, local-mgmt, wan2..wanN, lan1..lanN
#
# NIC 0 is your first ISP uplink - the interface used to onboard. Production
# GNOS images have no kernel-managed interface, so there is no mgmt NIC here;
# mgmt_bridge is devtest-only and must stay unset.
#
# Name a host bridge to put an interface on your existing network, or leave it
# empty and this module creates a libvirt network for it. Check what you have
# with: ip link show type bridge
# =============================================================================
wan_bridges = []            # e.g. ["br-wan"], or ["br-wan", "br-wan2"] for dual-WAN
lan_bridge  = ""            # shared by all LAN interfaces
lan_count   = 1

# =============================================================================
# Sizing
# =============================================================================
vcpus        = 4
memory_mb    = 8192
disk_size_gb = 20
storage_pool = "default"    # must be a pool libvirt can read; see README

# =============================================================================
# Optional
# =============================================================================
# vm_name = "graphiant-vedge"

# Hypervisor paths — override on RHEL-family hosts, where OVMF lives in
# /usr/share/edk2/ovmf/ rather than /usr/share/OVMF/
# uefi_loader_path         = "/usr/share/OVMF/OVMF_CODE.fd"
# uefi_nvram_template_path = "/usr/share/OVMF/OVMF_VARS.fd"
# nvram_dir                = "/var/lib/libvirt/qemu/nvram"

# Keep the VNC console on loopback and reach it over an SSH tunnel.
vnc_listen_address = "127.0.0.1"

# Test VM on the LAN, to verify traffic flows through the vEdge. Deploy after
# the edge has onboarded: test_vm_gateway is the vEdge LAN address from the Portal.
# deploy_test_vm         = true
# test_vm_ip_cidr        = "192.168.100.10/24"
# test_vm_gateway        = "192.168.100.1"
# test_vm_password       = ""
# test_vm_ssh_public_key = ""
