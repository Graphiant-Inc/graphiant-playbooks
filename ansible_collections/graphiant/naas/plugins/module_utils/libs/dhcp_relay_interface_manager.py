"""
DHCP Relay on Interfaces Manager for Graphiant Playbooks.

Configures DHCP relay (ipv4/ipv6) on main interfaces and VLAN subinterfaces.
"""

from typing import Any, Dict, List, Optional

from .base_manager import BaseManager
from .device_config_common import load_device_list_yaml_config, new_apply_result
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class DhcpRelayInterfaceManager(BaseManager):
    """Manage DHCP relay on main interfaces and subinterfaces."""

    @staticmethod
    def _relay_servers_from_config(relay_cfg: Any) -> List[str]:
        if relay_cfg is None:
            return []
        if isinstance(relay_cfg, dict):
            servers = relay_cfg.get("relayServers") or []
            return [str(s) for s in servers] if isinstance(servers, list) else []
        if isinstance(relay_cfg, (list, tuple)):
            return [str(s) for s in relay_cfg]
        return []

    @classmethod
    def _relay_servers_from_interface(cls, ip_obj: Any, af: str = "ipv4") -> List[str]:
        if not ip_obj:
            return []
        relay = getattr(ip_obj, "dhcp_relay", None)
        if not relay:
            return []
        attr = "dhcpv4_relays" if af == "ipv4" else "dhcpv6_relays"
        servers = getattr(relay, attr, None) or []
        if not isinstance(servers, list):
            return []
        return [str(s) for s in servers]

    @staticmethod
    def _interface_label(name: str, vlan: Optional[Any] = None) -> str:
        if vlan is not None and vlan != "":
            return f"{name}.{vlan}"
        return name

    @classmethod
    def _get_interface_object(cls, gcs_device_info, interface_name: str, vlan: Optional[Any] = None):
        if not hasattr(gcs_device_info, "device"):
            return None

        device = gcs_device_info.device
        if not hasattr(device, "interfaces") or not device.interfaces:
            return None

        target_interface = None
        for interface in device.interfaces:
            if getattr(interface, "name", None) == interface_name:
                target_interface = interface
                break

        if not target_interface:
            return None

        if vlan is not None and vlan != "":
            vlan_int = int(vlan)
            if hasattr(target_interface, "subinterfaces") and target_interface.subinterfaces:
                for subintf in target_interface.subinterfaces:
                    if getattr(subintf, "vlan", None) == vlan_int:
                        return subintf
            return None

        return target_interface

    @classmethod
    def _list_known_interfaces(cls, gcs_device_info) -> List[str]:
        names: set[str] = set()
        if not hasattr(gcs_device_info, "device"):
            return []

        device = gcs_device_info.device
        if not hasattr(device, "interfaces") or not device.interfaces:
            return []

        for interface in device.interfaces:
            parent = getattr(interface, "name", None)
            if parent:
                names.add(str(parent))
            subs = getattr(interface, "subinterfaces", None)
            if subs:
                for subintf in subs:
                    vlan = getattr(subintf, "vlan", None)
                    if parent is not None and vlan is not None:
                        names.add(f"{parent}.{vlan}")

        return sorted(names)

    @classmethod
    def _has_dhcp_subnet_on_interface(cls, gcs_device_info, interface_name: str, vlan=None) -> bool:
        """Return True if any segment on the device has a DHCP subnet pool on this interface."""
        label = cls._interface_label(str(interface_name), vlan)
        device = getattr(gcs_device_info, "device", None)
        if not device:
            return False
        for segment in getattr(device, "segments", None) or []:
            for pool in getattr(segment, "dhcp_subnets", None) or []:
                if getattr(pool, "interface", None) == label:
                    return True
        return False

    @classmethod
    def _validate_interface_entry(
        cls,
        device_name: str,
        gcs_device_info,
        interface_name: Any,
        vlan: Optional[Any] = None,
        operation: str = "configure",
    ) -> None:
        if not interface_name:
            raise ConfigurationError(
                f"Device '{device_name}': each dhcp relay entry " f"requires 'name' (interface name)."
            )

        intf_obj = cls._get_interface_object(gcs_device_info, interface_name, vlan)
        if intf_obj is None:
            label = cls._interface_label(str(interface_name), vlan)
            known = cls._list_known_interfaces(gcs_device_info)
            known_msg = (
                ", ".join(known)
                if known
                else "(none — configure interfaces first, e.g. interface_management.yml --tags lan)"
            )
            raise ConfigurationError(
                f"Device '{device_name}': dhcp relay references interface {label!r} which does not exist "
                f"on this device. Known interfaces: {known_msg}."
            )

        if operation == "configure":
            label = cls._interface_label(str(interface_name), vlan)
            if cls._has_dhcp_subnet_on_interface(gcs_device_info, interface_name, vlan):
                raise ConfigurationError(
                    f"Device '{device_name}': cannot configure DHCP relay on interface {label!r} — "
                    f"DHCP subnet (server) is already configured on this interface. "
                    f"An interface supports either DHCP relay or DHCP subnet, not both."
                )

    @classmethod
    def _get_existing_dhcp_relay_state(
        cls, gcs_device_info, interface_name: str, vlan: Optional[Any] = None
    ) -> Dict[str, List[str]]:
        state: Dict[str, List[str]] = {"ipv4": [], "ipv6": []}
        intf_obj = cls._get_interface_object(gcs_device_info, interface_name, vlan)
        if not intf_obj:
            return state

        state["ipv4"] = cls._relay_servers_from_interface(getattr(intf_obj, "ipv4", None), af="ipv4")
        state["ipv6"] = cls._relay_servers_from_interface(getattr(intf_obj, "ipv6", None), af="ipv6")
        return state

    @staticmethod
    def _af_action(iface_action: str, af_cfg: Any) -> str:
        """Return the effective action for one address family, respecting per-AF state."""
        if isinstance(af_cfg, dict):
            af_state = af_cfg.get("state")
            if af_state == "absent":
                return "delete"
            if af_state == "present":
                return "add"
        return iface_action

    @classmethod
    def _has_relay_config(cls, config: Dict[str, Any]) -> bool:
        for key in ("dhcpRelayIpv4", "dhcpRelayIpv6"):
            af_cfg = config.get(key)
            if af_cfg is None:
                continue
            if isinstance(af_cfg, dict) and "state" in af_cfg:
                return True  # explicit per-AF state is always actionable
            if cls._relay_servers_from_config(af_cfg):
                return True
        return False

    @classmethod
    def _desired_relay_state(cls, config: Dict[str, Any], action: str) -> Dict[str, List[str]]:
        desired: Dict[str, List[str]] = {"ipv4": [], "ipv6": []}
        for af, key in (("ipv4", "dhcpRelayIpv4"), ("ipv6", "dhcpRelayIpv6")):
            af_cfg = config.get(key)
            if af_cfg is None:
                continue
            af_action = cls._af_action(action, af_cfg)
            desired[af] = [] if af_action == "delete" else cls._relay_servers_from_config(af_cfg)
        return desired

    @classmethod
    def _relay_afs_in_scope(cls, config: Dict[str, Any]) -> List[str]:
        afs: List[str] = []
        if config.get("dhcpRelayIpv4") is not None:
            afs.append("ipv4")
        if config.get("dhcpRelayIpv6") is not None:
            afs.append("ipv6")
        return afs

    @classmethod
    def _relay_state_matches(
        cls, existing: Dict[str, List[str]], desired: Dict[str, List[str]], afs: List[str]
    ) -> bool:
        for af in afs:
            if sorted(existing.get(af) or []) != sorted(desired.get(af) or []):
                return False
        return True

    @classmethod
    def _dhcp_relay_block(cls, relay_cfg: Any, action: str) -> Optional[Dict[str, Any]]:
        af_action = cls._af_action(action, relay_cfg)
        if af_action == "delete":
            if relay_cfg is None:
                return None
            return {"dhcp": {"dhcpRelay": {"relayServers": []}}}

        servers = cls._relay_servers_from_config(relay_cfg)
        if not servers:
            return None
        return {"dhcp": {"dhcpRelay": {"relayServers": servers}}}

    @classmethod
    def build_dhcp_relay_interfaces_payload(cls, action: str, **config: Any) -> Dict[str, Any]:
        """Build edge.interfaces payload for DHCP relay configure or deconfigure."""
        name = config["name"]
        vlan = config.get("vlan")
        ipv4_cfg = config.get("dhcpRelayIpv4")
        ipv6_cfg = config.get("dhcpRelayIpv6")

        ip_blocks: Dict[str, Any] = {}
        ipv4_block = cls._dhcp_relay_block(ipv4_cfg, action)
        if ipv4_block:
            ip_blocks["ipv4"] = ipv4_block
        ipv6_block = cls._dhcp_relay_block(ipv6_cfg, action)
        if ipv6_block:
            ip_blocks["ipv6"] = ipv6_block

        if not ip_blocks:
            return {}

        if vlan is not None and vlan != "":
            interface_body = {"vlan": int(vlan), **ip_blocks}
            return {
                "interfaces": {
                    name: {
                        "interface": {
                            "subinterfaces": {
                                str(vlan): {
                                    "interface": interface_body,
                                }
                            }
                        }
                    }
                }
            }

        return {"interfaces": {name: {"interface": ip_blocks}}}

    @classmethod
    def _deep_merge_subinterface_entry(cls, base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        _bi: Any = base.get("interface")
        base_intf: Dict[str, Any] = _bi if isinstance(_bi, dict) else {}
        _ui: Any = update.get("interface")
        upd_intf: Dict[str, Any] = _ui if isinstance(_ui, dict) else {}
        if base_intf or upd_intf:
            merged = dict(base_intf)
            merged.update(upd_intf)
            return {"interface": merged}
        return update if update else base

    @classmethod
    def _deep_merge_interface_entry(cls, base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two interface stubs for the same parent interface name."""
        base_intf = dict(base.get("interface") or {})
        upd_intf = dict(update.get("interface") or {})
        merged_intf = dict(base_intf)

        for key, val in upd_intf.items():
            if key == "subinterfaces":
                merged_subs = dict(base_intf.get("subinterfaces") or {})
                for vlan_key, sub_entry in (val or {}).items():
                    if vlan_key in merged_subs:
                        merged_subs[vlan_key] = cls._deep_merge_subinterface_entry(merged_subs[vlan_key], sub_entry)
                    else:
                        merged_subs[vlan_key] = sub_entry
                merged_intf["subinterfaces"] = merged_subs
            else:
                merged_intf[key] = val

        return {"interface": merged_intf}

    @classmethod
    def merge_dhcp_relay_payload(cls, config_payload: Dict[str, Any], relay_payload: Dict[str, Any]) -> None:
        if not relay_payload.get("interfaces"):
            return
        if "interfaces" not in config_payload:
            config_payload["interfaces"] = {}

        for iface_name, iface_data in relay_payload["interfaces"].items():
            existing = config_payload["interfaces"].get(iface_name)
            if existing is None:
                config_payload["interfaces"][iface_name] = iface_data
            else:
                config_payload["interfaces"][iface_name] = cls._deep_merge_interface_entry(existing, iface_data)

    @staticmethod
    def _row_from_params(mp: Dict[str, Any]) -> Dict[str, Any]:
        """Build a per-device row dict from module params for load_device_list_yaml_config."""
        if mp.get("interfaces"):
            return {"interfaces": list(mp["interfaces"])}
        entry: Dict[str, Any] = {}
        for key in ("name", "vlan", "dhcpRelayIpv4", "dhcpRelayIpv6"):
            if mp.get(key) is not None:
                entry[key] = mp[key]
        return {"interfaces": [entry]} if entry.get("name") else {}

    @staticmethod
    def _validate_cfg(device_name: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
        ifaces = cfg.get("interfaces")
        if not isinstance(ifaces, list):
            raise ConfigurationError(f"Device '{device_name}': expected 'interfaces' list in dhcp_relay_config entry.")
        return cfg

    def _load_device_configs(
        self,
        dhcp_relay_config_file: Optional[str],
        module_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        by_name = load_device_list_yaml_config(
            "dhcp_relay_config",
            dhcp_relay_config_file,
            module_params,
            self.render_config_file,
            missing_input_error="Provide dhcp_relay_config_file and/or device (portal device name).",
            build_row_from_params=self._row_from_params,
            validate_device_cfg=self._validate_cfg,
        )
        return {name: cfg.get("interfaces") or [] for name, cfg in by_name.items()}

    def apply_dhcp_relay_interfaces(
        self,
        dhcp_relay_config_file: Optional[str],
        operation: str,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        action = "add" if operation == "configure" else "delete"
        result = new_apply_result(
            deconfigured_interfaces=[],
            skipped_interfaces=[],
        )
        output_config: Dict[int, Dict[str, Any]] = {}

        try:
            for device_name, interfaces in self._load_device_configs(dhcp_relay_config_file, module_params).items():
                device_id = self.gsdk.get_device_id(device_name)
                if device_id is None:
                    raise ConfigurationError(
                        f"Device '{device_name}' is not found in the current enterprise: "
                        f"{self.gsdk.enterprise_info['company_name']}. "
                        f"Please check device name and enterprise credentials."
                    )

                gcs_device_info = self.gsdk.get_device_info(device_id)
                device_before: Dict[str, Any] = {}
                device_after: Dict[str, Any] = {}
                device_changed = False

                for config in interfaces:
                    interface_name = config.get("name")
                    vlan = config.get("vlan")
                    iface_state = config.get("state")

                    # Per-interface state overrides the module-level operation.
                    if iface_state == "absent":
                        iface_action = "delete"
                    elif iface_state == "present":
                        iface_action = "add"
                    else:
                        iface_action = action

                    iface_operation = "deconfigure" if iface_action == "delete" else "configure"
                    label = self._interface_label(str(interface_name or ""), vlan)

                    self._validate_interface_entry(
                        device_name, gcs_device_info, interface_name, vlan, operation=iface_operation
                    )

                    if iface_action == "add" and not self._has_relay_config(config):
                        LOG.info(
                            "Skipping interface '%s' on %s - no DHCP relay servers configured",
                            interface_name,
                            device_name,
                        )
                        continue

                    afs = self._relay_afs_in_scope(config)
                    effective_config = config

                    # When deleting with no explicit address families, clear whatever is live.
                    if iface_action == "delete" and not afs:
                        existing_for_afs = self._get_existing_dhcp_relay_state(
                            gcs_device_info, str(interface_name), vlan
                        )
                        afs = [af for af in ("ipv4", "ipv6") if existing_for_afs.get(af)]
                        if not afs:
                            result["skipped_interfaces"].append(
                                {
                                    "device": device_name,
                                    "interface": interface_name,
                                    "vlan": vlan,
                                    "reason": "DHCP relay already matches desired state",
                                }
                            )
                            continue
                        effective_config = dict(config)
                        for af in afs:
                            effective_config["dhcpRelayIpv4" if af == "ipv4" else "dhcpRelayIpv6"] = {}

                    if not afs:
                        continue

                    existing = self._get_existing_dhcp_relay_state(gcs_device_info, str(interface_name), vlan)
                    desired = self._desired_relay_state(effective_config, iface_action)

                    if self._relay_state_matches(existing, desired, afs):
                        result["skipped_interfaces"].append(
                            {
                                "device": device_name,
                                "interface": interface_name,
                                "vlan": vlan,
                                "reason": "DHCP relay already matches desired state",
                            }
                        )
                        continue

                    payload = self.build_dhcp_relay_interfaces_payload(action=iface_action, **effective_config)
                    if not payload:
                        result["skipped_interfaces"].append(
                            {
                                "device": device_name,
                                "interface": interface_name,
                                "vlan": vlan,
                                "reason": "No DHCP relay payload generated",
                            }
                        )
                        continue

                    if device_id not in output_config:
                        output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}}}

                    self.merge_dhcp_relay_payload(output_config[device_id]["edge"], payload)
                    device_changed = True

                    before_entry = {
                        af: {"dhcp": {"dhcpRelay": {"relayServers": list(existing.get(af) or []) or None}}}
                        for af in afs
                    }
                    after_entry = {
                        af: {"dhcp": {"dhcpRelay": {"relayServers": list(desired.get(af) or []) or None}}} for af in afs
                    }
                    device_before[label] = before_entry
                    device_after[label] = after_entry

                    if iface_action == "add":
                        LOG.info("Will configure DHCP relay on %s for device %s", label, device_name)
                    else:
                        result["deconfigured_interfaces"].append(
                            {"device": device_name, "interface": interface_name, "vlan": vlan}
                        )
                        LOG.info("Will deconfigure DHCP relay on %s for device %s", label, device_name)

                if device_changed:
                    result["configured_devices"].append(device_name)
                    result["diff_plan"].append(
                        {
                            "device": device_name,
                            "branch": "edge.interfaces",
                            "before": device_before,
                            "after": device_after,
                        }
                    )
                else:
                    result["skipped_devices"].append(device_name)

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True

            return result
        except DeviceNotFoundError:
            raise
        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(f"DHCP relay interface {operation} failed: {str(e)}")

    def configure(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.configure_dhcp_relay_interfaces(config_yaml_file, module_params=module_params)

    def deconfigure(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.deconfigure_dhcp_relay_interfaces(config_yaml_file, module_params=module_params)

    def configure_dhcp_relay_interfaces(
        self,
        dhcp_relay_config_file: Optional[str],
        module_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.apply_dhcp_relay_interfaces(
            dhcp_relay_config_file, operation="configure", module_params=module_params
        )

    def deconfigure_dhcp_relay_interfaces(
        self,
        dhcp_relay_config_file: Optional[str],
        module_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.apply_dhcp_relay_interfaces(
            dhcp_relay_config_file, operation="deconfigure", module_params=module_params
        )
