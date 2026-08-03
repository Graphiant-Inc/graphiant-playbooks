"""
OSPFv2 Manager

OSPF processes are configured under:
    edge.segments.<segment>.ospfv2Process

This module handles configure and deconfigure operations for OSPF processes.
Both operations are idempotent, and are safe to run multiple times.

Payload shape (captured from the Graphiant Portal "New OSPF" flow):
edge.segments.<segment>.ospfv2.process = {
        "areas": {
            "<areaName>": {
                "area": {
                    "areaId": "<areaId>",
                    "interfaces": {
                        "<interfaceName>": {
                            "interface": {
                                "authentication": {"authentication": {"keyId": <int>, "key": "<string>"}},
                                "bfd": {"bfd": {"enabled": <bool>, "minimumInterval": <int|null>}},
                                "deadIntervalValue": {"deadInterval": <int>},
                                "helloIntervalValue": {"helloInterval": <int>},
                                "interfaceName": "<interfaceName>",
                                "retransmitIntervalValue": {"retransmitInterval": <int>},
                                "type": "point_to_point" | "broadcast",
                            }
                        }
                    },
                    "name": "<areaName>",
                    "type": "normal" | "stub" | "nssa", -----> (on the portal, "normal" is the only available option)
                }
            }
        },
        "defaultOriginate": "unconditional" | "conditional" | "disabled",
        "manual": "<router-id>",
        "redistribution": {
            "<protocol>": {
                "protocol": {
                "type": "<protocol>",
                "metric": <int>,
                "metricType": "type_1"|"type_2"
                }
            }
        },
    }

    Deconfigure payload shape (captured device-config PUTs). Each area/redistribution
    protocol named in the YAML is identified by its key alone ('name' / 'protocol')
    and removed entirely -- every other field on that entry (areaId, type, interfaces,
    and each interface's own authentication/bfd/intervals) is ignored. This mirrors how
    every other manager in this collection handles deconfigure (e.g. static_routes_manager
    keys a route deletion off 'destinationPrefix' alone; bgp_manager off the peer key
    alone) -- it's what lets the SAME configure-shaped YAML be reused for deconfigure,
    since sibling descriptive fields never change the delete decision:

        "process": {
            "areas": {
                "secondArea": {"area": null},
                "CoreArea": {"area": null}
            },
            "redistribution": {"static": {"protocol": null}}
        }

    'defaultOriginate' and 'adminDistance' are scalar process-level settings, not named
    containers, so they're addressed by explicit value instead ('defaultOriginate:
    "disabled"'; 'adminDistance: null') rather than by key presence -- see
    _build_deconfigure_payload.

"""

from typing import Any, Dict, Iterator, Optional, Tuple

from .base_manager import BaseManager
from .device_config_common import fetch_device_by_name, format_config_payload_for_log, new_apply_result
from .exceptions import ConfigurationError
from .logger import setup_logger

LOG = setup_logger()


