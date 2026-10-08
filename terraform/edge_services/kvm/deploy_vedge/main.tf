terraform {
  required_version = ">= 1.3.0"

  required_providers {
    libvirt = {
      source = "dmacvicar/libvirt"
      # Pinned to 0.8.x. This provider is pre-1.0, so minor bumps are breaking:
      # 0.9.x replaces the resource schema used here with an XML-shaped one.
      version = "~> 0.8.0"
    }
  }
}

provider "libvirt" {
  uri = var.libvirt_uri
}

# -----------------------------------------------------------------------------
# Locals
# -----------------------------------------------------------------------------
locals {
  # An interface attaches to the host bridge you name, or - if you leave it
  # empty - to a libvirt network this module creates.
  create_wan_net  = length(var.wan_bridges) == 0
  create_lan_nets = var.lan_bridge == ""

  # GNOS assigns interface roles by PCI order, so this order is a contract:
  #   wan1, local-mgmt, wan2..wanN, lan1..lanN
  nics = concat(
    [{
      label      = "wan1"
      bridge     = local.create_wan_net ? null : var.wan_bridges[0]
      network_id = local.create_wan_net ? libvirt_network.wan[0].id : null
    }],
    [{
      label      = "local-mgmt"
      bridge     = null
      network_id = libvirt_network.local_mgmt.id
    }],
    local.create_wan_net ? [] : [
      for i, b in slice(var.wan_bridges, 1, length(var.wan_bridges)) : {
        label      = "wan${i + 2}"
        bridge     = b
        network_id = null
      }
    ],
    [for i in range(var.lan_count) : {
      label      = "lan${i + 1}"
      bridge     = local.create_lan_nets ? null : var.lan_bridge
      network_id = local.create_lan_nets ? libvirt_network.lan[i].id : null
    }]
  )

  lan_network_id = local.create_lan_nets ? try(libvirt_network.lan[0].id, null) : null

  # Cloud-init user data: the graphnos block GNOS reads at first boot.
  user_data = <<-USERDATA
    #cloud-config

    graphnos:
      role: ${var.graphnos_role}
      token: "${var.token}"
  USERDATA

  base_volume_id = var.base_volume_id != "" ? var.base_volume_id : try(libvirt_volume.gnos_base[0].id, "")

  # The provider cannot set either of these: q35 has no IDE controller for the
  # CD-ROM, and a file disk carries no format so libvirt would assume raw.
  domain_xslt = <<-XSLT
    <?xml version="1.0" ?>
    <xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
      <xsl:output omit-xml-declaration="yes" indent="yes"/>
      <xsl:template match="node()|@*">
        <xsl:copy><xsl:apply-templates select="node()|@*"/></xsl:copy>
      </xsl:template>
      <xsl:template match="/domain/devices/disk[@device='cdrom']/target">
        <target dev="sda" bus="sata"/>
      </xsl:template>
      <xsl:template match="/domain/devices/disk[@device='disk']">
        <disk>
          <xsl:apply-templates select="@*"/>
          <driver name="qemu" type="qcow2"/>
          <xsl:apply-templates select="node()[not(self::driver)]"/>
        </disk>
      </xsl:template>
    </xsl:stylesheet>
  XSLT
}

# -----------------------------------------------------------------------------
# Networks — created only for interfaces with no host bridge. WAN is NAT so the
# vEdge can reach the backbone; LAN is isolated so the vEdge is the only way
# off it.
# -----------------------------------------------------------------------------
resource "libvirt_network" "wan" {
  count = local.create_wan_net ? 1 : 0

  name      = "${var.vm_name}-wan"
  mode      = "nat"
  addresses = [var.wan_network_prefix]
  autostart = true

  dhcp {
    enabled = true
  }

  dns {
    enabled = true
  }
}

resource "libvirt_network" "local_mgmt" {
  name      = "${var.vm_name}-local-mgmt"
  mode      = "none"
  autostart = true
}

resource "libvirt_network" "lan" {
  count = local.create_lan_nets ? var.lan_count : 0

  name      = "${var.vm_name}-lan-${count.index + 1}"
  mode      = "none"
  autostart = true
}

# -----------------------------------------------------------------------------
# Volumes — the GNOS qcow2 is imported once and backed by a thin overlay.
# -----------------------------------------------------------------------------
resource "libvirt_volume" "gnos_base" {
  count = var.base_volume_id == "" ? 1 : 0

  name   = "${var.vm_name}-gnos-base.qcow2"
  pool   = var.storage_pool
  source = var.image_source
  format = "qcow2"

  lifecycle {
    precondition {
      condition     = var.image_source != ""
      error_message = "Set image_source to the GNOS qcow2 (hypervisor path or HTTP(S) URL), or base_volume_id to reuse an imported base volume."
    }
  }
}

resource "libvirt_volume" "vedge" {
  name           = "${var.vm_name}.qcow2"
  pool           = var.storage_pool
  format         = "qcow2"
  base_volume_id = local.base_volume_id
  size           = var.disk_size_gb * 1024 * 1024 * 1024
}

