"""
VRRP on Interfaces Manager for Graphiant Playbooks.

This module handles VRRP interface configuration management for Graphiant Playbooks.

VRRP configuration is applied to both main interfaces and subinterfaces (VLANs).

Idempotency Support:
    - deconfigure: Checks if VRRP is already disabled before pushing config.
      Skips interfaces where VRRP is already disabled (enabled=false).
    - enable: Checks if VRRP is already enabled before pushing config.
      Skips interfaces where VRRP is already enabled.
    - configure: Field-level idempotent. Each interface's desired VRRP groups are
      compared against live state (``get_device_info``); only interfaces that are
      absent or drifted are pushed (a merge PUT), and unchanged interfaces and
      devices are skipped.

Diff Support:
    All operations populate ``diff_plan`` (per-device before/after) so the module
    renders a readable Ansible ``--diff``. Pushes no-op under check mode.
"""

from typing import Any, Dict

from .base_manager import BaseManager
from .device_config_common import new_apply_result, redact_sensitive_for_log
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class VRRPInterfaceManager(BaseManager):
    """
    Manages VRRP on interfaces configurations.

    Handles the configuration and deconfiguration of VRRP interfaces,
    including both main interfaces and VLAN subinterfaces.
    """

    # --- Desired-payload builders -----------------------------------------
    # Translate a config-file VRRP entry into the ``edge`` PUT payload. These
    # replace the former Jinja2 template templates/vrrp_interfaces_template.yaml.
    # Notes the template handled implicitly:
    #   * ``true``/``false`` became real ``True``/``False`` after yaml.safe_load.
    #   * Subinterface keys were quoted (``"{{ vlan }}"``) so they parse back as
    #     *strings*, while the inner ``"vlan"`` value stays an *int*.
    #   * ``delete``/``enable`` actions emit only ``enabled: false/true``; ``add``
    #     emits the full VRRP group (with defaults matching the template).

    @staticmethod
    def _vrrp_group_block(family_cfg, action, interface_name):
        """
        Build the ``{"vrrp": {"group": {...}}}`` body for one IP family (ipv4/ipv6).

        ``delete`` and ``enable`` only toggle ``enabled``; ``add`` emits the full
        group with the same field defaults the template applied.
        """
        if action == "delete":
            return {"vrrp": {"group": {"enabled": False}}}
        if action == "enable":
            return {"vrrp": {"group": {"enabled": True}}}

        # action == "add": full configuration.
        vrid = family_cfg["virtualRouterId"]
        group = {
            "enabled": family_cfg.get("enabled", True),
            "allowInterOperability": family_cfg.get("allowInterOperability", False),
            "virtualRouterId": vrid,
            "description": family_cfg.get("description", "{} VRRP group {}".format(interface_name, vrid)),
            "priority": family_cfg.get("priority", 100),
            "virtualIp": family_cfg["virtualIp"],
            "preempt": family_cfg.get("preempt", False),
        }
        # A present ``trackedInterfaces`` key is always sent, even when empty/null
        # (``trackedInterfaces:`` in YAML parses as None). To clear the device's
        # tracked interfaces the API expects a single empty object ``[{}]`` (an
        # empty list ``[]`` is ignored by the merge PUT), so an empty desired list
        # is sent as the clear sentinel. Omitting the key entirely leaves them
        # unmanaged (not sent).
        if "trackedInterfaces" in family_cfg:
            entries = [
                {
                    "interface": entry["interface"],
                    "priorityDecrement": entry.get("priorityDecrement", 10),
                }
                for entry in (family_cfg.get("trackedInterfaces") or [])
            ]
            group["trackedInterfaces"] = entries if entries else [{}]
        return {"vrrp": {"group": group}}

    @staticmethod
    def _build_vrrp_interface(name, action="add", **cfg):
        """
        Build the VRRP interface payload for one interface entry.

        Returns ``{"interfaces": {<name>: {"interface": {...}}}}`` (formerly
        rendered by templates/vrrp_interfaces_template.yaml). A ``vlan`` wraps the
        VRRP bodies in a ``subinterfaces`` block; otherwise they attach to the
        main interface.
        """
        vlan = cfg.get("vlan")
        vrrp_ipv4 = cfg.get("vrrp_ipv4")
        vrrp_ipv6 = cfg.get("vrrp_ipv6")

        families = {}  # type: Dict[str, Any]
        if vrrp_ipv4 is not None:
            families["ipv4"] = VRRPInterfaceManager._vrrp_group_block(vrrp_ipv4, action, name)
        if vrrp_ipv6 is not None:
            families["ipv6"] = VRRPInterfaceManager._vrrp_group_block(vrrp_ipv6, action, name)

        if vlan is not None:
            # Key is quoted in the template -> parses back as a string, while the
            # inner "vlan" value stays an int.
            interface_body = {"subinterfaces": {str(vlan): {"interface": dict(vlan=vlan, **families)}}}
        else:
            interface_body = families

        return {"interfaces": {name: {"interface": interface_body}}}

    def _apply_vrrp(self, config_payload, action="add", **kwargs):
        """
        Build a VRRP payload and merge it into ``config_payload["interfaces"]``.

        Replaces the former ``config_utils.vrrp_interfaces`` (template-based) hop.
        """
        name = kwargs.pop("name", None)
        if not name:
            raise ConfigurationError("Missing required parameters: ['name']")
        LOG.info("VRRP on interfaces: %s %s", action.upper(), name)

        try:
            result = self._build_vrrp_interface(name, action=action, **kwargs)
            if "interfaces" not in config_payload:
                config_payload["interfaces"] = {}
            config_payload["interfaces"].update(result["interfaces"])
        except ConfigurationError:
            raise
        except Exception as e:  # pylint: disable=broad-except
            LOG.error("Failed to process VRRP on interfaces %s: %s", name, str(e))
            raise ConfigurationError(f"VRRP on interfaces processing failed: {str(e)}")

    @staticmethod
    def _find_interface_obj(gcs_device_info, interface_name, vlan=None):
        """
        Return the SDK interface object (main interface, or the subinterface for
        ``vlan``) from device info, or None when it is not present.
        """
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

        if not vlan:
            return target_interface

        vlan_int = int(vlan)
        for subintf in getattr(target_interface, "subinterfaces", None) or []:
            if getattr(subintf, "vlan", None) == vlan_int:
                return subintf
        return None

    # --- Field-level idempotency / diff (configure path) -------------------
    # Compare each device's desired VRRP groups against live GET state so
    # unchanged devices are skipped. Desired is normalized from the raw config
    # (sparse: only the fields the builder would send); current is normalized
    # from the SDK GET model. Only keys present in the desired side are compared
    # (see _sparse_differs), so fields the config omits never trigger a false
    # change. Safety bias: when a group is absent on the device, prefer "changed".

    @staticmethod
    def _sparse_differs(desired, existing):
        """
        Return True if any key present in ``desired`` doesn't match ``existing``.

        Keys absent from ``desired`` are never compared. Recurses into nested dicts.
        Mirrors ``InterfaceManager._sparse_differs``.
        """
        if not isinstance(desired, dict):
            return desired != existing
        if not isinstance(existing, dict):
            return bool(desired)
        for key, desired_value in desired.items():
            existing_value = existing.get(key)
            if isinstance(desired_value, dict):
                if VRRPInterfaceManager._sparse_differs(desired_value, existing_value):
                    return True
            elif desired_value != existing_value:
                return True
        return False

    @staticmethod
    def _project_to(existing, desired):
        """
        Restrict *existing* to only the keys present in *desired* (recursively).

        Builds the ``--diff`` ``before`` so it mirrors the sparse ``after`` and
        shows only the fields this run would actually change. A merge PUT never
        removes fields the config omits, so ``before`` must not imply otherwise.
        """
        if not isinstance(desired, dict) or not isinstance(existing, dict):
            return existing
        projected = {}  # type: Dict[str, Any]
        for key, desired_value in desired.items():
            if key not in existing:
                continue
            existing_value = existing[key]
            if isinstance(desired_value, dict) and isinstance(existing_value, dict):
                projected[key] = VRRPInterfaceManager._project_to(existing_value, desired_value)
            else:
                projected[key] = existing_value
        return projected

    @staticmethod
    def _tracked_key(pair):
        """Stable sort key for a ``[interface, priorityDecrement]`` pair tolerant of None."""
        interface, decrement = pair
        return (interface or "", -1 if decrement is None else decrement)

    @staticmethod
    def _normalized_vrrp_from_config(family_cfg):
        """
        Sparse desired-state dict for one VRRP family (ipv4/ipv6) from config.

        Only fields that are also readable from the device GET model
        (``ManaV2VrrpGroup``) are included, so the sparse comparison in
        ``_sparse_differs`` never trips on a field the GET side can't report.
        Notably ``virtualRouterId`` is intentionally omitted: the GET model does
        not expose it, so comparing it would make every run report "changed".
        """
        desired = {
            "enabled": bool(family_cfg.get("enabled", True)),
            "priority": family_cfg.get("priority", 100),
            "virtualIp": family_cfg.get("virtualIp"),
            "preempt": bool(family_cfg.get("preempt", False)),
            "allowInterOperability": bool(family_cfg.get("allowInterOperability", False)),
        }  # type: Dict[str, Any]
        # A present ``trackedInterfaces`` key is compared even when empty/null, so
        # clearing it in the config (``trackedInterfaces:`` or ``[]``) is detected as
        # drift. Omitting the key entirely leaves it uncompared (unmanaged).
        if "trackedInterfaces" in family_cfg:
            desired["trackedInterfaces"] = sorted(
                (
                    [entry["interface"], entry.get("priorityDecrement", 10)]
                    for entry in (family_cfg.get("trackedInterfaces") or [])
                ),
                key=VRRPInterfaceManager._tracked_key,
            )
        # Description is only compared when the user set it explicitly; the builder
        # synthesizes a default otherwise, which must not count as drift.
        if family_cfg.get("description") is not None:
            desired["description"] = family_cfg["description"]
        return desired

    @staticmethod
    def _normalized_vrrp_from_get(vrrp_group):
        """
        Current-state dict for one VRRP family from its SDK ``vrrp_group`` object; None when absent.

        Reads the device GET model (``ManaV2VrrpGroup``), whose field names differ
        from the config/PUT model: the virtual IP is ``virtual_ip_address`` (not
        ``virtual_ip``) and there is no ``virtual_router_id``. Keys here must mirror
        ``_normalized_vrrp_from_config`` exactly for the sparse comparison to work.
        """
        if vrrp_group is None:
            return None
        current = {
            "enabled": bool(getattr(vrrp_group, "enabled", False)),
            "priority": getattr(vrrp_group, "priority", None),
            "virtualIp": getattr(vrrp_group, "virtual_ip_address", None),
            "preempt": bool(getattr(vrrp_group, "preempt", False)),
            "allowInterOperability": bool(getattr(vrrp_group, "allow_inter_operability", False)),
        }  # type: Dict[str, Any]
        # Always present (``[]`` when the device has none) so a cleared config
        # (desired ``trackedInterfaces: []``) matches a device with none on the
        # next run instead of looping. Sparse comparison only reads this key when
        # the config side also set it, so an omitted config key stays unmanaged.
        tracked = getattr(vrrp_group, "tracked_interfaces", None) or []
        current["trackedInterfaces"] = sorted(
            ([getattr(entry, "interface", None), getattr(entry, "priority_decrement", None)] for entry in tracked),
            key=VRRPInterfaceManager._tracked_key,
        )
        description = getattr(vrrp_group, "description", None)
        if description is not None:
            current["description"] = description
        return current

    def _get_current_vrrp_groups(self, gcs_device_info, interface_name, vlan=None):
        """Return the SDK ``vrrp_group`` objects for an interface as ``{"ipv4": .., "ipv6": ..}`` (None when absent)."""
        intf_obj = self._find_interface_obj(gcs_device_info, interface_name, vlan)
        groups = {"ipv4": None, "ipv6": None}  # type: Dict[str, Any]
        if intf_obj is None:
            return groups
        for family in ("ipv4", "ipv6"):
            family_obj = getattr(intf_obj, family, None)
            if family_obj is not None:
                groups[family] = getattr(family_obj, "vrrp_group", None)
        return groups

    def _configure_device_diff(self, gcs_device_info, configs):
        """
        Compare each VRRP interface entry against live state.

        Returns ``(changed_entries, before, after)``:
          - ``changed_entries``: the subset of *configs* whose VRRP groups are
            absent or differ field-for-field from live state — i.e. the exact
            interfaces to push (unchanged interfaces are left untouched).
          - ``before``/``after``: normalized per-interface dicts (keyed by
            interface label, then ipv4/ipv6) for the Ansible ``--diff``, limited
            to the changed interfaces.
        """
        changed_entries = []  # type: list
        before = {}  # type: Dict[str, Any]
        after = {}  # type: Dict[str, Any]

        for config in configs:
            interface_name = config.get("name")
            vlan = config.get("vlan")
            if not (config.get("vrrp_ipv4") or config.get("vrrp_ipv6")):
                continue
            label = interface_name if not vlan else "{}.{}".format(interface_name, vlan)
            groups = self._get_current_vrrp_groups(gcs_device_info, interface_name, vlan)

            entry_before = {}  # type: Dict[str, Any]
            entry_after = {}  # type: Dict[str, Any]
            entry_changed = False
            for family in ("ipv4", "ipv6"):
                family_cfg = config.get("vrrp_" + family)
                if not family_cfg:
                    continue
                desired = self._normalized_vrrp_from_config(family_cfg)
                current = self._normalized_vrrp_from_get(groups.get(family))
                entry_after[family] = desired
                entry_before[family] = self._project_to(current, desired) if current else {}
                if current is None or self._sparse_differs(desired, current):
                    entry_changed = True

            if entry_changed:
                changed_entries.append(config)
                before[label] = entry_before
                after[label] = entry_after

        return changed_entries, before, after

    @staticmethod
    def _record_device_diff(result, device_name, before, after, branch="edge"):
        """Append a ``diff_plan`` entry for *device_name* (redacted for display)."""
        result["diff_plan"].append(
            {
                "device": device_name,
                "branch": branch,
                "before": redact_sensitive_for_log(before),
                "after": redact_sensitive_for_log(after),
            }
        )

    @staticmethod
    def _entry_name(ent):
        """Format a ``{device, interface, vlan}`` entry as ``device:interface[.vlan]`` for logging."""
        suffix = (".%s" % ent["vlan"]) if ent.get("vlan") else ""
        return "%s:%s%s" % (ent.get("device", ""), ent.get("interface", ""), suffix)

    @staticmethod
    def _vrrp_interface_entries(device_name, configs):
        """Per-interface ``{device, interface, vlan}`` entries for every config row that carries VRRP."""
        return [
            {"device": device_name, "interface": config.get("name"), "vlan": config.get("vlan")}
            for config in configs
            if config.get("vrrp_ipv4") or config.get("vrrp_ipv6")
        ]

    @staticmethod
    def _get_existing_vrrp_state(gcs_device_info, interface_name, vlan=None):
        """
        Get existing VRRP state for an interface from device info.

        Args:
            gcs_device_info: Device info object from gsdk.get_device_info()
            interface_name: Name of the interface (e.g., 'GigabitEthernet7/0/0')
            vlan: Optional VLAN ID for subinterface VRRP

        Returns:
            dict: Dictionary with VRRP state for ipv4 and ipv6:
                  {'ipv4': {'enabled': bool, 'virtualRouterId': int},
                   'ipv6': {'enabled': bool, 'virtualRouterId': int}}
                  Returns None if interface not found or no VRRP configured.
        """
        vrrp_state = {"ipv4": None, "ipv6": None}

        intf_obj = VRRPInterfaceManager._find_interface_obj(gcs_device_info, interface_name, vlan)
        if intf_obj is None:
            LOG.debug(
                "_get_existing_vrrp_state: Interface object not found for %s%s",
                interface_name,
                f".{vlan}" if vlan else "",
            )
            return vrrp_state

        # Check IPv4 VRRP - API returns 'vrrp_group' not 'vrrp'
        ipv4_obj = getattr(intf_obj, "ipv4", None)
        if ipv4_obj:
            # The API returns VRRP data directly as 'vrrp_group' (not nested under 'vrrp')
            vrrp_group = getattr(ipv4_obj, "vrrp_group", None)
            LOG.debug(
                "_get_existing_vrrp_state: %s%s - IPv4 vrrp_group exists: %s",
                interface_name,
                f".{vlan}" if vlan else "",
                vrrp_group is not None,
            )
            if vrrp_group:
                enabled_value = getattr(vrrp_group, "enabled", None)
                vrrp_state["ipv4"] = {
                    "enabled": enabled_value,
                    "virtualRouterId": getattr(vrrp_group, "virtual_router_id", None),
                }
                LOG.info(
                    "_get_existing_vrrp_state: %s%s - IPv4 VRRP state: enabled=%s",
                    interface_name,
                    f".{vlan}" if vlan else "",
                    enabled_value,
                )

        # Check IPv6 VRRP - API returns 'vrrp_group' not 'vrrp'
        ipv6_obj = getattr(intf_obj, "ipv6", None)
        if ipv6_obj:
            vrrp_group = getattr(ipv6_obj, "vrrp_group", None)
            LOG.debug(
                "_get_existing_vrrp_state: %s%s - IPv6 vrrp_group exists: %s",
                interface_name,
                f".{vlan}" if vlan else "",
                vrrp_group is not None,
            )
            if vrrp_group:
                enabled_value = getattr(vrrp_group, "enabled", None)
                vrrp_state["ipv6"] = {
                    "enabled": enabled_value,
                    "virtualRouterId": getattr(vrrp_group, "virtual_router_id", None),
                }
                LOG.info(
                    "_get_existing_vrrp_state: %s%s - IPv6 VRRP state: enabled=%s",
                    interface_name,
                    f".{vlan}" if vlan else "",
                    enabled_value,
                )

        return vrrp_state

    def configure(self, config_yaml_file: str) -> dict:
        """
        Configure VRRP interfaces (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices
        """
        return self.configure_vrrp_interfaces(config_yaml_file)

    def deconfigure(self, config_yaml_file: str) -> dict:
        """
        Deconfigure VRRP interfaces (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status, deconfigured and skipped devices/interfaces
        """
        return self.deconfigure_vrrp_interfaces(config_yaml_file)

    def enable_vrrp_interfaces(self, vrrp_config_file: str) -> dict:
        """
        Enable existing VRRP interfaces for multiple devices concurrently (idempotent).

        This operation only enables VRRP that is already configured. It does not create
        new VRRP configurations. If VRRP is already enabled, the operation is skipped.

        Args:
            vrrp_config_file: Path to the YAML file containing VRRP interface references

        Returns:
            dict: Result with 'changed' status, enabled and skipped devices/interfaces

        Raises:
            ConfigurationError: If VRRP configuration doesn't exist or processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {
            "changed": False,
            "enabled_devices": [],
            "enabled_interfaces": [],
            "skipped_interfaces": [],
            "diff_plan": [],
        }

        try:
            # Load VRRP configurations
            vrrp_config_data = self.render_config_file(vrrp_config_file)
            output_config = {}

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect VRRP configurations per device
            for device_info in vrrp_config_data.get("vrrp_config") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )

                    LOG.info("[enable] Processing device: %s (ID: %s)", device_name, device_id)

                    # Get device info for idempotency check
                    gcs_device_info = self.gsdk.get_device_info(device_id)

                    # Process VRRP enable for this device
                    vrrp_to_enable = 0
                    vrrp_skipped = 0
                    device_before: Dict[str, Any] = {}
                    device_after: Dict[str, Any] = {}

                    for config in configs.get("interfaces", []):
                        interface_name = config.get("name")
                        vlan = config.get("vlan")
                        vrrp_ipv4 = config.get("vrrp_ipv4")
                        vrrp_ipv6 = config.get("vrrp_ipv6")

                        # Get existing VRRP state
                        existing_vrrp = self._get_existing_vrrp_state(gcs_device_info, interface_name, vlan)

                        # Check if any VRRP needs to be enabled
                        needs_enable = False
                        has_vrrp_config = False

                        # Check IPv4 VRRP
                        if vrrp_ipv4:
                            if existing_vrrp["ipv4"] is None:
                                raise ConfigurationError(
                                    f"VRRP IPv4 configuration does not exist on {interface_name}"
                                    f"{f'.{vlan}' if vlan else ''} for device '{device_name}'. "
                                    "Please configure VRRP first before enabling it."
                                )
                            has_vrrp_config = True
                            if existing_vrrp["ipv4"].get("enabled") is not True:
                                needs_enable = True
                                LOG.info(
                                    " ✓ IPv4 VRRP is disabled on %s%s, will enable",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            else:
                                LOG.info(
                                    " ✗ IPv4 VRRP already enabled on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )

                        # Check IPv6 VRRP
                        if vrrp_ipv6:
                            if existing_vrrp["ipv6"] is None:
                                raise ConfigurationError(
                                    f"VRRP IPv6 configuration does not exist on {interface_name}"
                                    f"{f'.{vlan}' if vlan else ''} for device '{device_name}'. "
                                    "Please configure VRRP first before enabling it."
                                )
                            has_vrrp_config = True
                            if existing_vrrp["ipv6"].get("enabled") is not True:
                                needs_enable = True
                                LOG.info(
                                    " ✓ IPv6 VRRP is disabled on %s%s, will enable",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            else:
                                LOG.info(
                                    " ✗ IPv6 VRRP already enabled on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )

                        if not has_vrrp_config:
                            LOG.warning(
                                " ✗ No VRRP configuration specified for %s%s, skipping",
                                interface_name,
                                f".{vlan}" if vlan else "",
                            )
                            vrrp_skipped += 1
                            result["skipped_interfaces"].append(
                                {
                                    "device": device_name,
                                    "interface": interface_name,
                                    "vlan": vlan,
                                    "reason": "No VRRP config specified",
                                }
                            )
                            continue

                        if needs_enable:
                            # Initialize device config if not already
                            if device_id not in output_config:
                                output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}}}

                            # Build config dict for template (no virtualRouterId needed for enable)
                            enable_config = {"name": interface_name}
                            if vlan:
                                enable_config["vlan"] = vlan

                            # Add vrrp_ipv4/vrrp_ipv6 keys (empty dict is fine; the builder only needs the key)
                            if vrrp_ipv4 and existing_vrrp["ipv4"] and existing_vrrp["ipv4"].get("enabled") is not True:
                                enable_config["vrrp_ipv4"] = {}

                            if vrrp_ipv6 and existing_vrrp["ipv6"] and existing_vrrp["ipv6"].get("enabled") is not True:
                                enable_config["vrrp_ipv6"] = {}

                            # Build payload directly (consistent with deconfigure)
                            self._apply_vrrp(output_config[device_id]["edge"], action="enable", **enable_config)

                            # Record the per-interface diff (enabling: false -> true)
                            label = interface_name if not vlan else "{}.{}".format(interface_name, vlan)
                            for fam in ("ipv4", "ipv6"):
                                if "vrrp_" + fam in enable_config:
                                    device_after.setdefault(label, {})[fam] = {"enabled": True}
                                    device_before.setdefault(label, {})[fam] = {"enabled": False}

                            vrrp_to_enable += 1
                            result["enabled_interfaces"].append(
                                {"device": device_name, "interface": interface_name, "vlan": vlan}
                            )
                        else:
                            vrrp_skipped += 1
                            result["skipped_interfaces"].append(
                                {
                                    "device": device_name,
                                    "interface": interface_name,
                                    "vlan": vlan,
                                    "reason": "VRRP already enabled",
                                }
                            )

                    LOG.info(
                        "Device %s summary: %d VRRP interface(s) to enable, %d skipped (already enabled)",
                        device_name,
                        vrrp_to_enable,
                        vrrp_skipped,
                    )

                    if device_id in output_config and (device_before or device_after):
                        self._record_device_diff(result, device_name, device_before, device_after)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except ConfigurationError:
                    raise
                except Exception as e:
                    LOG.error("Error enabling VRRP on device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Enable VRRP failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["enabled_devices"] = list(output_config.keys())
                LOG.info(
                    "VRRP enable completed: %d device(s) updated, %d interface(s) enabled, "
                    "%d interface(s) skipped (already enabled) (changed: %s)",
                    len(output_config),
                    len(result["enabled_interfaces"]),
                    len(result["skipped_interfaces"]),
                    result["changed"],
                )
            else:
                LOG.info("No VRRP changes needed - all interfaces already enabled (changed: %s)", result["changed"])

            return result

        except Exception as e:
            LOG.error("Error in VRRP interface enable: %s", str(e))
            raise ConfigurationError(f"VRRP interface enable failed: {str(e)}")

    def configure_vrrp_interfaces(self, vrrp_config_file: str) -> dict:
        """
        Configure VRRP interfaces for multiple devices concurrently.
        This method combines all VRRP configurations in a single API call per device.

        Args:
            vrrp_config_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices
            Note: Always returns changed=True when devices are configured since we push
            via PUT API. True idempotency would require comparing current vs desired state.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = new_apply_result(configured_interfaces=[], skipped_interfaces=[])

        try:
            # Load VRRP configurations
            vrrp_config_data = self.render_config_file(vrrp_config_file)
            output_config = {}

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect VRRP configurations per device
            for device_info in vrrp_config_data.get("vrrp_config") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )
                    # Collect interface names referenced in this device's VRRP configurations
                    referenced_interfaces = set()
                    for vrrp_config in configs.get("interfaces", []):
                        # Check main interface for interface reference
                        if vrrp_config.get("name"):
                            referenced_interfaces.add(vrrp_config["name"])
                        # Check subinterfaces for interface references
                        if vrrp_config.get("vlan"):
                            referenced_interfaces.add(vrrp_config["vlan"])

                    LOG.info("[configure] Processing device: %s (ID: %s)", device_name, device_id)
                    LOG.info("Referenced interfaces: %s", list(referenced_interfaces))

                    # Field-level idempotency: compare each VRRP interface against live
                    # state and push only the interfaces that are absent or drifted,
                    # leaving unchanged interfaces (and the rest of the device) untouched.
                    # The PUT is a merge, so a partial per-interface payload is safe.
                    gcs_device_info = self.gsdk.get_device_info(device_id)
                    changed_entries, before, after = self._configure_device_diff(
                        gcs_device_info, configs.get("interfaces", [])
                    )

                    all_entries = self._vrrp_interface_entries(device_name, configs.get("interfaces", []))
                    changed_keys = {(entry.get("name"), entry.get("vlan")) for entry in changed_entries}

                    if changed_entries:
                        edge = {"interfaces": {}}  # type: Dict[str, Any]
                        for entry in changed_entries:
                            self._apply_vrrp(edge, action="add", **entry)
                        output_config[device_id] = {"device_id": device_id, "edge": edge}
                        self._record_device_diff(result, device_name, before, after)
                        result["configured_devices"].append(device_name)
                        for ent in all_entries:
                            if (ent["interface"], ent["vlan"]) in changed_keys:
                                result["configured_interfaces"].append(ent)
                            else:
                                result["skipped_interfaces"].append(ent)
                        LOG.info(
                            "Device %s: %d of %d VRRP interface(s) changed, pushing only those",
                            device_name,
                            len(changed_entries),
                            len(all_entries),
                        )
                    else:
                        result["skipped_devices"].append(device_name)
                        result["skipped_interfaces"].extend(all_entries)
                        LOG.info(" ✓ No VRRP changes needed for %s, skipping", device_name)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error configuring device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Configuration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = bool(result["configured_devices"])
                LOG.info(
                    "VRRP configuration completed: %d device(s) configured, %d skipped (changed: %s)",
                    len(result["configured_devices"]),
                    len(result["skipped_devices"]),
                    result["changed"],
                )
            else:
                LOG.info(
                    "No VRRP changes needed - all devices already in desired state (changed: %s)",
                    result["changed"],
                )

            # Explicit per-interface lists for parity with deconfigure logging.
            configured_names = [self._entry_name(e) for e in result["configured_interfaces"]]
            skipped_names = [self._entry_name(e) for e in result["skipped_interfaces"]]
            LOG.info(
                "Configure completed: configured_interfaces=%s, skipped_interfaces=%s",
                configured_names,
                skipped_names,
            )

            return result
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Error in VRRP interface configuration: %s", str(e))
            raise ConfigurationError(f"VRRP interface configuration failed: {str(e)}")

    def deconfigure_vrrp_interfaces(self, vrrp_config_file: str) -> dict:
        """
        Deconfigure VRRP interfaces for multiple devices concurrently (idempotent).

        Checks if VRRP is already disabled before pushing configuration.
        Skips interfaces where VRRP is already disabled.

        Args:
            vrrp_config_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status, deconfigured and skipped devices/interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {
            "changed": False,
            "deconfigured_devices": [],
            "deconfigured_interfaces": [],
            "skipped_interfaces": [],
            "diff_plan": [],
        }

        try:
            # Load VRRP configurations
            vrrp_config_data = self.render_config_file(vrrp_config_file)
            output_config = {}

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect VRRP configurations per device
            for device_info in vrrp_config_data.get("vrrp_config") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(
                            f"Device '{device_name}' is not found in the current enterprise: "
                            f"{self.gsdk.enterprise_info['company_name']}. "
                            f"Please check device name and enterprise credentials."
                        )

                    LOG.info("[deconfigure] Processing device: %s (ID: %s)", device_name, device_id)

                    # Get device info for idempotency check
                    gcs_device_info = self.gsdk.get_device_info(device_id)

                    # Process VRRP removal for this device
                    vrrp_to_deconfigure = 0
                    vrrp_skipped = 0
                    device_before: Dict[str, Any] = {}
                    device_after: Dict[str, Any] = {}

                    for config in configs.get("interfaces", []):
                        interface_name = config.get("name")
                        vlan = config.get("vlan")
                        vrrp_ipv4 = config.get("vrrp_ipv4")
                        vrrp_ipv6 = config.get("vrrp_ipv6")

                        # Get existing VRRP state for idempotency check
                        existing_vrrp = self._get_existing_vrrp_state(gcs_device_info, interface_name, vlan)

                        # Check if any VRRP needs to be disabled
                        needs_deconfigure = False

                        # Check IPv4 VRRP
                        if vrrp_ipv4:
                            if existing_vrrp["ipv4"] and existing_vrrp["ipv4"].get("enabled") is True:
                                needs_deconfigure = True
                                LOG.info(
                                    " ✓ IPv4 VRRP is enabled on %s%s, will disable",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            elif existing_vrrp["ipv4"] and existing_vrrp["ipv4"].get("enabled") is False:
                                LOG.info(
                                    " ✗ IPv4 VRRP already disabled on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            else:
                                LOG.info(
                                    " ✗ No IPv4 VRRP configured on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )

                        # Check IPv6 VRRP
                        if vrrp_ipv6:
                            if existing_vrrp["ipv6"] and existing_vrrp["ipv6"].get("enabled") is True:
                                needs_deconfigure = True
                                LOG.info(
                                    " ✓ IPv6 VRRP is enabled on %s%s, will disable",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            elif existing_vrrp["ipv6"] and existing_vrrp["ipv6"].get("enabled") is False:
                                LOG.info(
                                    " ✗ IPv6 VRRP already disabled on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )
                            else:
                                LOG.info(
                                    " ✗ No IPv6 VRRP configured on %s%s, skipping",
                                    interface_name,
                                    f".{vlan}" if vlan else "",
                                )

                        if needs_deconfigure:
                            # Initialize device config if not already
                            if device_id not in output_config:
                                output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}}}

                            self._apply_vrrp(output_config[device_id]["edge"], action="delete", **config)

                            # Record the per-interface diff (disabling: true -> false)
                            label = interface_name if not vlan else "{}.{}".format(interface_name, vlan)
                            for fam in ("ipv4", "ipv6"):
                                if (
                                    config.get("vrrp_" + fam)
                                    and existing_vrrp[fam]
                                    and existing_vrrp[fam].get("enabled") is True
                                ):
                                    device_after.setdefault(label, {})[fam] = {"enabled": False}
                                    device_before.setdefault(label, {})[fam] = {"enabled": True}

                            vrrp_to_deconfigure += 1
                            result["deconfigured_interfaces"].append(
                                {"device": device_name, "interface": interface_name, "vlan": vlan}
                            )
                        else:
                            vrrp_skipped += 1
                            result["skipped_interfaces"].append(
                                {
                                    "device": device_name,
                                    "interface": interface_name,
                                    "vlan": vlan,
                                    "reason": "VRRP already disabled or not configured",
                                }
                            )

                    LOG.info(
                        "Device %s summary: %d VRRP interface(s) to deconfigure, %d skipped (already disabled)",
                        device_name,
                        vrrp_to_deconfigure,
                        vrrp_skipped,
                    )

                    if device_id in output_config and (device_before or device_after):
                        self._record_device_diff(result, device_name, device_before, device_after)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error deconfiguring device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Deconfiguration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["deconfigured_devices"] = list(output_config.keys())
                LOG.info(
                    "VRRP deconfiguration completed: %d device(s) updated, %d interface(s) deconfigured, "
                    "%d interface(s) skipped (changed: %s)",
                    len(output_config),
                    len(result["deconfigured_interfaces"]),
                    len(result["skipped_interfaces"]),
                    result["changed"],
                )

                # Explicit lists for consistency with global_config deconfigure logging
                deconfigured_names = [self._entry_name(e) for e in result["deconfigured_interfaces"]]
                skipped_names = [self._entry_name(e) for e in result["skipped_interfaces"]]
                LOG.info(
                    "Deconfigure completed: deconfigured_interfaces=%s, skipped_interfaces=%s",
                    deconfigured_names,
                    skipped_names,
                )
            else:
                LOG.info(
                    "No VRRP changes needed - all interfaces already disabled or not configured (changed: %s)",
                    result["changed"],
                )

            return result
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Error in VRRP interface deconfiguration: %s", str(e))
            raise ConfigurationError(f"VRRP interface deconfiguration failed: {str(e)}")
