"""
LAG Interfaces Manager for Graphiant Playbooks.

This module handles LAG (Link Aggregation Group) interface configuration management
for Graphiant Edge/Gateway devices.

Idempotency Support:
    - configure (add): Field-level idempotent. Each LAG's desired config (segment,
      alias, adminStatus, mtu, ipv4/ipv6, LACP, members, subinterfaces) is compared
      against live state (``get_device_info``); a LAG that is absent or drifted is
      pushed (a merge PUT), and a LAG already in the desired state is skipped. The
      comparison is biased toward "push" -- any field that cannot be read back from
      the device is treated as changed, so a real change is never silently dropped.
    - deconfigure: Skips LAGs that don't exist.
    - add_lag_members: Skips members already present in the LAG.
    - remove_lag_members: Skips members already removed from the LAG.
    - update_lacp_configs: Skips if LACP mode/timer already match desired state.
    - delete_lag_subinterfaces: Deletes specified subinterfaces.

Diff Support:
    All operations populate ``diff_plan`` (per-device before/after) so the module
    renders a readable Ansible ``--diff``. Pushes no-op under check mode
    (``gsdk.put_device_config`` logs the payload and skips the API write).
"""

import ipaddress
from typing import Any, Dict

from .base_manager import BaseManager
from .device_config_common import new_apply_result, redact_sensitive_for_log
from .exceptions import ConfigurationError
from .logger import setup_logger

LOG = setup_logger()