# Delivered as a CD-ROM, which is how GNOS expects cloud-init on KVM.
resource "libvirt_cloudinit_disk" "vedge" {
  name      = "${var.vm_name}-cloudinit.iso"
  pool      = var.storage_pool
  user_data = local.user_data

  # Placeholder hostname; the real device name comes from the Graphiant Portal.
  meta_data = <<-METADATA
    local-hostname: gnos
    instance-id: ${var.vm_name}
  METADATA
}

# -----------------------------------------------------------------------------
# vEdge domain — GNOS needs UEFI/OVMF, an emulated TPM 2.0, q35 and host CPU
# passthrough.
# -----------------------------------------------------------------------------
resource "libvirt_domain" "vedge" {
  name      = var.vm_name
  memory    = var.memory_mb
  vcpu      = var.vcpus
  machine   = var.machine_type
  autostart = true

  firmware = var.uefi_loader_path

  nvram {
    template = var.uefi_nvram_template_path
    file     = "${var.nvram_dir}/${var.vm_name}_VARS.fd"
  }

  cpu {
    mode = var.cpu_mode
  }

  tpm {
    backend_type    = "emulator"
    backend_version = "2.0"
    model           = "tpm-crb"
  }

  # By path, not volume_id: type='volume' stops libvirt labelling the backing
  # chain, and QEMU then cannot open it.
  disk {
    file = libvirt_volume.vedge.id
  }

  cloudinit = libvirt_cloudinit_disk.vedge.id

  dynamic "network_interface" {
    for_each = local.nics
    content {
      bridge     = network_interface.value.bridge
      network_id = network_interface.value.network_id
    }
  }

  console {
    type        = "pty"
    target_port = "0"
    target_type = "serial"
  }

  graphics {
    type           = "vnc"
    listen_type    = "address"
    listen_address = var.vnc_listen_address
    autoport       = true
  }

  xml {
    xslt = local.domain_xslt
  }
}

# -----------------------------------------------------------------------------
# Test VM (optional) — a Debian cloud image on the LAN, routing via the vEdge.
# Supply test_vm_gateway: deploy it after the edge has onboarded.
# -----------------------------------------------------------------------------
resource "libvirt_volume" "test_vm_base" {
  count = var.deploy_test_vm ? 1 : 0

  name   = "${var.test_vm_name}-base.qcow2"
  pool   = var.storage_pool
  source = var.test_vm_image_source
  format = "qcow2"
}

resource "libvirt_volume" "test_vm" {
  count = var.deploy_test_vm ? 1 : 0

  name           = "${var.test_vm_name}.qcow2"
  pool           = var.storage_pool
  format         = "qcow2"
  base_volume_id = libvirt_volume.test_vm_base[0].id
  size           = 10 * 1024 * 1024 * 1024
}

resource "libvirt_cloudinit_disk" "test_vm" {
  count = var.deploy_test_vm ? 1 : 0

  name = "${var.test_vm_name}-cloudinit.iso"
  pool = var.storage_pool

  user_data = <<-USERDATA
    #cloud-config

    users:
      - name: ${var.test_vm_username}
        plain_text_passwd: '${var.test_vm_password}'
        sudo: ["ALL=(ALL) NOPASSWD:ALL"]
        lock_passwd: false
        groups: sudo
        shell: /bin/bash
        ssh-authorized-keys:
          - ${var.test_vm_ssh_public_key}
  USERDATA

  # Static: the LAN has no DHCP, and the route must point at the vEdge.
  network_config = <<-NETCFG
    version: 2
    ethernets:
      primary:
        match:
          name: "en*"
        addresses: [${var.test_vm_ip_cidr}]
        routes:
          - to: 0.0.0.0/0
            via: ${var.test_vm_gateway}
  NETCFG

  lifecycle {
    precondition {
      condition     = var.test_vm_ip_cidr != "" && var.test_vm_gateway != ""
      error_message = "deploy_test_vm = true requires test_vm_ip_cidr and test_vm_gateway (the vEdge LAN address configured in Graphiant Portal)."
    }
    precondition {
      condition     = !local.create_lan_nets || var.lan_count > 0
      error_message = "deploy_test_vm = true needs a LAN to attach to: set lan_count > 0, or set lan_bridge to an existing host bridge."
    }
  }
}

resource "libvirt_domain" "test_vm" {
  count = var.deploy_test_vm ? 1 : 0

  name      = var.test_vm_name
  memory    = 1024
  vcpu      = 1
  machine   = var.machine_type
  autostart = true

  cpu {
    mode = var.cpu_mode
  }

  disk {
    file = libvirt_volume.test_vm[0].id
  }

  cloudinit = libvirt_cloudinit_disk.test_vm[0].id

  network_interface {
    bridge     = local.create_lan_nets ? null : var.lan_bridge
    network_id = local.lan_network_id
  }

  console {
    type        = "pty"
    target_port = "0"
    target_type = "serial"
  }

  xml {
    xslt = local.domain_xslt
  }
}
