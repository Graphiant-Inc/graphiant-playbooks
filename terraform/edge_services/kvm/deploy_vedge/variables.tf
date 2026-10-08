# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------
variable "libvirt_uri" {
  description = "libvirt connection URI. Use 'qemu:///system' when Terraform runs on the hypervisor, or 'qemu+ssh://<user>@<host>/system' for a remote KVM host. Note the GNOS image at image_source is read by whichever machine runs Terraform."
  type        = string
  default     = "qemu:///system"
}

variable "vm_name" {
  description = "libvirt domain name for the vEdge, also used to name its volumes and networks"
  type        = string
  default     = "graphiant-vedge"
}

variable "vcpus" {
  description = "Number of vCPUs assigned to the vEdge"
  type        = number
  default     = 4

  validation {
    condition     = var.vcpus >= 2
    error_message = "The Graphiant vEdge requires at least 2 vCPUs."
  }
}

variable "memory_mb" {
  description = "Memory assigned to the vEdge, in MiB"
  type        = number
  default     = 8192

  validation {
    condition     = var.memory_mb >= 4096
    error_message = "The Graphiant vEdge requires at least 4096 MiB of memory."
  }
}

variable "disk_size_gb" {
  description = "Size of the vEdge qcow2 overlay disk, in GiB. Must be at least as large as the GNOS base image."
  type        = number
  default     = 20
}

variable "storage_pool" {
  description = "libvirt storage pool used for the base image, overlay disk and cloud-init ISO"
  type        = string
  default     = "default"
}

variable "graphnos_role" {
  description = "GNOS device role announced in cloud-init: 'cpe' for an edge, 'gateway' for a gateway."
  type        = string
  default     = "cpe"

  validation {
    condition     = contains(["cpe", "gateway"], var.graphnos_role)
    error_message = "graphnos_role must be either 'cpe' or 'gateway'."
  }
}

variable "token" {
  description = "Graphiant vEdge onboarding authentication token"
  type        = string
  sensitive   = true
  default     = ""
}

# -----------------------------------------------------------------------------
# Image — set exactly one of these
# -----------------------------------------------------------------------------
variable "image_source" {
  description = "Path or URL to the GNOS qcow2 image, imported as a base volume. Ignored when base_volume_id is set."
  type        = string
  default     = ""
}

variable "base_volume_id" {
  description = "ID of an already-imported GNOS base volume to back the vEdge disk. Set this to share one base image across several vEdge deployments instead of re-importing the qcow2."
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Domain hardware — defaults match the GNOS boot requirements
# -----------------------------------------------------------------------------
variable "machine_type" {
  description = "QEMU machine type. GNOS is validated on q35."
  type        = string
  default     = "q35"
}

variable "cpu_mode" {
  description = "libvirt CPU mode. host-passthrough is required for the vEdge dataplane to use host CPU features."
  type        = string
  default     = "host-passthrough"
}

variable "uefi_loader_path" {
  description = "Path on the hypervisor to the OVMF UEFI firmware code. GNOS boots via UEFI, not SeaBIOS. Debian/Ubuntu use /usr/share/OVMF/OVMF_CODE.fd; RHEL-family hosts typically use /usr/share/edk2/ovmf/OVMF_CODE.fd."
  type        = string
  default     = "/usr/share/OVMF/OVMF_CODE.fd"
}

variable "nvram_dir" {
  description = "Directory the per-domain UEFI NVRAM file is written to. Debian and RHEL both use the default; change it if your hypervisor differs."
  type        = string
  default     = "/var/lib/libvirt/qemu/nvram"
}

variable "uefi_nvram_template_path" {
  description = "Path on the hypervisor to the OVMF NVRAM variables template used to seed each domain's NVRAM store"
  type        = string
  default     = "/usr/share/OVMF/OVMF_VARS.fd"
}

variable "vnc_listen_address" {
  description = "Address the domain's VNC console listens on. Defaults to loopback; set to 0.0.0.0 only on a trusted management network."
  type        = string
  default     = "127.0.0.1"
}

# -----------------------------------------------------------------------------
# Networking
#
# NIC order is a contract with GNOS, which assigns interface roles positionally
# by PCI address:
#
#   wan1, local-mgmt, wan2..wanN, lan1..lanN
#
# Each interface either attaches to a host bridge you name, or - when you leave
# that setting empty - to a libvirt network this module creates. Leaving them all
# empty deploys a working edge on a hypervisor with no networking prepared.
# -----------------------------------------------------------------------------
variable "wan_bridges" {
  description = "Host bridges for the ISP WAN interfaces, in order; the first is the interface used to onboard. Add a second entry for dual-WAN. Leave the list empty to have the module create a single NAT WAN network."
  type        = list(string)
  default     = []
}

variable "lan_bridge" {
  description = "Host bridge shared by all LAN (customer ingress) interfaces. Leave empty to have the module create one isolated network per LAN, so the vEdge is the only path off the LAN."
  type        = string
  default     = ""
}

variable "lan_count" {
  description = "Number of LAN interfaces to attach after the WAN interfaces"
  type        = number
  default     = 1

  validation {
    condition     = var.lan_count >= 0
    error_message = "lan_count cannot be negative."
  }
}

variable "wan_network_prefix" {
  description = "CIDR for the WAN NAT network. Only used when wan_bridges is empty."
  type        = string
  default     = "10.30.1.0/24"
}

# -----------------------------------------------------------------------------
# Test VM (optional)
#
# Verifies that traffic actually flows through the vEdge. The vEdge LAN address
# is configured in the Graphiant Portal and is not known to Terraform, so the
# test VM is statically addressed and needs test_vm_gateway supplied - deploy it
# after the edge has onboarded.
# -----------------------------------------------------------------------------
variable "deploy_test_vm" {
  description = "Whether to deploy a test VM on the LAN with its default route via the vEdge"
  type        = bool
  default     = false
}

variable "test_vm_name" {
  description = "libvirt domain name for the test VM"
  type        = string
  default     = "graphiant-vedge-test-vm"
}

variable "test_vm_image_source" {
  description = "Path or URL to a cloud-init enabled qcow2 for the test VM"
  type        = string
  default     = "https://cloud.debian.org/images/cloud/trixie/latest/debian-13-generic-amd64.qcow2"
}

variable "test_vm_ip_cidr" {
  description = "Static address and prefix for the test VM on the LAN, e.g. \"192.168.100.10/24\". Required when deploy_test_vm = true."
  type        = string
  default     = ""
}

variable "test_vm_gateway" {
  description = "Default gateway for the test VM: the vEdge LAN address as configured in the Graphiant Portal. Required when deploy_test_vm = true."
  type        = string
  default     = ""
}

variable "test_vm_username" {
  description = "Username created on the test VM"
  type        = string
  default     = "graphiant"
}

variable "test_vm_password" {
  description = "Password for the test VM user"
  type        = string
  sensitive   = true
  default     = ""
}

variable "test_vm_ssh_public_key" {
  description = "SSH public key authorised for the test VM user"
  type        = string
  default     = ""
}