class LagInterfaceManager(BaseManager):

    # --- Desired-payload builders -----------------------------------------
    # Translate a config-file LAG entry into the ``edge`` PUT payload. These
    # replace the former Jinja2 template templates/lag_interfaces_template.yaml.
    # Notes the template handled implicitly:
    #   * ``true``/``false`` / ``1500`` became real booleans/ints after
    #     yaml.safe_load; the builders emit native Python types directly.
    #   * lagMember and subinterface keys were quoted (``"{{ id }}"``) so they
    #     parse back as *strings*, while inner values stay *ints*.
    #   * absent ``ipv4``/``ipv6`` fell back to a DHCP-disabled block.

    @staticmethod
    def _ip_block(address):
        """Build an ``ipv4``/``ipv6`` block: a static address when given, else DHCP disabled."""
        if address:
            return {"address": {"address": address}}
        return {"dhcp": {"dhcpClient": False}}

    @staticmethod
    def _resolve_admin_status(cfg):
        """
        Resolve the admin status for a LAG or subinterface the *same* way for the
        builder and the diff so they never disagree.

        ``adminStatus`` wins over ``enabled``; an explicit ``false`` is honored, but
        a missing or ``null`` value defaults to ``True``. Returns a bool.
        """
        for key in ("adminStatus", "enabled"):
            value = cfg.get(key)
            if value is not None:
                return bool(value)
        return True

    @staticmethod
    def _build_subinterface(sub):
        """
        Build one subinterface ``interface`` body (the ``add`` branch of the template).

        ``adminStatus`` falls back to ``enabled`` then ``True``; ``description``
        defaults to ``"<vlan>_<segment>"``; a missing ``segment`` renders as "".
        """
        vlan = sub.get("vlan")
        admin_status = LagInterfaceManager._resolve_admin_status(sub)
        segment = sub.get("segment")
        body = {
            "vlan": int(vlan) if vlan is not None else vlan,
            "description": sub.get("description") or "{}_{}".format(vlan, segment or ""),
            "adminStatus": admin_status,
            "segment": "" if segment is None else segment,
            "ipv4": LagInterfaceManager._ip_block(sub.get("ipv4")),
            "ipv6": LagInterfaceManager._ip_block(sub.get("ipv6")),
        }
        if "alias" in sub:
            body["alias"] = sub["alias"]
        return body

    @staticmethod
    def _build_lag_interface(name, action="add", **cfg):
        """
        Build the LAG payload for one config entry (formerly rendered by
        templates/lag_interfaces_template.yaml).

        Returns either:
          * ``{"interfaces": {<name>: {"interface": None}}}`` for ``delete_lag``
            (removes the main LAG interface), or
          * ``{"lagInterfaces": {<name>: {"interface": {...}}}}`` for every other
            action, with only the sections that action emits.
        """
        if action == "delete_lag":
            return {"interfaces": {name: {"interface": None}}}

        interface = {}  # type: Dict[str, Any]

        if action == "add":
            # An omitted segment renders as "" (the former Jinja template behavior),
            # keeping the generated payload identical to the template's.
            segment = cfg.get("segment")
            interface["segment"] = "" if segment is None else segment
            if "alias" in cfg:
                interface["alias"] = cfg["alias"]
            interface["adminStatus"] = LagInterfaceManager._resolve_admin_status(cfg)
            interface["mtu"] = cfg.get("mtu") or 1500
            interface["ipv4"] = LagInterfaceManager._ip_block(cfg.get("ipv4"))
            interface["ipv6"] = LagInterfaceManager._ip_block(cfg.get("ipv6"))
            interface["lacp"] = {
                "mode": cfg.get("lacpMode") or "ACTIVE",
                "timer": cfg.get("lacpTimer") or "SLOW",
            }

        if action == "update_lacp_configs":
            lacp = {}  # type: Dict[str, Any]
            if cfg.get("lacpMode"):
                lacp["mode"] = cfg["lacpMode"]
            if cfg.get("lacpTimer"):
                lacp["timer"] = cfg["lacpTimer"]
            interface["lacp"] = lacp

        if cfg.get("lagMembers") and action in ("add", "add_lag_members", "remove_lag_members"):
            members = {}  # type: Dict[str, Any]
            for interface_id in cfg.get("interfaceMemberIds", []):
                # add/add_lag_members send the member id; remove_lag_members sends {}.
                members[str(interface_id)] = {"interface": interface_id} if action in ("add", "add_lag_members") else {}
            interface["lagMembers"] = members

        # Accept both spellings (``subinterfaces`` / ``sub_interfaces``) that the
        # diff and InterfaceManager accept, so a config using either still pushes.
        subinterfaces = cfg.get("subinterfaces") or cfg.get("sub_interfaces")
        if subinterfaces and action in ("add", "delete"):
            subs = {}  # type: Dict[str, Any]
            for sub in subinterfaces:
                key = str(sub.get("vlan"))
                if action == "delete":
                    subs[key] = {"interface": None}
                else:  # add
                    subs[key] = {"interface": LagInterfaceManager._build_subinterface(sub)}
            interface["subinterfaces"] = subs

        return {"lagInterfaces": {name: {"interface": interface}}}

    def _apply_lag(self, config_payload, action="add", **kwargs):
        """
        Build a LAG payload and merge it into ``config_payload``.

        Replaces the former ``config_utils.lag_interfaces`` (template-based) hop.
        ``delete_lag`` targets the top-level ``interfaces`` section (removing the
        main LAG); every other action targets ``lagInterfaces``.
        """
        name = kwargs.pop("name", None)
        if not name:
            raise ConfigurationError("Missing required parameters: ['name']")
        LOG.info("LAG on interfaces: %s %s", action.upper(), name)

        try:
            result = self._build_lag_interface(name, action=action, **kwargs)
            if "lagInterfaces" in result:
                config_payload.setdefault("lagInterfaces", {})
                config_payload["lagInterfaces"].update(result["lagInterfaces"])
            elif "interfaces" in result:
                config_payload.setdefault("interfaces", {})
                config_payload["interfaces"].update(result["interfaces"])
        except ConfigurationError:
            raise
        except Exception as e:  # pylint: disable=broad-except
            LOG.error("Failed to process LAG on interfaces %s: %s", name, str(e))
            raise ConfigurationError(f"LAG on interfaces processing failed: {str(e)}")

    # --- Field-level idempotency / diff helpers ---------------------------
    # Compare each device's desired LAG config against live GET state so
    # unchanged LAGs are skipped and ``--diff`` shows an honest before/after.
    # Desired is normalized from the raw config (sparse: only the fields the
    # builder sends); current is normalized from the SDK GET model
    # (``ManaV2Interface``: ``lan`` holds the segment, ``enabled`` the admin
    # status, ``lag_interface.members`` the member ids, and
    # ``lag_interface.lacp_config`` the LACP mode/timer). Only keys present in
    # the desired side are compared (see ``_sparse_differs``), so a field the
    # config omits never trips a false change; any field that cannot be read
    # back is treated as changed (bias to push), so a real change is never
    # silently dropped.

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
                if LagInterfaceManager._sparse_differs(desired_value, existing_value):
                    return True
            elif desired_value != existing_value:
                return True
        return False

    @staticmethod
    def _project_to(existing, desired):
        """
        Restrict *existing* to only the keys present in *desired* (recursively).

        Builds the ``--diff`` ``before`` so it mirrors the sparse ``after`` and
        shows only the fields this run would change. A merge PUT never removes
        fields the config omits, so ``before`` must not imply otherwise.
        """
        if not isinstance(desired, dict) or not isinstance(existing, dict):
            return existing
        projected = {}  # type: Dict[str, Any]
        for key, desired_value in desired.items():
            if key not in existing:
                continue
            existing_value = existing[key]
            if isinstance(desired_value, dict) and isinstance(existing_value, dict):
                projected[key] = LagInterfaceManager._project_to(existing_value, desired_value)
            else:
                projected[key] = existing_value
        return projected

    @staticmethod
    def _canonical_ip(value):
        """
        Canonicalize an ``address/prefix`` string so equal IPs compare equal.

        The device GET can return a different textual form of the same address
        than the config (e.g. IPv6 ``2001:10:1::1/64`` vs ``2001:10:1:0::1/64``),
        which would otherwise show as drift on every run. Only the comparison is
        canonicalized -- the pushed payload still uses the raw config string.
        Non-IP values are returned unchanged.
        """
        if not value or not isinstance(value, str):
            return value
        ip, sep, prefix = value.partition("/")
        try:
            ip = str(ipaddress.ip_address(ip.strip()))
        except ValueError:
            return value
        return ip + sep + prefix

    @staticmethod
    def _norm_ip_from_config(value):
        """
        Desired IP intent from config, matching what the builder sends.

        A config address is a static IP (compared by canonicalized ``address``);
        an omitted address makes the builder send ``dhcp.dhcpClient: false`` (DHCP
        disabled, no static address) -- note this differs from a plain interface,
        where an omitted address enables DHCP.
        """
        if value:
            return {"address": LagInterfaceManager._canonical_ip(value)}
        return {"dhcpClient": False}

    @staticmethod
    def _norm_ip_from_get(addr):
        """Current IP state from an SDK ``ManaV2InterfaceAddress`` (``address`` / ``dhcp_client``)."""
        address = getattr(addr, "address", None) if addr is not None else None
        if address:
            return {"address": LagInterfaceManager._canonical_ip(address)}
        return {"dhcpClient": bool(getattr(addr, "dhcp_client", False)) if addr is not None else False}

    @staticmethod
    def _find_lag_interface_obj(gcs_device_info, lag_name):
        """Return the SDK interface object for ``lag_name`` from device info, or None."""
        device = getattr(gcs_device_info, "device", None)
        for interface in getattr(device, "interfaces", None) or []:
            if getattr(interface, "name", None) == lag_name:
                return interface
        return None

    @staticmethod
    def _normalized_sub_from_config(sub):
        """
        Sparse desired-state dict for one subinterface from config.

        ``segment``, ``description`` and ``alias`` are compared only when the config
        sets them (mirroring ``InterfaceManager`` and the LAG-level ``segment``):
        the builder renders an omitted ``segment`` as "" and auto-synthesizes an
        omitted ``description``, so comparing either when unset would report drift
        on every run. When the user *does* set a ``description``, it is compared so a
        description-only edit is still pushed.
        """
        desired = {
            "adminStatus": LagInterfaceManager._resolve_admin_status(sub),
            "ipv4": LagInterfaceManager._norm_ip_from_config(sub.get("ipv4")),
            "ipv6": LagInterfaceManager._norm_ip_from_config(sub.get("ipv6")),
        }  # type: Dict[str, Any]
        if sub.get("segment") is not None:
            desired["segment"] = sub["segment"]
        if sub.get("description") is not None:
            desired["description"] = sub["description"]
        if sub.get("alias") is not None:
            desired["alias"] = sub["alias"]
        return desired

    @staticmethod
    def _normalized_sub_from_get(sub_obj):
        """Current-state dict for one subinterface SDK object, mirroring ``_normalized_sub_from_config``."""
        enabled = getattr(sub_obj, "enabled", None)
        current = {
            "adminStatus": True if enabled is None else bool(enabled),
            "ipv4": LagInterfaceManager._norm_ip_from_get(getattr(sub_obj, "ipv4", None)),
            "ipv6": LagInterfaceManager._norm_ip_from_get(getattr(sub_obj, "ipv6", None)),
        }  # type: Dict[str, Any]
        segment = getattr(sub_obj, "lan", None)
        if segment is not None:
            current["segment"] = segment
        description = getattr(sub_obj, "description", None)
        if description is not None:
            current["description"] = description
        alias = getattr(sub_obj, "alias", None)
        if alias is not None:
            current["alias"] = alias
        return current

    @staticmethod
    def _normalized_lag_from_config(config):
        """
        Sparse desired-state dict for a LAG ``add`` from its raw config entry.

        Only fields the builder sends are included. ``segment``, ``members`` and
        ``subinterfaces`` are compared only when the config carries them; ``alias``
        only when explicitly set. ``description`` is never compared (the builder
        auto-synthesizes it, so it must not count as drift). An omitted ``segment``
        is not compared because the builder renders it as "" (a merge PUT that
        never asserts a value), so comparing it would report perpetual drift.
        """
        desired = {
            "adminStatus": LagInterfaceManager._resolve_admin_status(config),
            "mtu": config.get("mtu") or 1500,
            "ipv4": LagInterfaceManager._norm_ip_from_config(config.get("ipv4")),
            "ipv6": LagInterfaceManager._norm_ip_from_config(config.get("ipv6")),
            "lacp": {
                "mode": (config.get("lacpMode") or "ACTIVE").upper(),
                "timer": (config.get("lacpTimer") or "SLOW").upper(),
            },
        }  # type: Dict[str, Any]
        if config.get("segment") is not None:
            desired["segment"] = config["segment"]
        if config.get("alias") is not None:
            desired["alias"] = config["alias"]
        if config.get("lagMembers"):
            desired["members"] = sorted(config.get("interfaceMemberIds", []))
        subs = config.get("subinterfaces") or config.get("sub_interfaces")
        if subs:
            desired["subinterfaces"] = {
                str(sub.get("vlan")): LagInterfaceManager._normalized_sub_from_config(sub) for sub in subs
            }
        return desired

    @staticmethod
    def _normalized_lag_from_get(interface_obj):
        """Current-state dict for a LAG main interface SDK object; None when absent."""
        if interface_obj is None:
            return None
        lag = getattr(interface_obj, "lag_interface", None)
        lacp = getattr(lag, "lacp_config", None) if lag else None
        enabled = getattr(interface_obj, "enabled", None)
        # Prefer the configured MTU over the operational one when the GET exposes it.
        mtu = getattr(interface_obj, "configured_max_transmission_unit", None)
        if mtu is None:
            mtu = getattr(interface_obj, "max_transmission_unit", None)
        current = {
            "segment": getattr(interface_obj, "lan", None),
            "adminStatus": True if enabled is None else bool(enabled),
            "mtu": mtu,
            "ipv4": LagInterfaceManager._norm_ip_from_get(getattr(interface_obj, "ipv4", None)),
            "ipv6": LagInterfaceManager._norm_ip_from_get(getattr(interface_obj, "ipv6", None)),
            "lacp": {
                "mode": (getattr(lacp, "mode", None) or "").upper(),
                "timer": (getattr(lacp, "timer", None) or "").upper(),
            },
        }  # type: Dict[str, Any]
        alias = getattr(interface_obj, "alias", None)
        if alias is not None:
            current["alias"] = alias
        members = getattr(lag, "members", None) if lag else None
        current["members"] = sorted(int(m) for m in (members or []))
        current["subinterfaces"] = {
            str(getattr(sub_obj, "vlan", None)): LagInterfaceManager._normalized_sub_from_get(sub_obj)
            for sub_obj in getattr(interface_obj, "subinterfaces", None) or []
        }
        return current

    def _lag_add_diff(self, interface_obj, config):
        """
        Compare one LAG's desired ``add`` config against live state.

        Returns ``(changed, before, after)``: ``changed`` is True when the LAG is
        absent or any compared field drifts; ``before``/``after`` are the sparse
        normalized dicts for ``--diff`` (``before`` projected to the desired keys).

        ``members`` use subset semantics (desired ⊆ live) rather than exact match:
        the push is a merge PUT that can only add members, so a LAG whose live
        members already include every desired member is not drifted. Comparing
        exactly would report a perpetual change whenever the device carries extra
        members the config omits. This mirrors how ``subinterfaces`` already behave
        (the sparse compare only looks at the vlans the config lists).
        """
        desired = self._normalized_lag_from_config(config)
        current = self._normalized_lag_from_get(interface_obj)
        if current is None:
            return True, {}, desired
        # Members are compared as a subset; the rest with sparse (exact) semantics.
        members_changed = "members" in desired and not set(desired["members"]).issubset(
            set(current.get("members") or [])
        )
        rest = {key: value for key, value in desired.items() if key != "members"}
        changed = members_changed or self._sparse_differs(rest, current)
        if changed:
            self._log_lag_drift(config.get("name"), rest, current, members_changed)
        before = self._project_to(current, desired)
        return changed, before, desired

    @staticmethod
    def _log_lag_drift(lag_name, desired_rest, current, members_changed):
        """
        Log which field drove a LAG to be reported as changed, at INFO.

        A perpetual ``changed`` (e.g. a field the device GET never reports back, so
        the bias-to-push treats it as drifted every run) is otherwise opaque; naming
        the first drifted field makes it debuggable.
        """
        if members_changed:
            LOG.info("[add] LAG '%s' drift: members (desired not a subset of live)", lag_name)
            return
        for key, desired_value in desired_rest.items():
            if LagInterfaceManager._sparse_differs({key: desired_value}, current):
                LOG.info(
                    "[add] LAG '%s' drift: field '%s' desired=%r current=%r",
                    lag_name,
                    key,
                    desired_value,
                    current.get(key),
                )
                return

    @staticmethod
    def _action_diff_blocks(action, config, existing_lag):
        """
        Build ``(before, after)`` diff blocks for a non-``add`` LAG action.

        ``existing_lag`` is the ``_get_existing_lag_info`` entry for the LAG.
        ``config`` has already been filtered to the entries this run will push
        (only new members, only existing subinterfaces, etc.).
        """
        existing = existing_lag or {}
        if action in ("add_lag_members", "remove_lag_members"):
            existing_ids = set(existing.get("member_ids") or set())
            delta = set(config.get("interfaceMemberIds") or [])
            after_ids = (existing_ids | delta) if action == "add_lag_members" else (existing_ids - delta)
            return {"members": sorted(existing_ids)}, {"members": sorted(after_ids)}
        if action == "update_lacp_configs":
            existing_lacp = existing.get("lacp_config") or {}
            before = {"mode": existing_lacp.get("mode"), "timer": existing_lacp.get("timer")}
            after = {}  # type: Dict[str, Any]
            if config.get("lacpMode"):
                after["mode"] = config["lacpMode"]
            if config.get("lacpTimer"):
                after["timer"] = config["lacpTimer"]
            return {"lacp": before}, {"lacp": after}
        if action == "delete":
            vlans = [str(sub.get("vlan")) for sub in config.get("subinterfaces") or []]
            return (
                {"subinterfaces": {vlan: "present" for vlan in vlans}},
                {"subinterfaces": {vlan: None for vlan in vlans}},
            )
        return {}, {}

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
    def _get_existing_lag_info(gcs_device_info):
        """
        Get existing LAG interface information from device info.

        LAG interfaces are regular interfaces in the device.interfaces array
        that have the lag_interface property set. Subinterfaces are also captured
        with their aliases (name format: LAG1.101).

        Args:
            gcs_device_info: Device info object from gsdk.get_device_info()

        Returns:
            dict: Dictionary mapping LAG name to its properties including subinterfaces
                  e.g., {'LAG1': {'alias': 'LAG1', 'subinterfaces': {101: {'alias': 'LAG1-101'}}}}
        """
        existing_lags = {}
        if not hasattr(gcs_device_info, "device"):
            return existing_lags

        device = gcs_device_info.device

        # First pass: Find all LAG main interfaces and their nested subinterfaces
        if hasattr(device, "interfaces") and device.interfaces:
            # Debug: Log all interface names that contain 'LAG'
            lag_related_names = [
                getattr(i, "name", "N/A") for i in device.interfaces if "LAG" in str(getattr(i, "name", ""))
            ]
            LOG.info("_get_existing_lag_info: All LAG-related interface names: %s", lag_related_names)
            for interface in device.interfaces:
                if hasattr(interface, "lag_interface") and interface.lag_interface:
                    interface_name = getattr(interface, "name", None)
                    if interface_name:
                        # Get LAG member IDs and LACP config if available
                        lag_member_ids = set()
                        lacp_config = {}
                        lag_intf_obj = getattr(interface, "lag_interface", None)
                        if lag_intf_obj:
                            if hasattr(lag_intf_obj, "members") and lag_intf_obj.members:
                                for member in lag_intf_obj.members:
                                    # Members can be integers (the ID directly) or objects with an id attribute
                                    if isinstance(member, int):
                                        lag_member_ids.add(member)
                                    else:
                                        member_id = getattr(member, "id", None) or getattr(member, "interface_id", None)
                                        if member_id:
                                            lag_member_ids.add(member_id)
                                LOG.info(
                                    "_get_existing_lag_info: LAG '%s' has %d member(s): %s",
                                    interface_name,
                                    len(lag_member_ids),
                                    list(lag_member_ids),
                                )
                            # Get LACP config (mode, timer)
                            lacp_cfg_obj = getattr(lag_intf_obj, "lacp_config", None)
                            if lacp_cfg_obj:
                                lacp_config = {
                                    "mode": getattr(lacp_cfg_obj, "mode", None),
                                    "timer": getattr(lacp_cfg_obj, "timer", None),
                                }
                                LOG.info(
                                    "_get_existing_lag_info: LAG '%s' LACP config: %s", interface_name, lacp_config
                                )
                        existing_lags[interface_name] = {
                            "alias": getattr(interface, "alias", None),
                            "id": getattr(interface, "id", None),
                            "subinterfaces": {},
                            "member_ids": lag_member_ids,
                            "lacp_config": lacp_config,
                        }
                        # Debug: Log all attributes of the LAG interface to find subinterfaces
                        lag_attrs = [
                            attr
                            for attr in dir(interface)
                            if not attr.startswith("_") and not callable(getattr(interface, attr, None))
                        ]
                        LOG.debug("_get_existing_lag_info: LAG '%s' attributes: %s", interface_name, lag_attrs)
                        # Check for subinterfaces as a nested property on the LAG interface
                        # Note: The attribute is 'subinterfaces' (no underscore)
                        subinterfaces_list = getattr(interface, "subinterfaces", None)
                        if subinterfaces_list:
                            for sub_intf in subinterfaces_list:
                                sub_vlan = getattr(sub_intf, "vlan", None)
                                sub_alias = getattr(sub_intf, "alias", None)
                                if sub_vlan is not None:
                                    existing_lags[interface_name]["subinterfaces"][sub_vlan] = {
                                        "alias": sub_alias,
                                        "id": getattr(sub_intf, "id", None),
                                    }
                                    LOG.info(
                                        "_get_existing_lag_info: Found nested subinterface vlan %s "
                                        "with alias '%s' on LAG '%s'",
                                        sub_vlan,
                                        sub_alias,
                                        interface_name,
                                    )

            # Second pass: Find all LAG subinterfaces as separate entries (format: LAG1.101)
            # Some APIs may return subinterfaces as separate interface entries
            for interface in device.interfaces:
                interface_name = getattr(interface, "name", None)
                if interface_name and "." in interface_name:
                    # This is a subinterface, check if parent is a LAG
                    parent_name, vlan_str = interface_name.rsplit(".", 1)
                    if parent_name in existing_lags:
                        try:
                            vlan = int(vlan_str)
                            # Only add if not already found via nested property
                            if vlan not in existing_lags[parent_name]["subinterfaces"]:
                                interface_alias = getattr(interface, "alias", None)
                                existing_lags[parent_name]["subinterfaces"][vlan] = {
                                    "alias": interface_alias,
                                    "id": getattr(interface, "id", None),
                                }
                                LOG.info(
                                    "_get_existing_lag_info: Found subinterface %s with alias '%s'",
                                    interface_name,
                                    interface_alias,
                                )
                        except ValueError:
                            pass  # Not a valid vlan number

        if existing_lags:
            LOG.info("_get_existing_lag_info: Found existing LAGs: %s", list(existing_lags.keys()))

        return existing_lags

    def configure(self, config_yaml_file: str) -> dict:  # pylint: disable=arguments-renamed
        """
        Configure LAG interfaces for multiple devices concurrently (field-level idempotent -
        compares each LAG's desired config against live state and pushes only LAGs that are
        absent or drifted; unchanged LAGs are skipped).

        Automatically handles duplicate alias assignments by removing alias from payload when
        it matches existing (an API-error workaround). Subinterface aliases are also handled
        to prevent duplicate alias errors.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of configured device names.
                - created_lags (list): LAGs that were newly created.
                - updated_lags (list): LAGs that were updated.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.configure_lag_interfaces(config_yaml_file, action="add")

    def deconfigure(self, config_yaml_file: str) -> dict:  # pylint: disable=arguments-renamed
        """
        Deconfigure LAG interfaces for multiple devices concurrently (idempotent).

        Deletes subinterfaces first, then removes the LAG. Skips LAGs that
        don't exist on the device.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - deconfigured_devices (list): List of affected device names.
                - deconfigured_lags (list): LAGs that were removed.
                - skipped_lags (list): LAGs that were skipped (not found).

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.deconfigure_lag_interfaces(config_yaml_file)

    def add_lag_members(self, config_yaml_file: str) -> dict:
        """
        Add interface members to an existing LAG for multiple devices (idempotent).

        Skips members that are already present in the LAG. If all specified
        members are already added, no API call is made for that LAG.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device names.
                - created_lags (list): Empty for this operation.
                - updated_lags (list): LAGs that had members added.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.configure_lag_interfaces(config_yaml_file, action="add_lag_members")

    def remove_lag_members(self, config_yaml_file: str) -> dict:
        """
        Remove interface members from an existing LAG for multiple devices (idempotent).

        Skips members that are already removed from the LAG. If all specified
        members are already absent, no API call is made for that LAG.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device names.
                - created_lags (list): Empty for this operation.
                - updated_lags (list): LAGs that had members removed.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.configure_lag_interfaces(config_yaml_file, action="remove_lag_members")

    def update_lacp_configs(self, config_yaml_file: str) -> dict:
        """
        Update LACP parameters (mode/timer) for LAGs across devices (idempotent).

        Compares current LACP mode and timer with desired values. Skips LAGs
        where the configuration already matches. Case-insensitive comparison
        is used for mode and timer values.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device names.
                - created_lags (list): Empty for this operation.
                - updated_lags (list): LAGs that had LACP config updated.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        return self.configure_lag_interfaces(config_yaml_file, action="update_lacp_configs")

    def delete_lag_subinterfaces(self, config_yaml_file: str) -> dict:
        """
        Delete VLAN subinterfaces under a LAG for multiple devices concurrently (idempotent).

        Skips deletion if:
        - The LAG does not exist.
        - The subinterface does not exist.
        - All specified subinterfaces are already deleted.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device names.
                - updated_lags (list): LAGs that had subinterfaces deleted.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        return self.configure_lag_interfaces(config_yaml_file, action="delete")

    def configure_lag_interfaces(self, config_yaml_file: str, action: str = "add") -> dict:
        """
        Configure/update LAG interfaces for multiple devices concurrently.

        This is the core method that handles all LAG configuration operations. All actions
        have built-in idempotency checks:
            - add: Field-level idempotent - compares each LAG's desired config against live
              state and pushes only LAGs that are absent or drifted (bias to push on any
              field that cannot be read back). Handles duplicate aliases automatically.
            - add_lag_members: Skips already-present members.
            - remove_lag_members: Skips already-absent members.
            - update_lacp_configs: Skips if mode/timer already match.
            - delete: Deletes subinterfaces under LAG, skipping ones that don't exist.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.
            action: Which operation to run (``add`` / ``add_lag_members`` /
                ``remove_lag_members`` / ``update_lacp_configs`` / ``delete``); selects
                which sections the Python payload builder emits.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of configured device names.
                - created_lags (list): LAGs newly created (for 'add' action).
                - updated_lags (list): LAGs updated or modified.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        try:
            result: Dict[str, Any] = new_apply_result(
                created_lags=[],
                updated_lags=[],
                skipped_lags=[],
            )

            config_data = self.render_config_file(config_yaml_file)
            output_config = {}
            device_configs: Dict[str, Any] = {}
            # Cache for device info to avoid redundant API calls
            device_info_cache = {}

            if "lagInterfaces" not in config_data:
                LOG.warning("No LAG interfaces configuration found in %s", config_yaml_file)
                return result

            for device_info in config_data.get("lagInterfaces") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = []
                    device_configs[device_name].extend(config_list)

            for device_name, configs in device_configs.items():
                LOG.info("Processing device: %s (%d LAG config(s))", device_name, len(configs))

                # Get device_id once per device
                device_id = self.gsdk.get_device_id(device_name)
                if device_id is None:
                    raise ConfigurationError(
                        f"Device '{device_name}' is not found in the current enterprise: "
                        f"{self.gsdk.enterprise_info['company_name']}. "
                        "Please check device name and enterprise credentials."
                    )

                # Get device info once per device (use cache if available)
                if device_id not in device_info_cache:
                    device_info_cache[device_id] = self.gsdk.get_device_info(device_id)
                gcs_device_info = device_info_cache[device_id]

                # Get existing LAG info once per device
                existing_lags = self._get_existing_lag_info(gcs_device_info)

                # Per-device --diff accumulators (keyed by LAG name).
                device_before: Dict[str, Any] = {}
                device_after: Dict[str, Any] = {}

                for config in configs:
                    try:
                        lag_name = config.get("name")

                        # If LAG already exists, check if alias needs to be removed to avoid
                        # "cannot assign alias LAG1 to LAG1 as that alias is in use" error
                        if lag_name in existing_lags:
                            existing_lag_info = existing_lags[lag_name]
                            existing_alias = existing_lag_info.get("alias")
                            config_alias = config.get("alias")

                            # If alias in config matches existing alias, remove it
                            # to avoid the duplicate alias error during update
                            if config_alias and config_alias == existing_alias:
                                LOG.info(
                                    "Removing unchanged alias '%s' from LAG '%s' config "
                                    "to avoid duplicate alias error",
                                    config_alias,
                                    lag_name,
                                )
                                config.pop("alias", None)

                            # Also check subinterface aliases
                            existing_subinterfaces = existing_lag_info.get("subinterfaces", {})
                            LOG.info("Existing subinterfaces for LAG '%s': %s", lag_name, existing_subinterfaces)
                            _subinterfaces = config.get("subinterfaces") or config.get("sub_interfaces")
                            if _subinterfaces:
                                LOG.info(
                                    "Config subinterfaces for LAG '%s': %s",
                                    lag_name,
                                    [{"vlan": s.get("vlan"), "alias": s.get("alias")} for s in _subinterfaces],
                                )
                                for subinterface in _subinterfaces:
                                    vlan = subinterface.get("vlan")
                                    # Convert vlan to int for comparison (existing_subinterfaces keys are ints)
                                    try:
                                        vlan_int = int(vlan) if vlan is not None else None
                                    except (ValueError, TypeError):
                                        vlan_int = None
                                    if vlan_int and vlan_int in existing_subinterfaces:
                                        existing_sub_alias = existing_subinterfaces[vlan_int].get("alias")
                                        config_sub_alias = subinterface.get("alias")
                                        if config_sub_alias and config_sub_alias == existing_sub_alias:
                                            LOG.info(
                                                "Removing unchanged alias '%s' from LAG '%s' "
                                                "subinterface vlan %s to avoid duplicate alias error",
                                                config_sub_alias,
                                                lag_name,
                                                vlan,
                                            )
                                            subinterface.pop("alias", None)

                        # Get the interface IDs for the interface members
                        config["interfaceMemberIds"] = []
                        lag_members_config = config.get("lagMembers", [])

                        # Check if lagMembers is required but not specified
                        if action in ("add_lag_members", "remove_lag_members") and not lag_members_config:
                            LOG.warning(
                                "[%s] No 'lagMembers' specified for LAG '%s' on device '%s'. "
                                "Skipping LAG member operation.",
                                action,
                                lag_name,
                                device_name,
                            )
                            # For add action, we still process the LAG (just without members)
                            # For add_lag_members/remove_lag_members, skip entirely
                            if action in ("add_lag_members", "remove_lag_members"):
                                result["skipped_lags"].append({"device": device_name, "lag": lag_name})
                                continue

                        found_member_names = set()
                        for interface_info in gcs_device_info.device.interfaces:
                            if interface_info.name in lag_members_config:
                                config["interfaceMemberIds"].append(interface_info.id)
                                found_member_names.add(interface_info.name)

                        # Warn about configured member names that don't exist on the device
                        # so a typo isn't silently dropped (which would make the task report
                        # a no-op instead of the intended member change).
                        missing_member_names = [name for name in lag_members_config if name not in found_member_names]
                        if missing_member_names:
                            LOG.warning(
                                "[%s] LAG '%s' on device '%s': ignoring member interface(s) "
                                "not found on the device: %s",
                                action,
                                lag_name,
                                device_name,
                                missing_member_names,
                            )

                        # Get existing member IDs for idempotency checks
                        existing_member_ids = existing_lags.get(lag_name, {}).get("member_ids", set())

                        # Idempotency check for add_lag_members:
                        # Only include member IDs that are NOT already in the LAG
                        if action == "add_lag_members" and lag_name in existing_lags:
                            LOG.info(
                                "[add_lag_members] Existing member IDs in LAG '%s': %s",
                                lag_name,
                                list(existing_member_ids),
                            )
                            original_member_ids = config["interfaceMemberIds"][:]
                            config["interfaceMemberIds"] = [
                                mid for mid in config["interfaceMemberIds"] if mid not in existing_member_ids
                            ]
                            skipped_ids = set(original_member_ids) - set(config["interfaceMemberIds"])
                            if skipped_ids:
                                LOG.info(
                                    "[add_lag_members] Skipping already added members to LAG '%s' "
                                    "on device '%s': %s",
                                    lag_name,
                                    device_name,
                                    list(skipped_ids),
                                )
                            if not config["interfaceMemberIds"]:
                                LOG.info(
                                    "[add_lag_members] All members already added to LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                result["skipped_lags"].append({"device": device_name, "lag": lag_name})
                                continue  # Skip this LAG config, nothing to add

                        # Idempotency check for remove_lag_members:
                        # Only include member IDs that actually exist in the LAG
                        if action == "remove_lag_members" and lag_name in existing_lags:
                            LOG.info(
                                "[remove_lag_members] Existing member IDs in LAG '%s': %s",
                                lag_name,
                                list(existing_member_ids),
                            )
                            original_member_ids = config["interfaceMemberIds"][:]
                            config["interfaceMemberIds"] = [
                                mid for mid in config["interfaceMemberIds"] if mid in existing_member_ids
                            ]
                            skipped_ids = set(original_member_ids) - set(config["interfaceMemberIds"])
                            if skipped_ids:
                                LOG.info(
                                    "[remove_lag_members] Skipping already removed members from LAG '%s' "
                                    "on device '%s': %s",
                                    lag_name,
                                    device_name,
                                    list(skipped_ids),
                                )
                            if not config["interfaceMemberIds"]:
                                LOG.info(
                                    "[remove_lag_members] All members already removed from LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                result["skipped_lags"].append({"device": device_name, "lag": lag_name})
                                continue  # Skip this LAG config, nothing to remove

                        # Idempotency check for update_lacp_configs:
                        # Skip if LACP config (mode, timer) matches existing config
                        if action == "update_lacp_configs" and lag_name in existing_lags:
                            existing_lacp = existing_lags[lag_name].get("lacp_config", {})
                            # Config uses lacpMode/lacpTimer (not nested lacpConfigs)
                            desired_mode = config.get("lacpMode")
                            desired_timer = config.get("lacpTimer")
                            existing_mode = existing_lacp.get("mode")
                            existing_timer = existing_lacp.get("timer")

                            LOG.info(
                                "[update_lacp_configs] LAG '%s' - Existing LACP: mode=%s, timer=%s | "
                                "Desired LACP: mode=%s, timer=%s",
                                lag_name,
                                existing_mode,
                                existing_timer,
                                desired_mode,
                                desired_timer,
                            )

                            # Check if both mode and timer match (case-insensitive comparison)
                            # If desired is not specified (None), we can't compare, so don't skip
                            if desired_mode is None and desired_timer is None:
                                LOG.warning(
                                    "[update_lacp_configs] No lacpMode/lacpTimer specified for LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                result["skipped_lags"].append({"device": device_name, "lag": lag_name})
                                continue  # Skip - nothing to update

                            mode_matches = desired_mode is None or (
                                existing_mode and desired_mode.upper() == existing_mode.upper()
                            )
                            timer_matches = desired_timer is None or (
                                existing_timer and desired_timer.upper() == existing_timer.upper()
                            )

                            if mode_matches and timer_matches:
                                LOG.info(
                                    "[update_lacp_configs] LACP config already matches for LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                result["skipped_lags"].append({"device": device_name, "lag": lag_name})
                                continue  # Skip this LAG config, nothing to update

                        # Idempotency check for delete action (delete_lag_subinterfaces):
                        # Only delete subinterfaces that actually exist
                        if action == "delete":
                            # Check if LAG exists
                            if lag_name not in existing_lags:
                                LOG.info(
                                    "[delete] LAG '%s' does not exist on device '%s', skipping", lag_name, device_name
                                )
                                result["skipped_lags"].append({"device": device_name, "lag": lag_name})
                                continue  # Skip - LAG doesn't exist

                            # Check if subinterfaces exist
                            existing_subinterfaces = existing_lags[lag_name].get("subinterfaces", {})
                            _subinterfaces = config.get("subinterfaces") or config.get("sub_interfaces")

                            if not _subinterfaces:
                                LOG.warning(
                                    "[delete] No 'subinterfaces' specified for LAG '%s' on device '%s'. "
                                    "Skipping subinterface deletion.",
                                    lag_name,
                                    device_name,
                                )
                                result["skipped_lags"].append({"device": device_name, "lag": lag_name})
                                continue  # Skip - no subinterfaces to delete

                            # Filter subinterfaces to only include those that exist
                            subinterfaces_to_delete = []
                            for subinterface in _subinterfaces:
                                vlan = subinterface.get("vlan")
                                try:
                                    vlan_int = int(vlan) if vlan is not None else None
                                except (ValueError, TypeError):
                                    vlan_int = None

                                if vlan_int and vlan_int in existing_subinterfaces:
                                    subinterfaces_to_delete.append(subinterface)
                                    LOG.info(
                                        "[delete] Subinterface vlan %s exists on LAG '%s', will delete",
                                        vlan_int,
                                        lag_name,
                                    )
                                else:
                                    LOG.info(
                                        "[delete] Subinterface vlan %s does not exist on LAG '%s', skipping",
                                        vlan,
                                        lag_name,
                                    )

                            if not subinterfaces_to_delete:
                                LOG.info(
                                    "[delete] All subinterfaces already deleted from LAG '%s' "
                                    "on device '%s', skipping",
                                    lag_name,
                                    device_name,
                                )
                                result["skipped_lags"].append({"device": device_name, "lag": lag_name})
                                continue  # Skip - nothing to delete

                            # Update config to only include subinterfaces that exist
                            config["subinterfaces"] = subinterfaces_to_delete

                        # Field-level idempotency for the 'add' (configure) action:
                        # skip a LAG already in the desired state, capturing the
                        # per-LAG before/after for --diff when it does change.
                        add_before: Dict[str, Any] = {}
                        add_after: Dict[str, Any] = {}
                        if action == "add":
                            interface_obj = self._find_lag_interface_obj(gcs_device_info, lag_name)
                            add_changed, add_before, add_after = self._lag_add_diff(interface_obj, config)
                            if not add_changed:
                                LOG.info(
                                    "[add] LAG '%s' on device '%s' already in desired state, skipping",
                                    lag_name,
                                    device_name,
                                )
                                result["skipped_lags"].append({"device": device_name, "lag": lag_name})
                                continue

                        # Only initialize output_config AFTER all skip checks pass
                        # Also, only initialize if device_id not already present, otherwise it will be overwritten.
                        if device_id not in output_config:
                            output_config[device_id] = {"device_id": device_id, "edge": {"lagInterfaces": {}}}

                        self._apply_lag(output_config[device_id]["edge"], action=action, **config)

                        # Record the per-LAG before/after for --diff.
                        if action == "add":
                            device_before[lag_name] = add_before
                            device_after[lag_name] = add_after
                        else:
                            before_block, after_block = self._action_diff_blocks(
                                action, config, existing_lags.get(lag_name)
                            )
                            device_before[lag_name] = before_block
                            device_after[lag_name] = after_block

                        # Track whether this is a create or update operation
                        if lag_name in existing_lags:
                            result["updated_lags"].append({"device": device_name, "lag": lag_name})
                            LOG.info(
                                "[configure] Updating LAG '%s' on device: %s (ID: %s)", lag_name, device_name, device_id
                            )
                        else:
                            result["created_lags"].append({"device": device_name, "lag": lag_name})
                            LOG.info(
                                "[configure] Creating LAG '%s' on device: %s (ID: %s)", lag_name, device_name, device_id
                            )

                        if device_name not in result["configured_devices"]:
                            result["configured_devices"].append(device_name)
                    except ConfigurationError:
                        raise
                    except Exception as e:
                        LOG.error("Error configuring LAG interfaces: %s", str(e))
                        raise ConfigurationError(f"LAG interface configuration failed: {str(e)}")

                # Record this device's --diff entry, or mark it skipped when nothing changed.
                if device_id in output_config and (device_before or device_after):
                    self._record_device_diff(result, device_name, device_before, device_after)
                elif device_id not in output_config and device_name not in result["skipped_devices"]:
                    result["skipped_devices"].append(device_name)

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)

            result["changed"] = bool(output_config)

            LOG.info(
                "LAG interface configuration completed: %s created, %s updated, %s skipped (changed: %s)",
                len(result["created_lags"]),
                len(result["updated_lags"]),
                len(result["skipped_lags"]),
                result["changed"],
            )
            # Explicit per-device lists for parity with other managers' completion logging.
            LOG.info(
                "Configure completed: configured_devices=%s, skipped_devices=%s",
                result["configured_devices"],
                result["skipped_devices"],
            )

            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Error in LAG interface configuration: %s", str(e))
            raise ConfigurationError(f"LAG interface configuration failed: {str(e)}")

    def deconfigure_lag_interfaces(self, config_yaml_file: str) -> dict:
        """
        Deconfigure (remove) LAG interfaces for multiple devices concurrently (idempotent).

        Performs a two-step deletion: first deletes all subinterfaces, then deletes
        the main LAG interface. Skips LAGs that don't exist on the device.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary containing:
                - changed (bool): Whether changes were applied.
                - deconfigured_devices (list): List of affected device names.
                - deconfigured_lags (list): LAGs that were successfully removed.
                - skipped_lags (list): LAGs skipped because they don't exist.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        try:
            result: Dict[str, Any] = {
                "changed": False,
                # ``configured_devices`` mirrors ``deconfigured_devices`` because the
                # module's exit payload reads ``configured_devices`` for every operation.
                "configured_devices": [],
                "deconfigured_devices": [],
                "deconfigured_lags": [],
                "skipped_lags": [],
                "skipped_devices": [],
                "diff_plan": [],
            }

            config_data = self.render_config_file(config_yaml_file)
            del_lag_subinterfaces_config = {}
            del_lag_interface_config = {}
            device_configs: Dict[str, Any] = {}
            # Cache for device info to avoid redundant API calls
            device_info_cache = {}

            if "lagInterfaces" not in config_data:
                LOG.warning("No LAG interfaces configuration found in %s", config_yaml_file)
                return result

            for device_info in config_data.get("lagInterfaces") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = []
                    device_configs[device_name].extend(config_list)

            lag_names_per_device = {d: [c.get("name") for c in configs] for d, configs in device_configs.items()}
            LOG.info(
                "Attempting to deconfigure LAG interfaces for devices: %s (LAGs: %s)",
                list(device_configs.keys()),
                lag_names_per_device,
            )

            for device_name, configs in device_configs.items():
                LOG.info("Processing device: %s (%d LAG config(s) to be deconfigured)", device_name, len(configs))

                # Get device_id once per device (outside inner loop)
                device_id = self.gsdk.get_device_id(device_name)
                if device_id is None:
                    raise ConfigurationError(
                        f"Device '{device_name}' is not found in the current enterprise: "
                        f"{self.gsdk.enterprise_info['company_name']}. "
                        "Please check device name and enterprise credentials."
                    )

                # Get device info once per device (use cache if available)
                if device_id not in device_info_cache:
                    device_info_cache[device_id] = self.gsdk.get_device_info(device_id)
                gcs_device_info = device_info_cache[device_id]

                # Get existing LAG info once per device
                existing_lags = self._get_existing_lag_info(gcs_device_info)

                # Per-device --diff accumulators (keyed by LAG name).
                device_before: Dict[str, Any] = {}
                device_after: Dict[str, Any] = {}

                """
                Note: To delete LAG main interface with subinterfaces, we need to delete the subinterfaces first
                and then delete the main interface.

                Example payload to delete subinterfaces:
                {"edge":{"lagInterfaces":{"LAG1":{"interface":{"subinterfaces":{"101":{"interface":null},
                "102":{"interface":null}}}}}},"description":"","configurationMetadata":{"name":""}}

                Example payload to delete main interface:
                {"edge":{"interfaces":{"LAG1":{"interface":null}}},"description":"","configurationMetadata":{"name":""}}
                """

                for config in configs:
                    try:
                        lag_name = config.get("name")

                        # Check if LAG exists - skip if it doesn't (idempotent)
                        if lag_name not in existing_lags:
                            LOG.info(
                                " ✓ LAG '%s' does not exist on device '%s' - skipping (idempotent)",
                                lag_name,
                                device_name,
                            )
                            result["skipped_lags"].append(
                                {"device": device_name, "lag": lag_name, "reason": "does not exist"}
                            )
                            continue

                        # Only initialize if device_id not already present, otherwise it will be overwritten.
                        if device_id not in del_lag_subinterfaces_config:
                            del_lag_subinterfaces_config[device_id] = {
                                "device_id": device_id,
                                "edge": {"lagInterfaces": {}},
                            }

                        if device_id not in del_lag_interface_config:
                            del_lag_interface_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}}}

                        # Get the interface IDs for the interface members
                        config["interfaceMemberIds"] = []
                        for interface_info in gcs_device_info.device.interfaces:
                            if interface_info.name in config.get("lagMembers", []):
                                config["interfaceMemberIds"].append(interface_info.id)

                        # Deconfigure deletes ALL existing subinterfaces (not just those in config)
                        # This is a complete cleanup operation
                        existing_subinterfaces = existing_lags[lag_name].get("subinterfaces", {})

                        # Record the per-LAG before/after for --diff (whole LAG removed).
                        device_before[lag_name] = {
                            "interface": "present",
                            "subinterfaces": sorted(str(vlan) for vlan in existing_subinterfaces),
                        }
                        device_after[lag_name] = {"interface": None}

                        if existing_subinterfaces:
                            # Build subinterfaces list from all existing subinterfaces
                            subinterfaces_to_delete = []
                            for vlan_int, subif_info in existing_subinterfaces.items():
                                subinterfaces_to_delete.append({"vlan": vlan_int})
                                LOG.info(
                                    "[deconfigure] Subinterface vlan %s exists on LAG '%s', will delete",
                                    vlan_int,
                                    lag_name,
                                )

                            # Add all existing subinterfaces to config for deletion
                            config["subinterfaces"] = subinterfaces_to_delete
                            self._apply_lag(del_lag_subinterfaces_config[device_id]["edge"], action="delete", **config)
                        else:
                            LOG.info(
                                "[deconfigure] LAG '%s' has no subinterfaces, skipping subinterface deletion step",
                                lag_name,
                            )

                        # Delete the main LAG interface
                        self._apply_lag(del_lag_interface_config[device_id]["edge"], action="delete_lag", **config)

                        result["deconfigured_lags"].append({"device": device_name, "lag": lag_name})
                        if device_name not in result["deconfigured_devices"]:
                            result["deconfigured_devices"].append(device_name)
                            result["configured_devices"].append(device_name)

                        LOG.info(
                            "[deconfigure] Processing LAG '%s' on device: %s (ID: %s)", lag_name, device_name, device_id
                        )
                    except ConfigurationError:
                        raise
                    except Exception as e:
                        LOG.error("Error deconfiguring LAG interfaces: %s", str(e))
                        raise ConfigurationError(f"LAG interface deconfiguration failed: {str(e)}")

                # Record this device's --diff entry, or mark it skipped when nothing changed.
                if device_id in del_lag_interface_config and (device_before or device_after):
                    self._record_device_diff(result, device_name, device_before, device_after)
                elif device_id not in del_lag_interface_config and device_name not in result["skipped_devices"]:
                    result["skipped_devices"].append(device_name)

            if del_lag_subinterfaces_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, del_lag_subinterfaces_config)
                result["changed"] = True

            if del_lag_interface_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, del_lag_interface_config)
                result["changed"] = True

            LOG.info(
                "LAG interface deconfiguration completed: %s deleted, %s skipped (changed: %s)",
                len(result["deconfigured_lags"]),
                len(result["skipped_lags"]),
                result["changed"],
            )
            # Explicit lists for consistency with global_config deconfigure logging
            LOG.info(
                "Deconfigure completed: deconfigured_lags=%s, skipped_lags=%s",
                [e.get("lag") for e in result["deconfigured_lags"]],
                [e.get("lag") for e in result["skipped_lags"]],
            )
            LOG.info(
                "Deconfigure completed: deconfigured_devices=%s, skipped_devices=%s",
                result["deconfigured_devices"],
                result["skipped_devices"],
            )

            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Error in LAG interface deconfiguration: %s", str(e))
            raise ConfigurationError(f"LAG interface deconfiguration failed: {str(e)}")
