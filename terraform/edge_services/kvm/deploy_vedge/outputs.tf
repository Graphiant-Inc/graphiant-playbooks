output "mode" {
  description = "Deployment mode (production or devtest)"
  value       = var.mode
}

output "domain_id" {
  description = "libvirt domain ID (UUID) of the vEdge"
  value       = libvirt_domain.vedge.id
}

output "domain_name" {
  description = "libvirt domain name of the vEdge"
  value       = var.vm_name
}

output "interface_order" {
  description = "Ordered interface roles as attached to the domain, for the mode this deployment uses. GNOS assigns roles positionally, so this is what the appliance sees. The leading 'mgmt' (kernel-managed, non-VPP) NIC exists in devtest only; in production the list starts at wan1. Cross-check with `virsh domiflist <domain_name>`."
  value       = [for n in local.nics : n.label]
}

output "networks_created" {
  description = "Map of interface role to the libvirt network this module created for it. Roles attached to a host bridge are absent, since those bridges are not managed here."
  value = merge(
    local.create_mgmt_net ? { mgmt = libvirt_network.mgmt[0].name } : {},
    local.create_wan_net ? { wan1 = libvirt_network.wan[0].name } : {},
    { "local-mgmt" = libvirt_network.local_mgmt.name },
    { for i, n in libvirt_network.lan : "lan${i + 1}" => n.name },
  )
}

output "host_bridges_required" {
  description = "Host bridges this deployment expects to already exist. Empty when the module creates every network itself. Confirm with `ip link show type bridge` before applying."
  value = concat(
    local.attach_mgmt_nic && !local.create_mgmt_net ? [var.mgmt_bridge] : [],
    var.wan_bridges,
    local.create_lan_nets ? [] : [var.lan_bridge],
  )
}

output "base_volume_id" {
  description = "ID of the GNOS base volume backing the vEdge disk. Pass this as base_volume_id in further deployments to reuse the imported image."
  value       = local.base_volume_id
}

output "serial_console_command" {
  description = "Command to attach to the vEdge serial console on the hypervisor"
  value       = "virsh --connect ${var.libvirt_uri} console ${var.vm_name}"
}

output "test_vm_ip" {
  description = "Static address of the test VM on the LAN (only when deploy_test_vm = true)"
  value       = var.deploy_test_vm ? var.test_vm_ip_cidr : null
}
