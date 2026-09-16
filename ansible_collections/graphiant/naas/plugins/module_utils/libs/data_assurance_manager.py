"""
Data Assurance Manager for Graphiant Playbooks.

Manages Graphiant Data Assurance policies via the portal API:
  POST   /v1/data/assurance/assurances/global         — create
  PUT    /v1/data/assurance/assurances/global/{id}    — update (overwrite)
  DELETE /v1/data/assurance/assurances/global/{id}    — delete
  GET    /v1/data/assurance/assurances/global          — list all
  GET    /v1/data/assurance/assurances/global/{id}    — get by ID

Config file format (YAML, Jinja2 templating supported):

  DataAssurancePolicies:
    - name: "assurance-latency-1"        # assurance policy (has flexAlgo)
      flexAlgo: "LATENCY"
      useAllSites: true
      lanNames:
        - "lan-segment-1"
      apps:
        - name: "iperf"
          profileName: "Graphiant_Assured"   # resolved to bucketId 256
          useAllServers: true
          servers:
            - { ip: "10.1.1.2", port: 5201, protocol: "tcp" }

    - name: "block-17ebook"              # block / protection policy (no flexAlgo)
      useAllSites: true
      lanNames:
        - "lan-segment-1"
      apps:
        - name: "17ebook.com"
          profileName: "Threat_Blocked"      # resolved to bucketId 16384
          isDomain: true
          useAllServers: true
          servers:
            - { ip: "208.91.196.152", port: 80, protocol: "tcp" }

Configure is idempotent: compares the desired ManaV2AssuranceConfig against the
current policy config (fetched per-policy via GET /{id}) and skips the PUT when
the normalized configs are equal.

Deconfigure is idempotent: missing policies are silently skipped. Deleting a policy is a
two-step flow — the portal requires a policy to be unassigned from all sites first, so the
manager PUTs a detached config (no sites, empty apps/rules) and then DELETEs the policy.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from .base_manager import BaseManager
from .exceptions import ConfigurationError
from .logger import setup_logger

LOG = setup_logger()

_YAML_KEY = "DataAssurancePolicies"
_CF_YAML_KEY = "ContentFilterPolicies"
_LOG_PREFIX = "[data-assurance]"

_APP_FIELDS = ("bucketId", "builtinAppId", "customAppId", "isDomain", "name", "useAllServers")
_SERVER_FIELDS = ("ip", "port", "protocol")
_CONFIG_FIELDS = ("flexAlgo", "lanNames", "useAllSites")
# Content-filter (block-by-category) policy fields forwarded to the API as-is.
# name/rules are built separately; siteListId is resolved from siteListName.
_CF_CONFIG_FIELDS = ("lanNames", "useAllSites")
# siteListId is always resolved from siteListName (or kept as-is if already an int)
# via _resolve_site_list() — it is intentionally excluded from _CONFIG_FIELDS to avoid
# passing a raw user-provided integer before validation.

# Human-readable profile name → integer bucketId.
# These are fixed Graphiant platform constants (a bitmask enum); there is no runtime API to
# query them. Users may specify `profileName` in YAML instead of the raw integer `bucketId`.
# Use `bucketId` directly (as an integer) for any value not listed here.
#
# Source of truth: the AssuranceBucket enum in
#   apidefs/proto/assurance/assurance_messages.ts (a.k.a. assurance_messages.proto).
# Keep this map in sync with that enum.
_PROFILE_BUCKET_MAP: Dict[str, int] = {
    "Unknown_Bucket": 0,
    "Unsecured_DIA": 1,
    "Unsecured_DIA_Risky": 2,
    "Unclassified_Public_Apps": 4,
    "Classified_Public_Apps": 8,
    "Enterprise_Saas_Application": 16,
    "Public_Application": 32,
    "Public_AI_Application": 64,
    "Public_Other_Application": 128,
    "Graphiant_Assured": 256,
    "Data_Assured": 512,
    "General_Assured": 1024,
    "General_Unclassified_Assured": 2048,
    "General_Private_Assured": 4096,
    "Critical_Compliance": 8192,
    "Threat_Blocked": 16384,
    "Unsecured_DIA_Private_Apps": 32768,
    "Data_Unclassified_Assured": 65536,
    "Graphiant_Unclassified_Assured": 131072,
    "Unsecured_DIA_Unclassified": 262144,
    "Data_Exchange": 524288,
    "Data_Exchange_General": 1048576,
    "Data_Exchange_Flex": 2097152,
    "Dns_Proxy": 4194304,
    "Packet_Dropped": 8388608,
}

# Reverse lookup: integer bucketId → profile (enum) name. Used to derive the bucket enum
# name (which the bucket-apps API expects) for apps that specify a raw integer bucketId
# instead of a profileName.
_BUCKET_ID_TO_PROFILE: Dict[int, str] = {v: k for k, v in _PROFILE_BUCKET_MAP.items()}

# Default time window for the bucket-apps telemetry query (mirrors the portal UI:
# a 30-day window bucketed in 12-hour (43200s) intervals).
_BUCKET_APPS_WINDOW_DAYS = 30
_BUCKET_APPS_BUCKET_SIZE_SEC = 43200


def _resolve_profile_name(app_cfg: Dict, policy_name: str) -> Optional[int]:
    """
    Resolve ``profileName`` (human-readable) to an integer ``bucketId``.

    Returns None when neither ``profileName`` nor ``bucketId`` is present so the
    API omits the field (some apps may not need it).

    Raises:
        ConfigurationError: when ``profileName`` is specified but not in ``_PROFILE_BUCKET_MAP``.
    """
    profile_name = app_cfg.get("profileName")
    if profile_name is not None:
        if profile_name not in _PROFILE_BUCKET_MAP:
            raise ConfigurationError(
                f"Policy '{policy_name}', app '{app_cfg.get('name')}': "
                f"profileName '{profile_name}' is not recognised. "
                f"Valid profile names: {sorted(_PROFILE_BUCKET_MAP.keys())}. "
                "Use 'bucketId' (integer) for values not in this list."
            )
        return _PROFILE_BUCKET_MAP[profile_name]
    return app_cfg.get("bucketId")


def _canon_server_ip(ip: Any) -> Any:
    """Strip a host-mask suffix so a bare IP compares equal to its CIDR host form.

    Users typically supply a bare address (``10.1.1.2``) but the portal echoes it back as a
    /32 (IPv4) or /128 (IPv6) host address; normalizing keeps the two equal for idempotency
    without changing what we send. Real subnets (e.g. ``10.1.1.0/24``) are left untouched.
    """
    if isinstance(ip, str):
        for suffix in ("/32", "/128"):
            if ip.endswith(suffix):
                return ip[: -len(suffix)]
    return ip


def _norm_servers(servers: Optional[List[Any]]) -> List[Dict]:
    if not servers:
        return []
    result = []
    for s in servers:
        if isinstance(s, dict):
            entry = {k: s.get(k) for k in _SERVER_FIELDS if s.get(k) is not None}
        else:
            entry = {k: getattr(s, k, None) for k in _SERVER_FIELDS if getattr(s, k, None) is not None}
        if "ip" in entry:
            entry["ip"] = _canon_server_ip(entry["ip"])
        result.append(entry)
    return sorted(result, key=lambda x: (x.get("ip") or "", x.get("port") or 0))


def _norm_app(app: Any) -> Dict:
    if isinstance(app, dict):

        def get(k):
            return app.get(k)

    else:

        def get(k):
            return getattr(app, k, None)

    # Boolean flags default to False. The portal echoes them back as false when unset, but a
    # user may simply omit them (e.g. an app with explicit servers and no useAllServers).
    # Coercing both sides to a bool keeps "absent" and "false" equal so a false flag does not
    # cause a spurious idempotency diff (which otherwise re-updates the policy on every run).
    d: Dict[str, Any] = {
        "isDomain": bool(get("isDomain")),
        "useAllServers": bool(get("useAllServers")),
    }
    for k in ("bucketId", "builtinAppId", "customAppId", "name"):
        value = get(k)
        if value is not None:
            d[k] = value
    d["servers"] = _norm_servers(get("servers"))
    return d


def _norm_apps(apps: Optional[List[Any]]) -> List[Dict]:
    if not apps:
        return []
    normalized = [_norm_app(a) for a in apps]
    return sorted(
        normalized, key=lambda x: (x.get("builtinAppId") or 0, x.get("customAppId") or 0, x.get("name") or "")
    )


def _norm_config(config: Any) -> Dict:
    """Normalize a ManaV2AssuranceConfig (SDK object or dict) for idempotency comparison.

    SDK model objects expose snake_case attributes (e.g. ``bucket_id``) but serialize to
    camelCase via ``to_dict()``. The desired payload is built in camelCase, so convert any
    SDK object to its camelCase dict form first; otherwise nested app/server fields would
    normalize to ``None`` and the idempotency comparison would never match.
    """
    if not isinstance(config, dict) and hasattr(config, "to_dict"):
        config = config.to_dict()

    if isinstance(config, dict):

        def get(k):
            return config.get(k)

    else:

        def get(k):
            return getattr(config, k, None)

    lan_names = get("lanNames") or get("lan_names") or []
    return {
        "flexAlgo": get("flexAlgo") or get("flex_algo") or "",
        "lanNames": sorted(lan_names),
        "siteListId": get("siteListId") or get("site_list_id"),
        "useAllSites": bool(get("useAllSites") or get("use_all_sites")),
        "apps": _norm_apps(get("apps")),
    }


def _build_config_payload(policy_cfg: Dict, site_list_id: Optional[int] = None) -> Dict:
    """
    Build the ManaV2AssuranceConfig wire shape from a YAML policy entry.

    ``siteListName`` is a user-facing alias resolved upstream to ``site_list_id``
    and never forwarded to the API.

    ``profileName`` in each app entry is resolved to integer ``bucketId`` here;
    raw ``bucketId`` integers are passed through unchanged.
    """
    policy_name = policy_cfg.get("name", "")
    payload: Dict[str, Any] = {"name": policy_name}
    for field in _CONFIG_FIELDS:
        value = policy_cfg.get(field)
        if value is not None:
            payload[field] = value
    if site_list_id is not None:
        payload["siteListId"] = site_list_id
    if "apps" in policy_cfg:
        resolved_apps = []
        for app in policy_cfg["apps"] or []:
            if not isinstance(app, dict):
                resolved_apps.append(app)
                continue
            app_wire = {k: v for k, v in app.items() if k not in ("profileName", "bucketId")}
            bucket_id = _resolve_profile_name(app, policy_name)
            if bucket_id is not None:
                app_wire["bucketId"] = bucket_id
            resolved_apps.append(app_wire)
        payload["apps"] = resolved_apps
    return payload


def _build_detach_payload(policy_cfg: Dict) -> Dict:
    """
    Build a "detached" ManaV2AssuranceConfig used before deletion: clears the site association
    (empty ``sites`` oneof — no ``siteListId``/``useAllSites``) and empties ``apps``, keeping
    ``name`` (and ``flexAlgo``/``lanNames`` when present). The portal requires a policy to be
    unassigned from all sites before it can be deleted.
    """
    payload: Dict[str, Any] = {"name": policy_cfg.get("name", ""), "apps": []}
    if policy_cfg.get("flexAlgo"):
        payload["flexAlgo"] = policy_cfg["flexAlgo"]
    if policy_cfg.get("lanNames"):
        payload["lanNames"] = policy_cfg["lanNames"]
    return payload


def _build_cf_detach_payload(policy_cfg: Dict) -> Dict:
    """
    Build a "detached" ManaV2GlobalContentFilterConfig used before deletion: clears the site
    association and empties ``rules``, keeping ``name`` (and ``lanNames`` when present).
    """
    payload: Dict[str, Any] = {"name": policy_cfg.get("name", ""), "rules": []}
    if policy_cfg.get("lanNames"):
        payload["lanNames"] = policy_cfg["lanNames"]
    return payload


def _build_content_filter_payload(
    policy_cfg: Dict, category_map: Dict[str, int], site_list_id: Optional[int] = None
) -> Dict:
    """
    Build the ManaV2GlobalContentFilterConfig wire shape from a ContentFilterPolicies entry.

    A content-filter policy blocks one or more domain ``categories`` (by name, resolved here to
    ``domainCategoryId`` via ``category_map``). The policy-level ``allowedUrlList`` — the
    "Allowed URL List" — is applied as ``exceptionWildcards`` on every category rule.

    Raises:
        ConfigurationError: when a category name is not in ``category_map``.
    """
    policy_name = policy_cfg.get("name", "")
    payload: Dict[str, Any] = {"name": policy_name}
    for field in _CF_CONFIG_FIELDS:
        value = policy_cfg.get(field)
        if value is not None:
            payload[field] = value
    if site_list_id is not None:
        payload["siteListId"] = site_list_id

    allowed_urls = policy_cfg.get("allowedUrlList") or []
    rules: List[Dict[str, Any]] = []
    for category in policy_cfg.get("categories") or []:
        if category not in category_map:
            raise ConfigurationError(
                f"Content-filter policy '{policy_name}': category '{category}' is not recognised. "
                f"Available categories: {sorted(category_map.keys())}"
            )
        rule: Dict[str, Any] = {"domainCategoryId": category_map[category]}
        if allowed_urls:
            rule["exceptionWildcards"] = allowed_urls
        rules.append(rule)
    payload["rules"] = rules
    return payload


def _norm_cf_config(config: Any) -> Dict:
    """Normalize a ManaV2GlobalContentFilterConfig (SDK object or dict) for idempotency."""
    if not isinstance(config, dict) and hasattr(config, "to_dict"):
        config = config.to_dict()

    if isinstance(config, dict):

        def get(k):
            return config.get(k)

    else:

        def get(k):
            return getattr(config, k, None)

    raw_rules = get("rules") or []
    norm_rules = sorted(
        (
            {
                "domainCategoryId": (
                    r.get("domainCategoryId") if isinstance(r, dict) else getattr(r, "domain_category_id", None)
                ),
                "exceptionWildcards": sorted(
                    (r.get("exceptionWildcards") if isinstance(r, dict) else getattr(r, "exception_wildcards", None))
                    or []
                ),
            }
            for r in raw_rules
        ),
        key=lambda x: x["domainCategoryId"] or 0,
    )
    return {
        "lanNames": sorted(get("lanNames") or get("lan_names") or []),
        "siteListId": get("siteListId") or get("site_list_id"),
        "useAllSites": bool(get("useAllSites") or get("use_all_sites")),
        "rules": norm_rules,
    }


class DataAssuranceManager(BaseManager):
    """
    Manager for Data Assurance and block/protection policy CRUD via the Graphiant portal API.

    Both assurance policies (with ``flexAlgo``) and block/protection policies (without
    ``flexAlgo``, typically ``Threat_Blocked`` (bucketId 16384) with ``isDomain: true``) are entries in the
    same ``DataAssurancePolicies`` YAML list and are sent to the same portal API endpoint.
    """

    def configure(
        self,
        config_yaml_file: Optional[str] = None,
        data_assurance_policies: Optional[List[Any]] = None,
        content_filter_policies: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create or update Data Assurance / block policies from a YAML file and/or
        directly-provided module parameters.

        Idempotent: compares each intended config against live portal state and skips
        the PUT when already matched.

        Args:
            config_yaml_file: Optional path to the YAML config file containing a
                ``DataAssurancePolicies`` and/or ``ContentFilterPolicies`` list.
            data_assurance_policies: Optional list of assurance/block policy dicts supplied
                directly as module parameters. Overlaid on top of the config file, keyed by
                policy ``name`` — supplied fields override the config-file values.
            content_filter_policies: Optional list of content-filter (block-by-category)
                policy dicts supplied directly as module parameters, merged the same way.

        Returns:
            dict: ``{changed, configured, skipped, diff_plan}``
        """
        result: Dict[str, Any] = {"changed": False, "configured": [], "skipped": [], "diff_plan": []}

        config_data = self._resolve_config_data(config_yaml_file, data_assurance_policies, content_filter_policies)
        if not config_data or (_YAML_KEY not in config_data and _CF_YAML_KEY not in config_data):
            LOG.info("%s No %s or %s key found in YAML file", _LOG_PREFIX, _YAML_KEY, _CF_YAML_KEY)
            return result

        policies = config_data.get(_YAML_KEY) or []
        if not isinstance(policies, list):
            raise ConfigurationError(f"{_YAML_KEY} must be a list.")

        if policies:
            existing = self.gsdk.get_data_assurance_policies()
            existing_by_name: Dict[str, Any] = self._index_by_name(existing)

            valid_flex_algos = self._fetch_valid_flex_algos()
            valid_lan_segments = self._fetch_valid_lan_segments()
            bucket_apps_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
            bucket_app_servers_cache: Dict[str, List[Dict[str, Any]]] = {}

            for policy_cfg in policies:
                if not isinstance(policy_cfg, dict):
                    continue
                name = policy_cfg.get("name")
                if not name:
                    raise ConfigurationError(f"{_YAML_KEY}: each policy entry must have a 'name' field.")

                LOG.info("%s Processing policy '%s'", _LOG_PREFIX, name)
                self._validate_flex_algo(policy_cfg.get("flexAlgo"), name, valid_flex_algos)
                self._validate_lan_names(
                    policy_cfg.get("lanNames") or policy_cfg.get("lan_names"), name, valid_lan_segments
                )
                site_list_id = self._resolve_site_list(policy_cfg)

                # For an existing policy, fetch its current config first so auto-fill can reuse the
                # already-stored servers/hints (only genuinely new apps hit telemetry). This keeps
                # re-runs idempotent even though telemetry is time-windowed and can drift.
                is_update = name in existing_by_name
                assurance_id = self._row_id(existing_by_name[name]) if is_update else None
                current_config = self.gsdk.get_data_assurance_policy_config(assurance_id) if is_update else None

                self._validate_and_autofill_apps(
                    policy_cfg, bucket_apps_cache, bucket_app_servers_cache, current_config=current_config
                )
                config_payload = _build_config_payload(policy_cfg, site_list_id=site_list_id)

                if not is_update:
                    LOG.info("%s Creating new policy '%s'", _LOG_PREFIX, name)
                    result["diff_plan"].append(
                        {"policy": name, "action": "create", "before": {}, "after": config_payload}
                    )
                    self.gsdk.create_data_assurance_policy(config_payload)
                    result["configured"].append(name)
                    result["changed"] = True
                else:
                    current_norm = _norm_config(current_config) if current_config else {}
                    desired_norm = _norm_config(config_payload)

                    if current_norm == desired_norm:
                        LOG.info("%s Policy '%s' already matches desired state, skipping", _LOG_PREFIX, name)
                        result["skipped"].append(name)
                    else:
                        LOG.info("%s Updating policy '%s' (ID: %s)", _LOG_PREFIX, name, assurance_id)
                        result["diff_plan"].append(
                            {
                                "policy": name,
                                "action": "update",
                                "before": current_norm,
                                "after": desired_norm,
                            }
                        )
                        self.gsdk.update_data_assurance_policy(assurance_id, config_payload)
                        result["configured"].append(name)
                        result["changed"] = True

        self._configure_content_filters(config_data, result)

        LOG.info(
            "%s Configure completed: %s configured, %s skipped (changed: %s)",
            _LOG_PREFIX,
            len(result["configured"]),
            len(result["skipped"]),
            result["changed"],
        )
        return result

    def _configure_content_filters(self, config_data: Dict, result: Dict[str, Any]) -> None:
        """
        Create or update content-filter (block-by-category) policies from the
        ``ContentFilterPolicies`` key. Idempotent — skips policies already matching.

        Mutates ``result`` (shared with the DataAssurancePolicies pass): appends to
        ``configured`` / ``skipped`` / ``diff_plan`` and sets ``changed``.
        """
        cf_policies = config_data.get(_CF_YAML_KEY) or []
        if not cf_policies:
            return
        if not isinstance(cf_policies, list):
            raise ConfigurationError(f"{_CF_YAML_KEY} must be a list.")

        existing_by_name = self._index_cf_by_name(self.gsdk.get_content_filters())
        category_map = self._fetch_domain_categories()

        for policy_cfg in cf_policies:
            if not isinstance(policy_cfg, dict):
                continue
            name = policy_cfg.get("name")
            if not name:
                raise ConfigurationError(f"{_CF_YAML_KEY}: each policy entry must have a 'name' field.")

            LOG.info("%s Processing content-filter policy '%s'", _LOG_PREFIX, name)
            site_list_id = self._resolve_site_list(policy_cfg)
            config_payload = _build_content_filter_payload(policy_cfg, category_map, site_list_id=site_list_id)

            if name not in existing_by_name:
                LOG.info("%s Creating new content-filter policy '%s'", _LOG_PREFIX, name)
                result["diff_plan"].append({"policy": name, "action": "create", "before": {}, "after": config_payload})
                self.gsdk.create_content_filter(config_payload)
                result["configured"].append(name)
                result["changed"] = True
            else:
                cf_id = self._cf_row_id(existing_by_name[name])
                current_config = self.gsdk.get_content_filter_config(cf_id)
                current_norm = _norm_cf_config(current_config) if current_config else {}
                desired_norm = _norm_cf_config(config_payload)

                if current_norm == desired_norm:
                    LOG.info("%s Content-filter policy '%s' already matches desired state, skipping", _LOG_PREFIX, name)
                    result["skipped"].append(name)
                else:
                    LOG.info("%s Updating content-filter policy '%s' (ID: %s)", _LOG_PREFIX, name, cf_id)
                    result["diff_plan"].append(
                        {"policy": name, "action": "update", "before": current_norm, "after": desired_norm}
                    )
                    self.gsdk.update_content_filter(cf_id, config_payload)
                    result["configured"].append(name)
                    result["changed"] = True

    def deconfigure(
        self,
        config_yaml_file: Optional[str] = None,
        data_assurance_policies: Optional[List[Any]] = None,
        content_filter_policies: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Delete Data Assurance / block policies listed in a YAML file and/or supplied
        directly as module parameters.

        Idempotent: policies not found are silently skipped.

        Args:
            config_yaml_file: Optional path to the YAML config file containing a
                ``DataAssurancePolicies`` and/or ``ContentFilterPolicies`` list.
            data_assurance_policies: Optional list of assurance/block policy dicts supplied
                directly as module parameters (merged with the config file by policy ``name``).
            content_filter_policies: Optional list of content-filter policy dicts supplied
                directly as module parameters (merged the same way).

        Returns:
            dict: ``{changed, deleted, skipped}``
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": []}

        config_data = self._resolve_config_data(config_yaml_file, data_assurance_policies, content_filter_policies)
        if not config_data or (_YAML_KEY not in config_data and _CF_YAML_KEY not in config_data):
            LOG.info("%s No %s or %s key found in YAML file", _LOG_PREFIX, _YAML_KEY, _CF_YAML_KEY)
            return result

        policies = config_data.get(_YAML_KEY) or []
        if not isinstance(policies, list):
            raise ConfigurationError(f"{_YAML_KEY} must be a list.")

        if policies:
            names = [p.get("name") for p in policies if isinstance(p, dict) and p.get("name")]
            LOG.info("%s Attempting to delete policies: %s", _LOG_PREFIX, names)

            existing = self.gsdk.get_data_assurance_policies()
            existing_by_name: Dict[str, Any] = self._index_by_name(existing)

            for policy_cfg in policies:
                if not isinstance(policy_cfg, dict):
                    continue
                name = policy_cfg.get("name")
                if not name:
                    raise ConfigurationError(f"{_YAML_KEY}: each policy entry must have a 'name' field.")

                if name not in existing_by_name:
                    LOG.info("%s Policy '%s' not found, skipping deletion", _LOG_PREFIX, name)
                    result["skipped"].append(name)
                    continue

                assurance_id = self._row_id(existing_by_name[name])
                # The portal requires a policy to be unassigned from all sites before deletion:
                # first PUT a detached config (no sites, empty apps), then DELETE.
                LOG.info(
                    "%s Detaching sites/apps from policy '%s' (ID: %s) before deletion",
                    _LOG_PREFIX,
                    name,
                    assurance_id,
                )
                self.gsdk.update_data_assurance_policy(assurance_id, _build_detach_payload(policy_cfg))
                LOG.info("%s Deleting policy '%s' (ID: %s)", _LOG_PREFIX, name, assurance_id)
                self.gsdk.delete_data_assurance_policy(assurance_id)
                result["deleted"].append(name)
                result["changed"] = True

        self._deconfigure_content_filters(config_data, result)

        LOG.info(
            "%s Deconfigure completed: deleted=%s, skipped=%s",
            _LOG_PREFIX,
            result["deleted"],
            result["skipped"],
        )
        return result

    def _deconfigure_content_filters(self, config_data: Dict, result: Dict[str, Any]) -> None:
        """
        Delete content-filter (block-by-category) policies listed under ``ContentFilterPolicies``.
        Idempotent — policies not found are skipped. Mutates ``result``.
        """
        cf_policies = config_data.get(_CF_YAML_KEY) or []
        if not cf_policies:
            return
        if not isinstance(cf_policies, list):
            raise ConfigurationError(f"{_CF_YAML_KEY} must be a list.")

        existing_by_name = self._index_cf_by_name(self.gsdk.get_content_filters())

        for policy_cfg in cf_policies:
            if not isinstance(policy_cfg, dict):
                continue
            name = policy_cfg.get("name")
            if not name:
                raise ConfigurationError(f"{_CF_YAML_KEY}: each policy entry must have a 'name' field.")

            if name not in existing_by_name:
                LOG.info("%s Content-filter policy '%s' not found, skipping deletion", _LOG_PREFIX, name)
                result["skipped"].append(name)
                continue

            cf_id = self._cf_row_id(existing_by_name[name])
            # Detach sites (and clear rules) before deleting, same as assurance policies.
            LOG.info(
                "%s Detaching sites/rules from content-filter policy '%s' (ID: %s) before deletion",
                _LOG_PREFIX,
                name,
                cf_id,
            )
            self.gsdk.update_content_filter(cf_id, _build_cf_detach_payload(policy_cfg))
            LOG.info("%s Deleting content-filter policy '%s' (ID: %s)", _LOG_PREFIX, name, cf_id)
            self.gsdk.delete_content_filter(cf_id)
            result["deleted"].append(name)
            result["changed"] = True

    def _resolve_config_data(
        self,
        config_yaml_file: Optional[str],
        data_assurance_policies: Optional[List[Any]],
        content_filter_policies: Optional[List[Any]],
    ) -> Dict[str, Any]:
        """
        Build the effective config dict from the (optional) YAML config file and the
        (optional) directly-provided module parameters.

        The config file is rendered first (when given), then the module-parameter policy
        lists are overlaid on top of it, keyed by policy ``name``: a supplied field
        overrides the config-file value for that field, and a policy not present in the
        file is appended. This lets a playbook keep a config file as the base and override
        (or add) individual policies/fields directly through module parameters.
        """
        config_data: Dict[str, Any] = {}
        if config_yaml_file:
            config_data = dict(self.render_config_file(config_yaml_file) or {})

        if data_assurance_policies:
            config_data[_YAML_KEY] = self._merge_policies(config_data.get(_YAML_KEY) or [], data_assurance_policies)
        if content_filter_policies:
            config_data[_CF_YAML_KEY] = self._merge_policies(
                config_data.get(_CF_YAML_KEY) or [], content_filter_policies
            )
        return config_data

    @classmethod
    def _merge_policies(cls, base_policies: List[Any], override_policies: List[Any]) -> List[Any]:
        """
        Overlay ``override_policies`` (from module parameters) onto ``base_policies``
        (from the config file), keyed by policy ``name``.

        For a policy present in both, the override's fields are merged in (override wins per
        field); a policy only in the override list is appended. ``None`` values in the override
        (Ansible fills unset sub-options with ``None``) are pruned first so they neither clobber
        config-file values nor leak nulls into the API payload.
        """
        merged: List[Any] = []
        index: Dict[str, Dict[str, Any]] = {}
        for policy in base_policies:
            entry = dict(policy) if isinstance(policy, dict) else policy
            merged.append(entry)
            if isinstance(entry, dict) and entry.get("name"):
                index[entry["name"]] = entry

        for policy in override_policies or []:
            if not isinstance(policy, dict):
                continue
            clean = cls._prune_none(policy)
            if not clean:
                continue
            name = clean.get("name")
            if name and name in index:
                index[name].update(clean)
            else:
                merged.append(clean)
                if name:
                    index[name] = clean
        return merged

    @classmethod
    def _prune_none(cls, value: Any) -> Any:
        """Recursively drop ``None`` values from dicts (and dicts nested in lists).

        Module sub-options that the user did not set arrive as ``None``; removing them makes a
        directly-supplied policy match the shape of a config-file policy, where absent fields
        are simply omitted.
        """
        if isinstance(value, dict):
            return {k: cls._prune_none(v) for k, v in value.items() if v is not None}
        if isinstance(value, list):
            return [cls._prune_none(v) for v in value]
        return value

    def _validate_and_autofill_apps(
        self,
        policy_cfg: Dict,
        bucket_apps_cache: Dict[str, Dict[str, Dict[str, Any]]],
        bucket_app_servers_cache: Dict[str, List[Dict[str, Any]]],
        current_config: Any = None,
    ) -> None:
        """
        Validate each app ``name`` against the apps in its profile's bucket and auto-fill the
        app hint fields (``isDomain`` / ``builtinAppId`` / ``customAppId``) and its back-end
        ``servers`` from bucket telemetry.

        The bucket enum name is taken from the app's ``profileName`` (or reverse-mapped from a
        raw integer ``bucketId``) and passed to the bucket-apps telemetry API. Results are
        cached (apps per bucket, servers per bucket+app) for the duration of a configure run.

        Notes:
            - User-provided fields always take precedence; auto-fill only sets a field (hint or
              ``servers``) that is absent/empty.
            - ``servers`` are only filled when the API returns some; an app with no server
              telemetry is left as-is (its ``name`` is already validated above).
            - Update path: when ``current_config`` is given (existing policy) and an app is already
              present in it, the stored servers/hints are reused for fields the user did not set,
              and the telemetry lookup is skipped. This keeps re-runs idempotent (telemetry is
              time-windowed and can drift) and avoids failing a no-op update on an empty window.
              Only genuinely new apps are validated and auto-filled from telemetry.

        Raises:
            ConfigurationError: when a new app's profile bucket returns no apps, or returns apps
                but the app ``name`` is not among them.
        """
        apps = policy_cfg.get("apps")
        if not apps:
            return
        policy_name = policy_cfg.get("name", "")
        stored_apps = self._index_stored_apps(current_config)

        for app in apps:
            if not isinstance(app, dict):
                continue
            app_name = app.get("name")
            if not app_name:
                continue

            # Existing app on an update: reuse stored servers/hints, skip telemetry.
            if app_name in stored_apps:
                self._reuse_stored_app(app, stored_apps[app_name], policy_name)
                continue

            bucket_name = self._app_bucket_name(app)
            if not bucket_name:
                continue

            bucket_apps = self._get_bucket_apps_cached(bucket_name, bucket_apps_cache)
            if not bucket_apps:
                raise ConfigurationError(
                    f"Policy '{policy_name}', app '{app_name}': profile '{bucket_name}' "
                    "returned no apps over the query window, so the app name cannot be "
                    "validated. Verify the profileName/bucketId is correct and that the "
                    "profile has recent application telemetry."
                )

            match = bucket_apps.get(app_name)
            if match is None:
                raise ConfigurationError(
                    f"Policy '{policy_name}', app '{app_name}': not found in profile "
                    f"'{bucket_name}'. Available apps: {sorted(bucket_apps.keys())}"
                )

            # The hint fields are a proto oneof — only one is meaningful per app, and only
            # when truthy (is_domain=True, or a non-zero app id). Auto-filling a falsy hint
            # (isDomain=False, id=0) would add noise the portal won't echo back and cause
            # spurious idempotency diffs, so only fill truthy values the user did not set.
            for cfg_key, src_key in (
                ("isDomain", "is_domain"),
                ("builtinAppId", "builtin_app_id"),
                ("customAppId", "custom_app_id"),
            ):
                if app.get(cfg_key) is None and match.get(src_key):
                    app[cfg_key] = match[src_key]
                    LOG.info(
                        "%s Policy '%s', app '%s': auto-filled %s=%s from profile '%s'",
                        _LOG_PREFIX,
                        policy_name,
                        app_name,
                        cfg_key,
                        match[src_key],
                        bucket_name,
                    )

            # Auto-fill the app's back-end servers from bucket telemetry when the user did not
            # provide any. User-supplied servers always take precedence.
            if not app.get("servers"):
                servers = self._get_bucket_app_servers(bucket_name, app_name, bucket_app_servers_cache)
                if servers:
                    app["servers"] = servers
                    LOG.info(
                        "%s Policy '%s', app '%s': auto-filled %s server(s) from profile '%s'",
                        _LOG_PREFIX,
                        policy_name,
                        app_name,
                        len(servers),
                        bucket_name,
                    )

    @staticmethod
    def _index_stored_apps(current_config: Any) -> Dict[str, Dict[str, Any]]:
        """
        Index the apps of an existing policy config by app name (camelCase dict form).

        Returns an empty mapping when there is no current config (create path).
        """
        if current_config is None:
            return {}
        cfg = current_config.to_dict() if hasattr(current_config, "to_dict") else current_config
        indexed: Dict[str, Dict[str, Any]] = {}
        for app in (cfg.get("apps") if isinstance(cfg, dict) else None) or []:
            name = app.get("app_name") if app.get("app_name") is not None else app.get("name")
            if name:
                indexed[name] = app
        return indexed

    @staticmethod
    def _reuse_stored_app(app: Dict, stored: Dict[str, Any], policy_name: str) -> None:
        """
        On update, reuse the stored ``servers`` / hint fields for an already-configured app,
        for any field the user did not set explicitly. Avoids re-deriving from time-windowed
        telemetry (which would churn updates) and skips re-validation of an existing app.
        """
        for key in ("isDomain", "builtinAppId", "customAppId"):
            if app.get(key) is None and stored.get(key) is not None:
                app[key] = stored[key]
        if not app.get("servers") and stored.get("servers"):
            app["servers"] = stored["servers"]
        LOG.info(
            "%s Policy '%s', app '%s': existing app — reused stored servers/hints (telemetry skipped)",
            _LOG_PREFIX,
            policy_name,
            app.get("name"),
        )

    @staticmethod
    def _app_bucket_name(app: Dict) -> Optional[str]:
        """
        Resolve an app entry to its AssuranceBucket enum name (what the bucket-apps API expects).

        Prefers ``profileName`` (already the enum name); otherwise reverse-maps a raw integer
        ``bucketId`` via ``_BUCKET_ID_TO_PROFILE``. Returns None when neither is resolvable.
        """
        profile_name = app.get("profileName")
        if profile_name:
            return profile_name
        bucket_id = app.get("bucketId")
        if isinstance(bucket_id, int):
            return _BUCKET_ID_TO_PROFILE.get(bucket_id)
        return None

    def _get_bucket_apps_cached(
        self, bucket_name: str, cache: Dict[str, Dict[str, Dict[str, Any]]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch (and cache) the apps for a bucket, indexed by ``app_name``.

        Each indexed value holds the hint fields (``is_domain``, ``builtin_app_id``,
        ``custom_app_id``) used for auto-fill.
        """
        if bucket_name in cache:
            return cache[bucket_name]

        entries = self.gsdk.get_data_assurance_bucket_apps(bucket_name, self._default_time_window())
        indexed: Dict[str, Dict[str, Any]] = {}
        for entry in entries:
            entry_name = self._bucket_app_field(entry, "app_name", "appName")
            if not entry_name:
                continue
            indexed[entry_name] = {
                "is_domain": self._bucket_app_field(entry, "is_domain", "isDomain"),
                "builtin_app_id": self._bucket_app_field(entry, "builtin_app_id", "builtinAppId"),
                "custom_app_id": self._bucket_app_field(entry, "custom_app_id", "customAppId"),
            }

        LOG.info("%s Bucket '%s' apps available: %s", _LOG_PREFIX, bucket_name, sorted(indexed.keys()))
        cache[bucket_name] = indexed
        return indexed

    def _get_bucket_app_servers(
        self, bucket_name: str, app_name: str, cache: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Fetch (and cache) the back-end servers observed for an app in a bucket, normalized to
        the config ``servers`` shape (``{ip, port, protocol}``).

        ``server_port`` comes from telemetry as a string but the config API expects an integer,
        so it is coerced to int when numeric (kept as-is otherwise).
        """
        cache_key = f"{bucket_name}\x00{app_name}"
        if cache_key in cache:
            return cache[cache_key]

        entries = self.gsdk.get_data_assurance_bucket_app_servers(bucket_name, app_name, self._default_time_window())
        servers: List[Dict[str, Any]] = []
        for entry in entries:
            ip = self._bucket_app_field(entry, "server_ip", "serverIp")
            port = self._bucket_app_field(entry, "server_port", "serverPort")
            protocol = self._bucket_app_field(entry, "server_protocol", "serverProtocol")
            server: Dict[str, Any] = {}
            if ip is not None:
                server["ip"] = ip
            if port is not None:
                server["port"] = int(port) if isinstance(port, str) and port.isdigit() else port
            if protocol is not None:
                server["protocol"] = protocol
            if server:
                servers.append(server)

        cache[cache_key] = servers
        return servers

    @staticmethod
    def _bucket_app_field(entry: Any, snake_key: str, camel_key: str) -> Any:
        """Read a bucket-app field from an SDK object (snake_case) or a dict (either case)."""
        if isinstance(entry, dict):
            value = entry.get(snake_key)
            return value if value is not None else entry.get(camel_key)
        return getattr(entry, snake_key, None)

    @staticmethod
    def _default_time_window() -> Dict[str, Any]:
        """
        Build the bucket-apps telemetry time window (mirrors the portal UI: a
        ``_BUCKET_APPS_WINDOW_DAYS``-day window in ``_BUCKET_APPS_BUCKET_SIZE_SEC`` buckets).
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_ts = int(now.timestamp())
        old_ts = int((now - datetime.timedelta(days=_BUCKET_APPS_WINDOW_DAYS)).timestamp())
        return {
            "recentTs": {"seconds": recent_ts, "nanos": 0},
            "oldTs": {"seconds": old_ts, "nanos": 0},
            "bucketSizeSec": _BUCKET_APPS_BUCKET_SIZE_SEC,
        }

    def _fetch_valid_flex_algos(self) -> Dict[str, Any]:
        """
        Fetch all flex-algo entries once and return a name → entry mapping.
        Block/protection policies skip flex-algo validation (empty flexAlgo),
        so this is called once per configure run rather than per-policy.
        """
        entries = self.gsdk.get_data_assurance_flex_algos()
        valid: Dict[str, Any] = {}
        for entry in entries:
            entry_name = entry.get("name") if isinstance(entry, dict) else getattr(entry, "name", None)
            if entry_name:
                valid[entry_name] = entry
        LOG.info("%s Available flex-algos: %s", _LOG_PREFIX, list(valid.keys()))
        return valid

    @staticmethod
    def _validate_flex_algo(flex_algo: Optional[str], policy_name: str, valid_flex_algos: Dict[str, Any]) -> None:
        """
        Validate that ``flex_algo`` exists in the enterprise.
        Skips validation when ``flex_algo`` is empty or None (block/protection policies).

        Raises:
            ConfigurationError: when the name is non-empty but not in ``valid_flex_algos``.
        """
        if not flex_algo:
            return
        if flex_algo not in valid_flex_algos:
            raise ConfigurationError(
                f"Policy '{policy_name}': flexAlgo '{flex_algo}' does not exist in this enterprise. "
                f"Available flex-algos: {sorted(valid_flex_algos.keys())}"
            )
        LOG.info("%s flexAlgo '%s' validated for policy '%s'", _LOG_PREFIX, flex_algo, policy_name)

    def _fetch_valid_lan_segments(self) -> Dict[str, Any]:
        """
        Fetch all global LAN segments once and return a name → id mapping.
        Policies without ``lanNames`` skip this validation, so this is called once
        per configure run rather than per-policy.
        """
        valid = self.gsdk.get_lan_segments_dict()
        LOG.info("%s Available LAN segments: %s", _LOG_PREFIX, list(valid.keys()))
        return valid

    @staticmethod
    def _validate_lan_names(
        lan_names: Optional[List[str]], policy_name: str, valid_lan_segments: Dict[str, Any]
    ) -> None:
        """
        Validate that each name in ``lan_names`` exists in the enterprise.
        Skips validation when ``lan_names`` is empty or None (applies to all segments).

        Raises:
            ConfigurationError: when any name is not in ``valid_lan_segments``.
        """
        if not lan_names:
            return
        missing = [name for name in lan_names if name not in valid_lan_segments]
        if missing:
            raise ConfigurationError(
                f"Policy '{policy_name}': lanNames {missing} do not exist in this enterprise. "
                f"Available LAN segments: {sorted(valid_lan_segments.keys())}"
            )
        LOG.info("%s lanNames %s validated for policy '%s'", _LOG_PREFIX, lan_names, policy_name)

    def _resolve_site_list(self, policy_cfg: Dict) -> Optional[int]:
        """
        Resolve ``siteListName`` (user-facing YAML key) to a ``siteListId`` integer,
        validate the site list exists, and return the ID.

        Returns None when neither ``siteListName`` nor ``siteListId`` is specified
        (i.e. ``useAllSites: true`` is the scoping mechanism instead).

        Raises:
            ConfigurationError: when ``siteListName`` is provided but not found.
        """
        site_list_name = policy_cfg.get("siteListName")
        if site_list_name:
            site_list_id = self.gsdk.get_site_list_id(site_list_name)
            if site_list_id is None:
                raise ConfigurationError(
                    f"Site list '{site_list_name}' not found in this enterprise. "
                    "Verify the name matches a site list in the Graphiant portal."
                )
            LOG.info("%s Resolved siteListName '%s' → siteListId %s", _LOG_PREFIX, site_list_name, site_list_id)
            return site_list_id
        # Fall back to an explicit siteListId if already provided as an integer
        return policy_cfg.get("siteListId")

    @classmethod
    def _index_by_name(cls, rows: List[Any]) -> Dict[str, Any]:
        """Build a name → row lookup, skipping rows whose name cannot be resolved."""
        indexed: Dict[str, Any] = {}
        for row in rows:
            name = cls._row_name(row)
            if name is not None:
                indexed[name] = row
        return indexed

    @staticmethod
    def _row_name(row: Any) -> Optional[str]:
        if isinstance(row, dict):
            return row.get("assuranceName")
        return getattr(row, "assurance_name", None) or getattr(row, "assuranceName", None)

    @staticmethod
    def _row_id(row: Any) -> Optional[int]:
        if isinstance(row, dict):
            return row.get("assuranceId")
        return getattr(row, "assurance_id", None) or getattr(row, "assuranceId", None)

    def _fetch_domain_categories(self) -> Dict[str, int]:
        """
        Fetch all domain categories once and return a name → id mapping, used to resolve the
        category names in ContentFilterPolicies to ``domainCategoryId`` values.
        """
        entries = self.gsdk.get_domain_categories()
        mapping: Dict[str, int] = {}
        for entry in entries:
            if isinstance(entry, dict):
                name, cat_id = entry.get("name"), entry.get("id")
            else:
                name, cat_id = getattr(entry, "name", None), getattr(entry, "id", None)
            if name is not None and cat_id is not None:
                mapping[name] = cat_id
        LOG.info("%s Available domain categories: %s", _LOG_PREFIX, sorted(mapping.keys()))
        return mapping

    @classmethod
    def _index_cf_by_name(cls, rows: List[Any]) -> Dict[str, Any]:
        """Build a name → content-filter row lookup, skipping rows with no resolvable name."""
        indexed: Dict[str, Any] = {}
        for row in rows:
            name = cls._cf_row_name(row)
            if name is not None:
                indexed[name] = row
        return indexed

    @staticmethod
    def _cf_row_name(row: Any) -> Optional[str]:
        if isinstance(row, dict):
            return row.get("globalContentFilterName")
        return getattr(row, "global_content_filter_name", None) or getattr(row, "globalContentFilterName", None)

    @staticmethod
    def _cf_row_id(row: Any) -> Optional[int]:
        if isinstance(row, dict):
            return row.get("globalContentFilterId")
        return getattr(row, "global_content_filter_id", None) or getattr(row, "globalContentFilterId", None)
