"""
BGP Manager for Graphiant Playbooks.

This module handles BGP peering configuration management,
including bgp multipath, route aggregations and routing-policy attachment/detachment.

Config lives under:
  edge.segments.<segment>.bgpNeighbors
  edge.segments.<segment>.bgpAggregations
  edge.segments.<segment>.ebgpMultipath
  edge.routePolicies                     (device-level global policy attachment)

Idempotency: configure/deconfigure/detach_policies each fetch the device's current
state via get_device_info and compare the intended change (per segment + neighbor /
aggregation) against what is already on the device. If the desired state already
matches, the config push for that device is skipped. Note: BGP MD5 passwords are
excluded from the comparison because the GET API never returns the secret value.
"""

from typing import Any, Dict

from .base_manager import BaseManager
from .device_config_common import fetch_device_by_name, new_apply_result, redact_sensitive_for_log
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class BGPManager(BaseManager):
    """
    Manages BGP peering configurations.

    Handles the configuration, deconfiguration, and policy management
    for BGP peering relationships with per-device idempotency and diff support.
    """

    # --- Desired-payload builders -----------------------------------------
    # Translate a device's config-file entry into the ``edge`` PUT payload
    # (routePolicies + per-segment bgpNeighbors/bgpAggregations).

    # Legacy snake_case config keys (pre-26.9.0) -> camelCase. camelCase is the
    # documented form; snake_case is still accepted so old configs keep working.
    _SNAKE_TO_CAMEL = {
        "bgp_peering": "bgpPeering",
        "route_policies": "routePolicies",
        "lan_segment": "lanSegment",
        "bgp_aggregations": "bgpAggregations",
        "ebgp_multipath": "ebgpMultipath",
        "remote_ipv4_address": "remoteIpv4Address",
        "peer_as": "peerAs",
        "local_interface": "localInterface",
        "ipv4_inbound_filter": "ipv4InboundFilter",
        "ipv4_outbound_filter": "ipv4OutboundFilter",
        "ipv6_inbound_filter": "ipv6InboundFilter",
        "ipv6_outbound_filter": "ipv6OutboundFilter",
        "hold_timer": "holdTimer",
        "keepalive_timer": "keepaliveTimer",
        "ebgp_multi_hop": "ebgpMultiHop",
        "as_override": "asOverride",
        "remote_private_as": "remotePrivateAs",
        "allow_as_in": "allowAsIn",
        "send_community": "sendCommunity",
        "md5_password": "md5Password",
        "minimum_interval": "minimumInterval",
        "local_multiplier": "localMultiplier",
        "as_set": "asSet",
        "summary_only": "summaryOnly",
    }

    # Defaults applied only when a neighbor is NEW. For an existing neighbor we send
    # only the keys the user wrote, so a partial update never resets unspecified
    # fields (BFD, timers, communities, ...) back to these values.
    _NEIGHBOR_DEFAULTS = {
        "holdTimer": 90,
        "keepaliveTimer": 30,
        "ebgpMultiHop": 1,
        "bfd": False,
        "sendCommunity": True,
        "asOverride": False,
        "remotePrivateAs": False,
    }

    @staticmethod
    def _camelize(entry):
        """
        Return a shallow copy of a config dict with legacy snake_case keys renamed to
        camelCase. When both forms are present the camelCase value wins. Non-dict input
        and unknown keys pass through untouched.
        """
        if not isinstance(entry, dict):
            return entry
        out = dict(entry)
        for snake, camel in BGPManager._SNAKE_TO_CAMEL.items():
            if snake in out:
                out.setdefault(camel, out[snake])  # camelCase takes precedence when both given
                del out[snake]
        return out

    def _build_device_payload(self, config, action, device_name=None, vault_md5_passwords=None, device_dict=None):
        """
        Build the ``edge`` BGP payload for a single device from its config entry.

        Args:
            config (dict): Per-device config (``segments`` plus optional ``routePolicies``).
            action (str): One of "add" (configure), "delete" (deconfigure), or
                "detach" (detach policies).
            device_name (str, optional): Owning device, used for the vault MD5 lookup.
            vault_md5_passwords (dict, optional): ``{device: {remoteAddress: md5}}`` from Ansible Vault.
            device_dict (dict, optional): The device GET response, used to decide new-vs-existing
                neighbors so an existing neighbor gets a sparse (merge-only) payload.

        Returns:
            dict: The device BGP payload (``routePolicies`` and ``segments``).

        Raises:
            ConfigurationError: If ``segments`` is missing or a route policy is not found.
        """
        config = self._camelize(config)
        if not isinstance(config, dict) or config.get("segments") is None:
            raise ConfigurationError("Missing required parameters: ['segments']")

        route_policies = config.get("routePolicies") or []
        LOG.debug("Edge BGP peering: %s %s", action.upper(), config.get("segments"))

        try:
            # Resolve route-policy names to global IDs (the API expects an integer).
            global_ids = {}
            for policy_name in route_policies:
                rid = self.gsdk.get_global_routing_policy_id(policy_name)
                if rid is None:
                    raise ConfigurationError(
                        f"Routing policy '{policy_name}' not found. "
                        "Configure global BGP filters first "
                        "(e.g. graphiant_global_config with sample_global_bgp_filters.yaml)."
                    )
                global_ids[policy_name] = rid
                LOG.debug("Global ID for %s: %s", policy_name, rid)

            return self._build_bgp_peering(
                action=action,
                segments=config.get("segments") or [],
                route_policies=route_policies,
                global_ids=global_ids,
                device_name=device_name,
                vault_md5_passwords=vault_md5_passwords,
                device_dict=device_dict,
            )
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to process device BGP peering %s: %s", config.get("segments"), str(e))
            raise ConfigurationError(f"Device BGP peering processing failed: {str(e)}")

    @staticmethod
    def _is_absent(entry):
        """Return True when a config entry is marked ``state: absent``."""
        return isinstance(entry, dict) and str(entry.get("state", "")).lower() == "absent"

    @staticmethod
    def _policy_ref(value, force_detach=False):
        """
        Build a BGP address-family policy reference from a config filter field.

        Args:
            value: The filter field value (a policy name, ``absent``, or blank/None).
            force_detach (bool): When True (the ``detach`` action), detach regardless of value.

        Returns:
            None when the field is absent/blank -- the caller omits the key so the
            policy is left unchanged on the merge PUT.
            ``{"policy": None}`` to detach the policy (value ``absent`` or O(force_detach)).
            ``{"policy": <name>}`` to attach the named policy.
        """
        if value is None:
            return None
        text = str(value).strip()
        if text == "":
            return None
        if force_detach or text.lower() == "absent":
            return {"policy": None}
        return {"policy": value}

    @staticmethod
    def _build_bgp_neighbor(neighbor, action, device_name=None, vault_md5_passwords=None, is_new=True):
        """
        Build the payload for a single BGP neighbor.

        Args:
            neighbor (dict): Neighbor configuration from the config file.
            action (str): One of "add", "delete", or "detach".
            device_name (str, optional): Owning device, used for the vault MD5 lookup.
            vault_md5_passwords (dict, optional): ``{device: {remoteAddress: md5}}`` from Ansible
                Vault. Fills a neighbor's MD5 password only when the YAML leaves it null/absent.
            is_new (bool): True when the neighbor does not yet exist on the device. Only then
                are the per-field defaults and the create-time scaffolding (``enabled``, ``state``,
                ``bgpType``, ``maxPrefixValue``) sent. For an existing neighbor the payload carries
                only the keys the user wrote, so a merge PUT leaves unspecified fields alone.

        Returns:
            dict: The neighbor payload ({"neighbor": None} when deleting).

        Note:
            A per-neighbor ``state: absent`` under the configure (``add``) action
            removes just that neighbor, leaving the rest of the device untouched.
        """
        neighbor = BGPManager._camelize(neighbor)
        if action == "delete" or (action == "add" and BGPManager._is_absent(neighbor)):
            return {"neighbor": None}

        # A new neighbor gets the full set of defaults; an existing one keeps only
        # the keys the user supplied (sparse merge).
        if is_new:
            neighbor = {**BGPManager._NEIGHBOR_DEFAULTS, **neighbor}

        # Address-family policies: attach by name, detach with `absent` (or the
        # detach action), or leave unchanged when the field is omitted.
        ipv4_family = {"addressFamily": "ipv4"}
        ipv4_inbound = BGPManager._policy_ref(neighbor.get("ipv4InboundFilter"), force_detach=action == "detach")
        if ipv4_inbound is not None:
            ipv4_family["inboundPolicy"] = ipv4_inbound
        ipv4_outbound = BGPManager._policy_ref(neighbor.get("ipv4OutboundFilter"), force_detach=action == "detach")
        if ipv4_outbound is not None:
            ipv4_family["outboundPolicy"] = ipv4_outbound

        ipv6_family = {"addressFamily": "ipv6"}
        ipv6_inbound = BGPManager._policy_ref(neighbor.get("ipv6InboundFilter"))
        if ipv6_inbound is not None:
            ipv6_family["inboundPolicy"] = ipv6_inbound
        ipv6_outbound = BGPManager._policy_ref(neighbor.get("ipv6OutboundFilter"))
        if ipv6_outbound is not None:
            ipv6_family["outboundPolicy"] = ipv6_outbound

        # MD5 password: YAML wins if non-null; otherwise fill from vault (device -> remoteAddress).
        md5_password = neighbor.get("md5Password")
        if md5_password is None and vault_md5_passwords and device_name:
            md5_password = (vault_md5_passwords.get(device_name) or {}).get(neighbor.get("remoteIpv4Address"))
            if md5_password:
                LOG.debug(
                    "Injected BGP MD5 password for device '%s' neighbor '%s' from vault",
                    device_name,
                    neighbor.get("remoteIpv4Address"),
                )

        payload = {
            "remoteAddress": neighbor["remoteIpv4Address"],
            "addressFamilies": {
                "ipv4": {"family": ipv4_family},
                "ipv6": {"family": ipv6_family},
            },
        }
        # Create-time scaffolding the device needs only when first adding the neighbor.
        if is_new:
            payload.update(
                {
                    "enabled": True,
                    "state": "UnknownBGPNeighborState",
                    "bgpType": "EBGP",
                    "maxPrefixValue": {},
                }
            )

        # Scalar fields: emit only the ones the user wrote (or the defaults merged in above).
        if "holdTimer" in neighbor:
            payload["holdTimerValue"] = {"timer": neighbor["holdTimer"]}
        if "keepaliveTimer" in neighbor:
            payload["keepaliveTimerValue"] = {"timer": neighbor["keepaliveTimer"]}
        if "ebgpMultiHop" in neighbor:
            payload["ebgpMultihopTtl"] = {"multiHop": neighbor["ebgpMultiHop"]}
        if "sendCommunity" in neighbor:
            payload["sendCommunity"] = bool(neighbor["sendCommunity"])
        if "asOverride" in neighbor:
            payload["asOverride"] = bool(neighbor["asOverride"])
        if "remotePrivateAs" in neighbor:
            payload["removePrivateAs"] = bool(neighbor["remotePrivateAs"])
        if "allowAsIn" in neighbor:
            payload["allowAsIn"] = {"count": neighbor["allowAsIn"]}

        # BFD: send only the sub-fields present so a partial update doesn't reset the rest. This
        # matches the portal UI payload exactly -- e.g. changing just the interval sends
        # ``bfd: {bfd: {minimumInterval: N}}`` with no ``enabled``, which the API merges without
        # turning BFD off.
        if any(k in neighbor for k in ("bfd", "minimumInterval", "localMultiplier")):
            bfd = {}
            if "bfd" in neighbor:
                bfd["enabled"] = bool(neighbor["bfd"])
            if neighbor.get("minimumInterval") is not None:
                bfd["minimumInterval"] = neighbor["minimumInterval"]
            if neighbor.get("localMultiplier") is not None:
                bfd["localMultiplier"] = neighbor["localMultiplier"]
            payload["bfd"] = {"bfd": bfd}

        # MD5 is write-only: send it only when we actually have a value, so a configure
        # without a password never overwrites an existing one with null.
        if md5_password is not None:
            payload["md5Password"] = {"md5Password": md5_password}

        if neighbor.get("peerAs"):
            payload["peerAsn"] = neighbor["peerAs"]
        if neighbor.get("localInterface"):
            payload["localInterface"] = {"interface": neighbor["localInterface"]}

        return {"neighbor": payload}

    @staticmethod
    def _build_ebgp_multipath(value, action):
        """
        Build the segment-level eBGP multipath payload (``{"config": {"enabled": bool}}``).

        Args:
            value: The config value -- a bool, or a dict with an ``enabled`` key.
            action (str): "add" uses the configured value; "delete" disables multipath.

        Returns:
            dict: The ``ebgpMultipath`` payload.
        """
        if action == "delete":
            enabled = False
        elif isinstance(value, dict):
            enabled = bool(value.get("enabled"))
        else:
            enabled = bool(value)
        return {"config": {"enabled": enabled}}

    @staticmethod
    def _build_bgp_aggregation(aggregation, action, is_new=True):
        """
        Build the payload for a single BGP route aggregation.

        Args:
            aggregation (dict): Aggregation configuration from the config file.
            action (str): One of "add", "delete", or "detach".
            is_new (bool): True when the aggregation does not yet exist on the device. Only then
                are ``asSet``/``summaryOnly`` defaulted; for an existing aggregation only the flags
                the user set are sent, so a partial update doesn't reset the other.

        Returns:
            dict: The aggregation payload ({"config": None} when deleting).

        Note:
            A per-aggregation ``state: absent`` under the configure (``add``) action
            removes just that aggregation, leaving the rest of the device untouched.
        """
        aggregation = BGPManager._camelize(aggregation)
        if action == "delete" or (action == "add" and BGPManager._is_absent(aggregation)):
            return {"config": None}

        # prefix/id identify the aggregation and are always sent.
        config = {"prefix": aggregation["prefix"], "id": aggregation["prefix"]}
        if is_new:
            config["asSet"] = bool(aggregation.get("asSet", False))
            config["summaryOnly"] = bool(aggregation.get("summaryOnly", False))
        else:
            if "asSet" in aggregation:
                config["asSet"] = bool(aggregation["asSet"])
            if "summaryOnly" in aggregation:
                config["summaryOnly"] = bool(aggregation["summaryOnly"])
        return {"config": config}

    @staticmethod
    def _build_bgp_peering(
        action, segments, route_policies, global_ids, device_name=None, vault_md5_passwords=None, device_dict=None
    ):
        """
        Build the full BGP peering payload for a device.

        Args:
            action (str): One of "add", "delete", or "detach".
            segments (list): LAN segment entries, each with optional neighbors/bgpAggregations.
            route_policies (list): Global routing policy names to attach at device level.
            global_ids (dict): Mapping of routing policy name to resolved global ID.
            device_name (str, optional): Owning device, used for the vault MD5 lookup.
            vault_md5_passwords (dict, optional): ``{device: {remoteAddress: md5}}`` from Ansible Vault.
            device_dict (dict, optional): The device GET response. Used to decide whether each
                neighbor is new (full defaults) or existing (sparse merge). When omitted, every
                neighbor is treated as new.

        Returns:
            dict: The device BGP peering payload.
        """
        payload = {}

        # Route policies are only attached on add; delete/detach leave them untouched here.
        if route_policies and action == "add":
            payload["routePolicies"] = {
                policy_name: {
                    "policy": {
                        "globalId": global_ids.get(policy_name, 0),
                        "isGlobalSync": True,
                    }
                }
                for policy_name in route_policies
            }

        segments_payload = {}
        for entry in segments:
            entry = BGPManager._camelize(entry)
            segment = {}
            if entry.get("neighbors"):
                existing_neighbors = BGPManager._index_by(
                    BGPManager._get_existing_vrf(device_dict or {}, entry["lanSegment"]).get("bgpNeighbors"),
                    "remoteAddress",
                )
                bgp_neighbors = {}
                for neighbor in entry["neighbors"]:
                    neighbor = BGPManager._camelize(neighbor)
                    address = neighbor["remoteIpv4Address"]
                    bgp_neighbors[address] = BGPManager._build_bgp_neighbor(
                        neighbor, action, device_name, vault_md5_passwords, is_new=address not in existing_neighbors
                    )
                segment["bgpNeighbors"] = bgp_neighbors
            if entry.get("bgpAggregations"):
                existing_aggregations = BGPManager._index_by(
                    BGPManager._get_existing_vrf(device_dict or {}, entry["lanSegment"]).get("bgpAggregations"),
                    "prefix",
                )
                bgp_aggregations = {}
                for aggregation in entry["bgpAggregations"]:
                    aggregation = BGPManager._camelize(aggregation)
                    prefix = aggregation["prefix"]
                    bgp_aggregations[prefix] = BGPManager._build_bgp_aggregation(
                        aggregation, action, is_new=prefix not in existing_aggregations
                    )
                segment["bgpAggregations"] = bgp_aggregations
            # Segment-level eBGP multipath (configure/deconfigure only; detach leaves it alone).
            if entry.get("ebgpMultipath") is not None and action in ("add", "delete"):
                segment["ebgpMultipath"] = BGPManager._build_ebgp_multipath(entry["ebgpMultipath"], action)
            segments_payload[entry["lanSegment"]] = segment

        payload["segments"] = segments_payload
        return payload

    # --- Normalized comparison helpers -------------------------------------
    # Both the desired PUT payload (nested, dict-keyed) and the device GET
    # response (flat, list-based) are reduced to the same small "normalized"
    # dict of user-controllable fields so they can be compared directly.

    @staticmethod
    def _sparse_differs(desired: Any, existing: Any) -> bool:
        """
        Return True if any key present in ``desired`` doesn't match ``existing``.

        Keys absent from ``desired`` are never compared -- they mean "not touched
        by this run," not "should be empty." Recurses into nested dicts.
        """
        if not isinstance(desired, dict):
            return desired != existing
        if not isinstance(existing, dict):
            return bool(desired)
        for key, desired_value in desired.items():
            existing_value = existing.get(key)
            if isinstance(desired_value, dict):
                if BGPManager._sparse_differs(desired_value, existing_value):
                    return True
            elif desired_value != existing_value:
                return True
        return False

    @staticmethod
    def _index_by(items: Any, key: str) -> Dict[Any, Dict[str, Any]]:
        """Index a GET-response list of dicts by one of their fields."""
        out: Dict[Any, Dict[str, Any]] = {}
        for item in items or []:
            if isinstance(item, dict) and item.get(key) is not None:
                out[item[key]] = item
        return out

    @staticmethod
    def _get_existing_vrf(device_dict: Dict[str, Any], seg_name: str) -> Dict[str, Any]:
        """Return the VRF (segment) dict for ``seg_name`` from the device GET response."""
        segments = device_dict.get("segments") if isinstance(device_dict, dict) else None
        if isinstance(segments, list):
            for seg in segments:
                if isinstance(seg, dict) and seg.get("name") == seg_name:
                    return seg
        elif isinstance(segments, dict):
            seg = segments.get(seg_name)
            if isinstance(seg, dict):
                return seg
        return {}

    @staticmethod
    def _existing_routing_policy_names(device_dict: Dict[str, Any]) -> set:
        """Collect the names of routing policies already known to the device."""
        names = set()
        policies = device_dict.get("routingPolicies") if isinstance(device_dict, dict) else None
        for policy in policies or []:
            if isinstance(policy, dict) and policy.get("name"):
                names.add(policy["name"])
        return names

    @staticmethod
    def _normalized_neighbor_from_desired(neighbor: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reduce a desired PUT neighbor payload (the dict under ``neighbor``) to normalized form.

        Only the keys actually present in the payload are emitted. For an existing neighbor the
        payload is sparse, so the diff compares just the fields the user wrote.
        """
        normalized: Dict[str, Any] = {}
        if "holdTimerValue" in neighbor:
            normalized["holdTimer"] = neighbor["holdTimerValue"]["timer"]
        if "keepaliveTimerValue" in neighbor:
            normalized["keepaliveTimer"] = neighbor["keepaliveTimerValue"]["timer"]
        if "ebgpMultihopTtl" in neighbor:
            normalized["multiHop"] = neighbor["ebgpMultihopTtl"]["multiHop"]
        if "sendCommunity" in neighbor:
            normalized["sendCommunity"] = bool(neighbor["sendCommunity"])
        if "asOverride" in neighbor:
            normalized["asOverride"] = bool(neighbor["asOverride"])
        if "removePrivateAs" in neighbor:
            normalized["removePrivateAs"] = bool(neighbor["removePrivateAs"])
        if "peerAsn" in neighbor:
            normalized["peerAsn"] = neighbor["peerAsn"]
        if "localInterface" in neighbor:
            normalized["localInterface"] = neighbor["localInterface"]["interface"]
        allow = (neighbor.get("allowAsIn") or {}).get("count")
        if allow:
            normalized["allowAsIn"] = allow

        if "bfd" in neighbor:
            bfd = neighbor["bfd"]["bfd"]
            if "enabled" in bfd:
                normalized["bfdEnabled"] = bool(bfd.get("enabled"))
            # Emit the sub-fields whenever the config set them, regardless of ``enabled`` -- a partial
            # update (e.g. only minimumInterval, no bfd key) must still be compared and pushed.
            if "minimumInterval" in bfd:
                normalized["bfdMinimumInterval"] = bfd["minimumInterval"]
            if "localMultiplier" in bfd:
                normalized["bfdMultiplier"] = bfd["localMultiplier"]

        families = neighbor.get("addressFamilies") or {}
        ipv4 = (families.get("ipv4") or {}).get("family") or {}
        if "inboundPolicy" in ipv4:
            normalized["ipv4Inbound"] = ipv4["inboundPolicy"]["policy"]
        if "outboundPolicy" in ipv4:
            normalized["ipv4Outbound"] = ipv4["outboundPolicy"]["policy"]
        ipv6 = (families.get("ipv6") or {}).get("family") or {}
        if "inboundPolicy" in ipv6:
            normalized["ipv6Inbound"] = ipv6["inboundPolicy"]["policy"]
        if "outboundPolicy" in ipv6:
            normalized["ipv6Outbound"] = ipv6["outboundPolicy"]["policy"]
        return normalized

    @staticmethod
    def _normalized_neighbor_from_get(neighbor: Dict[str, Any]) -> Dict[str, Any]:
        """Reduce a device GET-response neighbor to the same normalized form."""
        normalized: Dict[str, Any] = {
            "holdTimer": neighbor.get("holdTimer"),
            "keepaliveTimer": neighbor.get("keepaliveTimer"),
            "multiHop": neighbor.get("multiHop"),
            "sendCommunity": bool(neighbor.get("sendCommunity")),
            "asOverride": bool(neighbor.get("asOverride")),
            "removePrivateAs": bool(neighbor.get("removePrivateAs")),
            "bfdEnabled": bool((neighbor.get("bfd") or {}).get("enabled")),
        }
        if neighbor.get("peerAsn") is not None:
            normalized["peerAsn"] = neighbor["peerAsn"]
        if neighbor.get("localInterface"):
            normalized["localInterface"] = neighbor["localInterface"]
        allow = neighbor.get("allowAsIn")
        if allow:
            normalized["allowAsIn"] = allow

        # Emit the sub-fields independently of ``enabled`` so they compare symmetrically with the
        # desired side when the config asserts only a BFD sub-field.
        bfd = neighbor.get("bfd") or {}
        if bfd.get("minimumInterval") is not None:
            normalized["bfdMinimumInterval"] = bfd["minimumInterval"]
        if bfd.get("multiplier") is not None:
            normalized["bfdMultiplier"] = bfd["multiplier"]

        for family in neighbor.get("addressFamilies") or []:
            if not isinstance(family, dict):
                continue
            if family.get("addressFamily") == "ipv4":
                normalized["ipv4Inbound"] = family.get("inboundPolicy")
                normalized["ipv4Outbound"] = family.get("outboundPolicy")
            elif family.get("addressFamily") == "ipv6":
                normalized["ipv6Inbound"] = family.get("inboundPolicy")
                normalized["ipv6Outbound"] = family.get("outboundPolicy")
        return normalized

    @staticmethod
    def _normalized_aggregation_from_desired(config: Dict[str, Any]) -> Dict[str, Any]:
        # Only the flags present in the (possibly sparse) payload, so the diff compares just
        # what the config asserts for an existing aggregation.
        normalized: Dict[str, Any] = {}
        if "asSet" in config:
            normalized["asSet"] = bool(config.get("asSet"))
        if "summaryOnly" in config:
            normalized["summaryOnly"] = bool(config.get("summaryOnly"))
        return normalized

    @staticmethod
    def _normalized_aggregation_from_get(aggregation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "asSet": bool(aggregation.get("asSet")),
            "summaryOnly": bool(aggregation.get("summaryOnly")),
        }

    def _prune_absent_noops(self, payload: Dict[str, Any], device_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove delete markers for neighbors/aggregations that are not present on the device.

        A ``state: absent`` (or whole-device deconfigure) entry builds a null delete marker
        (``{"neighbor": None}`` / ``{"config": None}``). Deleting an object the device does not
        have is a no-op, but the API rejects it (500 "unable to delete ... error resolving BGP
        instance"). Dropping those markers keeps the push to only real changes. Segments left
        empty after pruning are removed too.
        """
        pruned_segments: Dict[str, Any] = {}
        for seg_name, seg in (payload.get("segments") or {}).items():
            existing_vrf = self._get_existing_vrf(device_dict, seg_name)
            existing_neighbors = self._index_by(existing_vrf.get("bgpNeighbors"), "remoteAddress")
            existing_aggregations = self._index_by(existing_vrf.get("bgpAggregations"), "prefix")

            new_seg: Dict[str, Any] = {}
            # Keep non-neighbor/aggregation keys (e.g. ebgpMultipath) as-is.
            for key, value in seg.items():
                if key not in ("bgpNeighbors", "bgpAggregations"):
                    new_seg[key] = value

            neighbors = seg.get("bgpNeighbors")
            if neighbors:
                kept = {
                    address: entry
                    for address, entry in neighbors.items()
                    if not (entry.get("neighbor") is None and address not in existing_neighbors)
                }
                if kept:
                    new_seg["bgpNeighbors"] = kept

            aggregations = seg.get("bgpAggregations")
            if aggregations:
                kept = {
                    prefix: entry
                    for prefix, entry in aggregations.items()
                    if not (entry.get("config") is None and prefix not in existing_aggregations)
                }
                if kept:
                    new_seg["bgpAggregations"] = kept

            if new_seg:
                pruned_segments[seg_name] = new_seg

        result = dict(payload)
        result["segments"] = pruned_segments
        return result

    def _device_diff(self, payload: Dict[str, Any], device_dict: Dict[str, Any], action: str):
        """
        Compare the desired device payload against current device state.

        Returns:
            (changed, before, after): whether a push is needed plus the
            normalized before/after used for the Ansible diff.
        """
        changed = False
        before: Dict[str, Any] = {"segments": {}}
        after: Dict[str, Any] = {"segments": {}}

        # Device-level routing-policy attachment is only asserted on configure.
        desired_route_policies = payload.get("routePolicies") or {}
        if action == "add" and desired_route_policies:
            existing_names = self._existing_routing_policy_names(device_dict)
            if any(name not in existing_names for name in desired_route_policies):
                changed = True
            before["routePolicies"] = sorted(n for n in desired_route_policies if n in existing_names)
            after["routePolicies"] = sorted(desired_route_policies)

        for seg_name, seg in (payload.get("segments") or {}).items():
            existing_vrf = self._get_existing_vrf(device_dict, seg_name)
            existing_neighbors = self._index_by(existing_vrf.get("bgpNeighbors"), "remoteAddress")
            existing_aggregations = self._index_by(existing_vrf.get("bgpAggregations"), "prefix")

            before_seg: Dict[str, Any] = {}
            after_seg: Dict[str, Any] = {}

            desired_neighbors = seg.get("bgpNeighbors") or {}
            if desired_neighbors:
                before_n: Dict[str, Any] = {}
                after_n: Dict[str, Any] = {}
                for address, entry in desired_neighbors.items():
                    existing = existing_neighbors.get(address)
                    # A None payload means removal -- whole-device deconfigure OR a
                    # per-neighbor `state: absent` on configure. Change only if present.
                    if entry.get("neighbor") is None:
                        before_n[address] = self._normalized_neighbor_from_get(existing) if existing else {}
                        after_n[address] = {}
                        if existing is not None:
                            changed = True
                    else:
                        desired_normalized = self._normalized_neighbor_from_desired(entry["neighbor"])
                        existing_normalized = self._normalized_neighbor_from_get(existing) if existing else {}
                        # Show "before" only for the fields this run asserts. For an existing neighbor
                        # the desired payload is sparse (a merge PUT), so fields the config omits are
                        # left unchanged on the device -- restricting the diff to the asserted keys keeps
                        # those untouched fields from rendering as deletions.
                        # New neighbor -> empty "before" (it doesn't exist). Existing neighbor ->
                        # only the asserted keys, so a partial update's merge-preserved fields aren't
                        # rendered as deletions.
                        before_n[address] = (
                            {key: existing_normalized.get(key) for key in desired_normalized} if existing else {}
                        )
                        after_n[address] = desired_normalized
                        if existing is None or self._sparse_differs(desired_normalized, existing_normalized):
                            changed = True
                before_seg["bgpNeighbors"] = before_n
                after_seg["bgpNeighbors"] = after_n

            desired_aggregations = seg.get("bgpAggregations") or {}
            if desired_aggregations:
                before_a: Dict[str, Any] = {}
                after_a: Dict[str, Any] = {}
                for prefix, entry in desired_aggregations.items():
                    existing = existing_aggregations.get(prefix)
                    # A None payload means removal -- whole-device deconfigure OR a
                    # per-aggregation `state: absent` on configure. Change only if present.
                    if entry.get("config") is None:
                        before_a[prefix] = self._normalized_aggregation_from_get(existing) if existing else {}
                        after_a[prefix] = {}
                        if existing is not None:
                            changed = True
                    else:
                        desired_normalized = self._normalized_aggregation_from_desired(entry["config"])
                        existing_normalized = self._normalized_aggregation_from_get(existing) if existing else {}
                        # Show "before" only for the flags this run asserts (sparse merge), so an
                        # omitted flag isn't rendered as a deletion.
                        # New aggregation -> empty "before"; existing -> only the asserted flags.
                        before_a[prefix] = (
                            {key: existing_normalized.get(key) for key in desired_normalized} if existing else {}
                        )
                        after_a[prefix] = desired_normalized
                        if existing is None or self._sparse_differs(desired_normalized, existing_normalized):
                            changed = True
                before_seg["bgpAggregations"] = before_a
                after_seg["bgpAggregations"] = after_a

            # Segment-level eBGP multipath. Desired payload key is ``ebgpMultipath``
            # ({"config": {"enabled": bool}}); the device GET reports it as ``bgpMultipath``.
            desired_multipath = seg.get("ebgpMultipath")
            if desired_multipath is not None:
                desired_enabled = bool((desired_multipath.get("config") or {}).get("enabled"))
                existing_enabled = bool((existing_vrf.get("bgpMultipath") or {}).get("enabled"))
                before_seg["ebgpMultipath"] = {"enabled": existing_enabled}
                after_seg["ebgpMultipath"] = {"enabled": desired_enabled}
                if desired_enabled != existing_enabled:
                    changed = True

            before["segments"][seg_name] = before_seg
            after["segments"][seg_name] = after_seg

        return changed, before, after

    def apply(self, config_yaml_file: str, action: str, vault_bgp_peering_md5_passwords=None) -> dict:
        """
        Apply a BGP operation across all devices in the config file, idempotently.

        Args:
            config_yaml_file: Path to the YAML file with BGP peering configurations.
            action: One of "add" (configure), "delete" (deconfigure), or
                "detach" (detach policies).
            vault_bgp_peering_md5_passwords (dict, optional): ``{device: {remoteAddress: md5}}`` from Ansible
                Vault; fills a neighbor's MD5 password when the YAML leaves it null/absent.

        Returns:
            dict: Result with ``changed``, ``configured_devices``,
            ``skipped_devices``, and ``diff_plan``.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found.
        """
        if action not in ("add", "delete", "detach"):
            raise ConfigurationError(f"Unsupported BGP action '{action}'")

        vault_md5 = vault_bgp_peering_md5_passwords if isinstance(vault_bgp_peering_md5_passwords, dict) else {}
        result = new_apply_result()
        output_config: Dict[int, Dict[str, Any]] = {}

        try:
            config_data = self._camelize(self.render_config_file(config_yaml_file))
            if not config_data or "bgpPeering" not in config_data:
                LOG.warning("No BGP peering configuration found in %s", config_yaml_file)
                return result

            enterprise = self.gsdk.enterprise_info["company_name"]

            for device_config in config_data.get("bgpPeering") or []:
                for device_name, config in device_config.items():
                    try:
                        device_id, device_dict = fetch_device_by_name(self.gsdk, device_name, enterprise)

                        config_payload = self._build_device_payload(
                            config, action, device_name, vault_md5, device_dict=device_dict
                        )
                        # Drop delete markers for neighbors/aggregations not present on the device;
                        # deleting a non-existent object is a no-op the API rejects (500).
                        config_payload = self._prune_absent_noops(config_payload, device_dict)

                        changed, before, after = self._device_diff(config_payload, device_dict, action)
                        if not changed:
                            LOG.info(
                                "[bgp] ✓ No changes needed for %s (ID: %s), skipping",
                                device_name,
                                device_id,
                            )
                            result["skipped_devices"].append(device_name)
                            continue

                        result["diff_plan"].append(
                            {
                                "device": device_name,
                                "branch": "edge.segments",
                                "before": redact_sensitive_for_log(before),
                                "after": redact_sensitive_for_log(after),
                            }
                        )
                        output_config[device_id] = {"device_id": device_id, "edge": config_payload}
                        result["configured_devices"].append(device_name)
                        LOG.info("[bgp] Prepared BGP payload for device: %s (ID: %s)", device_name, device_id)

                    except DeviceNotFoundError:
                        LOG.error("Device '%s' not found, skipping BGP operation", device_name)
                        raise
                    except ConfigurationError:
                        raise
                    except Exception as e:
                        LOG.error("Error processing BGP for device '%s': %s", device_name, str(e))
                        raise ConfigurationError(f"Failed to process BGP for {device_name}: {str(e)}")

            if not output_config:
                LOG.info("[bgp] No devices need changes; nothing to push")
                return result

            LOG.info("[bgp] Pushing payload for %d device(s)...", len(output_config))
            self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
            result["changed"] = True
            return result

        except (ConfigurationError, DeviceNotFoundError):
            raise
        except Exception as e:
            LOG.error("Error in BGP %s: %s", action, str(e))
            raise ConfigurationError(f"BGP {action} failed: {str(e)}")

    def configure(self, config_yaml_file: str, vault_bgp_peering_md5_passwords=None) -> dict:
        """Configure BGP neighbors, aggregations, and attach routing policies (idempotent).

        ``vault_bgp_peering_md5_passwords`` (``{device: {remoteAddress: md5}}``) fills a neighbor's MD5
        password from Ansible Vault when the YAML leaves it null/absent (YAML wins otherwise).
        """
        return self.apply(
            config_yaml_file, action="add", vault_bgp_peering_md5_passwords=vault_bgp_peering_md5_passwords
        )

    def deconfigure(self, config_yaml_file: str) -> dict:
        """Remove BGP neighbors and aggregations listed in the config file (idempotent)."""
        return self.apply(config_yaml_file, action="delete")

    def detach_policies(self, config_yaml_file: str) -> dict:
        """Detach routing policies from BGP peers without removing peers (idempotent)."""
        return self.apply(config_yaml_file, action="detach")

    # Backward compatibility methods
    def configure_bgp_peers(self, config_yaml_file: str) -> dict:
        """Alias for configure method for backward compatibility."""
        return self.configure(config_yaml_file)

    def deconfigure_bgp_peers(self, config_yaml_file: str) -> dict:
        """Alias for deconfigure method for backward compatibility."""
        return self.deconfigure(config_yaml_file)

    def detach_policies_from_bgp_peers(self, config_yaml_file: str) -> dict:
        """Alias for detach_policies method for backward compatibility."""
        return self.detach_policies(config_yaml_file)