class OSPFv2Manager(BaseManager):
    """
    Manage OSPFv2 process configuration for a given device via raw device-config payload generation.
    """

    @staticmethod
    def _build_bfd(bfd_cfg: Any) -> Dict[str, Any]:
        if not isinstance(bfd_cfg, dict):
            raise ConfigurationError("'bfd' must be a dict")
        bfd_obj: Dict[str, Any] = {}
        if bfd_cfg.get("enabled") is not None:
            bfd_obj["enabled"] = bfd_cfg.get("enabled")
        if bfd_cfg.get("minimumInterval") is not None:
            bfd_obj["minimumInterval"] = bfd_cfg.get("minimumInterval")
        if bfd_cfg.get("multiplier") is not None:
            bfd_obj["multiplier"] = bfd_cfg.get("multiplier")
        return {"bfd": bfd_obj}

    @staticmethod
    def _build_authentication(
        auth_cfg: Any,
        device_name: Optional[str] = None,
        interface_name: Optional[str] = None,
        vault_md5_passwords: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if auth_cfg is None:
            return {"authentication": {}}
        if not isinstance(auth_cfg, dict):
            raise ConfigurationError("'authentication' must be a dict")

        auth_obj: Dict[str, Any] = {}
        # MD5 key: YAML wins if non-null, else vault fills it in (keyed by device -> interface),
        # else left unset (optional -- same precedence used for BGP md5Password elsewhere).
        key_val = auth_cfg.get("key")
        if key_val is None and vault_md5_passwords and device_name and interface_name:
            vault_key = (vault_md5_passwords.get(device_name) or {}).get(interface_name)
            if vault_key:
                key_val = vault_key
                LOG.debug(
                    "Injected OSPF MD5 authentication key for device '%s' interface '%s' from vault",
                    device_name,
                    interface_name,
                )
        if auth_cfg.get("keyId") is not None:
            auth_obj["keyId"] = auth_cfg.get("keyId")
        if key_val is not None:
            auth_obj["key"] = key_val
        return {"authentication": auth_obj}

    @staticmethod
    def _build_interface(
        if_cfg: Dict[str, Any],
        is_new: bool = False,
        device_name: Optional[str] = None,
        vault_md5_passwords: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not isinstance(if_cfg, dict):
            raise ConfigurationError("Each OSPF interface entry must be a dict")

        interface_name = if_cfg.get("interfaceName")
        if not interface_name:
            raise ConfigurationError("OSPF interface entry missing 'interfaceName'")

        interface_obj: Dict[str, Any] = {}
        if if_cfg.get("authentication") is not None:
            interface_obj["authentication"] = OSPFv2Manager._build_authentication(
                if_cfg.get("authentication"),
                device_name,
                interface_name,
                vault_md5_passwords,
            )

        if is_new:
            # A newly created interface will require these parameters to be added to the payload
            interface_obj["type"] = if_cfg.get("type", "point_to_point")
            interface_obj["helloIntervalValue"] = {"helloInterval": if_cfg.get("helloInterval", 10)}
            interface_obj["deadIntervalValue"] = {"deadInterval": if_cfg.get("deadInterval", 40)}
            interface_obj["retransmitIntervalValue"] = {"retransmitInterval": if_cfg.get("retransmitInterval", 5000)}
            if if_cfg.get("bfd") is not None:
                interface_obj["bfd"] = OSPFv2Manager._build_bfd(if_cfg.get("bfd"))
            else:
                interface_obj["bfd"] = {"bfd": {"enabled": False, "minimumInterval": None}}
            # Creation-only legacy flat fields (always zero; real values live in
            # the *Value siblings above)
            interface_obj["ifIndex"] = 0
            interface_obj["helloInterval"] = 0
            interface_obj["deadInterval"] = 0
            interface_obj["retransmitInterval"] = 0
            interface_obj["mtuIgnore"] = False
        else:
            if if_cfg.get("bfd") is not None:
                interface_obj["bfd"] = OSPFv2Manager._build_bfd(if_cfg.get("bfd"))
            if if_cfg.get("deadInterval") is not None:
                interface_obj["deadIntervalValue"] = {"deadInterval": if_cfg.get("deadInterval")}
            if if_cfg.get("helloInterval") is not None:
                interface_obj["helloIntervalValue"] = {"helloInterval": if_cfg.get("helloInterval")}
            if if_cfg.get("interfaceName") is not None:
                interface_obj["interfaceName"] = if_cfg.get("interfaceName")
            if if_cfg.get("retransmitInterval") is not None:
                interface_obj["retransmitIntervalValue"] = {"retransmitInterval": if_cfg.get("retransmitInterval")}
            if if_cfg.get("type") is not None:
                interface_obj["type"] = if_cfg.get("type")

        return {interface_name: {"interface": interface_obj}}

    @staticmethod
    def _build_area(
        area_cfg: Dict[str, Any],
        existing_areas: Optional[Dict[str, Any]] = None,
        device_name: Optional[str] = None,
        vault_md5_passwords: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        if not isinstance(area_cfg, dict):
            raise ConfigurationError("Each OSPF area entry must be a dict")

        area_obj: Dict[str, Any] = {}

        area_key = area_cfg.get("name")
        if not area_key:
            raise ConfigurationError("OSPF area entry missing 'name'")

        existing_areas = existing_areas or {}
        existing_area_entry = existing_areas.get(area_key)
        is_new_area = existing_area_entry is None
        existing_interfaces: Dict[str, Any] = {}
        if existing_area_entry is not None:
            existing_interfaces = (existing_area_entry.get("area") or {}).get("interfaces") or {}

        if is_new_area and area_cfg.get("areaId") is None:
            raise ConfigurationError(f"New OSPF area {area_key!r} requires 'areaId'")

        if area_cfg.get("areaId") is not None:
            area_obj["areaId"] = OSPFv2Manager._canonicalize_area_id(area_cfg.get("areaId"))

        if is_new_area:
            area_obj["type"] = area_cfg.get("type", "normal")
        elif area_cfg.get("type") is not None:
            area_obj["type"] = area_cfg.get("type")

        interfaces_cfg = area_cfg.get("interfaces")
        if interfaces_cfg is not None:
            if not isinstance(interfaces_cfg, list):
                raise ConfigurationError("'interfaces' must be a list")
            interfaces_payload: Dict[str, Any] = {}
            for if_cfg in interfaces_cfg:
                if_name = if_cfg.get("interfaceName") if isinstance(if_cfg, dict) else None
                is_new_if = if_name not in existing_interfaces
                interfaces_payload.update(
                    OSPFv2Manager._build_interface(if_cfg, is_new_if, device_name, vault_md5_passwords)
                )
            area_obj["interfaces"] = interfaces_payload
        elif is_new_area:
            # New area, no interfaces given -- API requires an explicit blank
            # map, not an omitted key.
            area_obj["interfaces"] = {}

        return area_key, {"area": area_obj}

    @staticmethod
    def _build_redistribution(
        redist_cfg: Dict[str, Any], existing_redistribution: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not redist_cfg:
            return {}
        if not isinstance(redist_cfg, list):
            raise ConfigurationError("'redistribution' must be a list")

        existing_redistribution = existing_redistribution or {}

        redistribution_payload: Dict[str, Any] = {}
        for entry in redist_cfg:
            redistribution_obj: Dict[str, Any] = {}
            if not isinstance(entry, dict):
                raise ConfigurationError("Each redistribution entry must be a dict")
            protocol = entry.get("protocol")
            if not protocol:
                raise ConfigurationError("Redistribution entry missing 'protocol'")

            is_new = protocol not in existing_redistribution

            redistribution_obj["type"] = protocol

            if is_new:
                # New redistribution entry: metric/metricType default if not
                # given in YAML.
                redistribution_obj["metric"] = entry.get("metric", 1)
                redistribution_obj["metricType"] = entry.get("metricType", "type_2")
            else:
                # Existing entry: sparse update -- only touch what's specified.
                if entry.get("metric") is not None:
                    redistribution_obj["metric"] = entry.get("metric")
                if entry.get("metricType") is not None:
                    redistribution_obj["metricType"] = entry.get("metricType")

            redistribution_payload[protocol] = {"protocol": redistribution_obj}
        return redistribution_payload

    @staticmethod
    def _build_deconfigure_area(area_cfg: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Build one area entry for a deconfigure payload.

        Identified by 'name' alone; every other field on the entry (areaId, type,
        interfaces, and each interface's own authentication/bfd/etc.) is ignored,
        the same way deconfigure works everywhere else in this collection (e.g.
        static_routes_manager keys a route deletion off 'destinationPrefix' alone,
        bgp_manager off the peer key alone) -- this is what lets the SAME
        configure-shaped YAML be reused for deconfigure: whatever areas the YAML
        names get removed entirely, regardless of how they're described.
        """
        if not isinstance(area_cfg, dict):
            raise ConfigurationError("Each deconfigure area entry must be a dict")

        area_name = area_cfg.get("name")
        if not area_name:
            raise ConfigurationError("Each deconfigure area entry needs 'name'")

        return area_name, {"area": None}

    @staticmethod
    def _build_deconfigure_payload(
        ospf_cfg: Any, existing_ospf: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Build a payload that will remove/turn off OSPFv2 configuration on a segment.

        Returns one of two confirmed shapes:
        - {"process": {...}}  -- targeted removal of specific areas/redistribution
            entries and/or turning defaultOriginate off and/or clearing
            adminDistance.
        - {}                  -- the ONLY confirmed way to clear routerId/'manual'.
            Requires the device to ALREADY have zero areas and zero redistribution
            entries (this push isn't adding any either). If areas/redistribution still
            exist, 'routerId: null' is deferred: this push removes what it can, and a
            second deconfigure run (after this one lands) is required to actually clear
            the router ID.
        """
        if not isinstance(ospf_cfg, dict):
            raise ConfigurationError("'ospfv2' must be a dict for deconfigure")

        areas_cfg = ospf_cfg.get("areas") or []
        redist_cfg = ospf_cfg.get("redistribution") or []
        default_originate = ospf_cfg.get("defaultOriginate")
        admin_distance = ospf_cfg.get("adminDistance")
        wants_router_id_removed = "routerId" in ospf_cfg and ospf_cfg.get("routerId") is None

        existing_process = (existing_ospf or {}).get("process") or {}
        existing_areas = existing_process.get("areas") or {}
        existing_redist = existing_process.get("redistribution") or {}

        if not areas_cfg and not redist_cfg and default_originate is None and not wants_router_id_removed:
            raise ConfigurationError(
                "Deconfigure requires at least one entry under 'areas' and/or 'redistribution' "
                "identifying what to remove, a 'defaultOriginate' value to turn off, or "
                "'routerId: null' to remove the router ID once nothing else remains."
            )

        if wants_router_id_removed and not existing_areas and not existing_redist and not areas_cfg and not redist_cfg:
            # Confirmed: device already clean, this push adds nothing -- safe to
            # send the special full-clear payload.
            return {}

        if wants_router_id_removed:
            LOG.info(
                "[ospfv2] 'routerId: null' was requested, but areas and/or redistribution "
                "still exist (or are being removed in this same push). The API only clears "
                "the router ID once the OSPF process has zero areas and zero redistribution "
                "entries -- run deconfigure again after this push completes to actually "
                "remove the router ID."
            )

        process_obj: Dict[str, Any] = {}

        if "adminDistance" in ospf_cfg and admin_distance is None:
            process_obj["adminDistance"] = {}

        if default_originate:
            process_obj["defaultOriginate"] = "disabled"

        if areas_cfg:
            if not isinstance(areas_cfg, list):
                raise ConfigurationError("'areas' must be a list")
            areas_payload: Dict[str, Any] = {}
            for area_cfg in areas_cfg:
                area_key, area_obj = OSPFv2Manager._build_deconfigure_area(area_cfg)
                areas_payload[area_key] = area_obj
            process_obj["areas"] = areas_payload

        if redist_cfg:
            if not isinstance(redist_cfg, list):
                raise ConfigurationError("'redistribution' must be a list")
            redistribution_payload: Dict[str, Any] = {}
            for entry in redist_cfg:
                if not isinstance(entry, dict) or not entry.get("protocol"):
                    raise ConfigurationError("Each deconfigure redistribution entry needs 'protocol'")
                redistribution_payload[entry["protocol"]] = {"protocol": None}
            process_obj["redistribution"] = redistribution_payload

        return {"process": process_obj}

    @staticmethod
    def _build_configure_payload(
        ospf_cfg: Any,
        existing_ospf: Optional[Dict[str, Any]] = None,
        device_name: Optional[str] = None,
        vault_md5_passwords: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Convert one segment's 'ospfv2' YAML block into the API payload shape.
        """
        if not isinstance(ospf_cfg, dict):
            raise ConfigurationError("'ospfv2' must be a dict")

        existing_process = (existing_ospf or {}).get("process") or {}
        existing_areas = existing_process.get("areas") or {}
        is_new_process = not existing_process

        process_obj: Dict[str, Any] = {}

        if is_new_process:
            router_id = ospf_cfg.get("routerId")
            if not router_id:
                raise ConfigurationError("Creating a new OSPF process requires 'routerId'")
            process_obj["manual"] = router_id
        elif ospf_cfg.get("routerId") is not None:
            process_obj["manual"] = ospf_cfg.get("routerId")

        areas_cfg = ospf_cfg.get("areas")
        areas_payload: Dict[str, Any] = {}
        if areas_cfg:
            if not isinstance(areas_cfg, list):
                raise ConfigurationError("'areas' must be a list")
            for area_cfg in areas_cfg:
                area_key, area_obj = OSPFv2Manager._build_area(
                    area_cfg, existing_areas, device_name, vault_md5_passwords
                )
                areas_payload[area_key] = area_obj
            process_obj["areas"] = areas_payload

        # An area exists "after this push" if the device already has one, or
        # this push is adding one.
        will_have_area = bool(existing_areas) or bool(areas_payload)

        if ospf_cfg.get("defaultOriginate") is not None:
            if not will_have_area:
                raise ConfigurationError(
                    "'defaultOriginate' cannot be set until at least one OSPF area exists "
                    "(add an 'areas' entry in this same push, or configure an area first)."
                )
            default_originate = ospf_cfg.get("defaultOriginate")
            if default_originate not in ("unconditional", "conditional", "disabled"):
                raise ConfigurationError("'defaultOriginate' must be one of 'unconditional', 'conditional', 'disabled'")
            process_obj["defaultOriginate"] = default_originate

        if ospf_cfg.get("adminDistance") is not None:
            if not will_have_area:
                raise ConfigurationError(
                    "'adminDistance' cannot be set until at least one OSPF area exists "
                    "(add an 'areas' entry in this same push, or configure an area first)."
                )
            process_obj["adminDistance"] = {"adminDistance": ospf_cfg.get("adminDistance")}

        redistribution_cfg = ospf_cfg.get("redistribution")
        if redistribution_cfg:
            existing_redistribution = existing_process.get("redistribution") or {}
            process_obj["redistribution"] = OSPFv2Manager._build_redistribution(
                redistribution_cfg, existing_redistribution
            )

        return {"process": process_obj}

    @staticmethod
    def _lan_segment_names_from_device(device_dict: Dict[str, Any]) -> frozenset:
        """Collect LAN segment names from a device's GET response (top-level 'segments')."""
        names: set = set()
        segments = device_dict.get("segments") if isinstance(device_dict, dict) else None
        if isinstance(segments, dict):
            names.update(k for k in segments if k)
        elif isinstance(segments, list):
            for seg in segments:
                if isinstance(seg, dict) and seg.get("name"):
                    names.add(seg["name"])
        return frozenset(names)

    @staticmethod
    def _interface_names_from_device(device_dict: Dict[str, Any]) -> frozenset:
        """Collect main and subinterface names from a device's GET response (top-level 'interfaces')."""
        names: set = set()
        interfaces = device_dict.get("interfaces") if isinstance(device_dict, dict) else None
        for iface in interfaces or []:
            if not isinstance(iface, dict):
                continue
            parent = iface.get("name")
            if parent:
                names.add(parent)
            subs = iface.get("subinterfaces")
            if isinstance(subs, dict):
                for vlan_key, sub in subs.items():
                    if parent and vlan_key is not None:
                        names.add(f"{parent}.{vlan_key}")
                    if isinstance(sub, dict) and sub.get("name"):
                        names.add(sub["name"])
            elif isinstance(subs, list):
                for sub in subs:
                    if not isinstance(sub, dict):
                        continue
                    if sub.get("name"):
                        names.add(sub["name"])
                    elif parent and sub.get("vlan") is not None:
                        names.add(f"{parent}.{sub['vlan']}")
        return frozenset(names)

    @staticmethod
    def _validate_segment_and_interfaces(
        device_name: str, seg_name: str, ospf_cfg: Any, device_dict: Dict[str, Any]
    ) -> None:
        """
        Raise ConfigurationError if the OSPF config references a LAN segment or interface
        that does not exist on this device, per its GET response.
        """
        valid_segments = OSPFv2Manager._lan_segment_names_from_device(device_dict)
        if seg_name not in valid_segments:
            known = (
                ", ".join(sorted(valid_segments))
                if valid_segments
                else ("(none — device has no LAN segments in GET response)")
            )
            raise ConfigurationError(
                f"Device '{device_name}': ospfv2 references LAN segment {seg_name!r} which does not exist "
                f"on this device. Known segment names: {known}."
            )

        if not isinstance(ospf_cfg, dict):
            return
        areas_cfg = ospf_cfg.get("areas")
        if not isinstance(areas_cfg, list):
            return

        valid_interfaces = OSPFv2Manager._interface_names_from_device(device_dict)
        for area_cfg in areas_cfg:
            if not isinstance(area_cfg, dict):
                continue
            for if_cfg in area_cfg.get("interfaces") or []:
                if not isinstance(if_cfg, dict):
                    continue
                interface_name = if_cfg.get("interfaceName") or if_cfg.get("interface_name")
                if interface_name and interface_name not in valid_interfaces:
                    known = (
                        ", ".join(sorted(valid_interfaces))
                        if valid_interfaces
                        else ("(none — configure LAN interfaces first, e.g. interface_management.yml --tags lan)")
                    )
                    raise ConfigurationError(
                        f"Device '{device_name}': ospfv2 area {area_cfg.get('name')!r} references interface "
                        f"{interface_name!r} which does not exist on this device (segment {seg_name!r}). "
                        f"Known interfaces: {known}."
                    )

    @staticmethod
    def _canonicalize_area_id(area_id: Any) -> str:
        """
        Canonicalize an OSPF area ID for comparison. Area IDs sent on PUT use plain
        integers as strings ('0', '1'), but the device's GET response returns
        dotted-decimal form ('0.0.0.0', '0.0.0.1') -- the standard OSPF area ID
        representation. This makes both forms compare equal.
        """
        if area_id is None:
            return ""
        s = str(area_id)
        if "." in s:
            return s
        try:
            n = int(s)
        except ValueError:
            return s
        return f"{(n >> 24) & 0xFF}.{(n >> 16) & 0xFF}.{(n >> 8) & 0xFF}.{n & 0xFF}"

    @staticmethod
    def _extract_ospf_from_GET_response(
        ospfv2_process: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Translate the GET-shaped 'ospfv2Process' (list-based areas/redistributedProtocols,
        device field names) into the same dict-keyed-by-name shape that
        _build_area/_build_interface/_build_redistribution produce for the PUT payload's
        'process' object, so downstream comparison functions can treat both sides
        identically. Device-only fields (id, cost, the device-assigned ifIndex) are
        dropped since they have no equivalent on the desired/YAML side.
        """
        if not isinstance(ospfv2_process, dict):
            return {}

        areas_payload: Dict[str, Any] = {}
        for area in ospfv2_process.get("areas") or []:
            if not isinstance(area, dict):
                continue
            area_name = area.get("name")
            if not area_name:
                continue

            interfaces_payload: Dict[str, Any] = {}
            for iface in area.get("interfaces") or []:
                if not isinstance(iface, dict):
                    continue
                iface_name = iface.get("interface")
                if not iface_name:
                    continue

                interface_obj: Dict[str, Any] = {
                    "interfaceName": iface_name,
                    "type": iface.get("type"),
                }
                if iface.get("retransmitIntervalValue") is not None:
                    interface_obj["retransmitIntervalValue"] = {
                        "retransmitInterval": iface.get("retransmitIntervalValue")
                    }

                auth = iface.get("authentication")

                if auth:
                    interface_obj["authentication"] = {
                        "authentication": {
                            "keyId": auth.get("keyId"),
                            "key": auth.get("key"),
                        }
                    }

                bfd = iface.get("bfd")
                if bfd:
                    if bfd.get("enabled"):
                        interface_obj["bfd"] = {
                            "bfd": {
                                "enabled": True,
                                "minimumInterval": bfd.get("minimumInterval"),
                                "multiplier": bfd.get("multiplier"),
                            }
                        }
                    else:
                        # enabled is null (or False) -> BFD is off; minimumInterval/multiplier
                        # are meaningless in this state and must be excluded from comparison,
                        # matching the shape _build_bfd produces when BFD is off.
                        interface_obj["bfd"] = {"bfd": {"enabled": False}}

                if iface.get("deadIntervalValue") is not None:
                    interface_obj["deadIntervalValue"] = {"deadInterval": iface.get("deadIntervalValue")}
                if iface.get("helloIntervalValue") is not None:
                    interface_obj["helloIntervalValue"] = {"helloInterval": iface.get("helloIntervalValue")}

                interfaces_payload[iface_name] = {"interface": interface_obj}

            areas_payload[area_name] = {
                "area": {
                    "areaId": OSPFv2Manager._canonicalize_area_id(area.get("areaId")),
                    "type": area.get("type", "normal"),
                    "interfaces": interfaces_payload,
                    "name": area_name,
                }
            }

        redistribution_payload: Dict[str, Any] = {}
        for entry in ospfv2_process.get("redistributedProtocols") or []:
            if not isinstance(entry, dict):
                continue
            protocol = entry.get("redistType")
            if not protocol:
                continue
            protocol_obj: Dict[str, Any] = {"type": protocol}
            if entry.get("metric") is not None:
                protocol_obj["metric"] = entry.get("metric")
            if entry.get("metricType") is not None:
                protocol_obj["metricType"] = entry.get("metricType")
            redistribution_payload[protocol] = {"protocol": protocol_obj}

        existing_admin_distance = ospfv2_process.get("adminDistance")
        if not existing_admin_distance:  # None or 0 both mean "not configured"
            existing_admin_distance = None

        return {
            "manual": ospfv2_process.get("routerId"),
            "defaultOriginate": ospfv2_process.get("defaultOriginate"),
            "adminDistance": (
                {"adminDistance": existing_admin_distance} if existing_admin_distance is not None else {}
            ),
            "areas": areas_payload,
            "redistribution": redistribution_payload,
        }

    @staticmethod
    def _get_existing_ospf_payload(device_dict: Dict[str, Any], seg_name: str) -> Optional[Dict[str, Any]]:
        """
        Extract the existing OSPFv2 payload from the device config.
        """
        if not isinstance(device_dict, dict):
            return None

        segments = device_dict.get("segments")
        seg_obj = None
        if isinstance(segments, dict):
            # Common case: segments is a dict keyed by segment name
            seg_obj = segments.get(seg_name)
        elif isinstance(segments, list):
            for item in segments:
                if isinstance(item, dict) and item.get("name") == seg_name:
                    seg_obj = item
                    break

        if not isinstance(seg_obj, dict):
            return {}

        ospfv2_process = seg_obj.get("ospfv2Process")
        if not ospfv2_process:
            return {}

        return {"process": OSPFv2Manager._extract_ospf_from_GET_response(ospfv2_process)}

    @staticmethod
    def _normalize_ospf(ospf: Any) -> Optional[Dict[str, Any]]:
        """Normalize an ospfv2 block for stable before/after comparison."""
        if not isinstance(ospf, dict):
            return None
        process = ospf.get("process")
        if not isinstance(process, dict):
            return None
        normalized: Dict[str, Any] = {}
        if "manual" in process:
            normalized["manual"] = process["manual"]
        if "defaultOriginate" in process:
            normalized["defaultOriginate"] = process["defaultOriginate"]
        if "adminDistance" in process:
            normalized["adminDistance"] = process["adminDistance"]
        if "areas" in process:
            normalized["areas"] = process["areas"] or {}
        if "redistribution" in process:
            normalized["redistribution"] = process["redistribution"] or {}
        return normalized

    @staticmethod
    def _deconfigure_targets_present(desired_process: Dict[str, Any], existing_ospf: Any) -> bool:
        """
        For deconfigure: return True if anything the payload targets for removal/turn-off
        currently exists (in some form) on the device -- i.e. there's actually a change to push.
        Expects existing_ospf already translated into {'process': {...}} shape by
        _get_existing_ospf_payload (dict-keyed areas/redistribution, not raw GET lists).
        """
        existing_process = (existing_ospf or {}).get("process") if isinstance(existing_ospf, dict) else None
        existing_areas = (existing_process or {}).get("areas") or {}
        existing_redist = (existing_process or {}).get("redistribution") or {}

        if "defaultOriginate" in desired_process:
            existing_default_originate = (existing_process or {}).get("defaultOriginate")
            if desired_process["defaultOriginate"] != existing_default_originate:
                return True

        if "adminDistance" in desired_process:
            existing_admin_distance = (existing_process or {}).get("adminDistance")
            if existing_admin_distance:  # non-empty/non-None means still set, needs resetting
                return True

        for area_key in desired_process.get("areas") or {}:
            if area_key in existing_areas:
                return True  # whole-area removal target exists

        for protocol_key in desired_process.get("redistribution") or {}:
            if protocol_key in existing_redist:
                return True

        return False

    @staticmethod
    def _sparse_differs(desired: Any, existing: Any) -> bool:
        """
        Return True if any key present in `desired` doesn't match the corresponding
        value in `existing`. Keys absent from `desired` are never compared -- they
        mean "not touched by this run," not "should be empty." Recurses into nested
        dicts so partial updates at any depth (e.g. one interface's bfd settings)
        don't trigger false differences from sibling fields the user didn't specify.
        """
        if not isinstance(desired, dict):
            return desired != existing

        if not isinstance(existing, dict):
            # desired has structure but existing doesn't (or is None/absent) --
            # only a real difference if desired actually has any keys to check.
            return bool(desired)

        for key, desired_value in desired.items():
            existing_value = existing.get(key)
            if isinstance(desired_value, dict):
                if OSPFv2Manager._sparse_differs(desired_value, existing_value):
                    return True
            else:
                if desired_value != existing_value:
                    return True
        return False

    def _payload_differs_from_existing(
        self, desired_payload: Dict[str, Any], device_info_dict: Any, operation: str
    ) -> bool:
        desired_edge = (desired_payload or {}).get("edge") or {}
        desired_segments = desired_edge.get("segments") or {}
        if not desired_segments:
            return False

        device_dict = device_info_dict if isinstance(device_info_dict, dict) else {}

        for seg_name, seg_cfg in desired_segments.items():
            desired_ospf = (seg_cfg or {}).get("ospfv2") or {}
            existing_ospf = self._get_existing_ospf_payload(device_dict, seg_name)

            if operation == "deconfigure":
                if desired_ospf == {}:
                    # Special routerId-clearing payload -- only a real change if the
                    # device still has a router ID set.
                    existing_process = (existing_ospf or {}).get("process") or {}
                    if existing_process.get("manual"):
                        return True
                    continue
                desired_process = desired_ospf.get("process") or {}
                if self._deconfigure_targets_present(desired_process, existing_ospf):
                    return True
                continue

            desired_normalized = self._normalize_ospf(desired_ospf) or {}
            existing_normalized = self._normalize_ospf(existing_ospf) or {}
            if self._sparse_differs(desired_normalized, existing_normalized):
                return True

        return False

    def _iter_device_payloads(
        self,
        config_yaml_file: str,
        operation: str,
        vault_ospf_md5_passwords: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Tuple[int, str, Dict[str, Any], Dict[str, Any]]]:
        """
        Iterate through the YAML and yield per-device payloads.

        Yields:
            (device_id, device_name, payload, device_dict)
        """
        if operation not in ("configure", "deconfigure"):
            raise ConfigurationError(f"Unsupported operation '{operation}'")

        vault_md5 = vault_ospf_md5_passwords if isinstance(vault_ospf_md5_passwords, dict) else {}

        cfg = self.render_config_file(config_yaml_file) or {}
        device_list = cfg.get("ospfv2") or []
        if not device_list:
            LOG.info("[ospfv2] No 'ospfv2' section found in %s", config_yaml_file)
            return

        if self.gsdk.enterprise_info is None:
            raise ConfigurationError("enterprise_info not set on gsdk")
        enterprise = self.gsdk.enterprise_info["company_name"]

        for device_entry in device_list:
            if not isinstance(device_entry, dict):
                raise ConfigurationError("Each entry in 'ospfv2' must be a dict keyed by device name")

            for device_name, device_cfg in device_entry.items():
                if not isinstance(device_cfg, dict):
                    raise ConfigurationError(f"Device '{device_name}' config must be a dict")

                device_id, device_dict = fetch_device_by_name(self.gsdk, device_name, enterprise)

                segments_cfg = device_cfg.get("segments") or device_cfg.get("lanSegments") or []
                if not isinstance(segments_cfg, list):
                    raise ConfigurationError(f"Device '{device_name}': 'segments' must be a list")

                segments_payload: Dict[str, Any] = {}
                for seg in segments_cfg:
                    if not isinstance(seg, dict):
                        raise ConfigurationError(f"Device '{device_name}': each segment must be a dict")

                    seg_name = seg.get("lanSegment") or seg.get("name")
                    if not seg_name:
                        raise ConfigurationError(f"Device '{device_name}': segment missing 'lanSegment'")

                    ospf_cfg = seg.get("ospfv2")
                    if ospf_cfg is None:
                        # No 'ospfv2' block for this segment -- nothing to configure/deconfigure, skip it.
                        LOG.info(
                            "[ospfv2] Device '%s' segment '%s' has no 'ospfv2' block, nothing to configure; skipping",
                            device_name,
                            seg_name,
                        )
                        continue

                    existing_ospf = self._get_existing_ospf_payload(device_dict, seg_name)
                    if operation == "configure":
                        self._validate_segment_and_interfaces(device_name, seg_name, ospf_cfg, device_dict)
                        ospf_payload = OSPFv2Manager._build_configure_payload(
                            ospf_cfg, existing_ospf, device_name, vault_md5
                        )
                    else:
                        ospf_payload = OSPFv2Manager._build_deconfigure_payload(ospf_cfg, existing_ospf)

                    segments_payload[seg_name] = {"ospfv2": ospf_payload}

                payload: Dict[str, Any] = {"edge": {"segments": segments_payload}}

                yield device_id, device_name, payload, device_dict

    def _push_device_config_preserving_nulls(self, device_id: int, payload: Dict[str, Any]):
        """
        PUT one device's OSPFv2 config payload while preserving explicit `null` values.

        Deconfigure payloads built by this manager rely on an explicit `null` (e.g.
        {"interface": None}, {"protocol": None}) to tell the API "delete this key" --
        as opposed to omitting the key, which means "leave it untouched" (see the module
        docstring above). Pushing that payload via gsdk.put_device_config_raw() builds a
        graphiant_sdk.V1DevicesDeviceIdConfigPutRequest and serializes it through that
        model's .to_dict() (used both for the log line and for the actual request body) --
        which calls pydantic's model_dump(exclude_none=True) and silently collapses every
        explicit None down to an omitted key (e.g. {"interface": None} -> {}). The API then
        rejects/misinterprets that empty object instead of performing the intended deletion
        (observed as 500s like "error creating ospf process on device ..."). This method
        instead builds the request via the SDK's api_client.param_serialize()/call_api()
        directly, with the raw payload dict as the body -- the same "bypass the typed
        request model" pattern already used elsewhere in gcsdk_client.py (see
        edit_data_exchange_customer) for calls that need explicit control over what's on
        the wire. ApiClient.sanitize_for_serialization() preserves None for plain dicts, so
        the nulls this payload depends on actually reach the API.

        This is scoped to ospfv2_manager.py deliberately -- gsdk.put_device_config_raw()
        is shared across many managers, so it is not touched here.
        """
        gsdk = self.gsdk

        request_body: Dict[str, Any] = {}
        if payload.get("edge") is not None:
            request_body["edge"] = payload["edge"]
        if payload.get("core") is not None:
            request_body["core"] = payload["core"]

        if getattr(gsdk, "check_mode", False):
            LOG.info(
                "[check_mode] ospfv2: would push config for device_id=%s: \n%s",
                device_id,
                format_config_payload_for_log(request_body),
            )
            return None

        gsdk.verify_device_portal_status(device_id=device_id)
        LOG.info(
            "ospfv2: config to be pushed for %s: \n%s",
            device_id,
            format_config_payload_for_log(request_body),
        )

        api_client = gsdk.api.api_client
        method, url, header_params, body, post_params = api_client.param_serialize(
            "PUT",
            "/v1/devices/{deviceId}/config",
            path_params={"deviceId": device_id},
            header_params={
                "Authorization": gsdk.bearer_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body=request_body,
        )
        try:
            response_data = api_client.call_api(method, url, header_params, body, post_params)
            response_data.read()
        except Exception as e:
            raise ConfigurationError(f"ospfv2: config push failed for device {device_id}: {e}") from e

        gsdk.verify_device_portal_status(device_id=device_id)
        return response_data

    def apply_ospf(
        self,
        config_yaml_file: str,
        operation: str,
        vault_ospf_md5_passwords: Optional[Dict[str, Any]] = None,
    ) -> dict:
        result = new_apply_result()
        output_config: Dict[int, Dict[str, Any]] = {}

        for device_id, device_name, payload, device_dict in self._iter_device_payloads(
            config_yaml_file,
            operation=operation,
            vault_ospf_md5_passwords=vault_ospf_md5_passwords,
        ):
            if not self._payload_differs_from_existing(payload, device_dict, operation=operation):
                LOG.info(
                    "[ospfv2] ✓ No changes needed for %s (ID: %s), skipping",
                    device_name,
                    device_id,
                )
                result["skipped_devices"].append(device_name)
                continue

            desired_segments = payload.get("edge", {}).get("segments", {})
            before_segments: Dict[str, Any] = {}
            for seg_name in desired_segments:
                before_segments[seg_name] = {"ospfv2": self._get_existing_ospf_payload(device_dict, seg_name) or {}}
            result["diff_plan"].append(
                {
                    "device": device_name,
                    "branch": "edge.segments",
                    "before": {"segments": before_segments},
                    "after": {"segments": desired_segments},
                }
            )

            output_config[device_id] = {"device_id": device_id, "payload": payload}
            result["configured_devices"].append(device_name)

        if not output_config:
            return result

        LOG.info("[ospfv2] Pushing payload for %d device(s)...", len(output_config))
        self.execute_concurrent_tasks(self._push_device_config_preserving_nulls, output_config)

        result["changed"] = True
        return result

    def configure(
        self,
        config_yaml_file: str,
        vault_ospf_md5_passwords: Optional[Dict[str, Any]] = None,
    ) -> dict:
        return self.apply_ospf(
            config_yaml_file,
            operation="configure",
            vault_ospf_md5_passwords=vault_ospf_md5_passwords,
        )

    def deconfigure(self, config_yaml_file: str) -> dict:
        return self.apply_ospf(config_yaml_file, operation="deconfigure")
