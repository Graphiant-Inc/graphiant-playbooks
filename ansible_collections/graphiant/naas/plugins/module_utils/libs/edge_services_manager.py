"""
Edge Services Manager for Graphiant Playbooks.

Configures edge-only services on ``PUT /v1/devices/{device_id}/config``:

- Device-level ``localWebServerPassword``
- Edge-level DNS mode (``DNSModeStatic``, ``DNSModeCloudflare``, ``DNSModeDynamic``)
- LAN interface ``lldpEnabled``
- LAN segment ``dhcpSubnets`` (key ``{interface}-{ipPrefix}``)

YAML uses the ``edge_services`` list-of-single-key-dicts pattern (same as ``device_system``).
Configure-only; DHCP subnet removal uses ``state: absent`` (``subnet: null`` in the API payload).

LWS passwords are hashed in GET responses. Without ``localWebServerPasswordForce``, password is
pushed only when none is configured; with force, requires password from YAML, vault, or module params
(clear force after rotate). Diff uses ``localWebServerPasswordConfigured`` booleans.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .base_manager import BaseManager
from .device_config_common import (
    as_dict,
    coerce_str,
    fetch_device_by_name,
    load_device_list_yaml_config,
    new_apply_result,
    push_device_config_raw,
)
from .logger import setup_logger
from .exceptions import ConfigurationError

LOG = setup_logger()

_LOG_PREFIX = "[edge-services]"
_YAML_KEY = "edge_services"
_ALLOWED = frozenset(
    {
        "localWebServerPassword",
        "localWebServerPasswordForce",
        "dns",
        "lldp",
        "dhcpSubnets",
    }
)
_DNS_MODES = frozenset({"DNSModeStatic", "DNSModeCloudflare", "DNSModeDynamic"})
_LWS_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


class EdgeServicesManager(BaseManager):
    """Manage edge DHCP, DNS, LLDP, and local web server settings via the device config API."""

    _str = staticmethod(coerce_str)
    _as_dict = staticmethod(as_dict)

    @classmethod
    def _dhcp_subnet_key(cls, interface: Any, ip_prefix: Any) -> str:
        return f"{cls._str(interface)}-{cls._str(ip_prefix)}"

    @classmethod
    def _normalize_mac(cls, mac: Any) -> str:
        """Canonical MAC for compare/PUT (portal GET may return lowercase)."""
        return cls._str(mac).upper()

    @classmethod
    def _normalize_static_leases_from_get(cls, static_leases: Any) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if isinstance(static_leases, list):
            for item in static_leases:
                if not isinstance(item, dict):
                    continue
                ip = cls._str(item.get("ipAddress"))
                mac = cls._normalize_mac(item.get("macAddress"))
                if ip and mac:
                    out[ip] = {"lease": {"ipAddress": ip, "macAddress": mac}}
        elif isinstance(static_leases, dict):
            for ip, body in static_leases.items():
                if not isinstance(body, dict):
                    continue
                lease = cls._as_dict(body.get("lease"))
                ip_addr = cls._str(lease.get("ipAddress")) or cls._str(ip)
                mac = cls._normalize_mac(lease.get("macAddress"))
                if ip_addr and mac:
                    out[cls._str(ip)] = {"lease": {"ipAddress": ip_addr, "macAddress": mac}}
        return out

    @classmethod
    def _normalize_static_leases_in_subnet(cls, subnet: Dict[str, Any]) -> None:
        """Normalize staticLeases MACs in-place on a subnet dict used for snapshots."""
        static = subnet.get("staticLeases")
        if not isinstance(static, dict):
            return
        normalized = cls._normalize_static_leases_from_get(static)
        if normalized:
            subnet["staticLeases"] = normalized
        elif "staticLeases" in subnet:
            del subnet["staticLeases"]

    @classmethod
    def _validate_lws_password(cls, password: str) -> None:
        if not _LWS_PASSWORD_RE.match(password):
            raise ConfigurationError(
                "localWebServerPassword must be at least 8 characters and include "
                "1 uppercase letter, 1 lowercase letter, and 1 digit."
            )

    @classmethod
    def _normalize_dhcp_subnet_from_get(cls, pool: Dict[str, Any]) -> Dict[str, Any]:
        ns = cls._as_dict(pool.get("nameservers"))
        ranges = pool.get("ranges") or []
        ip_range: List[Dict[str, str]] = []
        if isinstance(ranges, list):
            for r in ranges:
                if isinstance(r, dict) and r.get("start") and r.get("end"):
                    ip_range.append({"start": cls._str(r["start"]), "end": cls._str(r["end"])})
        out: Dict[str, Any] = {
            "ipPrefix": cls._str(pool.get("ipPrefix")),
            "interface": cls._str(pool.get("interface")),
            "name": cls._str(pool.get("name")),
            "description": cls._str(pool.get("description")),
            "ipGateway": cls._str(pool.get("gateway") or pool.get("ipGateway")),
            "defaultLeaseTimeSecs": pool.get("defaultLeaseTimeSecs"),
            "maxLeaseTimeSecs": pool.get("maxLeaseTimeSecs"),
            "minLeaseTimeSecs": pool.get("minLeaseTimeSecs"),
        }
        dn = cls._str(pool.get("domainName"))
        if dn:
            out["domainName"] = dn
        if ns:
            out["domainNameServer"] = {
                "primary": cls._str(ns.get("primary")),
                "secondary": cls._str(ns.get("secondary")),
            }
        if ip_range:
            out["ipRangesV2"] = {"ipRange": ip_range}
        static = cls._normalize_static_leases_from_get(pool.get("staticLeases"))
        if static:
            out["staticLeases"] = static
        return {k: v for k, v in out.items() if v not in (None, "", {}, [])}

    @classmethod
    def _normalize_dhcp_subnet_from_yaml(cls, subnet: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(subnet)
        if "ipGateway" not in out and out.get("gateway"):
            out["ipGateway"] = out.pop("gateway")
        if "domainNameServer" not in out and out.get("nameservers"):
            out["domainNameServer"] = out.pop("nameservers")
        if "ipRangesV2" not in out and out.get("ranges"):
            ranges = out.pop("ranges")
            if isinstance(ranges, list):
                out["ipRangesV2"] = {"ipRange": ranges}
        cls._normalize_static_leases_in_subnet(out)
        return {k: v for k, v in out.items() if v is not None}

    @classmethod
    def _dns_snapshot_from_device(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        dns = cls._as_dict(d.get("dns"))
        mode = cls._str(dns.get("mode"))
        snap: Dict[str, Any] = {"mode": mode} if mode else {}
        if mode == "DNSModeStatic":
            v2 = cls._as_dict(dns.get("staticServersV2"))
            static: Dict[str, str] = {}
            for key, label in (
                ("primaryIpv4Server", "primaryIpv4"),
                ("primaryIpv6Server", "primaryIpv6"),
                ("secondaryIpv4Server", "secondaryIpv4"),
                ("secondaryIpv6Server", "secondaryIpv6"),
            ):
                srv = cls._as_dict(v2.get(key))
                addr = cls._str(srv.get("ipv4") or srv.get("ipv6"))
                if addr:
                    static[label] = addr
            if static:
                snap["static"] = static
        return snap

    @classmethod
    def _lldp_snapshot_from_device(cls, d: Dict[str, Any]) -> Dict[str, bool]:
        out: Dict[str, bool] = {}
        for iface in d.get("interfaces") or []:
            if not isinstance(iface, dict):
                continue
            name = cls._str(iface.get("name"))
            if not name:
                continue
            if iface.get("circuit") or iface.get("circuitName"):
                continue
            if "lldpEnabled" in iface:
                out[name] = bool(iface.get("lldpEnabled"))
        return out

    @classmethod
    def _lan_lldp_interface_names_from_device(cls, d: Dict[str, Any]) -> frozenset:
        """Portal hostnames for LAN interfaces (no circuit); LLDP applies to these only."""
        names: set = set()
        for iface in d.get("interfaces") or []:
            if not isinstance(iface, dict):
                continue
            name = cls._str(iface.get("name"))
            if not name:
                continue
            if iface.get("circuit") or iface.get("circuitName"):
                continue
            names.add(name)
        return frozenset(names)

    @classmethod
    def _validate_lldp_entries(cls, device_name: str, lldp_cfg: Dict[str, Any], current_device: Dict[str, Any]) -> None:
        """Require each lldp key to name a LAN interface (no WAN/circuit) on the device."""
        if not lldp_cfg:
            return
        lan_names = cls._lan_lldp_interface_names_from_device(current_device)
        all_names = cls._interface_names_from_device(current_device)
        for if_name in lldp_cfg:
            name = cls._str(if_name)
            if not name:
                continue
            if name in lan_names:
                continue
            known = (
                ", ".join(sorted(lan_names))
                if lan_names
                else "(none — configure LAN interfaces first, e.g. interface_management.yml --tags lan)"
            )
            if name not in all_names:
                raise ConfigurationError(
                    f"Device '{device_name}': lldp references interface {name!r} which does not exist "
                    f"on this device. Known LAN interfaces for LLDP: {known}."
                )
            raise ConfigurationError(
                f"Device '{device_name}': lldp references interface {name!r} which is not a LAN interface "
                f"(WAN/circuit interfaces cannot use LLDP). Known LAN interfaces: {known}."
            )

    @classmethod
    def _dhcp_snapshot_from_device(cls, d: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for seg in d.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            seg_name = cls._str(seg.get("name"))
            for pool in seg.get("dhcpSubnets") or []:
                if not isinstance(pool, dict):
                    continue
                iface = cls._str(pool.get("interface"))
                prefix = cls._str(pool.get("ipPrefix"))
                if not iface or not prefix:
                    continue
                key = cls._dhcp_subnet_key(iface, prefix)
                norm = cls._normalize_dhcp_subnet_from_get(pool)
                norm["segment"] = seg_name
                out[key] = norm
        return out

    @classmethod
    def _edge_services_snapshot(cls, d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "localWebServerPasswordConfigured": bool(cls._str(d.get("localWebServerPassword"))),
            "dns": cls._dns_snapshot_from_device(d),
            "lldp": cls._lldp_snapshot_from_device(d),
            "dhcpSubnets": cls._dhcp_snapshot_from_device(d),
        }

    @classmethod
    def _build_dns_put(cls, dns_cfg: Dict[str, Any]) -> Dict[str, Any]:
        mode = cls._str(dns_cfg.get("mode"))
        if mode not in _DNS_MODES:
            raise ConfigurationError(f"dns.mode must be one of {sorted(_DNS_MODES)}.")
        inner: Dict[str, Any] = {}
        if mode == "DNSModeCloudflare":
            inner["cloudflare"] = {}
        elif mode == "DNSModeDynamic":
            inner["dynamic"] = dict(dns_cfg.get("dynamic") or {})
        elif mode == "DNSModeStatic":
            static_in = cls._as_dict(dns_cfg.get("static"))
            static_body: Dict[str, Any] = {}
            mapping = (
                ("primaryIpv4", "primaryIpv4V2"),
                ("primaryIpv6", "primaryIpv6V2"),
                ("secondaryIpv4", "secondaryIpv4V2"),
                ("secondaryIpv6", "secondaryIpv6V2"),
            )
            for yaml_key, api_key in mapping:
                val = cls._str(static_in.get(yaml_key))
                if val:
                    static_body[api_key] = {"address": val}
            if not static_body:
                raise ConfigurationError("dns.mode DNSModeStatic requires at least one static server address.")
            inner["static"] = static_body
        return {"dns": inner}

    @classmethod
    def _desired_dns_snapshot(cls, dns_cfg: Dict[str, Any]) -> Dict[str, Any]:
        mode = cls._str(dns_cfg.get("mode"))
        snap: Dict[str, Any] = {"mode": mode}
        if mode == "DNSModeStatic":
            static_in = cls._as_dict(dns_cfg.get("static"))
            static = {k: cls._str(v) for k, v in static_in.items() if cls._str(v)}
            if static:
                snap["static"] = static
        return snap

    @classmethod
    def _build_lldp_put(cls, lldp_map: Dict[str, bool]) -> Dict[str, Any]:
        interfaces: Dict[str, Any] = {}
        for if_name, enabled in sorted(lldp_map.items()):
            interfaces[if_name] = {"interface": {"lldpEnabled": bool(enabled)}}
        return {"interfaces": interfaces}

    @classmethod
    def _build_dhcp_put(cls, dhcp_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        segments: Dict[str, Any] = {}
        for entry in dhcp_entries:
            segment = cls._str(entry.get("segment"))
            iface = cls._str(entry.get("interface"))
            prefix = cls._str(entry.get("ipPrefix"))
            if not segment or not iface or not prefix:
                raise ConfigurationError("Each dhcpSubnets entry requires segment, interface, and ipPrefix.")
            key = cls._dhcp_subnet_key(iface, prefix)
            state = cls._str(entry.get("state") or "present").lower()
            seg_block = segments.setdefault(segment, {})
            dhcp_block = seg_block.setdefault("dhcpSubnets", {})
            if state == "absent":
                dhcp_block[key] = {"subnet": None}
                continue
            subnet_raw = cls._as_dict(entry.get("subnet"))
            if not subnet_raw:
                raise ConfigurationError(
                    f"dhcpSubnets entry {key} on segment {segment} requires a subnet dict when state is present."
                )
            subnet = cls._normalize_dhcp_subnet_from_yaml(subnet_raw)
            subnet.setdefault("ipPrefix", prefix)
            subnet.setdefault("interface", iface)
            dhcp_block[key] = {"subnet": subnet}
        return {"segments": segments}

    def _validate_cfg(self, device_name: str, cfg: Any) -> Dict[str, Any]:
        if not isinstance(cfg, dict):
            raise ConfigurationError(f"Device '{device_name}' config must be a dict")
        bad = set(cfg) - _ALLOWED
        if bad:
            raise ConfigurationError(
                f"Device '{device_name}' has unknown keys: {sorted(bad)}. Allowed: {sorted(_ALLOWED)}"
            )
        out = dict(cfg)
        pwd = out.get("localWebServerPassword")
        if pwd is not None:
            self._validate_lws_password(self._str(pwd))
        if out.get("dns") is not None:
            if not isinstance(out["dns"], dict):
                raise ConfigurationError(f"Device '{device_name}' dns must be a dict.")
            self._build_dns_put(out["dns"])
        if out.get("lldp") is not None:
            if not isinstance(out["lldp"], dict):
                raise ConfigurationError(f"Device '{device_name}' lldp must be a dict of interface names to bool.")
        if out.get("dhcpSubnets") is not None:
            if not isinstance(out["dhcpSubnets"], list):
                raise ConfigurationError(f"Device '{device_name}' dhcpSubnets must be a list.")
            for entry in out["dhcpSubnets"]:
                if not isinstance(entry, dict):
                    raise ConfigurationError("Each dhcpSubnets entry must be a dict.")
        return out

    @staticmethod
    def _row_from_params(params: Dict[str, Any]) -> Dict[str, Any]:
        return {key: params[key] for key in _ALLOWED if params.get(key) is not None}

    @staticmethod
    def _merge_edge_services_override(merged: Dict[str, Any], ov: Dict[str, Any]) -> Dict[str, Any]:
        for k, v in ov.items():
            if k == "dhcpSubnets" and isinstance(merged.get("dhcpSubnets"), list) and isinstance(v, list):
                merged["dhcpSubnets"] = v
            elif k == "lldp" and isinstance(merged.get("lldp"), dict) and isinstance(v, dict):
                merged_lldp = dict(merged["lldp"])
                merged_lldp.update(v)
                merged["lldp"] = merged_lldp
            elif k == "dns" and isinstance(merged.get("dns"), dict) and isinstance(v, dict):
                merged_dns = dict(merged["dns"])
                merged_dns.update(v)
                merged["dns"] = merged_dns
            else:
                merged[k] = v
        return merged

    def _load_edge_services(
        self, config_yaml_file: Optional[str], module_params: Optional[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        return load_device_list_yaml_config(
            _YAML_KEY,
            config_yaml_file,
            module_params,
            self.render_config_file,
            missing_input_error="Provide edge_services_config_file and/or device (portal device name).",
            build_row_from_params=self._row_from_params,
            merge_override=self._merge_edge_services_override,
            validate_device_cfg=self._validate_cfg,
        )

    def _assert_edge_device(self, device_name: str, d: Dict[str, Any]) -> None:
        role = self._str(d.get("role")).lower()
        if role == "core":
            raise ConfigurationError(
                f"Device '{device_name}' has role 'core'; edge services apply to Edge/Gateway (CPE) devices only."
            )

    def _compute_after_snapshot(self, cfg: Dict[str, Any], before: Dict[str, Any]) -> Dict[str, Any]:
        after: Dict[str, Any] = {
            "localWebServerPasswordConfigured": before.get("localWebServerPasswordConfigured", False),
            "dns": dict(before.get("dns") or {}),
            "lldp": dict(before.get("lldp") or {}),
            "dhcpSubnets": dict(before.get("dhcpSubnets") or {}),
        }
        if cfg.get("localWebServerPassword") is not None:
            after["localWebServerPasswordConfigured"] = True
        if cfg.get("dns"):
            after["dns"] = self._desired_dns_snapshot(cfg["dns"])
        if cfg.get("lldp"):
            merged_lldp = dict(after["lldp"])
            merged_lldp.update({k: bool(v) for k, v in cfg["lldp"].items()})
            after["lldp"] = merged_lldp
        for entry in cfg.get("dhcpSubnets") or []:
            if not isinstance(entry, dict):
                continue
            key = self._dhcp_subnet_key(entry.get("interface"), entry.get("ipPrefix"))
            state = self._str(entry.get("state") or "present").lower()
            if state == "absent":
                after["dhcpSubnets"].pop(key, None)
                continue
            subnet = self._normalize_dhcp_subnet_from_yaml(self._as_dict(entry.get("subnet")))
            subnet["segment"] = self._str(entry.get("segment"))
            merged = dict(after["dhcpSubnets"].get(key) or {})
            merged.update(subnet)
            after["dhcpSubnets"][key] = merged
        return after

    @classmethod
    def _lan_segment_names_from_device(cls, d: Dict[str, Any]) -> frozenset:
        names: set[str] = set()
        for seg in d.get("segments") or []:
            if not isinstance(seg, dict):
                continue
            nm = cls._str(seg.get("name"))
            if nm:
                names.add(nm)
        return frozenset(names)

    @classmethod
    def _interface_names_from_device(cls, d: Dict[str, Any]) -> frozenset:
        """Collect main and subinterface names from GET device (for DHCP validation)."""
        names: set[str] = set()
        for iface in d.get("interfaces") or []:
            if not isinstance(iface, dict):
                continue
            parent = cls._str(iface.get("name"))
            if parent:
                names.add(parent)
            subs = iface.get("subinterfaces")
            if isinstance(subs, dict):
                for vlan_key, sub in subs.items():
                    if parent and vlan_key is not None:
                        names.add(f"{parent}.{vlan_key}")
                    if isinstance(sub, dict):
                        sub_nm = cls._str(sub.get("name"))
                        if sub_nm:
                            names.add(sub_nm)
            elif isinstance(subs, list):
                for sub in subs:
                    if not isinstance(sub, dict):
                        continue
                    sub_nm = cls._str(sub.get("name"))
                    if sub_nm:
                        names.add(sub_nm)
                    elif parent and sub.get("vlan") is not None:
                        names.add(f"{parent}.{sub['vlan']}")
        for snap in cls._dhcp_snapshot_from_device(d).values():
            iface = cls._str(snap.get("interface"))
            if iface:
                names.add(iface)
        return frozenset(names)

    def _validate_dhcp_entries(
        self, device_name: str, dhcp_entries: List[Dict[str, Any]], current_device: Dict[str, Any]
    ) -> None:
        """Require segment and interface on each dhcpSubnets entry to exist on the device."""
        valid_segments = self._lan_segment_names_from_device(current_device)
        valid_interfaces = self._interface_names_from_device(current_device)
        for entry in dhcp_entries:
            if not isinstance(entry, dict):
                continue
            state = self._str(entry.get("state") or "present").lower()
            if state == "absent":
                continue
            seg = self._str(entry.get("segment"))
            if seg and seg not in valid_segments:
                known = (
                    ", ".join(sorted(valid_segments))
                    if valid_segments
                    else "(none — device has no LAN segments in GET response)"
                )
                raise ConfigurationError(
                    f"Device '{device_name}': dhcpSubnets references LAN segment {seg!r} which does not exist "
                    f"on this device. Known segment names: {known}."
                )
            iface = self._str(entry.get("interface"))
            if iface and iface not in valid_interfaces:
                known = (
                    ", ".join(sorted(valid_interfaces))
                    if valid_interfaces
                    else "(none — configure LAN interfaces first, e.g. interface_management.yml --tags lan)"
                )
                raise ConfigurationError(
                    f"Device '{device_name}': dhcpSubnets references interface {iface!r} which does not exist "
                    f"on this device. Known interfaces: {known}."
                )

    def _build_edge_payload(
        self, device_name: str, cfg: Dict[str, Any], current_device: Dict[str, Any]
    ) -> Dict[str, Any]:
        edge: Dict[str, Any] = {}

        if cfg.get("localWebServerPassword") is not None:
            force = bool(cfg.get("localWebServerPasswordForce"))
            if force or not self._str(current_device.get("localWebServerPassword")):
                edge["localWebServerPassword"] = cfg["localWebServerPassword"]

        if cfg.get("dns"):
            desired_dns = self._desired_dns_snapshot(cfg["dns"])
            current_dns = self._dns_snapshot_from_device(current_device)
            if desired_dns != current_dns:
                # API expects nested edge.dns.dns.{static|dynamic|cloudflare} (see PUT device config).
                edge["dns"] = self._build_dns_put(cfg["dns"])

        if cfg.get("lldp"):
            desired_lldp = {k: bool(v) for k, v in cfg["lldp"].items()}
            current_lldp = self._lldp_snapshot_from_device(current_device)
            delta = {k: v for k, v in desired_lldp.items() if current_lldp.get(k) != v}
            if delta:
                edge.update(self._build_lldp_put(delta))

        if cfg.get("dhcpSubnets"):
            self._validate_dhcp_entries(device_name, cfg["dhcpSubnets"], current_device)
            dhcp_delta: List[Dict[str, Any]] = []
            before_dhcp = self._dhcp_snapshot_from_device(current_device)
            for entry in cfg["dhcpSubnets"]:
                if not isinstance(entry, dict):
                    continue
                key = self._dhcp_subnet_key(entry.get("interface"), entry.get("ipPrefix"))
                state = self._str(entry.get("state") or "present").lower()
                if state == "absent":
                    if key in before_dhcp:
                        dhcp_delta.append(entry)
                    continue
                subnet_yaml = self._normalize_dhcp_subnet_from_yaml(self._as_dict(entry.get("subnet")))
                merged = dict(before_dhcp.get(key) or {})
                merged.update(subnet_yaml)
                if before_dhcp.get(key) != merged:
                    put_entry = dict(entry)
                    put_entry["subnet"] = merged
                    dhcp_delta.append(put_entry)
            if dhcp_delta:
                edge.update(self._build_dhcp_put(dhcp_delta))

        return edge

    def _iter_devices(
        self, by_name: Dict[str, Dict[str, Any]]
    ) -> Iterator[Tuple[int, str, Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
        enterprise = self.gsdk.enterprise_info["company_name"]
        for device_name, cfg in by_name.items():
            device_id, d = fetch_device_by_name(self.gsdk, device_name, enterprise)
            self._assert_edge_device(device_name, d)

            before = self._edge_services_snapshot(d)
            if cfg.get("lldp"):
                self._validate_lldp_entries(device_name, cfg["lldp"], d)
            edge_payload = self._build_edge_payload(device_name, cfg, d)
            after = self._compute_after_snapshot(cfg, before)
            yield device_id, device_name, cfg, before, after, edge_payload

    def _inject_vault_lws_passwords(
        self, by_name: Dict[str, Dict[str, Any]], vault_lws: Optional[Dict[str, Any]]
    ) -> None:
        """Inject localWebServerPassword from vault dict keyed by portal device name."""
        if not vault_lws:
            return
        for device_name, cfg in by_name.items():
            if cfg.get("localWebServerPassword") is not None:
                continue
            pwd = self._str(vault_lws.get(device_name))
            if pwd:
                cfg["localWebServerPassword"] = pwd
                LOG.debug("%s Injected localWebServerPassword for %s from vault", _LOG_PREFIX, device_name)

    @classmethod
    def _validate_lws_password_sources(cls, by_name: Dict[str, Dict[str, Any]]) -> None:
        """Fail when force is set but no password is available after vault injection."""
        for device_name, cfg in by_name.items():
            if not cfg.get("localWebServerPasswordForce"):
                continue
            if not cls._str(cfg.get("localWebServerPassword")):
                raise ConfigurationError(
                    f"Device '{device_name}': localWebServerPasswordForce is true but "
                    "localWebServerPassword is missing. Set localWebServerPassword in YAML, "
                    "include a matching key in vault_devices_lws_password, or pass the password "
                    "via module parameters."
                )

    def apply_edge_services(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        vault_devices_lws_password: Optional[Dict[str, Any]] = None,
    ) -> dict:
        by_name = self._load_edge_services(config_yaml_file, module_params)
        self._inject_vault_lws_passwords(by_name, vault_devices_lws_password)
        self._validate_lws_password_sources(by_name)
        if not by_name:
            LOG.info("%s No '%s' entries to process", _LOG_PREFIX, _YAML_KEY)
            return new_apply_result(no_input=True)

        result = new_apply_result()
        to_push: Dict[int, Dict[str, Any]] = {}
        configured: List[str] = []
        diff_plan: List[Dict[str, Any]] = []

        for device_id, device_name, _cfg, before, after, edge_payload in self._iter_devices(by_name):
            if not edge_payload:
                LOG.info("%s No changes needed for %s (ID: %s), skipping", _LOG_PREFIX, device_name, device_id)
                result["skipped_devices"].append(device_name)
                continue

            payload = {"edge": edge_payload}
            to_push[device_id] = {"device_id": device_id, "payload": payload}
            configured.append(device_name)
            diff_plan.append({"device": device_name, "branch": "edge", "before": before, "after": after})

        if not to_push:
            return result

        push_device_config_raw(
            self.execute_concurrent_tasks,
            self.gsdk.put_device_config_raw,
            to_push,
            log_prefix=_LOG_PREFIX,
        )
        result["changed"] = True
        result["configured_devices"] = configured
        result["diff_plan"] = diff_plan
        return result

    def configure(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
        vault_devices_lws_password: Optional[Dict[str, Any]] = None,
    ) -> dict:
        return self.apply_edge_services(
            config_yaml_file=config_yaml_file,
            module_params=module_params,
            vault_devices_lws_password=vault_devices_lws_password,
        )

    def deconfigure(self, config_yaml_file: str) -> dict:
        raise ConfigurationError(
            "Deconfigure is not supported for edge services. "
            "Use configure with desired values, or dhcpSubnets state: absent to remove a subnet."
        )
