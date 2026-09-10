"""
Gateway Services Manager for Graphiant Playbooks.

Manages Graphiant Gateway Services via the portal API:
  POST   /v1/gateways                 — create
  PUT    /v1/gateways                 — update (overwrite); only supported for connectivity services
  DELETE /v1/gateways                 — delete
  GET    /v1/gateways/summary         — list all
  GET    /v1/gateways/{id}/details    — get by ID

Two service types are configured under the top-level ``gatewayServices`` key:
  - cloudGateway : cloud peering [aws, azure, gcp, oci]
  - connectivity : site-to-site IPSec VPN gateway (ipsecGatewayPeers)

Region names, LAN segment names, and speeds are resolved before the request is sent:
  region -> regionId, lanSegment -> vrfId, speed -> S-prefixed enum (e.g. 1Gbps -> S1Gbps).

Config file format (YAML, Jinja2 templating supported):

  gatewayServices:
    cloudGateway:
      - region: us-west-1                 # supply exactly ONE provider block per entry
        speed: 1Gbps
        description: testing              # optional
        lanSegment: lan-1-test
        aws:
          accountId: "123456789012"
      - region: us-west-1
        speed: 1Gbps
        lanSegment: lan-1-test
        azure:
          serviceKey: "abcde-...-12345"
          msPeeringVlanId: "1"
          routingPolicy: "inbound"        # optional
      # gcp: { pairingKey, description, routingPolicy }
      # oci: { fastConnectOcid, description, routingPolicy }

    connectivity:
      - region: us-west-1
        speed: 1Gbps
        lanSegment: lan-1-test
        ipsecGatewayPeers:                # single object (not a list)
          name: test
          routing:                        # use either 'static' or 'bgp'
            static:
              destinationPrefix:
                - 0.0.0.0/0
          remotePeers:
            - destinationAddress: "0.0.0.0"
              ikeInitiator: false
              vpnProfile: "Default VPN Profile"
              tunnel1: { insideIpv4Cidr: null, insideIpv6Cidr: null, psk: null }
              tunnel2: { insideIpv4Cidr: null, insideIpv6Cidr: null, psk: null }
          # bgp routing alternative:
          #   bgp: { peerAsn: 65001, md5Password: null, addressFamilies: { ipv4: { addressFamily: ipv4 } } }

Connectivity tunnel ``insideIpv4Cidr``/``insideIpv6Cidr`` and ``psk`` are optional. Left null, the
inside CIDRs are auto-allocated by the portal (same as Data Exchange) and the psk is filled from
``vault_gateway_ipsec_psks`` (keyed gateway name -> peer-N -> tunnel1/2), or API auto-filled when
no vault entry exists; a non-null value in the config always wins. BGP ``routing.bgp.md5Password``
is likewise filled from ``vault_gateway_bgp_md5_passwords`` (by gateway name) when left null. See
``sample_gateway_services_config.yaml`` for full examples of all three psk modes and BGP routing.

Create is idempotent (create-or-update): services that do not exist are created; an existing
connectivity service is updated in place (PUT) only when the desired config differs from the
current config, otherwise it is skipped. Update is NOT supported for cloud gateway services —
an existing cloud gateway is skipped rather than updated (a change requires delete + create).

Delete is idempotent: missing gateways are silently skipped. Each gateway defined in the config
is resolved to its gateway id and removed via DELETE /v1/gateways with body {id}.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional, Set, Tuple

from .base_manager import BaseManager
from .exceptions import ConfigurationError
from .logger import setup_logger

LOG = setup_logger()

_YAML_KEY = "gatewayServices"
_LOG_PREFIX = "[gatewayServices]"

# Default gateway speed when a config entry omits 'speed' (resolved to the S-prefixed enum S1Gbps).
_DEFAULT_SPEED = "1Gbps"

# Cloud provider blocks and the config field that uniquely identifies each one.
_CLOUD_PROVIDERS = ("aws", "azure", "gcp", "oci")
_PROVIDER_ID_FIELD = {
    "aws": "accountId",
    "azure": "serviceKey",
    "gcp": "pairingKey",
    "oci": "fastConnectOcid",
}


class GatewayServicesManager(BaseManager):
    """
    Manager for Gateway Services CRUD via the Graphiant portal API.

    Handles both cloud gateway peering (``aws``, ``azure``, ``gcp``, ``oci``) and connectivity
    (site-to-site IPSec VPN, ``ipsecGatewayPeers``) entries defined under the ``gatewayServices``
    YAML key, sent to the same ``/v1/gateway`` portal API endpoint.
    """

    @staticmethod
    def _resolve_speed(speed: Optional[str]) -> str:
        """
        Map a config speed (e.g. ``1Gbps``) to the API's S-prefixed enum (``S1Gbps``).
        Defaults to ``1Gbps`` (``S1Gbps``) when not provided.
        """
        speed = str(speed) if speed else _DEFAULT_SPEED
        return speed if speed.startswith("S") else f"S{speed}"

    @staticmethod
    def _provider_block(service: Dict[str, Any]) -> Tuple[Optional[str], Optional[dict]]:
        """Return (provider_name, provider_block) for the single cloud provider in a config entry."""
        for provider in _CLOUD_PROVIDERS:
            block = service.get(provider)
            if block:
                return provider, block
        return None, None

    @staticmethod
    def _ipsec_block(details: Dict[str, Any]) -> Optional[dict]:
        """Return the ipsec block from a details dict (config uses ipsecGatewayPeers; API GET may use ipsecGateway)."""
        return details.get("ipsecGatewayPeers") or details.get("ipsecGateway")

    def _identity_of(self, details: Dict[str, Any]) -> Optional[Tuple]:
        """
        Build a hashable identity for a gateway from its ``details`` dict, so a desired config
        entry can be matched to an existing gateway without relying on the (auto-generated) name.

        Cloud:        (provider, regionId, vrfId, <provider id field value>)
        Connectivity: ("connectivity", regionId, vrfId, ipsecGatewayPeers.name)
        """
        region_id = details.get("regionId")
        vrf_id = details.get("vrfId")
        for provider in _CLOUD_PROVIDERS:
            block = details.get(provider)
            if block:
                return (provider, region_id, vrf_id, str(block.get(_PROVIDER_ID_FIELD[provider])))
        ipsec = self._ipsec_block(details)
        if ipsec:
            return ("connectivity", region_id, vrf_id, ipsec.get("name"))
        return None

    @staticmethod
    def _entry_label(identity: Optional[Tuple]) -> str:
        """Human-readable label for logs/results (no user-facing name exists on the payload)."""
        if not identity:
            return "gateway"
        return f"{identity[0]}:{identity[3]}"

    @staticmethod
    def _strip_volatile(ipsec: Optional[dict]) -> Optional[dict]:
        """
        Return a deep copy of an ipsec block normalized for idempotency comparison, removing fields
        that make an unchanged gateway look drifted on re-run:

        - ``psk`` and inside CIDRs (``insideIpv4Cidr``/``insideIpv6Cidr``) and the BGP
          ``routing.bgp.md5Password`` — when left null in the config these are auto-generated /
          auto-allocated by the portal (a fresh value per apply), so comparing them would make every
          re-run look drifted. (The portal *does* return them in cleartext on GET; because they are
          excluded here, a rotated secret is applied via the ``force_update`` option on
          :meth:`create`, not by the normal comparison.)
        - ``remotePeers[].remoteIkePeerIdentity`` — the portal auto-generates a value (e.g. the peer
          name) when the config omits it, so the GET returns something we never sent.
        - ``routing.bgp.addressFamilies`` — normalized to just the real inbound/outbound policy
          references (see :meth:`_norm_address_families`); the portal expands this into a shape the
          compact config never matches (extra families, ``family`` wrappers, empty ``{}`` policies).

        ``remotePeers`` is also sorted by a canonical key so the comparison is order-insensitive (the
        portal may return peers in a different order than the config).
        """
        if not isinstance(ipsec, dict):
            return ipsec
        clone = copy.deepcopy(ipsec)
        peers = clone.get("remotePeers")
        if isinstance(peers, list):
            for peer in peers:
                if not isinstance(peer, dict):
                    continue
                peer.pop("remoteIkePeerIdentity", None)
                for tunnel_key in ("tunnel1", "tunnel2"):
                    tunnel = peer.get(tunnel_key)
                    if isinstance(tunnel, dict):
                        tunnel.pop("psk", None)
                        tunnel.pop("insideIpv4Cidr", None)
                        tunnel.pop("insideIpv6Cidr", None)
            # Compare remotePeers as an unordered set: the portal may return peers in a different
            # order than the config, so sort by a canonical key to avoid false drift.
            clone["remotePeers"] = sorted(peers, key=lambda p: json.dumps(p, sort_keys=True, default=str))
        routing = clone.get("routing")
        if isinstance(routing, dict) and isinstance(routing.get("bgp"), dict):
            bgp = routing["bgp"]
            bgp.pop("md5Password", None)
            bgp["addressFamilies"] = GatewayServicesManager._norm_address_families(bgp.get("addressFamilies"))
        return clone

    @staticmethod
    def _norm_address_families(address_families: Any) -> Dict[str, Any]:
        """
        Reduce ``routing.bgp.addressFamilies`` to only the real inbound/outbound policy references
        each family carries, so the config's compact shape compares equal to the portal's expanded
        one. The portal (GET) adds families we never configured (e.g. ``ipv6``), wraps each family's
        policies under a ``family`` object, echoes unset policies as empty ``{}``, and includes the
        redundant inner ``addressFamily`` key — all of which would otherwise look like drift. A
        family with no policy reference is dropped entirely.
        """
        if not isinstance(address_families, dict):
            return {}
        normalized: Dict[str, Any] = {}
        for af_name, af_cfg in address_families.items():
            if not isinstance(af_cfg, dict):
                continue
            # Config puts policies at the top level; the portal nests them under 'family'.
            family = af_cfg.get("family")
            src = family if isinstance(family, dict) else af_cfg
            entry = {key: src[key] for key in ("inboundPolicy", "outboundPolicy") if src.get(key)}
            if entry:
                normalized[af_name] = entry
        return normalized

    _REDACTED = "********"

    @classmethod
    def _redact_secrets(cls, details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a deep copy of a ``details`` payload with every connectivity secret masked, for safe
        ``--diff``/log output: each remote peer's ``tunnel1``/``tunnel2`` ``psk`` and the BGP
        ``routing.bgp.md5Password``. Non-secret fields (regions, CIDRs, provider blocks) are kept so
        the diff still shows what changed. The original ``details`` sent to the API is untouched.
        """
        if not isinstance(details, dict):
            return details
        clone = copy.deepcopy(details)
        ipsec = clone.get("ipsecGatewayPeers")
        if isinstance(ipsec, dict):
            for peer in ipsec.get("remotePeers") or []:
                if not isinstance(peer, dict):
                    continue
                for tunnel_key in ("tunnel1", "tunnel2"):
                    tunnel = peer.get(tunnel_key)
                    if isinstance(tunnel, dict) and tunnel.get("psk") is not None:
                        tunnel["psk"] = cls._REDACTED
            routing = ipsec.get("routing")
            if isinstance(routing, dict) and isinstance(routing.get("bgp"), dict):
                if routing["bgp"].get("md5Password") is not None:
                    routing["bgp"]["md5Password"] = cls._REDACTED
        return clone

    def _norm(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize the manager-owned fields of a details dict for idempotency comparison."""
        return {
            "regionId": details.get("regionId"),
            "vrfId": details.get("vrfId"),
            "speed": details.get("speed"),
            "description": details.get("description") or "",
            "ipsecGatewayPeers": self._strip_volatile(self._ipsec_block(details)),
        }

    def _fill_missing_tunnel_values(self, ipsec_peers: Dict[str, Any], region_id: int, vrf_id: int) -> None:
        """
        Fill still-null tunnel values from the portal, mirroring the Data Exchange flow:
        ``insideIpv4Cidr``/``insideIpv6Cidr`` from ``get_ipsec_inside_subnet`` and ``psk`` from
        ``get_preshared_key`` — each fetched per tunnel that needs it. A CIDR is only filled when
        the key is present and set to null; a psk is filled whenever it is still null.

        Called right before create/update (not on skip) so re-runs of an existing, matching
        gateway don't allocate fresh subnets/keys.
        """
        for peer in ipsec_peers.get("remotePeers") or []:
            if not isinstance(peer, dict):
                continue
            for tunnel_key in ("tunnel1", "tunnel2"):
                tunnel = peer.get(tunnel_key)
                if not isinstance(tunnel, dict):
                    continue
                if "insideIpv4Cidr" in tunnel and tunnel["insideIpv4Cidr"] is None:
                    subnet = self.gsdk.get_ipsec_inside_subnet(region_id, vrf_id, "ipv4")
                    if subnet:
                        tunnel["insideIpv4Cidr"] = subnet
                if "insideIpv6Cidr" in tunnel and tunnel["insideIpv6Cidr"] is None:
                    subnet = self.gsdk.get_ipsec_inside_subnet(region_id, vrf_id, "ipv6")
                    if subnet:
                        tunnel["insideIpv6Cidr"] = subnet
                if tunnel.get("psk") is None:
                    psk = self.gsdk.get_preshared_key()
                    if psk:
                        tunnel["psk"] = psk

    def _inject_vault_psks(
        self, ipsec_peers: Dict[str, Any], gateway_name: Optional[str], vault_psks: Dict[str, Any]
    ) -> None:
        """
        Fill connectivity tunnel PSKs in place, mirroring the Data Exchange PSK vault:
        key = gateway name -> peer name -> tunnel. ``remotePeers`` have no name field, so the peer
        key is ``peer-<N>`` (1-based remotePeers index). Precedence: a non-null ``psk`` in YAML
        wins; a null/absent ``psk`` is filled from vault; if still null it is left as-is (optional
        — the API auto-fills a missing PSK).

        The vault structure::

            vault_gateway_ipsec_psks:
              <gateway name>:
                peer-1:
                  tunnel1: "<psk>"
                  tunnel2: "<psk>"
                peer-2:
                  tunnel1: "<psk>"
                  tunnel2: "<psk>"
        """
        if not gateway_name:
            return
        gw_vault = (vault_psks or {}).get(gateway_name) or {}
        if not isinstance(gw_vault, dict):
            return
        for idx, peer in enumerate(ipsec_peers.get("remotePeers") or []):
            if not isinstance(peer, dict):
                continue
            peer_vault = gw_vault.get(f"peer-{idx + 1}") or {}
            if not isinstance(peer_vault, dict):
                continue
            for tunnel_key in ("tunnel1", "tunnel2"):
                tunnel = peer.get(tunnel_key)
                if not isinstance(tunnel, dict) or tunnel.get("psk") is not None:
                    continue
                psk_val = peer_vault.get(tunnel_key)
                if psk_val:
                    tunnel["psk"] = str(psk_val).strip()
                    LOG.debug(
                        "%s Injected psk for gateway '%s' peer-%s %s from vault",
                        _LOG_PREFIX,
                        gateway_name,
                        idx + 1,
                        tunnel_key,
                    )

    def _inject_vault_md5(
        self, ipsec_peers: Dict[str, Any], gateway_name: Optional[str], vault_md5: Dict[str, Any]
    ) -> None:
        """
        Fill the BGP ``routing.bgp.md5Password`` in place (connectivity, BGP routing only).
        Precedence: a non-null value in YAML wins; a null/absent value is filled from
        ``vault_md5[gateway_name]`` as ``{"md5_password": <value>}``; if neither is set it is
        left as ``None`` (BGP without MD5 auth) — unlike the PSK, MD5 is optional.
        """
        routing = ipsec_peers.get("routing")
        if not isinstance(routing, dict) or not isinstance(routing.get("bgp"), dict):
            return
        bgp = routing["bgp"]
        if bgp.get("md5Password") is None:
            vault_pw = (vault_md5 or {}).get(gateway_name) if gateway_name else None
            bgp["md5Password"] = {"md5_password": str(vault_pw).strip()} if vault_pw else None
            if vault_pw:
                LOG.debug("%s Injected md5Password for gateway '%s' from vault", _LOG_PREFIX, gateway_name)

    def _build_details(
        self, service: Dict[str, Any], service_type: str, lan_segments: Dict[str, int]
    ) -> Dict[str, Any]:
        """
        Build the ``details`` payload (ManaV2GatewayDetails) from a config entry: resolve region
        name -> regionId, lanSegment name -> vrfId, speed -> S-prefixed enum, and attach the
        provider block (cloud) or ipsecGatewayPeers block (connectivity).
        """
        region = service.get("region")
        region_id = self.gsdk.get_region_id_by_name(region)
        if region_id is None:
            raise ConfigurationError(f"Gateway Service: region '{region}' does not exist in this enterprise.")
        lan_segment = service.get("lanSegment")
        vrf_id = lan_segments.get(lan_segment) if lan_segment else None
        if vrf_id is None:
            raise ConfigurationError(f"Gateway Service: lanSegment '{lan_segment}' does not exist in this enterprise.")

        details: Dict[str, Any] = {
            "regionId": region_id,
            "speed": self._resolve_speed(service.get("speed")),
            "vrfId": vrf_id,
        }
        description = service.get("description")
        if description is not None:
            details["description"] = description

        if service_type == "cloudGateway":
            provider, block = self._provider_block(service)
            if not provider:
                raise ConfigurationError(
                    f"Gateway Service: cloudGateway entry in region '{region}' must define one of "
                    f"{list(_CLOUD_PROVIDERS)}."
                )
            details[provider] = block
        else:  # connectivity
            peers = service.get("ipsecGatewayPeers")
            if not peers:
                raise ConfigurationError(
                    f"Gateway Service: connectivity entry in region '{region}' must define 'ipsecGatewayPeers'."
                )
            details["ipsecGatewayPeers"] = peers
        return details

    # Gateway summary statuses that mean the gateway is already being removed. Cloud gateway DELETE is
    # asynchronous — the gateway lingers in the summary as 'requested_removal' — so we treat these as
    # absent to keep re-runs of delete/create idempotent.
    _DELETING_STATUSES = frozenset({"requested_removal"})

    @classmethod
    def _is_deleting_status(cls, status: Any) -> bool:
        """True when a summary ``status`` indicates the gateway is already being removed."""
        return str(status or "").strip().lower() in cls._DELETING_STATUSES

    def _existing_gateways(self) -> List[Tuple[int, Dict[str, Any]]]:
        """
        Return [(gateway_id, details_dict), ...] for every *live* gateway, fetching per-gateway
        details once (the summary lacks the provider/vrf identity needed for matching). Gateways
        whose summary ``status`` marks them as already deleted / decommissioning are excluded so a
        re-run treats them as gone (cloud gateway DELETE is asynchronous — see
        :attr:`_DELETING_STATUS_MARKERS`).
        """
        summary = self.gsdk.get_gateway_summary()
        rows = getattr(summary, "summaries", None)
        if rows is None and hasattr(summary, "to_dict"):
            rows = summary.to_dict().get("summaries")
        gateways: List[Tuple[int, Dict[str, Any]]] = []
        for row in rows or []:
            gateway_id = row.id if hasattr(row, "id") else row.get("id")
            if gateway_id is None:
                continue
            status = row.status if hasattr(row, "status") else (row.get("status") if isinstance(row, dict) else None)
            if self._is_deleting_status(status):
                LOG.info(
                    "%s Gateway id %s is being removed (status %r); treating as absent",
                    _LOG_PREFIX,
                    gateway_id,
                    status,
                )
                continue
            detail_resp = self.gsdk.get_gateway_details(gateway_id)
            if hasattr(detail_resp, "to_dict"):
                details = detail_resp.to_dict().get("details") or {}
            elif isinstance(detail_resp, dict):
                details = detail_resp.get("details") or {}
            else:
                details = {}
            gateways.append((gateway_id, details))
        return gateways

    def _find_existing(
        self, identity: Optional[Tuple], existing: List[Tuple[int, Dict[str, Any]]]
    ) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
        """Find an existing gateway whose identity matches ``identity``. Returns (id, details) or (None, None)."""
        if identity is None:
            return None, None
        for gateway_id, details in existing:
            if self._identity_of(details) == identity:
                return gateway_id, details
        return None, None

    def _validate_lan_segment(self, lan_segment: Optional[str]) -> None:
        """
        Validate that ``lan_segment`` (a single LAN segment name) exists in the enterprise.
        Raises:
            ConfigurationError: when the name is not in ``valid_lan_segments``.
        """
        if not lan_segment:
            return
        # Fetch all global LAN segments once and return a name → id mapping.
        valid_lan_segments = self.gsdk.get_lan_segments_dict()
        if lan_segment not in valid_lan_segments:
            raise ConfigurationError(
                f"Gateway Service: lanSegment '{lan_segment}' does not exist in this enterprise. "
                f"Available LAN segments: {sorted(valid_lan_segments.keys())}"
            )
        LOG.info("%s lanSegment '%s' validated", _LOG_PREFIX, lan_segment)

    def _validate_region_name(self, region_name: Optional[str]) -> None:
        """
        Validate that ``region_name`` (a single region name) exists in the enterprise.
        Raises:
            ConfigurationError: when the region name cannot be resolved to a region id.
        """
        if not region_name:
            return
        # get_regions() returns a list of ManaV2Region objects; compare against their names.
        valid_region_names = [r.name for r in (self.gsdk.get_regions() or [])]
        if region_name not in valid_region_names:
            raise ConfigurationError(
                f"Gateway Service: region '{region_name}' does not exist in this enterprise. "
                f"Available regions: {sorted(valid_region_names)}"
            )
        LOG.info("%s region '%s' validated", _LOG_PREFIX, region_name)

    @staticmethod
    def _connectivity_vpn_profile_names(service: Dict[str, Any]) -> Set[str]:
        """Collect the ``vpnProfile`` names explicitly set across a connectivity entry's remotePeers."""
        names: Set[str] = set()
        peers = (service.get("ipsecGatewayPeers") or {}).get("remotePeers") or []
        for peer in peers:
            if isinstance(peer, dict) and peer.get("vpnProfile"):
                names.add(peer["vpnProfile"])
        return names

    def _validate_vpn_profiles(self, pending: List[Tuple[str, Dict[str, Any]]]) -> None:
        """
        Validate that every explicitly-set connectivity ``vpnProfile`` exists in the enterprise,
        failing fast before any gateway is pushed. A remote peer that omits ``vpnProfile`` is not
        checked (the API defaults it to ``Default VPN Profile``).
        Raises:
            ConfigurationError: when a referenced VPN profile is not found on the portal.
        """
        wanted: Set[str] = set()
        for service_type, service in pending:
            if service_type == "connectivity":
                wanted |= self._connectivity_vpn_profile_names(service)
        if not wanted:
            return
        portal_profiles = self.gsdk.get_global_ipsec_profiles() or {}
        missing = sorted(name for name in wanted if name not in portal_profiles)
        if missing:
            raise ConfigurationError(
                f"Gateway Service: vpnProfile(s) {missing} do not exist in this enterprise. "
                f"Available VPN profiles: {sorted(portal_profiles.keys())}"
            )
        LOG.info("%s Validated %s vpnProfile(s)", _LOG_PREFIX, len(wanted))

    def _iter_services(self, config_yaml_file: str):
        """
        Render the config file and yield (service_type, service_entry) for each cloudGateway and
        connectivity entry. Returns an empty iterator when the gatewayServices key is absent.
        """
        config_data = self.render_config_file(config_yaml_file)
        if not config_data or _YAML_KEY not in config_data:
            LOG.info("%s No %s key found in YAML file", _LOG_PREFIX, _YAML_KEY)
            return

        services = config_data.get(_YAML_KEY) or {}
        if not isinstance(services, dict):
            raise ConfigurationError(f"{_YAML_KEY} must be a dict.")

        for service_type in ("cloudGateway", "connectivity"):
            entries = services.get(service_type) or []
            if not isinstance(entries, list):
                raise ConfigurationError(f"{_YAML_KEY}.{service_type} must be a list.")
            for service in entries:
                if isinstance(service, dict):
                    yield service_type, service

    def configure(
        self,
        config_yaml_file: str,
        vault_gateway_ipsec_psks: Optional[Dict[str, Any]] = None,
        vault_gateway_bgp_md5_passwords: Optional[Dict[str, Any]] = None,
        force_update: bool = False,
    ) -> Dict[str, Any]:
        """BaseManager interface alias for :meth:`create`."""
        return self.create(
            config_yaml_file, vault_gateway_ipsec_psks, vault_gateway_bgp_md5_passwords, force_update=force_update
        )

    def deconfigure(self, config_yaml_file: str) -> Dict[str, Any]:
        """BaseManager interface alias for :meth:`delete`."""
        return self.delete(config_yaml_file)

    def create(
        self,
        config_yaml_file: str,
        vault_gateway_ipsec_psks: Optional[Dict[str, Any]] = None,
        vault_gateway_bgp_md5_passwords: Optional[Dict[str, Any]] = None,
        force_update: bool = False,
    ) -> Dict[str, Any]:
        """
        Create (or update connectivity) gateway services from the config file, idempotently.

        Cloud gateways cannot be updated: an existing match is skipped. Connectivity services are
        updated in place (PUT) when the desired details differ from the current details.

        Connectivity tunnel PSKs may be provided inline or, when null, filled from
        ``vault_gateway_ipsec_psks`` (optional — a still-null PSK is left for API auto-fill; see
        :meth:`_inject_vault_psks`). BGP ``routing.bgp.md5Password`` may likewise be filled from
        ``vault_gateway_bgp_md5_passwords`` (optional; see :meth:`_inject_vault_md5`).

        ``force_update``: PSK / inside CIDRs / BGP ``md5Password`` are excluded from the idempotency
        comparison (they are auto-generated/auto-allocated per apply when left null), so a rotated
        secret is not detected by the normal comparison. Set ``force_update=True`` to re-push every
        matching *connectivity* gateway (PUT) so a changed PSK/MD5 takes effect. Cloud gateways are
        never updated regardless of this flag (change one via delete + create).
        """
        vault_psks = vault_gateway_ipsec_psks if isinstance(vault_gateway_ipsec_psks, dict) else {}
        vault_md5 = vault_gateway_bgp_md5_passwords if isinstance(vault_gateway_bgp_md5_passwords, dict) else {}
        result: Dict[str, Any] = {
            "changed": False,
            "created": [],
            "updated": [],
            "skipped": [],
            "diff_plan": [],
        }

        pending = list(self._iter_services(config_yaml_file))
        if not pending:
            return result

        self._validate_vpn_profiles(pending)
        lan_segments = self.gsdk.get_lan_segments_dict()
        existing = self._existing_gateways()

        for service_type, service in pending:
            self._validate_region_name(service.get("region"))
            self._validate_lan_segment(service.get("lanSegment"))

            details = self._build_details(service, service_type, lan_segments)
            if service_type == "connectivity":
                ipsec_peers = details["ipsecGatewayPeers"]
                self._inject_vault_psks(ipsec_peers, ipsec_peers.get("name"), vault_psks)
                self._inject_vault_md5(ipsec_peers, ipsec_peers.get("name"), vault_md5)
            identity = self._identity_of(details)
            label = self._entry_label(identity)
            gateway_id, current = self._find_existing(identity, existing)

            if gateway_id is None:
                if service_type == "connectivity":
                    self._fill_missing_tunnel_values(
                        details["ipsecGatewayPeers"], details["regionId"], details["vrfId"]
                    )
                LOG.info("%s Creating %s gateway '%s'", _LOG_PREFIX, service_type, label)
                result["diff_plan"].append(
                    {
                        "device": label,
                        "branch": f"{service_type} (create)",
                        "before": {},
                        "after": self._redact_secrets(details),
                    }
                )
                self.gsdk.create_gateway_services(details)
                result["created"].append(label)
                result["changed"] = True
            elif service_type == "cloudGateway":
                LOG.info(
                    "%s Cloud gateway '%s' already exists (id %s); update not supported, skipping",
                    _LOG_PREFIX,
                    label,
                    gateway_id,
                )
                result["skipped"].append(label)
            elif not force_update and self._norm(details) == self._norm(current or {}):
                LOG.info("%s Connectivity gateway '%s' already matches desired state, skipping", _LOG_PREFIX, label)
                result["skipped"].append(label)
            else:
                self._fill_missing_tunnel_values(details["ipsecGatewayPeers"], details["regionId"], details["vrfId"])
                forced = force_update and self._norm(details) == self._norm(current or {})
                LOG.info(
                    "%s Updating connectivity gateway '%s' (id %s)%s",
                    _LOG_PREFIX,
                    label,
                    gateway_id,
                    " [force_update: re-pushing to apply rotated secrets]" if forced else "",
                )
                result["diff_plan"].append(
                    {
                        "device": label,
                        "branch": "connectivity (forced update)" if forced else "connectivity (update)",
                        "before": self._norm(current or {}),
                        "after": self._norm(details),
                    }
                )
                self.gsdk.update_gateway_services(gateway_id, details)
                result["updated"].append(label)
                result["changed"] = True

        LOG.info(
            "%s Create completed: %s created, %s updated, %s skipped (changed: %s)",
            _LOG_PREFIX,
            len(result["created"]),
            len(result["updated"]),
            len(result["skipped"]),
            result["changed"],
        )
        return result

    def delete(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Delete the gateway services defined in the config file, idempotently.

        Each config entry is resolved to its gateway id (by identity) and removed; entries with no
        matching existing gateway are silently skipped.
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": [], "diff_plan": []}

        pending = list(self._iter_services(config_yaml_file))
        if not pending:
            return result

        lan_segments = self.gsdk.get_lan_segments_dict()
        existing = self._existing_gateways()

        for service_type, service in pending:
            details = self._build_details(service, service_type, lan_segments)
            identity = self._identity_of(details)
            label = self._entry_label(identity)
            gateway_id, current = self._find_existing(identity, existing)

            if gateway_id is None:
                LOG.info("%s Gateway '%s' not found, skipping delete", _LOG_PREFIX, label)
                result["skipped"].append(label)
                continue

            LOG.info("%s Deleting %s gateway '%s' (id %s)", _LOG_PREFIX, service_type, label, gateway_id)
            result["diff_plan"].append(
                {
                    "device": label,
                    "branch": f"{service_type} (delete)",
                    "before": self._redact_secrets(current or {}),
                    "after": {},
                }
            )
            self.gsdk.delete_gateway_services(gateway_id)
            result["deleted"].append(label)
            result["changed"] = True

        LOG.info(
            "%s Delete completed: %s deleted, %s skipped (changed: %s)",
            _LOG_PREFIX,
            len(result["deleted"]),
            len(result["skipped"]),
            result["changed"],
        )
        return result
