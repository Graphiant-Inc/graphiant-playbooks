"""
Interface Manager for Graphiant Playbooks.

This module handles interface and circuit configuration management,
including both regular interfaces and sub-interfaces.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import traceback

from .base_manager import BaseManager
from .device_config_common import fetch_device_by_name, new_apply_result, redact_sensitive_for_log
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class InterfaceManager(BaseManager):
    """
    Manages interface and circuit configurations.

    Handles the configuration and deconfiguration of network interfaces,
    including both regular interfaces and VLAN sub-interfaces.

    Notes:
        - Configure workflows push configuration via PUT and may not be fully idempotent.
        - Deconfigure workflows are designed to be idempotent by checking current device state
          (via `gsdk.get_device_info`) before building delete payloads.
        - For WAN circuits, the backend can treat "detaching a circuit from an interface" as a
          circuit removal operation. If that circuit still has static routes, the request may
          fail with: `error removing circuit "<name>". Remove static routes first.`
          Use `deconfigure_wan_circuits_interfaces()` or `deconfigure_interfaces()` to ensure
          static routes are removed before WAN interface reset/detach.
    """

    @staticmethod
    def _get_subinterfaces(interface_config):
        """Get subinterfaces from config, supporting both 'subinterfaces' and 'sub_interfaces' keys."""
        return interface_config.get("subinterfaces") or interface_config.get("sub_interfaces") or []

    def _validate_referenced_lan_segments(self, interface_config_data):
        """
        Fail fast when an interface (or subinterface) is assigned to a LAN segment
        that does not exist in the enterprise.

        Assigning ``lan: <name>`` requires the segment to be created first (e.g. via
        ``lan_segments_management.yml --tag configure``). Validated against live
        portal state so the error lists the available segment names. This is a read,
        so it also runs in check mode.

        Raises:
            ConfigurationError: If any referenced LAN segment name is not found.
        """
        referenced = set()  # type: set
        for device_info in interface_config_data.get("interfaces") or []:
            for _device_name, config_list in device_info.items():
                for interface_config in config_list or []:
                    if interface_config.get("lan"):
                        referenced.add(interface_config["lan"])
                    for sub_interface in self._get_subinterfaces(interface_config):
                        if sub_interface.get("lan"):
                            referenced.add(sub_interface["lan"])
        if not referenced:
            return

        available = self.gsdk.get_lan_segments_dict() or {}
        missing = sorted(name for name in referenced if name not in available)
        if missing:
            raise ConfigurationError(
                f"LAN segment(s) {missing} referenced by the interface config do not exist in this "
                f"enterprise. Create them first (e.g. 'lan_segments_management.yml --tag configure'). "
                f"Available LAN segments: {sorted(available.keys())}"
            )
        LOG.info("Referenced LAN segments validated: %s", sorted(referenced))

    # --- Desired-payload builders -----------------------------------------
    # Translate a config-file interface/circuit entry into the ``edge`` PUT
    # payload. These replace the former Jinja2 templates interface_template.yaml
    # and circuit_template.yaml. Notes the templates handled implicitly:
    #   * ``true``/``null`` became real ``True``/``None`` after yaml.safe_load.
    #   * Subinterface keys were quoted (``"{{ vlan }}"``) so they parse back as
    #     *strings*, while the inner ``"vlan"`` value stays an *int*.
    #   * Legacy snake_case aliases (mtu, enabled, v4_tcp_mss, ...) are accepted.

    @staticmethod
    def _first(*values, default=None):
        """First non-None value, else ``default``. Mirrors chained Jinja ``default(...)``."""
        for value in values:
            if value is not None:
                return value
        return default

    @staticmethod
    def _ip_block(address, dhcp):
        """
        Static address block when an address is given, else a DHCP client block.

        Mirrors the ipv4/ipv6 ``{% if ipvX %}address{% else %}dhcp{% endif %}`` pattern.
        ``dhcp`` defaults to True (template: ``dhcpClient: {{ dhcp | default(true) }}``).
        """
        if address:
            return {"address": {"address": address}}
        return {"dhcp": {"dhcpClient": True if dhcp is None else dhcp}}

    @staticmethod
    def _build_interface(name, action="add", default_lan=None, **cfg):
        """
        Build the interface payload for one interface.

        Returns ``{"interfaces": {<name>: {"interface": {...}}}}`` (formerly
        rendered by templates/interface_template.yaml).
        """
        # Backward-compatible aliases.
        subinterfaces = InterfaceManager._first(cfg.get("subinterfaces"), cfg.get("sub_interfaces"))
        mtu = InterfaceManager._first(cfg.get("maxTransmissionUnit"), cfg.get("mtu"))
        admin_status = InterfaceManager._first(cfg.get("adminStatus"), cfg.get("enabled"), default=True)
        v4_tcp_mss = InterfaceManager._first(cfg.get("v4TcpMss"), cfg.get("v4_tcp_mss"))
        v6_tcp_mss = InterfaceManager._first(cfg.get("v6TcpMss"), cfg.get("v6_tcp_mss"))

        circuit = cfg.get("circuit")
        lan = cfg.get("lan")

        interface = {}  # type: Dict[str, Any]

        if action in ("default_lan", "delete"):
            if lan or circuit:
                interface = {
                    "lan": default_lan,
                    "circuit": None,
                    "description": "",
                    "alias": name,
                }
        elif action == "add":
            if circuit or lan:
                interface = {
                    "adminStatus": admin_status,
                    "loopback": cfg.get("loopback"),
                }
                if mtu is not None:
                    interface["maxTransmissionUnit"] = mtu

                if circuit:
                    interface["circuit"] = circuit
                    interface["description"] = cfg.get("description", circuit)
                    # Circuit interfaces keep a synthesized alias (the circuit name is unique
                    # across the device, so it never collides).
                    interface["alias"] = cfg.get("alias", circuit)
                elif lan:
                    interface["lan"] = lan
                    interface["description"] = cfg.get("description", lan)
                    # LAN alias is sent only when explicitly set — never synthesized. A generated
                    # default (the LAN segment name) is not unique across the device, so two
                    # interfaces on the same segment would collide. Omitting leaves it unset/auto.
                    if cfg.get("alias") is not None:
                        interface["alias"] = cfg["alias"]
                    if v4_tcp_mss is not None:
                        interface["v4TcpMss"] = {"tcpMssV4": v4_tcp_mss}
                    if v6_tcp_mss is not None:
                        interface["v6TcpMss"] = {"tcpMssV6": v6_tcp_mss}

                interface["ipv4"] = InterfaceManager._ip_block(cfg.get("ipv4"), cfg.get("dhcp"))
                interface["ipv6"] = InterfaceManager._ip_block(cfg.get("ipv6"), cfg.get("dhcp"))

        if subinterfaces and action in ("default_lan", "add", "delete"):
            interface["subinterfaces"] = {
                # Key is quoted in the template -> parses back as a string.
                # A sub with state:absent is always deleted regardless of the parent action.
                str(sub["vlan"]): {
                    "interface": InterfaceManager._build_subinterface(
                        name,
                        sub,
                        "delete" if (action == "add" and InterfaceManager._is_absent(sub)) else action,
                        default_lan,
                    )
                }
                for sub in subinterfaces
            }

        return {"interfaces": {name: {"interface": interface}}}

    @staticmethod
    def _build_subinterface(parent_name, sub, action, default_lan):
        """Build one subinterface body (formerly the subinterfaces block of the template)."""
        vlan = sub["vlan"]

        if action == "default_lan":
            return {
                "lan": default_lan,
                "vlan": vlan,
                "circuit": None,
                "description": "",
                "alias": "{}.{}".format(parent_name, vlan),
            }

        if action == "delete":  # template emitted "interface": null
            return None

        sub_admin = InterfaceManager._first(sub.get("adminStatus"), sub.get("enabled"), default=True)
        sub_v4 = InterfaceManager._first(sub.get("v4TcpMss"), sub.get("v4_tcp_mss"))
        sub_v6 = InterfaceManager._first(sub.get("v6TcpMss"), sub.get("v6_tcp_mss"))

        body = {}  # type: Dict[str, Any]
        if sub.get("circuit"):
            body["circuit"] = sub["circuit"]
        elif sub.get("lan"):
            body["lan"] = sub["lan"]

        # default(vlan ~ '_' ~ lan, true): the trailing `true` makes empty strings fall back too.
        default_label = "{}_{}".format(vlan, sub.get("lan"))
        body["vlan"] = vlan
        body["description"] = sub.get("description") or default_label
        # Alias handling: an explicit alias is always sent as-is. For a WAN/circuit sub an
        # omitted alias is synthesized from the circuit name (unique across the device). For a
        # LAN sub it is NOT synthesized — a generated "{vlan}_{lan}" is unique only within one
        # parent, so two parents sharing a VLAN+segment (e.g. Gi0/0/0.100 and Gi0/0/1.100 on
        # segment-A) would collide; omitting leaves it unset.
        if sub.get("alias") is not None:
            body["alias"] = sub["alias"]
        elif sub.get("circuit"):
            body["alias"] = sub["circuit"]
        body["adminStatus"] = sub_admin
        body["loopback"] = sub.get("loopback")
        if sub_v4 is not None:
            body["v4TcpMss"] = {"tcpMssV4": sub_v4}
        if sub_v6 is not None:
            body["v6TcpMss"] = {"tcpMssV6": sub_v6}
        body["ipv4"] = InterfaceManager._ip_block(sub.get("ipv4"), sub.get("dhcp"))
        body["ipv6"] = InterfaceManager._ip_block(sub.get("ipv6"), sub.get("dhcp"))
        return body

    @staticmethod
    def _build_circuit(circuit, action="add", **cfg):
        """
        Build the circuit payload for one circuit.

        Returns ``{"circuits": {<circuit>: {...}}}`` (formerly rendered by
        templates/circuit_template.yaml).
        """
        if not circuit:
            return {"circuits": {}}

        # Config fields are API-aligned camelCase; snake_case names are accepted as
        # backward-compatible aliases (camelCase wins when both are given).
        first = InterfaceManager._first
        static_routes = first(cfg.get("staticRoutes"), cfg.get("static_routes"))

        if action == "add":
            body = {
                "name": circuit,
                "description": cfg.get("description", circuit),
                "linkUpSpeedMbps": first(cfg.get("linkUpSpeedMbps"), cfg.get("upload_bandwidth"), default=100),
                "linkDownSpeedMbps": first(cfg.get("linkDownSpeedMbps"), cfg.get("download_bandwidth"), default=1000),
                "circuitType": first(cfg.get("circuitType"), cfg.get("circuit_type"), default="circuitType_internet"),
                "label": cfg.get("label", "internet_dia_4"),
                "diaEnabled": first(cfg.get("diaEnabled"), cfg.get("dia"), default=False),
                "lastResort": first(cfg.get("lastResort"), cfg.get("last_resort"), default=False),
                "loopback": cfg.get("loopback"),
                "qosProfile": first(cfg.get("qosProfile"), cfg.get("qos_profile"), default="gold10"),
                "qosProfileType": first(cfg.get("qosProfileType"), cfg.get("qos_profile_type"), default="balanced"),
                "staticRoutes": InterfaceManager._build_static_routes(static_routes, action),
            }
            return {"circuits": {circuit: body}}

        if action == "delete":
            return {
                "circuits": {circuit: {"staticRoutes": InterfaceManager._build_static_routes(static_routes, action)}}
            }

        return {"circuits": {}}

    @staticmethod
    def _build_static_routes(static_routes, action):
        """Build the ``staticRoutes`` map for a circuit (camelCase primary, snake_case aliases)."""
        routes = {}  # type: Dict[str, Any]
        if not static_routes:
            return routes

        first = InterfaceManager._first
        for prefix, route_config in static_routes.items():
            if action == "delete":  # template emitted "route": null
                routes[prefix] = {"route": None}
                continue
            hops = first(route_config.get("nextHops"), route_config.get("next_hops")) or []
            next_hops = [{"nextHopAddress": first(nh.get("nextHopAddress"), nh.get("next_hop_address"))} for nh in hops]
            routes[prefix] = {
                "route": {
                    "destinationPrefix": first(
                        route_config.get("destinationPrefix"), route_config.get("destination_prefix")
                    ),
                    "description": route_config.get("description", prefix),
                    "administrativeDistance": {
                        "distance": first(
                            route_config.get("administrativeDistance"),
                            route_config.get("administrative_distance"),
                            default=1,
                        )
                    },
                    "nextHops": next_hops,
                }
            }
        return routes

    def _apply_interface(self, config_payload, action="add", **kwargs):
        """
        Build an interface payload and merge it into ``config_payload["interfaces"]``.

        Replaces the former ``config_utils.device_interface`` (template-based) hop.
        """
        name = kwargs.pop("name", None)
        if not name:
            raise ConfigurationError("Missing required parameters: ['name']")
        LOG.info("Device interface: %s %s", action.upper(), name)

        try:
            result = self._build_interface(name, action=action, **kwargs)
            config_payload["interfaces"].update(result["interfaces"])
        except ConfigurationError:
            raise
        except Exception as e:  # pylint: disable=broad-except
            LOG.error("Failed to process device interface %s: %s", name, str(e))
            raise ConfigurationError(f"Device interface processing failed: {str(e)}")

    def _apply_circuit(self, config_payload, action="add", **kwargs):
        """
        Build a circuit payload and merge it into ``config_payload["circuits"]``.

        Replaces the former ``config_utils.device_circuit`` (template-based) hop.
        """
        circuit = kwargs.pop("circuit", None)
        if not circuit:
            raise ConfigurationError("Missing required parameters: ['circuit']")
        LOG.debug("Device circuit: %s %s", action.upper(), circuit)

        try:
            result = self._build_circuit(circuit, action=action, **kwargs)
            config_payload["circuits"].update(result["circuits"])
        except ConfigurationError:
            raise
        except Exception as e:  # pylint: disable=broad-except
            LOG.error("Failed to process device circuit %s: %s", circuit, str(e))
            raise ConfigurationError(f"Device circuit processing failed: {str(e)}")

    @staticmethod
    def _is_absent(entry):
        """Return True when the config entry carries ``state: absent``."""
        return isinstance(entry, dict) and str(entry.get("state", "")).lower() == "absent"

    # Device state is the normalized GET dict from ``fetch_device_by_name``
    # (``to_dict(by_alias=True)`` -> camelCase keys, None fields dropped). The
    # accessors below read that dict; ``device`` is the unwrapped device dict.

    @staticmethod
    def _extract_ref(obj, keys):
        """First present value among *keys*; unwrap ``{'name': ...}`` refs to their name."""
        for key in keys:
            val = obj.get(key)
            if val is None:
                continue
            if isinstance(val, dict):
                return val.get("name")
            return val if isinstance(val, str) else str(val)
        return None

    @staticmethod
    def _get_interface_obj(device, interface_name):
        """Return the interface dict from the device GET dict, if present."""
        for interface in (device or {}).get("interfaces") or []:
            if interface.get("name") == interface_name:
                return interface
        return None

    @classmethod
    def _check_interface_exists(cls, device, interface_name, vlan=None):
        """Check whether an interface (or a specific subinterface VLAN) exists on the device."""
        interface = cls._get_interface_obj(device, interface_name)
        if interface is None:
            return False
        if vlan:
            vlan_int = int(vlan)
            return any(sub.get("vlan") == vlan_int for sub in interface.get("subinterfaces") or [])
        return True

    @classmethod
    def _get_interface_lan(cls, device, interface_name):
        """Current interface LAN segment name, or None."""
        interface = cls._get_interface_obj(device, interface_name)
        return cls._extract_ref(interface, ("lan", "lanSegment", "lan_segment")) if interface else None

    @classmethod
    def _get_subinterface_lan(cls, device, interface_name, vlan):
        """Current LAN segment name for a subinterface VLAN, or None."""
        interface = cls._get_interface_obj(device, interface_name)
        if not interface:
            return None
        vlan_int = int(vlan) if vlan is not None else None
        for subintf in interface.get("subinterfaces") or []:
            if subintf.get("vlan") == vlan_int:
                return cls._extract_ref(subintf, ("lan", "lanSegment", "lan_segment"))
        return None

    @classmethod
    def _get_subinterface_circuit(cls, device, interface_name, vlan):
        """Current circuit name for a subinterface VLAN, or None (identifies a WAN sub)."""
        interface = cls._get_interface_obj(device, interface_name)
        if not interface:
            return None
        vlan_int = int(vlan) if vlan is not None else None
        for subintf in interface.get("subinterfaces") or []:
            if subintf.get("vlan") == vlan_int:
                return cls._extract_ref(subintf, ("circuit", "wanCircuit", "wan_circuit"))
        return None

    @classmethod
    def _get_interface_circuit(cls, device, interface_name):
        """Current interface circuit name, or None."""
        interface = cls._get_interface_obj(device, interface_name)
        return cls._extract_ref(interface, ("circuit", "wanCircuit", "wan_circuit")) if interface else None

    @staticmethod
    def _get_circuits_list(device):
        """Return the circuits list from the device GET dict."""
        return (device or {}).get("circuits") or []

    @classmethod
    def _get_circuit_obj(cls, device, circuit_name):
        """Return the circuit dict from the device GET dict, if present."""
        for circuit in cls._get_circuits_list(device):
            if circuit.get("name") == circuit_name:
                return circuit
        return None

    @classmethod
    def _get_circuit_static_route_prefixes(cls, device, circuit_name):
        """Return the set of static-route prefixes currently on a circuit."""
        circuit = cls._get_circuit_obj(device, circuit_name)
        if not circuit:
            return set()
        static_routes = circuit.get("staticRoutes")
        if static_routes is None:
            static_routes = circuit.get("static_routes")  # defensive: field-name fallback
        if not static_routes:
            return set()
        if isinstance(static_routes, list):
            return {r.get("prefix") for r in static_routes if r.get("prefix")}
        if isinstance(static_routes, dict):
            return {p for p, v in static_routes.items() if v not in (None, {})}
        return set()

    # --- Check mode / diff plan helpers -----------------------------------
    # Populate the standard apply-result (diff_plan/configured/skipped) so runs
    # with --diff show a per-device before/after and check mode reports honestly.
    # Note: pushes already no-op under check mode (gsdk.put_device_config).

    def _current_snapshot(self, device, desired_edge):
        """
        Best-effort current-state ("before") snapshot limited to the interfaces and
        circuits named in *desired_edge*, for ``--diff`` readability (deconfigure paths).

        Missing objects yield an empty/None entry.
        """
        snapshot = {"interfaces": {}, "circuits": {}}  # type: Dict[str, Any]

        for name, desired in (desired_edge.get("interfaces") or {}).items():
            current = {
                "lan": self._get_interface_lan(device, name),
                "circuit": self._get_interface_circuit(device, name),
            }  # type: Dict[str, Any]
            iface_obj = self._get_interface_obj(device, name)
            if iface_obj is not None:
                description = iface_obj.get("description")
                if description is not None:
                    current["description"] = description
                enabled = iface_obj.get("enabled") if iface_obj.get("enabled") is not None else iface_obj.get("up")
                if enabled is not None:
                    current["adminStatus"] = enabled

            desired_subs = ((desired.get("interface") or {}).get("subinterfaces")) or {}
            if desired_subs:
                current["subinterfaces"] = {
                    str(vlan): {
                        "lan": self._get_subinterface_lan(device, name, vlan),
                    }
                    for vlan in desired_subs
                }
            snapshot["interfaces"][name] = current

        for circuit_name in desired_edge.get("circuits") or {}:
            snapshot["circuits"][circuit_name] = {
                "staticRoutePrefixes": sorted(self._get_circuit_static_route_prefixes(device, circuit_name))
            }

        return snapshot

    @staticmethod
    def _record_device_diff(result, device_name, before_edge, desired_edge, branch="edge"):
        """
        Append a ``diff_plan`` entry for *device_name* and mark it configured.

        ``after`` is the exact payload that would be pushed; ``before`` is the
        best-effort current snapshot. Both are redacted for safe display.
        """
        result["diff_plan"].append(
            {
                "device": device_name,
                "branch": branch,
                "before": redact_sensitive_for_log(before_edge),
                "after": redact_sensitive_for_log(desired_edge),
            }
        )
        if device_name not in result["configured_devices"]:
            result["configured_devices"].append(device_name)

    # --- Field-level idempotency (configure paths) -------------------------
    # Compare each device's desired config against live GET state so unchanged
    # devices are skipped. Desired is normalized from the RAW config (sparse: only
    # keys the user wrote, plus the builder's forced functional defaults for
    # ipv4/ipv6/adminStatus); current is normalized from the SDK GET model. Only
    # keys present in the desired side are compared (see _sparse_differs), so
    # fields the config omits never trigger a false change. Safety bias: when a
    # value is absent/ambiguous on the device, prefer "changed" (push) over skip.

    @staticmethod
    def _sparse_differs(desired, existing):
        """
        Return True if any key present in ``desired`` doesn't match ``existing``.

        Keys absent from ``desired`` are never compared. Recurses into nested dicts.
        Mirrors ``BGPManager._sparse_differs``.
        """
        if not isinstance(desired, dict):
            return desired != existing
        if not isinstance(existing, dict):
            return bool(desired)
        for key, desired_value in desired.items():
            existing_value = existing.get(key)
            if isinstance(desired_value, dict):
                if InterfaceManager._sparse_differs(desired_value, existing_value):
                    return True
            elif desired_value != existing_value:
                return True
        return False

    @staticmethod
    def _project_to(existing, desired):
        """
        Restrict *existing* to only the keys present in *desired* (recursively).

        Used to build the ``--diff`` ``before`` so it mirrors the sparse ``after``
        and shows only the fields this run would actually change. A merge PUT never
        removes fields the config omits, so the ``before`` must not imply otherwise.
        """
        if not isinstance(desired, dict) or not isinstance(existing, dict):
            return existing
        projected = {}  # type: Dict[str, Any]
        for key, desired_value in desired.items():
            if key not in existing:
                continue
            existing_value = existing[key]
            if isinstance(desired_value, dict) and isinstance(existing_value, dict):
                projected[key] = InterfaceManager._project_to(existing_value, desired_value)
            else:
                projected[key] = existing_value
        return projected

    @staticmethod
    def _norm_ip_from_config(value):
        """
        Desired IP intent from config, using the real payload keys.

        A config address means a static IP (``dhcpClient: false`` + ``address``);
        an omitted address means the builder enables DHCP (``dhcpClient: true``).
        """
        if value:
            return {"dhcpClient": False, "address": value}
        return {"dhcpClient": True}

    @staticmethod
    def _norm_ip_from_get(addr):
        """
        Current IP state from a GET ipv4/ipv6 dict, using the real ``dhcpClient`` /
        ``address`` keys.

        ``dhcpClient`` is checked first: a DHCP interface reports both a leased
        ``address`` and ``dhcpClient: true``, so it must not be read as static. The
        DHCP lease ``address`` and ``origin`` are intentionally not compared -- they
        are operational (``origin`` only appears once an address exists), so keying
        on them would report a spurious change on a just-enabled DHCP interface. For
        DHCP only ``dhcpClient`` is compared; for static the ``address`` is compared.
        """
        if not addr:
            return {"dhcpClient": False}
        if addr.get("dhcpClient"):
            return {"dhcpClient": True}
        result = {"dhcpClient": False}  # type: Dict[str, Any]
        if addr.get("address"):
            result["address"] = addr["address"]
        return result

    @classmethod
    def _normalized_interface_from_config(cls, raw):
        """Sparse desired-state dict for one interface from its raw config entry."""
        if cls._is_absent(raw):
            return {"_absent": True}

        lan = raw.get("lan")
        circuit = raw.get("circuit")
        desired = {}  # type: Dict[str, Any]

        # Main-interface fields are only written by the builder when lan/circuit
        # is set (a subinterface-only entry leaves the parent untouched).
        if circuit or lan:
            if circuit:
                desired["circuit"] = circuit
            else:
                desired["lan"] = lan
            desired["adminStatus"] = bool(cls._first(raw.get("adminStatus"), raw.get("enabled"), default=True))
            desired["loopback"] = bool(raw.get("loopback"))
            mtu = cls._first(raw.get("maxTransmissionUnit"), raw.get("mtu"))
            if mtu is not None:
                desired["maxTransmissionUnit"] = mtu
            v4 = cls._first(raw.get("v4TcpMss"), raw.get("v4_tcp_mss"))
            if v4 is not None:
                desired["v4TcpMss"] = v4
            v6 = cls._first(raw.get("v6TcpMss"), raw.get("v6_tcp_mss"))
            if v6 is not None:
                desired["v6TcpMss"] = v6
            desired["ipv4"] = cls._norm_ip_from_config(raw.get("ipv4"))
            desired["ipv6"] = cls._norm_ip_from_config(raw.get("ipv6"))
            if raw.get("description") is not None:
                desired["description"] = raw["description"]
            if raw.get("alias") is not None:
                desired["alias"] = raw["alias"]

        subs = cls._first(raw.get("subinterfaces"), raw.get("sub_interfaces"))
        if subs:
            desired["subinterfaces"] = {
                int(s["vlan"]): {"_absent": True} if cls._is_absent(s) else cls._normalized_subinterface_from_config(s)
                for s in subs
            }
        return desired

    @classmethod
    def _normalized_subinterface_from_config(cls, s):
        """Sparse desired-state dict for one subinterface from its raw config entry."""
        desired = {}  # type: Dict[str, Any]
        if s.get("circuit"):
            desired["circuit"] = s["circuit"]
        elif s.get("lan"):
            desired["lan"] = s["lan"]
        desired["adminStatus"] = bool(cls._first(s.get("adminStatus"), s.get("enabled"), default=True))
        desired["loopback"] = bool(s.get("loopback"))
        v4 = cls._first(s.get("v4TcpMss"), s.get("v4_tcp_mss"))
        if v4 is not None:
            desired["v4TcpMss"] = v4
        v6 = cls._first(s.get("v6TcpMss"), s.get("v6_tcp_mss"))
        if v6 is not None:
            desired["v6TcpMss"] = v6
        desired["ipv4"] = cls._norm_ip_from_config(s.get("ipv4"))
        desired["ipv6"] = cls._norm_ip_from_config(s.get("ipv6"))
        if s.get("description") is not None:
            desired["description"] = s["description"]
        if s.get("alias") is not None:
            desired["alias"] = s["alias"]
        return desired

    def _normalized_interface_from_get(self, device, name):
        """Current-state dict for one interface from the device GET dict; None when absent."""
        obj = self._get_interface_obj(device, name)
        if obj is None:
            return None
        # WAN/circuit interfaces omit "enabled"; the API uses "up" for their admin status.
        enabled = obj.get("enabled") if obj.get("enabled") is not None else obj.get("up")
        current = {
            "lan": self._get_interface_lan(device, name),
            "circuit": self._get_interface_circuit(device, name),
            "adminStatus": True if enabled is None else bool(enabled),
            "loopback": bool(obj.get("loopback")),
            "ipv4": self._norm_ip_from_get(obj.get("ipv4")),
            "ipv6": self._norm_ip_from_get(obj.get("ipv6")),
        }  # type: Dict[str, Any]
        mtu = obj.get("maxTransmissionUnit")
        if mtu is not None:
            current["maxTransmissionUnit"] = mtu
        v4 = obj.get("tcpMssV4")
        if v4 is not None:
            current["v4TcpMss"] = v4
        v6 = obj.get("tcpMssV6")
        if v6 is not None:
            current["v6TcpMss"] = v6
        description = obj.get("description")
        if description is not None:
            current["description"] = description
        alias = obj.get("alias")
        if alias is not None:
            current["alias"] = alias
        current["subinterfaces"] = {
            int(s.get("vlan")): self._normalized_subinterface_from_get(s)
            for s in obj.get("subinterfaces") or []
            if s.get("vlan") is not None
        }
        return current

    def _normalized_subinterface_from_get(self, s):
        """Current-state dict for one subinterface dict from the device GET."""
        # WAN subinterfaces omit "enabled" but "up" reflects link status, not admin status
        # (the subinterface can be admin-enabled while the parent circuit is link-down).
        # Default to True (admin-up) when "enabled" is absent rather than falling back to "up".
        enabled = s.get("enabled")
        current = {
            "lan": s.get("lan"),
            "circuit": s.get("circuit"),
            "adminStatus": True if enabled is None else bool(enabled),
            "loopback": bool(s.get("loopback")),
            "ipv4": self._norm_ip_from_get(s.get("ipv4")),
            "ipv6": self._norm_ip_from_get(s.get("ipv6")),
        }  # type: Dict[str, Any]
        v4 = s.get("tcpMssV4")
        if v4 is not None:
            current["v4TcpMss"] = v4
        v6 = s.get("tcpMssV6")
        if v6 is not None:
            current["v6TcpMss"] = v6
        description = s.get("description")
        if description is not None:
            current["description"] = description
        alias = s.get("alias")
        if alias is not None:
            current["alias"] = alias
        return current

    @classmethod
    def _normalized_circuit_from_config(cls, raw):
        """
        Desired-state dict for one circuit from its raw config entry.

        The builder always writes every circuit parameter (with defaults), so they
        are always compared; ``description`` is compared only when the user set it.
        """
        first = cls._first
        desired = {
            "linkUpSpeedMbps": first(raw.get("linkUpSpeedMbps"), raw.get("upload_bandwidth"), default=100),
            "linkDownSpeedMbps": first(raw.get("linkDownSpeedMbps"), raw.get("download_bandwidth"), default=1000),
            "circuitType": first(raw.get("circuitType"), raw.get("circuit_type"), default="circuitType_internet"),
            "label": raw.get("label", "internet_dia_4"),
            "diaEnabled": bool(first(raw.get("diaEnabled"), raw.get("dia"), default=False)),
            "lastResort": bool(first(raw.get("lastResort"), raw.get("last_resort"), default=False)),
            "qosProfile": first(raw.get("qosProfile"), raw.get("qos_profile"), default="gold10"),
            "qosProfileType": first(raw.get("qosProfileType"), raw.get("qos_profile_type"), default="balanced"),
            "loopback": bool(raw.get("loopback")),
        }  # type: Dict[str, Any]
        if raw.get("description") is not None:
            desired["description"] = raw["description"]
        static_routes = first(raw.get("staticRoutes"), raw.get("static_routes"))
        if static_routes:
            desired["staticRoutes"] = {
                prefix: {
                    "distance": first(rc.get("administrativeDistance"), rc.get("administrative_distance"), default=1),
                    "nextHops": sorted(
                        first(nh.get("nextHopAddress"), nh.get("next_hop_address"))
                        for nh in (first(rc.get("nextHops"), rc.get("next_hops")) or [])
                    ),
                }
                for prefix, rc in static_routes.items()
            }
        return desired

    def _normalized_circuit_from_get(self, device, circuit_name):
        """Current-state dict for one circuit from the device GET dict; None when absent."""
        obj = self._get_circuit_obj(device, circuit_name)
        if obj is None:
            return None
        current = {
            "linkUpSpeedMbps": obj.get("linkUpSpeedMbps"),
            "linkDownSpeedMbps": obj.get("linkDownSpeedMbps"),
            "circuitType": obj.get("circuitType"),
            "label": obj.get("label"),
            "diaEnabled": bool(obj.get("diaEnabled")),
            "lastResort": bool(obj.get("lastResort")),
            "qosProfile": obj.get("qosProfile"),
            "qosProfileType": obj.get("qosProfileType"),
            "loopback": bool(obj.get("loopback")),
        }  # type: Dict[str, Any]
        description = obj.get("description")
        if description is not None:
            current["description"] = description
        routes = obj.get("staticRoutes")
        if routes is None:
            routes = obj.get("static_routes")
        static_map = {}  # type: Dict[str, Any]
        for r in routes or []:
            prefix = r.get("prefix")
            if not prefix:
                continue
            next_hops = [nh.get("nextHopAddress") for nh in (r.get("nextHops") or [])]
            static_map[prefix] = {
                "distance": r.get("administrativeDistance"),
                "nextHops": sorted(h for h in next_hops if h is not None),
            }
        current["staticRoutes"] = static_map
        return current

    def _configure_device_diff(self, device, edge, iface_by_name, circ_by_name, default_lan=None):
        """
        Compare a device's built edge payload against live state.

        Returns ``(changed, before, after)`` where before/after are normalized
        per-object dicts for the Ansible ``--diff``. A device is changed when any
        interface/circuit it configures is absent or differs field-for-field.
        """
        changed = False
        before = {"interfaces": {}, "circuits": {}}  # type: Dict[str, Any]
        after = {"interfaces": {}, "circuits": {}}  # type: Dict[str, Any]

        for name in edge.get("interfaces") or {}:
            desired = self._normalized_interface_from_config(iface_by_name.get(name) or {})
            existing = self._normalized_interface_from_get(device, name)

            # Main-interface state:absent — LAN-only: changed only when a non-default LAN is set.
            # WAN interfaces (circuit-attached) are left untouched, so they never diff here.
            if desired.get("_absent"):
                iface_is_configured = existing is not None and bool(
                    existing.get("lan") and existing.get("lan") != default_lan
                )
                if iface_is_configured:
                    before["interfaces"][name] = {"lan": existing["lan"]}
                else:
                    before["interfaces"][name] = {}
                after["interfaces"][name] = {"state": "absent"}
                if iface_is_configured:
                    changed = True
                continue

            # Absent-sub sentinels need special handling: strip them from the sparse
            # comparison (they carry no desired fields) and check existence separately.
            desired_subs = desired.get("subinterfaces", {})
            absent_vlans = {vlan for vlan, v in desired_subs.items() if isinstance(v, dict) and v.get("_absent")}
            if absent_vlans:
                non_absent = {k: v for k, v in desired_subs.items() if k not in absent_vlans}
                desired_cmp = {k: v for k, v in desired.items() if k != "subinterfaces"}
                if non_absent:
                    desired_cmp["subinterfaces"] = non_absent
            else:
                desired_cmp = desired

            existing_subs = (existing or {}).get("subinterfaces", {})
            # state:absent is LAN-only — a sub is actionable only if it exists on the device
            # as a LAN sub (no circuit).  WAN subs are left untouched and never diff.
            absent_lan_vlans = {
                vlan for vlan in absent_vlans if vlan in existing_subs and not existing_subs[vlan].get("circuit")
            }
            absent_sub_exists = bool(absent_lan_vlans)

            after_entry = desired_cmp
            # before mirrors after's keys only (a merge PUT won't remove omitted fields).
            before_entry = self._project_to(existing, desired_cmp) if existing else {}

            # Render actionable absent LAN subinterfaces explicitly in the diff:
            # after shows {"state": "absent"}, before shows the current lan.
            for vlan in absent_lan_vlans:
                cur = existing_subs[vlan]
                after_entry.setdefault("subinterfaces", {})[vlan] = {"state": "absent"}
                before_sub = {}
                if cur.get("lan"):
                    before_sub["lan"] = cur["lan"]
                before_entry.setdefault("subinterfaces", {})[vlan] = before_sub

            after["interfaces"][name] = after_entry
            before["interfaces"][name] = before_entry
            if existing is None or self._sparse_differs(desired_cmp, existing) or absent_sub_exists:
                changed = True

        for cname in edge.get("circuits") or {}:
            desired = self._normalized_circuit_from_config(circ_by_name.get(cname) or {})
            existing = self._normalized_circuit_from_get(device, cname)
            after["circuits"][cname] = desired
            before["circuits"][cname] = self._project_to(existing, desired) if existing else {}
            if existing is None or self._sparse_differs(desired, existing):
                changed = True

        return changed, before, after

    def configure(
        self,
        config_yaml_file=None,
        circuit_config_file=None,
        *,
        interface_config_file=None,
    ) -> dict:
        """
        Configure interfaces and circuits for multiple devices concurrently.
        This method combines all interface and circuit configurations in a single API call per device.

        Args:
            config_yaml_file: Path to the YAML file containing interface configurations (preferred; matches BaseManager)
            circuit_config_file: Optional path to the YAML file containing circuit configurations
            interface_config_file: Backward-compatible alias for ``config_yaml_file``
                (keyword-only). Use one or the other.

        Returns:
            dict: Standard apply-result (``changed``, ``configured_devices``,
            ``skipped_devices``, ``diff_plan``).
            Field-level idempotent: each device's desired config is compared
            against live state (``get_device_info``) and devices already in the
            desired state are skipped. Pushes no-op under check mode.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        yaml_path = config_yaml_file if config_yaml_file is not None else interface_config_file
        if yaml_path is None:
            raise TypeError(
                "configure() requires config_yaml_file (positional or keyword) or interface_config_file= (alias)"
            )
        if (
            config_yaml_file is not None
            and interface_config_file is not None
            and config_yaml_file != interface_config_file
        ):
            raise TypeError(
                "configure(): pass either config_yaml_file or interface_config_file=, not two different paths"
            )

        result: Dict[str, Any] = new_apply_result()

        try:
            # Load interface configurations
            interface_config_data = self.render_config_file(yaml_path)
            output_config: Dict[int, Dict[str, Any]] = {}
            default_lan = f"default-{self.gsdk.get_enterprise_id()}"

            # Load circuit configurations if provided
            circuit_config_data = None
            if circuit_config_file:
                circuit_config_data = self.render_config_file(circuit_config_file)

            if "interfaces" not in interface_config_data:
                LOG.warning("No interfaces configuration found in %s", yaml_path)
                return result

            # Prerequisite: LAN segments referenced by 'lan:' must already exist.
            self._validate_referenced_lan_segments(interface_config_data)

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect interface configurations per device
            for device_info in interface_config_data.get("interfaces") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": [], "circuits": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Collect circuit configurations per device if provided
            if circuit_config_data and "circuits" in circuit_config_data:
                for device_info in circuit_config_data.get("circuits") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["circuits"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id, gcs = fetch_device_by_name(
                        self.gsdk, device_name, self.gsdk.enterprise_info["company_name"]
                    )
                    output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}, "circuits": {}}}

                    # Collect circuit names referenced in this device's interfaces and subinterfaces
                    referenced_circuits = set()
                    for interface_config in configs.get("interfaces", []):
                        # Check main interface for circuit reference
                        if interface_config.get("circuit"):
                            referenced_circuits.add(interface_config["circuit"])
                        # Check subinterfaces for circuit references
                        for sub_interface in self._get_subinterfaces(interface_config):
                            if sub_interface.get("circuit"):
                                referenced_circuits.add(sub_interface["circuit"])

                    LOG.info("[configure] Processing device: %s (ID: %s)", device_name, device_id)
                    LOG.info("Referenced circuits: %s", list(referenced_circuits))

                    # Process circuits for this device
                    circuits_configured = 0
                    for circuit_config in configs.get("circuits", []):
                        if circuit_config.get("circuit") in referenced_circuits:
                            self._apply_circuit(output_config[device_id]["edge"], action="add", **circuit_config)
                            circuits_configured += 1
                            LOG.info(
                                " ✓ To configure circuit '%s' for device: %s",
                                circuit_config.get("circuit"),
                                device_name,
                            )
                        else:
                            LOG.info(
                                " ✗ Skipping circuit '%s' - not referenced in interface configs",
                                circuit_config.get("circuit"),
                            )

                    # Process all interfaces for this device (both LAN and WAN)
                    interfaces_configured = 0
                    for interface_config in configs.get("interfaces", []):
                        # Main interface state:absent — LAN-only: reset a non-default LAN to default.
                        # WAN interfaces (circuit-attached) are intentionally left untouched.
                        if self._is_absent(interface_config):
                            iface_name = interface_config.get("name")
                            current_lan = self._get_interface_lan(gcs, iface_name)
                            needs_reset = bool(current_lan and current_lan != default_lan)
                            if needs_reset:
                                self._apply_interface(
                                    output_config[device_id]["edge"],
                                    action="delete",
                                    default_lan=default_lan,
                                    name=iface_name,
                                    lan=current_lan,
                                    circuit=None,
                                )
                                interfaces_configured += 1
                                LOG.info(
                                    " ✓ To deconfigure LAN interface '%s' for device: %s",
                                    iface_name,
                                    device_name,
                                )
                            else:
                                LOG.info(
                                    " ✗ Interface '%s' has no LAN config to remove (WAN/default), skipping",
                                    iface_name,
                                )
                            continue

                        # Check if this interface has any configuration (LAN or WAN)
                        has_lan_main = interface_config.get("lan") is not None
                        has_wan_main = interface_config.get("circuit") is not None
                        lan_subinterfaces = []
                        wan_subinterfaces = []
                        absent_subinterfaces = []

                        iface_name_for_sub = interface_config.get("name")
                        for sub_interface in self._get_subinterfaces(interface_config):
                            if self._is_absent(sub_interface):
                                # state:absent is LAN-only.  Skip WAN subs (circuit-attached on device).
                                vlan = sub_interface.get("vlan")
                                if self._get_subinterface_circuit(gcs, iface_name_for_sub, vlan):
                                    LOG.info(
                                        " ✗ Skipping WAN subinterface '%s.%s' (state:absent is LAN-only)",
                                        iface_name_for_sub,
                                        vlan,
                                    )
                                elif self._check_interface_exists(gcs, iface_name_for_sub, vlan):
                                    absent_subinterfaces.append(sub_interface)
                                else:
                                    LOG.info(
                                        " ✗ Absent subinterface '%s.%s' already gone, skipping",
                                        iface_name_for_sub,
                                        vlan,
                                    )
                            else:
                                if sub_interface.get("lan"):
                                    lan_subinterfaces.append(sub_interface)
                                if sub_interface.get("circuit"):
                                    wan_subinterfaces.append(sub_interface)

                        # Process this interface if it has any configuration
                        if (
                            has_lan_main
                            or has_wan_main
                            or lan_subinterfaces
                            or wan_subinterfaces
                            or absent_subinterfaces
                        ):
                            # Combine all subinterfaces
                            all_subinterfaces = lan_subinterfaces + wan_subinterfaces + absent_subinterfaces

                            if all_subinterfaces:
                                # Interface has subinterfaces
                                combined_config = interface_config.copy()
                                combined_config["sub_interfaces"] = all_subinterfaces
                                self._apply_interface(output_config[device_id]["edge"], action="add", **combined_config)
                                interfaces_configured += 1 + len(all_subinterfaces)
                                LOG.info(
                                    " ✓ To configure interface '%s' with %s subinterfaces for device: %s",
                                    interface_config.get("name"),
                                    len(all_subinterfaces),
                                    device_name,
                                )
                            else:
                                # Interface has no subinterfaces
                                self._apply_interface(
                                    output_config[device_id]["edge"], action="add", **interface_config
                                )
                                interfaces_configured += 1
                                LOG.info(
                                    " ✓ To configure interface '%s' for device: %s",
                                    interface_config.get("name"),
                                    device_name,
                                )
                        else:
                            LOG.info(
                                " ✗ Skipping interface '%s' - no configuration found", interface_config.get("name")
                            )

                    LOG.info(
                        "Device %s summary: %s circuits, %s interfaces to be configured",
                        device_name,
                        circuits_configured,
                        interfaces_configured,
                    )
                    edge = output_config[device_id]["edge"]
                    LOG.info("Final config for %s: %s", device_name, edge)

                    # Field-level idempotency: skip the device when its live state
                    # already matches; otherwise record the per-object diff.
                    if edge.get("interfaces") or edge.get("circuits"):
                        iface_by_name = {c.get("name"): c for c in configs.get("interfaces", [])}
                        circ_by_name = {c.get("circuit"): c for c in configs.get("circuits", [])}
                        changed, before, after = self._configure_device_diff(
                            gcs, edge, iface_by_name, circ_by_name, default_lan
                        )
                        if changed:
                            self._record_device_diff(result, device_name, before, after)
                        else:
                            del output_config[device_id]
                            result["skipped_devices"].append(device_name)
                            LOG.info(" ✓ No changes needed for %s, skipping", device_name)
                    else:
                        del output_config[device_id]
                        result["skipped_devices"].append(device_name)
                        LOG.info(" ✓ No changes needed for %s, skipping", device_name)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error configuring device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Configuration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = bool(result["configured_devices"])
                LOG.info("Successfully configured interfaces and circuits for %s devices", len(output_config))
            else:
                LOG.warning("No valid device configurations found")

            return result

        except Exception as e:
            LOG.error("Error in interface and circuit configuration: %s", str(e))
            raise ConfigurationError(f"Interface and circuit configuration failed: {str(e)}")

    def deconfigure(
        self,
        config_yaml_file=None,
        circuit_config_file=None,
        circuits_only: bool = False,
        *,
        interface_config_file=None,
    ) -> dict:
        """
        Deconfigure interfaces and (optionally) circuit static routes for multiple devices concurrently (idempotent).

        This is the low-level deconfigure implementation that builds a single per-device payload.
        It checks current device state (interfaces, subinterfaces, LAN/circuit attachment) before
        building a delete payload.

        Important WAN note:
          - When resetting a WAN interface, the payload detaches the circuit (sets `circuit: null`).
            The backend may treat that as a circuit removal and fail if static routes still exist.
          - This method does NOT stage circuit-static-route deletion ahead of interface reset when
            `circuits_only=False`. For WAN-safe staged deconfiguration, use:
            `deconfigure_wan_circuits_interfaces(..., circuits_only=False)` or
            `deconfigure_interfaces(..., circuits_only=False)`.

        Args:
            config_yaml_file: Path to the YAML file containing interface configurations (preferred; matches BaseManager)
            circuit_config_file: Optional path to the YAML file containing circuit configurations
            circuits_only: If True, only remove circuit static routes (skip interface deconfiguration)
            interface_config_file: Backward-compatible alias for ``config_yaml_file``
                (keyword-only). Use one or the other.

        Returns:
            dict: Result with 'changed' status, deconfigured and skipped devices/interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        yaml_path = config_yaml_file if config_yaml_file is not None else interface_config_file
        if yaml_path is None:
            raise TypeError(
                "deconfigure() requires config_yaml_file (positional or keyword) or interface_config_file= (alias)"
            )
        if (
            config_yaml_file is not None
            and interface_config_file is not None
            and config_yaml_file != interface_config_file
        ):
            raise TypeError(
                "deconfigure(): pass either config_yaml_file or interface_config_file=, not two different paths"
            )

        result: Dict[str, Any] = new_apply_result(
            deconfigured_devices=[],
            deconfigured_interfaces=[],
            skipped_interfaces=[],
        )

        try:
            # Load interface configurations
            interface_config_data = self.render_config_file(yaml_path)
            output_config: Dict[int, Dict[str, Any]] = {}
            default_lan = f"default-{self.gsdk.get_enterprise_id()}"

            # Load circuit configurations if provided
            circuit_config_data = None
            if circuit_config_file:
                circuit_config_data = self.render_config_file(circuit_config_file)

            if "interfaces" not in interface_config_data:
                LOG.warning("No interfaces configuration found in %s", yaml_path)
                return result

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect interface configurations per device
            for device_info in interface_config_data.get("interfaces") or []:
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": [], "circuits": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Collect circuit configurations per device if provided
            if circuit_config_data and "circuits" in circuit_config_data:
                for device_info in circuit_config_data.get("circuits") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["circuits"] = config_list

            LOG.info(
                "Attempting to deconfigure interfaces for devices: %s (circuits_only=%s)",
                list(device_configs.keys()),
                circuits_only,
            )

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id, gcs_device_info = fetch_device_by_name(
                        self.gsdk, device_name, self.gsdk.enterprise_info["company_name"]
                    )

                    # Only include sections we actually intend to change.
                    # Avoid sending empty {"circuits": {}} which some backends interpret as "delete all circuits".
                    device_config: Dict[str, Any] = {"interfaces": {}}

                    # Collect circuit names referenced in this device's interfaces and subinterfaces
                    referenced_circuits = set()
                    for interface_config in configs.get("interfaces", []):
                        # Check main interface for circuit reference
                        if interface_config.get("circuit"):
                            referenced_circuits.add(interface_config["circuit"])
                        # Check subinterfaces for circuit references
                        for sub_interface in self._get_subinterfaces(interface_config):
                            if sub_interface.get("circuit"):
                                referenced_circuits.add(sub_interface["circuit"])

                    LOG.info("[deconfigure] Processing device: %s (ID: %s)", device_name, device_id)
                    LOG.info("Referenced circuits: %s", list(referenced_circuits))

                    # Process circuits for this device (explicit deconfiguration for circuits with staticRoutes)
                    circuits_deconfigured = 0
                    if circuits_only:
                        for circuit_config in configs.get("circuits", []):
                            if circuit_config.get("circuit") in referenced_circuits:
                                circuit_name = circuit_config.get("circuit")
                                # Idempotency: only push deletions for staticRoutes that actually exist
                                existing_prefixes = self._get_circuit_static_route_prefixes(
                                    gcs_device_info, circuit_name
                                )
                                if not existing_prefixes:
                                    LOG.info(
                                        " ✓ Circuit '%s' has no staticRoutes on %s, skipping", circuit_name, device_name
                                    )
                                    result["skipped_interfaces"].append(
                                        {
                                            "device": device_name,
                                            "interface": circuit_name,
                                            "vlan": None,
                                            "reason": "Circuit has no staticRoutes",
                                        }
                                    )
                                    continue

                                # If config provides specific static_routes, delete only those that exist;
                                # otherwise delete all existing staticRoutes on the circuit.
                                requested_routes = circuit_config.get("static_routes")
                                if requested_routes:
                                    requested_prefixes = set(requested_routes.keys())
                                    prefixes_to_delete = sorted(existing_prefixes.intersection(requested_prefixes))
                                else:
                                    prefixes_to_delete = sorted(existing_prefixes)

                                if not prefixes_to_delete:
                                    LOG.info(
                                        " ✓ Circuit '%s' staticRoutes already removed on %s, skipping",
                                        circuit_name,
                                        device_name,
                                    )
                                    result["skipped_interfaces"].append(
                                        {
                                            "device": device_name,
                                            "interface": circuit_name,
                                            "vlan": None,
                                            "reason": "StaticRoutes already removed",
                                        }
                                    )
                                    continue

                                delete_config = circuit_config.copy()
                                # Ensure we always generate explicit route deletions (route:null)
                                # instead of empty staticRoutes:{}
                                delete_config["static_routes"] = {pfx: {} for pfx in prefixes_to_delete}

                                device_config.setdefault("circuits", {})
                                self._apply_circuit(device_config, action="delete", **delete_config)
                                circuits_deconfigured += 1
                                LOG.info(
                                    " ✓ To deconfigure %s staticRoutes on circuit '%s' for device: %s",
                                    len(prefixes_to_delete),
                                    circuit_name,
                                    device_name,
                                )
                            else:
                                LOG.info(
                                    " ✗ Skipping circuit '%s' - not referenced in interface configs",
                                    circuit_config.get("circuit"),
                                )

                    # Process all interfaces for this device (both LAN and WAN) - skip if circuits_only=True
                    interfaces_deconfigured = 0
                    if not circuits_only:
                        for interface_config in configs.get("interfaces", []):
                            # Check if this interface has any configuration (LAN or WAN)
                            has_lan_main = interface_config.get("lan") is not None
                            has_wan_main = interface_config.get("circuit") is not None
                            lan_subinterfaces = []
                            wan_subinterfaces = []

                            for sub_interface in self._get_subinterfaces(interface_config):
                                if sub_interface.get("lan"):
                                    lan_subinterfaces.append(sub_interface)
                                if sub_interface.get("circuit"):
                                    wan_subinterfaces.append(sub_interface)

                            # Process this interface if it has any configuration
                            if has_lan_main or has_wan_main or lan_subinterfaces or wan_subinterfaces:
                                interface_name = interface_config.get("name")
                                main_interface_exists = self._check_interface_exists(gcs_device_info, interface_name)
                                current_lan = (
                                    self._get_interface_lan(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )
                                current_circuit = (
                                    self._get_interface_circuit(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )

                                # For ethernet interfaces, "deconfigure main" means:
                                # - set parent LAN to default LAN
                                # - clear circuit
                                # We should only do that if the parent isn't already in that state.
                                parent_requested = bool(has_lan_main or has_wan_main)
                                main_needs_reset = (
                                    main_interface_exists
                                    and parent_requested
                                    and ((current_lan != default_lan) or (current_circuit is not None))
                                )

                                # Check if main interface exists
                                if parent_requested:
                                    if not main_interface_exists:
                                        LOG.info(
                                            " ✗ Interface '%s' does not exist on %s, skipping",
                                            interface_name,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": None,
                                                "reason": "Interface does not exist",
                                            }
                                        )
                                    elif main_needs_reset:
                                        LOG.info(
                                            " ✓ Interface '%s' exists on %s (lan=%s circuit=%s), will reset to %s",
                                            interface_name,
                                            device_name,
                                            current_lan,
                                            current_circuit,
                                            default_lan,
                                        )
                                    else:
                                        LOG.info(
                                            " ✓ Interface '%s' already at default state on %s "
                                            "(lan=%s circuit=%s), skipping parent reset",
                                            interface_name,
                                            device_name,
                                            current_lan,
                                            current_circuit,
                                        )

                                # Check if subinterfaces exist
                                existing_subinterfaces = []
                                for sub_interface in lan_subinterfaces + wan_subinterfaces:
                                    vlan = sub_interface.get("vlan")
                                    if self._check_interface_exists(gcs_device_info, interface_name, vlan):
                                        existing_subinterfaces.append(sub_interface)
                                        needs_deconfigure = True
                                        LOG.info(
                                            " ✓ Subinterface '%s.%s' exists on %s, will deconfigure",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                    else:
                                        LOG.info(
                                            " ✗ Subinterface '%s.%s' does not exist on %s, skipping",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": vlan,
                                                "reason": "Subinterface does not exist",
                                            }
                                        )

                                needs_deconfigure = bool(existing_subinterfaces) or main_needs_reset

                                if needs_deconfigure:
                                    if existing_subinterfaces:
                                        # Interface has subinterfaces
                                        combined_config = interface_config.copy()
                                        # Remove any existing subinterface keys to avoid including
                                        # non-existent subinterfaces
                                        combined_config.pop("sub_interfaces", None)
                                        combined_config.pop("subinterfaces", None)
                                        combined_config["sub_interfaces"] = existing_subinterfaces

                                        # If the parent is already at default state, don't include
                                        # lan/circuit in payload.
                                        # This ensures we only delete subinterfaces (as per config)
                                        # without resetting parent again.
                                        if parent_requested and not main_needs_reset:
                                            combined_config.pop("lan", None)
                                            combined_config.pop("circuit", None)

                                        self._apply_interface(
                                            device_config, action="delete", default_lan=default_lan, **combined_config
                                        )
                                        interfaces_deconfigured += (1 if main_needs_reset else 0) + len(
                                            existing_subinterfaces
                                        )
                                        LOG.info(
                                            " ✓ To deconfigure interface '%s' with %s subinterfaces for device: %s",
                                            interface_name,
                                            len(existing_subinterfaces),
                                            device_name,
                                        )
                                        if main_needs_reset:
                                            result["deconfigured_interfaces"].append(
                                                {"device": device_name, "interface": interface_name, "vlan": None}
                                            )
                                        for sub_intf in existing_subinterfaces:
                                            result["deconfigured_interfaces"].append(
                                                {
                                                    "device": device_name,
                                                    "interface": interface_name,
                                                    "vlan": sub_intf.get("vlan"),
                                                }
                                            )
                                    elif main_needs_reset:
                                        # Interface has no subinterfaces (or all subinterfaces were skipped)
                                        # Remove any subinterface keys to avoid including non-existent subinterfaces
                                        clean_config = interface_config.copy()
                                        clean_config.pop("sub_interfaces", None)
                                        clean_config.pop("subinterfaces", None)
                                        self._apply_interface(
                                            device_config, action="delete", default_lan=default_lan, **clean_config
                                        )
                                        interfaces_deconfigured += 1
                                        LOG.info(
                                            " ✓ To deconfigure interface '%s' for device: %s",
                                            interface_name,
                                            device_name,
                                        )
                                        result["deconfigured_interfaces"].append(
                                            {"device": device_name, "interface": interface_name, "vlan": None}
                                        )
                            else:
                                LOG.info(
                                    " ✗ Skipping interface '%s' - no configuration found", interface_config.get("name")
                                )
                    else:
                        LOG.info(" ✗ Skipping interface '%s' - no configuration found", interface_config.get("name"))

                    # Only add to output_config if there's something to deconfigure
                    if device_config.get("interfaces") or device_config.get("circuits"):
                        output_config[device_id] = {"device_id": device_id, "edge": device_config}
                        before = self._current_snapshot(gcs_device_info, device_config)
                        self._record_device_diff(result, device_name, before, device_config)
                        if circuits_only:
                            LOG.info(
                                "Device %s summary: %s circuits to be deconfigured (circuits-only mode)",
                                device_name,
                                circuits_deconfigured,
                            )
                        else:
                            LOG.info(
                                "Device %s summary: %s circuits and %s interfaces to be deconfigured",
                                device_name,
                                circuits_deconfigured,
                                interfaces_deconfigured,
                            )
                        LOG.info("Final config for %s: %s", device_name, device_config)
                    else:
                        result["skipped_devices"].append(device_name)
                        LOG.info("Device %s: All interfaces already deconfigured or not configured", device_name)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error deconfiguring device %s: %s", device_name, str(e))
                    LOG.error("Device ID: %s, Device Name: %s", device_id, device_name)
                    LOG.error("Exception type: %s", type(e).__name__)
                    LOG.error("Full traceback: %s", traceback.format_exc())
                    raise ConfigurationError(f"Deconfiguration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = bool(result["configured_devices"])
                result["deconfigured_devices"] = list(output_config.keys())
                if circuits_only:
                    LOG.info(
                        "Successfully deconfigured circuits for %s devices (circuits-only mode)", len(output_config)
                    )
                else:
                    LOG.info("Successfully deconfigured interfaces and circuits for %s devices", len(output_config))
            else:
                if circuits_only:
                    LOG.warning("No valid circuit configurations found")
                else:
                    LOG.warning("No valid device configurations found")

            # Summary with explicit lists (consistent with global_config deconfigure logging)
            deconfigured_names = [
                "%s:%s%s" % (e.get("device", ""), e.get("interface", ""), (".%s" % e["vlan"]) if e.get("vlan") else "")
                for e in result["deconfigured_interfaces"]
            ]
            skipped_names = [
                "%s:%s%s (%s)"
                % (
                    e.get("device", ""),
                    e.get("interface", ""),
                    (".%s" % e["vlan"]) if e.get("vlan") else "",
                    e.get("reason", ""),
                )
                for e in result["skipped_interfaces"]
            ]
            LOG.info(
                "Deconfigure completed: deconfigured_interfaces=%s, skipped_interfaces=%s",
                deconfigured_names,
                skipped_names,
            )

            return result

        except Exception as e:
            LOG.error("Error in interface and circuit deconfiguration: %s", str(e))
            LOG.error("Exception type: %s", type(e).__name__)
            LOG.error("Full traceback: %s", traceback.format_exc())
            raise ConfigurationError(f"Interface and circuit deconfiguration failed: {str(e)}")

    def configure_interfaces(self, interface_config_file: str, circuit_config_file=None) -> dict:
        """
        Configure all interfaces and circuits for multiple devices concurrently.
        This method calls the configure method to handle all configurations in a single API call per device.

        Args:
            interface_config_file: Path to the YAML file containing interface configurations
            circuit_config_file: Optional path to the YAML file containing circuit configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        return self.configure(interface_config_file, circuit_config_file)

    def deconfigure_interfaces(
        self, interface_config_file: str, circuit_config_file=None, circuits_only: bool = False
    ) -> dict:
        """
        Deconfigure all interfaces and circuits for multiple devices concurrently.
        For WAN interfaces, circuit detachment may be treated by the backend as a "circuit removal" operation.
        If the referenced circuit still has static routes, that detachment can fail with:
        `error removing circuit "<name>". Remove static routes first.`

        To prevent this, this orchestrator performs a two-stage flow when `circuits_only=False`:
        - Stage 1: remove static routes from referenced circuits (idempotent)
        - Stage 2: deconfigure interfaces (reset WAN/LAN parents to default LAN, delete subinterfaces as needed)

        Args:
            interface_config_file: Path to the YAML file containing interface configurations
            circuit_config_file: Optional path to the YAML file containing circuit configurations
            circuits_only: If True, only deconfigure circuits, skip interface deconfiguration

        Returns:
            dict: Result with 'changed' status and list of deconfigured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        # Circuits-only mode is effectively "remove static routes from referenced circuits".
        if circuits_only:
            return self.deconfigure_wan_circuits_interfaces(
                interface_config_file=interface_config_file,
                circuit_config_file=circuit_config_file,
                circuits_only=True,
            )

        # Stage 1: ensure no static routes remain on referenced circuits before detaching WAN interfaces.
        stage1 = self.deconfigure_wan_circuits_interfaces(
            interface_config_file=interface_config_file,
            circuit_config_file=circuit_config_file,
            circuits_only=True,
        )

        # Stage 2: deconfigure interfaces (LAN + WAN).
        stage2 = self.deconfigure(interface_config_file, circuit_config_file, circuits_only=False)

        # Merge results: surface circuit-route work alongside interface work.
        merged = stage2
        merged["changed"] = bool(stage1.get("changed") or stage2.get("changed"))
        merged["deconfigured_devices"] = sorted(
            set(stage1.get("deconfigured_devices", [])) | set(stage2.get("deconfigured_devices", []))
        )
        merged["deconfigured_circuits"] = stage1.get("deconfigured_circuits", [])
        merged["skipped_circuits"] = stage1.get("skipped_circuits", [])
        # Combine standard apply-result fields so --diff shows both stages.
        merged["diff_plan"] = (stage1.get("diff_plan") or []) + (stage2.get("diff_plan") or [])
        merged["configured_devices"] = sorted(
            set(stage1.get("configured_devices", [])) | set(stage2.get("configured_devices", []))
        )
        # A device configured in either stage must not also appear as skipped (a device that
        # stage1 skipped — no static routes — but stage2 configured would otherwise be in both).
        merged["skipped_devices"] = sorted(
            (set(stage1.get("skipped_devices", [])) | set(stage2.get("skipped_devices", [])))
            - set(merged["configured_devices"])
        )
        return merged

    def configure_circuits(self, circuit_config_file: str, interface_config_file: str) -> dict:
        """
        Configure circuits only for multiple devices concurrently.
        This method uses configure_wan_circuits_interfaces with circuits_only=True.
        Only circuits referenced in the interface config will be configured.

        Args:
            circuit_config_file: Path to the YAML file containing circuit configurations
            interface_config_file: Path to the YAML file containing interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        LOG.info(
            "Configuring circuits only using circuit config: %s and interface config: %s",
            circuit_config_file,
            interface_config_file,
        )
        return self.configure_wan_circuits_interfaces(circuit_config_file, interface_config_file, circuits_only=True)

    def deconfigure_circuits(self, circuit_config_file: str, interface_config_file: str) -> dict:
        """
        Deconfigure circuits only (static routes) for multiple devices concurrently (idempotent).

        This operation removes static routes from the referenced circuits. It checks the current
        device state first, and skips the configuration push when there are no matching static routes
        to delete (returns `changed: False`).

        This method uses deconfigure_wan_circuits_interfaces with circuits_only=True.
        Only circuits referenced in the interface config will be deconfigured.

        Args:
            circuit_config_file: Path to the YAML file containing circuit configurations
            interface_config_file: Path to the YAML file containing interface configurations

        Returns:
            dict: Result with 'changed' status, deconfigured devices, and per-circuit details.
                  Includes `deconfigured_circuits` and `skipped_circuits` when available.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        LOG.info(
            "Deconfiguring circuits only using circuit config: %s and interface config: %s",
            circuit_config_file,
            interface_config_file,
        )
        return self.deconfigure_wan_circuits_interfaces(interface_config_file, circuit_config_file, circuits_only=True)

    def configure_lan_interfaces(self, interface_config_file: str) -> dict:
        """
        Configure LAN interfaces for multiple devices concurrently.
        Only interfaces with 'lan' key will be configured.

        The API does not allow moving an interface to a different LAN segment in the same
        request as other interface config changes. So when any interface/subinterface has
        only its segment (lan) changed, we push in two phases: first a segment-only payload,
        then the full config.

        Args:
            interface_config_file: Path to the YAML file containing interface configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = new_apply_result()

        try:
            config_data = self.render_config_file(interface_config_file)
            output_config: Dict[int, Dict[str, Any]] = {}
            device_infos = {}  # device_id -> gcs device info for segment-change detection
            default_lan = f"default-{self.gsdk.get_enterprise_id()}"

            if "interfaces" not in config_data:
                LOG.warning("No interfaces configuration found in %s", interface_config_file)
                return result

            # Prerequisite: LAN segments referenced by 'lan:' must already exist.
            self._validate_referenced_lan_segments(config_data)

            for device_info in config_data.get("interfaces") or []:
                for device_name, config_list in device_info.items():
                    try:
                        device_id, gcs = fetch_device_by_name(
                            self.gsdk, device_name, self.gsdk.enterprise_info["company_name"]
                        )
                        device_config: Dict[str, Any] = {"interfaces": {}}

                        lan_interfaces_configured = 0
                        for config in config_list:
                            # Main interface state:absent — LAN-only: reset a non-default LAN to default.
                            # WAN interfaces (circuit-attached) are intentionally left untouched.
                            if self._is_absent(config):
                                iface_name = config.get("name")
                                current_lan = self._get_interface_lan(gcs, iface_name)
                                needs_reset = bool(current_lan and current_lan != default_lan)
                                if needs_reset:
                                    self._apply_interface(
                                        device_config,
                                        action="delete",
                                        default_lan=default_lan,
                                        name=iface_name,
                                        lan=current_lan,
                                        circuit=None,
                                    )
                                    lan_interfaces_configured += 1
                                    LOG.info(
                                        " ✓ To deconfigure LAN interface '%s' for device: %s",
                                        iface_name,
                                        device_name,
                                    )
                                else:
                                    LOG.info(
                                        " ✗ Interface '%s' has no LAN config to remove (WAN/default), skipping",
                                        iface_name,
                                    )
                                continue

                            # Check if this interface has any LAN configuration (main interface or subinterfaces)
                            has_lan_main = config.get("lan") is not None
                            lan_subinterfaces = []
                            absent_subinterfaces = []

                            iface_name_for_sub = config.get("name")
                            for sub_interface in self._get_subinterfaces(config):
                                if self._is_absent(sub_interface):
                                    # state:absent is LAN-only.  Skip WAN subs (circuit-attached on device).
                                    vlan = sub_interface.get("vlan")
                                    if self._get_subinterface_circuit(gcs, iface_name_for_sub, vlan):
                                        LOG.info(
                                            " ✗ Skipping WAN subinterface '%s.%s' (state:absent is LAN-only)",
                                            iface_name_for_sub,
                                            vlan,
                                        )
                                    elif self._check_interface_exists(gcs, iface_name_for_sub, vlan):
                                        absent_subinterfaces.append(sub_interface)
                                    else:
                                        LOG.info(
                                            " ✗ Absent subinterface '%s.%s' already gone, skipping",
                                            iface_name_for_sub,
                                            vlan,
                                        )
                                elif sub_interface.get("lan"):
                                    lan_subinterfaces.append(sub_interface)
                                    LOG.info(
                                        " ✓ Found LAN subinterface '%s.%s' for device: %s",
                                        config.get("name"),
                                        sub_interface.get("vlan"),
                                        device_name,
                                    )

                            all_subinterfaces = lan_subinterfaces + absent_subinterfaces

                            # Process this interface if it has any LAN configuration
                            if has_lan_main or lan_subinterfaces or absent_subinterfaces:
                                if has_lan_main and all_subinterfaces:
                                    # Both main interface and subinterfaces have LAN config
                                    combined_config = config.copy()
                                    combined_config["sub_interfaces"] = all_subinterfaces
                                    self._apply_interface(device_config, action="add", **combined_config)
                                    lan_interfaces_configured += 1 + len(all_subinterfaces)
                                    LOG.info(
                                        " ✓ To configure LAN main interface '%s' and %s LAN "
                                        "subinterfaces for device: %s",
                                        config.get("name"),
                                        len(all_subinterfaces),
                                        device_name,
                                    )

                                elif has_lan_main:
                                    # Only main interface has LAN config
                                    main_config = config.copy()
                                    main_config.pop("sub_interfaces", None)  # Remove subinterfaces (both param names)
                                    main_config.pop("subinterfaces", None)
                                    self._apply_interface(device_config, action="add", **main_config)
                                    lan_interfaces_configured += 1
                                    LOG.info(
                                        " ✓ To configure LAN main interface '%s' for device: %s",
                                        config.get("name"),
                                        device_name,
                                    )

                                elif all_subinterfaces:
                                    # Only subinterfaces (LAN or absent) - create minimal config
                                    subinterface_config = {
                                        "name": config.get("name"),
                                        "sub_interfaces": all_subinterfaces,
                                    }
                                    self._apply_interface(device_config, action="add", **subinterface_config)
                                    lan_interfaces_configured += len(all_subinterfaces)
                                    LOG.info(
                                        " ✓ Configure %s subinterfaces for interface '%s' on device: %s",
                                        len(all_subinterfaces),
                                        config.get("name"),
                                        device_name,
                                    )
                            else:
                                LOG.info(" ✗ Skipping interface '%s' - no LAN configuration found", config.get("name"))

                        # Check if any LAN interfaces were configured for this device
                        # Note: This check is inside the loop to evaluate after processing all configs for this device
                        if lan_interfaces_configured > 0:
                            device_infos[device_id] = gcs
                            iface_by_name = {c.get("name"): c for c in config_list}
                            changed, before, after = self._configure_device_diff(
                                gcs, device_config, iface_by_name, {}, default_lan
                            )
                            if changed:
                                output_config[device_id] = {"device_id": device_id, "edge": device_config}
                                self._record_device_diff(result, device_name, before, after)
                                LOG.info(
                                    "Device %s summary: %s LAN interfaces to be configured",
                                    device_name,
                                    lan_interfaces_configured,
                                )
                            else:
                                result["skipped_devices"].append(device_name)
                                LOG.info(" ✓ No changes needed for %s, skipping", device_name)
                        else:
                            result["skipped_devices"].append(device_name)
                            LOG.info("Device %s: No LAN interfaces found to configure", device_name)

                    except DeviceNotFoundError:
                        LOG.error("Device not found: %s", device_name)
                        raise
                    except Exception as e:
                        LOG.error("Error configuring LAN interfaces for device %s: %s", device_name, str(e))
                        raise ConfigurationError(f"LAN interface configuration failed for {device_name}: {str(e)}")

            if output_config:
                # Build stage1 (segment-only) payloads for devices where an interface is moved to a new LAN.
                # API rejects moving segment and changing other interface config in the same request.
                _EMPTY_SEGMENT: Dict[str, Any] = {
                    "networks": [],
                    "bgpRedistribution": {},
                    "bgpNeighbors": {},
                    "syslogTargets": {},
                    "staticRoutes": {},
                    "dhcpSubnets": {},
                    "bgpAggregations": {},
                    "ipfixExporters": {},
                }
                stage1_config: Dict[int, Dict[str, Any]] = {}
                for device_id, entry in output_config.items():
                    device_config = entry["edge"]
                    gcs_info = device_infos.get(device_id)
                    if not gcs_info:
                        continue
                    # list of (interface_name, vlan or None, new_lan)
                    segment_changes: List[Tuple[str, Optional[int], Any]] = []
                    for ifname, ifdata in device_config.get("interfaces", {}).items():
                        inner = ifdata.get("interface", {})
                        # Main interface LAN: detect segment change whenever config has 'lan'
                        # (with or without subinterfaces)
                        intended_main_lan = inner.get("lan")
                        if intended_main_lan:
                            current_main_lan = self._get_interface_lan(gcs_info, ifname)
                            if current_main_lan is not None and current_main_lan != intended_main_lan:
                                segment_changes.append((ifname, None, intended_main_lan))
                        # Subinterface LANs
                        subinterfaces = inner.get("subinterfaces")
                        if subinterfaces:
                            for vlan_str, sub in subinterfaces.items():
                                # sub["interface"] may be None for an absent sub — use `or {}` to guard.
                                intended_lan = (sub.get("interface") or {}).get("lan")
                                if not intended_lan:
                                    continue
                                current_lan = self._get_subinterface_lan(gcs_info, ifname, int(vlan_str))
                                if current_lan is not None and current_lan != intended_lan:
                                    segment_changes.append((ifname, int(vlan_str), intended_lan))
                    if not segment_changes:
                        continue
                    stage1_edge: Dict[str, Any] = {"interfaces": {}, "segments": {}}
                    for ifname, vlan, new_lan in segment_changes:
                        stage1_edge["segments"][new_lan] = _EMPTY_SEGMENT.copy()
                        if vlan is None:
                            stage1_edge["interfaces"][ifname] = {"interface": {"lan": new_lan}}
                        else:
                            if ifname not in stage1_edge["interfaces"]:
                                stage1_edge["interfaces"][ifname] = {"interface": {"subinterfaces": {}}}
                            # Interface may already exist from main-interface segment change;
                            # ensure subinterfaces exists
                            stage1_edge["interfaces"][ifname]["interface"].setdefault("subinterfaces", {})[
                                str(vlan)
                            ] = {"interface": {"vlan": vlan, "lan": new_lan}}
                    stage1_config[device_id] = {"device_id": device_id, "edge": stage1_edge}
                if stage1_config:
                    LOG.info(
                        "Pushing segment-only update first for %s device(s) (LAN move), then full config",
                        len(stage1_config),
                    )
                    self.execute_concurrent_tasks(self.gsdk.put_device_config, stage1_config)
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = bool(result["configured_devices"])
                LOG.info("Successfully configured LAN interfaces for %s devices", len(output_config))
            else:
                LOG.warning("No LAN interface configurations to apply")

            return result

        except Exception as e:
            LOG.error("Error in LAN interface configuration: %s", str(e))
            raise ConfigurationError(f"LAN interface configuration failed: {str(e)}")

    def deconfigure_lan_interfaces(self, interface_config_file: str) -> dict:
        """
        Deconfigure LAN interfaces for multiple devices concurrently (idempotent).

        Behavior:
          - If the *parent* interface has a `lan` key in the config, deconfigure means "reset the
            parent to the enterprise default LAN" (and delete any listed LAN subinterfaces).
          - If the config only contains LAN subinterfaces under a parent, deconfigure deletes only
            those subinterfaces and does NOT reset the parent (important for ethernet parents that
            are allowed to remain on the default LAN).

        The method checks if interfaces/subinterfaces exist before attempting deletion.

        Args:
            interface_config_file: Path to the YAML file containing interface configurations

        Returns:
            dict: Result with 'changed' status, deconfigured and skipped devices/interfaces

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = new_apply_result(
            deconfigured_devices=[],
            deconfigured_interfaces=[],
            skipped_interfaces=[],
        )

        try:
            config_data = self.render_config_file(interface_config_file)
            output_config: Dict[int, Dict[str, Any]] = {}
            default_lan = f"default-{self.gsdk.get_enterprise_id()}"

            if "interfaces" not in config_data:
                LOG.warning("No interfaces configuration found in %s", interface_config_file)
                return result

            for device_info in config_data.get("interfaces") or []:
                for device_name, config_list in device_info.items():
                    try:
                        device_id, gcs_device_info = fetch_device_by_name(
                            self.gsdk, device_name, self.gsdk.enterprise_info["company_name"]
                        )

                        device_config: Dict[str, Any] = {"interfaces": {}}

                        lan_interfaces_deconfigured = 0
                        for config in config_list:
                            # Check if this interface has any LAN configuration (main interface or subinterfaces)
                            has_lan_main = config.get("lan") is not None
                            lan_subinterfaces = []

                            for sub_interface in self._get_subinterfaces(config):
                                if sub_interface.get("lan"):
                                    lan_subinterfaces.append(sub_interface)
                                    LOG.info(
                                        " ✓ Found LAN subinterface '%s.%s' for device: %s",
                                        config.get("name"),
                                        sub_interface.get("vlan"),
                                        device_name,
                                    )

                            # Process this interface if it has any LAN configuration
                            if has_lan_main or lan_subinterfaces:
                                interface_name = config.get("name")
                                main_interface_exists = self._check_interface_exists(gcs_device_info, interface_name)
                                current_lan = (
                                    self._get_interface_lan(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )
                                # In LAN deconfigure workflow for ethernet interfaces:
                                # - If the *parent* interface has a LAN config (`lan` key), deconfigure means
                                #   reset parent interface to default LAN (and optionally delete listed subinterfaces).
                                # - If the config only mentions LAN subinterfaces, we should ONLY delete those
                                #   subinterfaces and MUST NOT reset the parent (the parent may
                                #   already be in default LAN).
                                parent_should_default = main_interface_exists and has_lan_main
                                main_needs_reset = parent_should_default and (current_lan != default_lan)

                                if has_lan_main and not main_interface_exists:
                                    LOG.info(
                                        " ✗ LAN main interface '%s' does not exist on %s, skipping",
                                        interface_name,
                                        device_name,
                                    )
                                    result["skipped_interfaces"].append(
                                        {
                                            "device": device_name,
                                            "interface": interface_name,
                                            "vlan": None,
                                            "reason": "Interface does not exist",
                                        }
                                    )

                                # Check if subinterfaces exist
                                existing_subinterfaces = []
                                for sub_interface in lan_subinterfaces:
                                    vlan = sub_interface.get("vlan")
                                    if self._check_interface_exists(gcs_device_info, interface_name, vlan):
                                        existing_subinterfaces.append(sub_interface)
                                        LOG.info(
                                            " ✓ LAN subinterface '%s.%s' exists on %s, will deconfigure",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                    else:
                                        LOG.info(
                                            " ✗ LAN subinterface '%s.%s' does not exist on %s, skipping",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": vlan,
                                                "reason": "Subinterface does not exist",
                                            }
                                        )

                                needs_deconfigure = bool(existing_subinterfaces) or main_needs_reset

                                if not needs_deconfigure:
                                    if parent_should_default and current_lan == default_lan:
                                        LOG.info(
                                            " ✓ LAN interface '%s' already deconfigured on %s (parent on %s), skipping",
                                            interface_name,
                                            device_name,
                                            default_lan,
                                        )
                                    continue

                                # Build a minimal delete payload that matches UI behavior:
                                # - parent interface LAN set to default-<enterpriseId>
                                # - subinterfaces deleted (if any exist)
                                payload_config = {"name": interface_name}
                                if parent_should_default:
                                    # Any truthy value triggers template to set parent LAN to default_lan
                                    payload_config["lan"] = True
                                if existing_subinterfaces:
                                    payload_config["sub_interfaces"] = existing_subinterfaces

                                self._apply_interface(
                                    device_config, action="delete", default_lan=default_lan, **payload_config
                                )

                                lan_interfaces_deconfigured += (1 if main_needs_reset else 0) + len(
                                    existing_subinterfaces
                                )

                                if main_needs_reset:
                                    LOG.info(
                                        " ✓ To deconfigure LAN main interface '%s' (set to %s) for device: %s",
                                        interface_name,
                                        default_lan,
                                        device_name,
                                    )
                                    result["deconfigured_interfaces"].append(
                                        {"device": device_name, "interface": interface_name, "vlan": None}
                                    )
                                if existing_subinterfaces:
                                    LOG.info(
                                        " ✓ To deconfigure %s LAN subinterfaces for interface '%s' on device: %s",
                                        len(existing_subinterfaces),
                                        interface_name,
                                        device_name,
                                    )
                                    for sub_intf in existing_subinterfaces:
                                        result["deconfigured_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": sub_intf.get("vlan"),
                                            }
                                        )
                            else:
                                LOG.info(" ✗ Skipping interface '%s' - no LAN configuration found", config.get("name"))

                        # Only add to output_config if there's something to deconfigure
                        if device_config.get("interfaces") and lan_interfaces_deconfigured > 0:
                            output_config[device_id] = {"device_id": device_id, "edge": device_config}
                            before = self._current_snapshot(gcs_device_info, device_config)
                            self._record_device_diff(result, device_name, before, device_config)
                            LOG.info(
                                "Device %s summary: %s LAN interfaces to be deconfigured",
                                device_name,
                                lan_interfaces_deconfigured,
                            )
                        else:
                            result["skipped_devices"].append(device_name)
                            LOG.info("Device %s: All interfaces already deconfigured or not configured", device_name)

                    except DeviceNotFoundError:
                        LOG.error("Device not found: %s", device_name)
                        raise
                    except Exception as e:
                        LOG.error("Error deconfiguring LAN interfaces for device %s: %s", device_name, str(e))
                        LOG.error("Device ID: %s, Device Name: %s", device_id, device_name)
                        LOG.error("Exception type: %s", type(e).__name__)
                        LOG.error("Full traceback: %s", traceback.format_exc())
                        raise ConfigurationError(f"LAN interface deconfiguration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = bool(result["configured_devices"])
                result["deconfigured_devices"] = list(output_config.keys())
                LOG.info("Successfully deconfigured LAN interfaces for %s devices", len(output_config))
            else:
                LOG.info(
                    "No LAN changes needed - all interfaces already deconfigured or not configured (changed: %s)",
                    result["changed"],
                )

            return result

        except Exception as e:
            LOG.error("Error in LAN interface deconfiguration: %s", str(e))
            LOG.error("Exception type: %s", type(e).__name__)
            LOG.error("Full traceback: %s", traceback.format_exc())
            raise ConfigurationError(f"LAN interface deconfiguration failed: {str(e)}")

    def configure_wan_circuits_interfaces(
        self, circuit_config_file: str, interface_config_file: str, circuits_only: bool = False
    ) -> dict:
        """
        Configure WAN circuits and WAN interfaces for multiple devices concurrently.

        Only circuits referenced by the interface configuration (main interface or subinterfaces)
        are included in the payload.

        Args:
            circuit_config_file: Path to the YAML file containing circuit configurations
            interface_config_file: Path to the YAML file containing interface configurations
            circuits_only: If True, only configure referenced circuits (skip interface configuration)

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = new_apply_result()

        try:
            # Load circuit configurations
            circuit_config_data = self.render_config_file(circuit_config_file)
            interface_config_data = self.render_config_file(interface_config_file)

            output_config: Dict[int, Dict[str, Any]] = {}
            default_lan = f"default-{self.gsdk.get_enterprise_id()}"

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect interface configurations per device
            if "interfaces" in interface_config_data:
                for device_info in interface_config_data.get("interfaces") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["interfaces"] = config_list

            # Collect circuit configurations per device
            if "circuits" in circuit_config_data:
                for device_info in circuit_config_data.get("circuits") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["circuits"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id, gcs = fetch_device_by_name(
                        self.gsdk, device_name, self.gsdk.enterprise_info["company_name"]
                    )
                    output_config[device_id] = {"device_id": device_id, "edge": {"interfaces": {}, "circuits": {}}}

                    # Collect circuit names referenced in this device's interfaces and subinterfaces
                    referenced_circuits = set()
                    for interface_config in configs.get("interfaces", []):
                        # Check main interface for circuit reference
                        if interface_config.get("circuit"):
                            referenced_circuits.add(interface_config["circuit"])
                        # Check subinterfaces for circuit references
                        for sub_interface in self._get_subinterfaces(interface_config):
                            if sub_interface.get("circuit"):
                                referenced_circuits.add(sub_interface["circuit"])

                    if circuits_only:
                        LOG.info(
                            "[configure_wan_circuits_interfaces] Processing device: %s (ID: %s) - CIRCUITS ONLY MODE",
                            device_name,
                            device_id,
                        )
                    else:
                        LOG.info(
                            "[configure_wan_circuits_interfaces] Processing device: %s (ID: %s)", device_name, device_id
                        )
                    LOG.info("Referenced circuits: %s", list(referenced_circuits))

                    # Process circuits for this device
                    circuits_configured = 0
                    for circuit_config in configs.get("circuits", []):
                        if circuit_config.get("circuit") in referenced_circuits:
                            self._apply_circuit(output_config[device_id]["edge"], action="add", **circuit_config)
                            circuits_configured += 1
                            LOG.info(
                                " ✓ To configure circuit '%s' for device: %s",
                                circuit_config.get("circuit"),
                                device_name,
                            )
                        else:
                            LOG.info(
                                " ✗ Skipping circuit '%s' - not referenced in interface configs",
                                circuit_config.get("circuit"),
                            )

                    # Process interfaces for this device (only if not circuits_only)
                    interfaces_configured = 0
                    if not circuits_only:
                        for interface_config in configs.get("interfaces", []):
                            # state:absent is LAN-only — the WAN task never deconfigures via absent.
                            # LAN main interfaces / subinterfaces marked absent are handled by
                            # configure_lan_interfaces / configure_interfaces instead.
                            if self._is_absent(interface_config):
                                LOG.info(
                                    " ✗ Skipping interface '%s' state:absent (LAN-only; not handled by WAN task)",
                                    interface_config.get("name"),
                                )
                                continue

                            # Check if this interface has any WAN configuration (main interface or subinterfaces)
                            has_wan_main = interface_config.get("circuit") is not None
                            wan_subinterfaces = []

                            for sub_interface in self._get_subinterfaces(interface_config):
                                if self._is_absent(sub_interface):
                                    continue  # state:absent is LAN-only — ignore in the WAN task
                                if sub_interface.get("circuit"):
                                    wan_subinterfaces.append(sub_interface)
                                    LOG.info(
                                        " ✓ Found WAN subinterface '%s.%s' with circuit '%s' for device: %s",
                                        interface_config.get("name"),
                                        sub_interface.get("vlan"),
                                        sub_interface.get("circuit"),
                                        device_name,
                                    )

                            all_subinterfaces = wan_subinterfaces

                            # Process this interface if it has any WAN configuration
                            if has_wan_main or wan_subinterfaces:
                                if has_wan_main and all_subinterfaces:
                                    # Both main interface and subinterfaces have WAN config
                                    combined_config = interface_config.copy()
                                    combined_config["sub_interfaces"] = all_subinterfaces
                                    self._apply_interface(
                                        output_config[device_id]["edge"], action="add", **combined_config
                                    )
                                    interfaces_configured += 1 + len(all_subinterfaces)
                                    LOG.info(
                                        " ✓ To configure WAN main interface '%s' with circuit '%s' "
                                        "and %s WAN subinterfaces for device: %s",
                                        interface_config.get("name"),
                                        interface_config.get("circuit"),
                                        len(all_subinterfaces),
                                        device_name,
                                    )

                                elif has_wan_main:
                                    # Only main interface has WAN config
                                    main_config = interface_config.copy()
                                    main_config.pop("sub_interfaces", None)  # Remove subinterfaces (both param names)
                                    main_config.pop("subinterfaces", None)
                                    self._apply_interface(output_config[device_id]["edge"], action="add", **main_config)
                                    interfaces_configured += 1
                                    LOG.info(
                                        " ✓ To configure WAN main interface '%s' with circuit '%s' for device: %s",
                                        interface_config.get("name"),
                                        interface_config.get("circuit"),
                                        device_name,
                                    )

                                elif all_subinterfaces:
                                    # Only WAN subinterfaces - create minimal config
                                    subinterface_config = {
                                        "name": interface_config.get("name"),
                                        "sub_interfaces": all_subinterfaces,
                                    }
                                    self._apply_interface(
                                        output_config[device_id]["edge"], action="add", **subinterface_config
                                    )
                                    interfaces_configured += len(all_subinterfaces)
                                    LOG.info(
                                        " ✓ Configure %s subinterfaces for interface '%s' on device: %s",
                                        len(all_subinterfaces),
                                        interface_config.get("name"),
                                        device_name,
                                    )
                            else:
                                LOG.info(
                                    " ✗ Skipping interface '%s' - no configuration found", interface_config.get("name")
                                )

                    if circuits_only:
                        LOG.info(
                            "Device %s summary: %s circuits configured (circuits-only mode)",
                            device_name,
                            circuits_configured,
                        )
                    else:
                        LOG.info(
                            "Device %s summary: %s circuits, %s WAN interfaces to be configured",
                            device_name,
                            circuits_configured,
                            interfaces_configured,
                        )
                    edge = output_config[device_id]["edge"]
                    LOG.info("Final config for %s: %s", device_name, edge)

                    # Field-level idempotency: skip devices already in desired state.
                    if edge.get("interfaces") or edge.get("circuits"):
                        iface_by_name = {c.get("name"): c for c in configs.get("interfaces", [])}
                        circ_by_name = {c.get("circuit"): c for c in configs.get("circuits", [])}
                        changed, before, after = self._configure_device_diff(
                            gcs, edge, iface_by_name, circ_by_name, default_lan
                        )
                        if changed:
                            self._record_device_diff(result, device_name, before, after)
                        else:
                            del output_config[device_id]
                            result["skipped_devices"].append(device_name)
                            LOG.info(" ✓ No changes needed for %s, skipping", device_name)
                    else:
                        result["skipped_devices"].append(device_name)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error configuring device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Configuration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = bool(result["configured_devices"])
                if circuits_only:
                    LOG.info("Successfully configured circuits for %s devices (circuits-only mode)", len(output_config))
                else:
                    LOG.info("Successfully configured circuits and interfaces for %s devices", len(output_config))
            else:
                if circuits_only:
                    LOG.warning("No circuit configurations to apply")
                else:
                    LOG.warning("No circuit or interface configurations to apply")

            return result

        except Exception as e:
            LOG.error("Error in WAN circuits and interfaces configuration: %s", str(e))
            raise ConfigurationError(f"WAN circuits and interfaces configuration failed: {str(e)}")

    def deconfigure_wan_circuits_interfaces(
        self, interface_config_file: str, circuit_config_file=None, circuits_only: bool = False
    ) -> dict:
        """
        Deconfigure WAN interfaces and/or circuit static routes for multiple devices concurrently (idempotent).

        - If `circuits_only` is True: only deconfigure circuit static routes (skip interface deconfiguration).
          Static route deletion is idempotent: routes are removed only if they currently exist on the device.
        - If `circuits_only` is False: deconfigure WAN interfaces (circuits may be affected implicitly by the platform).

        For idempotency, this method checks for current interface/subinterface existence and for circuit static routes
        (via `gsdk.get_device_info`) before building a delete payload.

        Ordering:
          - This method performs a two-stage WAN workflow when `circuits_only=False`:
            1) Remove static routes from referenced circuits (if any exist)
            2) Reset WAN interfaces to enterprise default LAN and detach circuits
          - This avoids backend failures when detaching a circuit that still has static routes.

        Args:
            interface_config_file: Path to the YAML file containing interface configurations
            circuit_config_file: Optional path to the YAML file containing circuit configurations
            circuits_only: If True, only deconfigure circuits, skip interface deconfiguration

        Returns:
            dict: Result with 'changed' status, deconfigured and skipped devices/interfaces.
                  When `circuits_only=True`, also includes `deconfigured_circuits` and `skipped_circuits`.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = new_apply_result(
            deconfigured_devices=[],
            deconfigured_interfaces=[],
            skipped_interfaces=[],
            deconfigured_circuits=[],
            skipped_circuits=[],
        )

        try:
            interface_config_data = self.render_config_file(interface_config_file)

            # Load circuit configurations if provided
            circuit_config_data = None
            if circuit_config_file:
                circuit_config_data = self.render_config_file(circuit_config_file)

            # Two-stage workflow:
            # 1) Remove circuit static routes for referenced WAN circuits (if any).
            # 2) Reset WAN interface(s) to default LAN and detach circuits.
            #
            # The backend can treat detaching a circuit from a WAN interface as a "circuit removal"
            # operation and will fail if static routes still exist on that circuit.
            output_config_circuits: Dict[int, Dict[str, Any]] = {}
            output_config_interfaces: Dict[int, Dict[str, Any]] = {}
            default_lan = f"default-{self.gsdk.get_enterprise_id()}"

            # Collect all device configurations first
            device_configs: Dict[str, Any] = {}

            # Collect interface configurations per device
            if "interfaces" in interface_config_data:
                for device_info in interface_config_data.get("interfaces") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["interfaces"] = config_list

            # Collect circuit configurations per device if provided
            if circuit_config_data and "circuits" in circuit_config_data:
                for device_info in circuit_config_data.get("circuits") or []:
                    for device_name, config_list in device_info.items():
                        if device_name not in device_configs:
                            device_configs[device_name] = {"interfaces": [], "circuits": []}
                        device_configs[device_name]["circuits"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id, gcs_device_info = fetch_device_by_name(
                        self.gsdk, device_name, self.gsdk.enterprise_info["company_name"]
                    )

                    # Collect circuit names referenced in this device's interfaces and subinterfaces
                    referenced_circuits = set()
                    for interface_config in configs.get("interfaces", []):
                        # Check main interface for circuit reference
                        if interface_config.get("circuit"):
                            referenced_circuits.add(interface_config["circuit"])
                        # Check subinterfaces for circuit references
                        for sub_interface in self._get_subinterfaces(interface_config):
                            if sub_interface.get("circuit"):
                                referenced_circuits.add(sub_interface["circuit"])

                    LOG.info(
                        "[deconfigure_wan_circuits_interfaces] Processing device: %s (ID: %s)", device_name, device_id
                    )
                    LOG.info("Referenced circuits: %s", list(referenced_circuits))

                    # Build separate payloads for circuits vs interfaces to enforce ordering.
                    device_circuit_config: Dict[str, Any] = {}
                    device_interface_config: Dict[str, Any] = {}

                    # Process circuits for this device (static route deconfiguration)
                    circuits_deconfigured = 0
                    if configs.get("circuits"):
                        device_circuit_config.setdefault("circuits", {})
                        for circuit_config in configs.get("circuits", []):
                            circuit_name = circuit_config.get("circuit")
                            if circuit_name not in referenced_circuits:
                                LOG.info(" ✗ Skipping circuit '%s' - not referenced in interface configs", circuit_name)
                                continue

                            existing_prefixes = self._get_circuit_static_route_prefixes(gcs_device_info, circuit_name)
                            LOG.info(
                                "[circuits-idempotency] %s/%s circuit '%s' existing static route prefixes: %s",
                                device_name,
                                device_id,
                                circuit_name,
                                sorted(existing_prefixes),
                            )

                            # If static_routes are specified in YAML, delete only those (and only if they exist).
                            # If none specified, interpret deconfigure as "remove any existing static routes".
                            static_routes_cfg = circuit_config.get("static_routes") or {}

                            if static_routes_cfg:
                                requested_prefixes = (
                                    set(static_routes_cfg.keys()) if isinstance(static_routes_cfg, dict) else set()
                                )
                                prefixes_to_delete = sorted(requested_prefixes & existing_prefixes)
                                missing_prefixes = sorted(requested_prefixes - existing_prefixes)
                                LOG.info(
                                    "[circuits-idempotency] %s/%s circuit '%s' requested=%s will_delete=%s missing=%s",
                                    device_name,
                                    device_id,
                                    circuit_name,
                                    sorted(requested_prefixes),
                                    prefixes_to_delete,
                                    missing_prefixes,
                                )
                                for prefix in missing_prefixes:
                                    result["skipped_circuits"].append(
                                        {
                                            "device": device_name,
                                            "circuit": circuit_name,
                                            "prefix": prefix,
                                            "reason": "Static route does not exist",
                                        }
                                    )
                            else:
                                prefixes_to_delete = sorted(existing_prefixes)
                                LOG.info(
                                    "[circuits-idempotency] %s/%s circuit '%s' no static_routes in "
                                    "YAML; will_delete_all_existing=%s",
                                    device_name,
                                    device_id,
                                    circuit_name,
                                    prefixes_to_delete,
                                )

                            if not prefixes_to_delete:
                                LOG.info(
                                    " ✓ No static route changes needed for circuit '%s' on %s, skipping",
                                    circuit_name,
                                    device_name,
                                )
                                result["skipped_circuits"].append(
                                    {
                                        "device": device_name,
                                        "circuit": circuit_name,
                                        "prefix": None,
                                        "reason": "Static routes already deconfigured",
                                    }
                                )
                                continue

                            delete_circuit_config = circuit_config.copy()
                            # Template expects static_routes dict keyed by prefix; values can be empty for delete.
                            delete_circuit_config["static_routes"] = {p: {} for p in prefixes_to_delete}
                            LOG.info(
                                "[circuits-idempotency] %s/%s circuit '%s' building delete payload for prefixes=%s",
                                device_name,
                                device_id,
                                circuit_name,
                                prefixes_to_delete,
                            )

                            self._apply_circuit(device_circuit_config, action="delete", **delete_circuit_config)
                            circuits_deconfigured += 1
                            result["deconfigured_circuits"].append(
                                {"device": device_name, "circuit": circuit_name, "static_routes": prefixes_to_delete}
                            )
                            LOG.info(
                                " ✓ To deconfigure %s static routes on circuit '%s' for device: %s",
                                len(prefixes_to_delete),
                                circuit_name,
                                device_name,
                            )

                    # Process interfaces for this device - skip if circuits_only=True
                    interfaces_deconfigured = 0
                    if not circuits_only:
                        for interface_config in configs.get("interfaces", []):
                            # Check if this interface has any WAN configuration (main interface or subinterfaces)
                            has_wan_main = interface_config.get("circuit") is not None
                            wan_subinterfaces = []
                            interface_name = interface_config.get("name")

                            for sub_interface in self._get_subinterfaces(interface_config):
                                if sub_interface.get("circuit"):
                                    wan_subinterfaces.append(sub_interface)
                                    LOG.info(
                                        " ✓ Found WAN subinterface '%s.%s' with circuit '%s' for device: %s",
                                        interface_name,
                                        sub_interface.get("vlan"),
                                        sub_interface.get("circuit"),
                                        device_name,
                                    )

                            # Process this interface if it has any WAN configuration
                            if has_wan_main or wan_subinterfaces:
                                main_interface_exists = self._check_interface_exists(gcs_device_info, interface_name)
                                current_lan = (
                                    self._get_interface_lan(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )
                                current_circuit = (
                                    self._get_interface_circuit(gcs_device_info, interface_name)
                                    if main_interface_exists
                                    else None
                                )

                                # For ethernet WAN: "deconfigure main" means reset parent to default
                                # LAN and clear circuit.
                                # Only do that when needed (state-aware idempotency).
                                main_needs_reset = (
                                    has_wan_main
                                    and main_interface_exists
                                    and ((current_lan != default_lan) or (current_circuit is not None))
                                )

                                # Check if main interface exists (if it has WAN config)
                                if has_wan_main:
                                    if main_interface_exists:
                                        if main_needs_reset:
                                            LOG.info(
                                                " ✓ WAN main interface '%s' exists on %s "
                                                "(lan=%s circuit=%s), will reset to %s",
                                                interface_name,
                                                device_name,
                                                current_lan,
                                                current_circuit,
                                                default_lan,
                                            )
                                        else:
                                            LOG.info(
                                                " ✓ WAN main interface '%s' already deconfigured "
                                                "on %s (lan=%s circuit=%s), skipping parent reset",
                                                interface_name,
                                                device_name,
                                                current_lan,
                                                current_circuit,
                                            )
                                    else:
                                        LOG.info(
                                            " ✗ WAN main interface '%s' does not exist on %s, skipping",
                                            interface_name,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": None,
                                                "reason": "Interface does not exist",
                                            }
                                        )

                                # Check if subinterfaces exist
                                existing_subinterfaces = []
                                for sub_interface in wan_subinterfaces:
                                    vlan = sub_interface.get("vlan")
                                    if self._check_interface_exists(gcs_device_info, interface_name, vlan):
                                        existing_subinterfaces.append(sub_interface)
                                        LOG.info(
                                            " ✓ WAN subinterface '%s.%s' exists on %s, will deconfigure",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                    else:
                                        LOG.info(
                                            " ✗ WAN subinterface '%s.%s' does not exist on %s, skipping",
                                            interface_name,
                                            vlan,
                                            device_name,
                                        )
                                        result["skipped_interfaces"].append(
                                            {
                                                "device": device_name,
                                                "interface": interface_name,
                                                "vlan": vlan,
                                                "reason": "Subinterface does not exist",
                                            }
                                        )

                                needs_deconfigure = bool(existing_subinterfaces) or main_needs_reset

                                if not needs_deconfigure:
                                    # Nothing to do: parent already reset and no subinterfaces exist
                                    result["skipped_interfaces"].append(
                                        {
                                            "device": device_name,
                                            "interface": interface_name,
                                            "vlan": None,
                                            "reason": "WAN interface already deconfigured",
                                        }
                                    )
                                    continue

                                if needs_deconfigure:
                                    device_interface_config.setdefault("interfaces", {})
                                    if has_wan_main and existing_subinterfaces:
                                        # Both main interface and subinterfaces have WAN config
                                        combined_config = interface_config.copy()
                                        combined_config["sub_interfaces"] = existing_subinterfaces
                                        # If parent is already reset, don't include circuit in payload;
                                        # just delete subinterfaces.
                                        if has_wan_main and not main_needs_reset:
                                            combined_config.pop("circuit", None)
                                        self._apply_interface(
                                            device_interface_config,
                                            action="delete",
                                            default_lan=default_lan,
                                            **combined_config,
                                        )
                                        interfaces_deconfigured += (1 if main_needs_reset else 0) + len(
                                            existing_subinterfaces
                                        )
                                        if main_needs_reset:
                                            LOG.info(
                                                " ✓ To reset WAN main interface '%s' to %s and "
                                                "deconfigure %s WAN subinterfaces for device: %s",
                                                interface_name,
                                                default_lan,
                                                len(existing_subinterfaces),
                                                device_name,
                                            )
                                            result["deconfigured_interfaces"].append(
                                                {"device": device_name, "interface": interface_name, "vlan": None}
                                            )
                                        else:
                                            LOG.info(
                                                " ✓ To deconfigure %s WAN subinterfaces for interface "
                                                "'%s' on device: %s (parent already reset)",
                                                len(existing_subinterfaces),
                                                interface_name,
                                                device_name,
                                            )
                                        for sub_intf in existing_subinterfaces:
                                            result["deconfigured_interfaces"].append(
                                                {
                                                    "device": device_name,
                                                    "interface": interface_name,
                                                    "vlan": sub_intf.get("vlan"),
                                                }
                                            )

                                    elif has_wan_main and main_needs_reset:
                                        # Only main interface needs reset (idempotent)
                                        main_config = interface_config.copy()
                                        main_config.pop(
                                            "sub_interfaces", None
                                        )  # Remove subinterfaces (both param names)
                                        main_config.pop("subinterfaces", None)
                                        device_interface_config.setdefault("interfaces", {})
                                        self._apply_interface(
                                            device_interface_config,
                                            action="delete",
                                            default_lan=default_lan,
                                            **main_config,
                                        )
                                        interfaces_deconfigured += 1
                                        LOG.info(
                                            " ✓ To deconfigure WAN main interface '%s' with circuit "
                                            "'%s' for device: %s",
                                            interface_name,
                                            interface_config.get("circuit"),
                                            device_name,
                                        )
                                        result["deconfigured_interfaces"].append(
                                            {"device": device_name, "interface": interface_name, "vlan": None}
                                        )

                                    elif existing_subinterfaces:
                                        # Only subinterfaces have WAN config - create minimal config
                                        subinterface_config = {
                                            "name": interface_name,
                                            "sub_interfaces": existing_subinterfaces,
                                        }
                                        device_interface_config.setdefault("interfaces", {})
                                        self._apply_interface(
                                            device_interface_config,
                                            action="delete",
                                            default_lan=default_lan,
                                            **subinterface_config,
                                        )
                                        interfaces_deconfigured += len(existing_subinterfaces)
                                        LOG.info(
                                            " ✓ Deconfigure %s WAN subinterfaces for interface '%s' on device: %s",
                                            len(existing_subinterfaces),
                                            interface_name,
                                            device_name,
                                        )
                                        for sub_intf in existing_subinterfaces:
                                            result["deconfigured_interfaces"].append(
                                                {
                                                    "device": device_name,
                                                    "interface": interface_name,
                                                    "vlan": sub_intf.get("vlan"),
                                                }
                                            )
                            else:
                                LOG.info(
                                    " ✗ Skipping interface '%s' - no configuration found", interface_config.get("name")
                                )
                    else:
                        LOG.info(" ✓ Skipping WAN interface deconfiguration (circuits-only mode)")

                    # Stage 1 (circuits): only if we have any static routes to remove
                    if device_circuit_config.get("circuits"):
                        output_config_circuits[device_id] = {"device_id": device_id, "edge": device_circuit_config}
                        before = self._current_snapshot(gcs_device_info, device_circuit_config)
                        self._record_device_diff(
                            result, device_name, before, device_circuit_config, branch="edge.circuits"
                        )
                        LOG.info(
                            "Device %s summary (stage1): %s circuits with static routes to be deconfigured",
                            device_name,
                            circuits_deconfigured,
                        )
                        LOG.info("Final circuits config for %s: %s", device_name, device_circuit_config)
                    else:
                        LOG.info("Device %s (stage1): No circuit static route changes needed", device_name)

                    # Stage 2 (interfaces): only if interface changes exist and we're not in circuits-only mode
                    if not circuits_only and device_interface_config.get("interfaces"):
                        output_config_interfaces[device_id] = {"device_id": device_id, "edge": device_interface_config}
                        before = self._current_snapshot(gcs_device_info, device_interface_config)
                        self._record_device_diff(
                            result, device_name, before, device_interface_config, branch="edge.interfaces"
                        )
                        LOG.info(
                            "Device %s summary (stage2): %s WAN interfaces to be deconfigured",
                            device_name,
                            interfaces_deconfigured,
                        )
                        LOG.info("Final interfaces config for %s: %s", device_name, device_interface_config)
                    else:
                        if circuits_only:
                            LOG.info("Device %s (stage2): skipped (circuits-only mode)", device_name)
                        else:
                            LOG.info("Device %s (stage2): No WAN interface changes needed", device_name)

                    if not device_circuit_config.get("circuits") and not device_interface_config.get("interfaces"):
                        result["skipped_devices"].append(device_name)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error deconfiguring device %s: %s", device_name, str(e))
                    LOG.error("Device ID: %s, Device Name: %s", device_id, device_name)
                    LOG.error("Exception type: %s", type(e).__name__)
                    LOG.error("Full traceback: %s", traceback.format_exc())
                    raise ConfigurationError(f"Deconfiguration failed for {device_name}: {str(e)}")

            # Execute stage 1 first (remove static routes), then stage 2 (detach circuits / reset WAN interfaces).
            if output_config_circuits:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config_circuits)
                result["changed"] = True
                LOG.info(
                    "Successfully deconfigured circuit static routes for %s devices (stage1)",
                    len(output_config_circuits),
                )

            if output_config_interfaces:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config_interfaces)
                result["changed"] = True
                LOG.info(
                    "Successfully deconfigured WAN interfaces for %s devices (stage2)", len(output_config_interfaces)
                )

            deconfigured_device_ids = sorted(set(output_config_circuits.keys()) | set(output_config_interfaces.keys()))
            if deconfigured_device_ids:
                result["deconfigured_devices"] = deconfigured_device_ids
            else:
                LOG.info(
                    "No changes needed - all circuits/routes and interfaces already deconfigured (changed: %s)",
                    result["changed"],
                )

            return result

        except Exception as e:
            LOG.error("Error in WAN circuits and interfaces deconfiguration: %s", str(e))
            LOG.error("Exception type: %s", type(e).__name__)
            LOG.error("Full traceback: %s", traceback.format_exc())
            raise ConfigurationError(f"WAN circuits and interfaces deconfiguration failed: {str(e)}")
