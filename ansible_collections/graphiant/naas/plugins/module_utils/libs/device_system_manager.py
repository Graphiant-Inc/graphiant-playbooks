"""
Device System Manager for Graphiant Playbooks.

Manages ``name``, ``regionName``, and ``site`` on the Edge or Core branch of
``PUT /v1/devices/{device_id}/config``.

YAML uses the same list-of-single-key-dicts pattern as ``device_config`` (see ``_load_device_system``).
Config is loaded with ``render_config_file`` (Jinja2 in YAML supported by ``ConfigUtils``).

Idempotency: after ``GET /v1/devices/{id}`` (``get_device_info``), merge desired keys onto the
effective current system state and compare before ``PUT``. That state is derived from the device
object (not only nested ``edge``/``core``): ``hostname`` → ``name``, ``regionOverride.name`` if set
else ``region.name`` → ``regionName``, and ``site.name`` → ``site``. Branch choice follows portal
``role`` (``core`` → ``core``, ``cpe`` → ``edge``) when ``device_type`` is omitted in YAML or params.
Deconfigure is not supported.
"""

from typing import Any, Dict, Iterator, List, Optional, Tuple

from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()

_LOG_PREFIX = "[device-system]"
_YAML_KEY = "device_system"
_ALLOWED = frozenset({"device_type", "name", "regionName", "site"})
_UPDATE_KEYS = ("name", "regionName", "site")


class DeviceSystemManager(BaseManager):
    """Manage device ``name``, ``regionName``, and ``site`` via the device config API."""

    @staticmethod
    def _str(val: Any) -> str:
        return "" if val is None else str(val).strip()

    @staticmethod
    def _to_dict(obj: Any) -> Dict[str, Any]:
        if obj is None:
            return {}
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "to_dict"):
            try:
                d = obj.to_dict()
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _unwrap_device(root: Dict[str, Any]) -> Dict[str, Any]:
        inner = root.get("device")
        return inner if isinstance(inner, dict) else root

    @staticmethod
    def _as_dict(block: Any) -> Dict[str, Any]:
        if block is None:
            return {}
        if isinstance(block, dict):
            return block
        if hasattr(block, "to_dict"):
            try:
                d = block.to_dict()
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}
        return {}

    @classmethod
    def _site_name(cls, branch: Dict[str, Any]) -> str:
        site = cls._as_dict(branch.get("site"))
        return cls._str(site.get("name"))

    @classmethod
    def _branch_tuple(cls, branch: Dict[str, Any]) -> Tuple[str, str, str]:
        b = cls._as_dict(branch)
        return (cls._str(b.get("name")), cls._str(b.get("regionName")), cls._site_name(b))

    @classmethod
    def _region_display_name_from_device(cls, d: Dict[str, Any]) -> str:
        """Effective region display string: ``regionOverride.name`` when set, else ``region.name``."""
        ro = d.get("regionOverride")
        if ro is not None:
            nm = cls._str(cls._as_dict(ro).get("name"))
            if nm:
                return nm
        return cls._str(cls._as_dict(d.get("region")).get("name"))

    def _system_branch_from_device_get(
        self, d: Dict[str, Any], branch_key: str, nested_branch: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Map ``GET /v1/devices/{id}`` device fields to the same shape as ``edge``/``core`` config.

        Portal uses ``hostname`` and top-level ``region`` / ``regionOverride`` / ``site``; the
        config branch uses ``name``, ``regionName``, ``site``. Falls back to nested ``branch_key``
        when a top-level field is absent (e.g. older responses).
        """
        out: Dict[str, Any] = {}
        nm = self._str(d.get("hostname"))
        if not nm:
            nm = self._str(nested_branch.get("name"))
        if nm:
            out["name"] = nm

        rn = self._region_display_name_from_device(d)
        if not rn:
            rn = self._str(nested_branch.get("regionName"))
        if rn:
            out["regionName"] = rn

        site = self._as_dict(d.get("site"))
        sn = self._str(site.get("name"))
        if sn:
            out["site"] = {"name": sn}
        elif nested_branch.get("site") is not None:
            parsed = self._parse_site(nested_branch.get("site"))
            if parsed:
                out["site"] = parsed
        return out

    def _parse_site(self, site_val: Any) -> Optional[Dict[str, str]]:
        if site_val is None:
            return None
        if not isinstance(site_val, dict):
            raise ConfigurationError("'site' must be a dict with a 'name' field, or null/omit.")
        nm = self._str(site_val.get("name"))
        if not nm:
            return None
        return {"name": nm}

    def _merge_branch(self, current: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(self._as_dict(current))
        if "name" in updates:
            out["name"] = self._str(updates["name"])
        if "regionName" in updates:
            out["regionName"] = self._str(updates["regionName"])
        if "site" in updates:
            site_val = updates["site"]
            if site_val is not None:
                parsed = self._parse_site(site_val)
                if parsed is not None:
                    out["site"] = parsed
                # Empty dict, missing name, or comment-only YAML under site: — leave existing site
        return out

    def _build_payload(self, dtype: str, branch: Dict[str, Any]) -> Dict[str, Any]:
        b = self._as_dict(branch)
        body: Dict[str, Any] = {"name": self._str(b.get("name")), "regionName": self._str(b.get("regionName"))}
        sn = self._site_name(b)
        if sn:
            body["site"] = {"name": sn}
        return {"core": body} if dtype == "core" else {"edge": body}

    @staticmethod
    def _normalized_device_type(raw: Any) -> Optional[str]:
        """Return ``edge`` or ``core`` when set; ``None`` when absent (infer from API ``role`` later)."""
        if raw is None or DeviceSystemManager._str(raw) == "":
            return None
        dt = DeviceSystemManager._str(raw).lower()
        if dt not in ("edge", "core"):
            raise ConfigurationError("'device_type' must be 'edge' or 'core'.")
        return dt

    @classmethod
    def _dtype_from_device_role(cls, role: Any) -> Optional[str]:
        """
        Map portal device ``role`` from ``GET /v1/devices/{id}`` to config branch.

        ``core`` → ``core`` payload branch; ``cpe`` (edge/CPE) → ``edge`` branch.
        """
        r = cls._str(role).lower()
        if r == "core":
            return "core"
        if r == "cpe":
            return "edge"
        return None

    def _resolve_device_type(self, device_name: str, device_dict: Dict[str, Any], cfg: Dict[str, Any]) -> str:
        """
        Choose ``edge`` vs ``core`` using device ``role`` when ``device_type`` is not in config.

        If ``device_type`` is set, it must match the role-derived value.
        """
        inferred = self._dtype_from_device_role(device_dict.get("role"))
        declared = self._normalized_device_type(cfg.get("device_type"))

        if inferred is not None:
            if declared is not None and declared != inferred:
                raise ConfigurationError(
                    f"Device '{device_name}' has portal role {device_dict.get('role')!r} "
                    f"(config branch '{inferred}'), but device_type '{declared}' was specified. "
                    f"Omit device_type or set it to '{inferred}'."
                )
            return inferred

        if declared is not None:
            LOG.warning(
                "%s Device '%s' role=%r is not 'core' or 'cpe'; using explicit device_type=%s",
                _LOG_PREFIX,
                device_name,
                device_dict.get("role"),
                declared,
            )
            return declared

        raise ConfigurationError(
            f"Device '{device_name}': cannot infer edge vs core from role={device_dict.get('role')!r} "
            f"(expected 'core' or 'cpe'). Set device_type to 'edge' or 'core' in YAML or module params."
        )

    def _validate_cfg(self, device_name: str, cfg: Any) -> Dict[str, Any]:
        if not isinstance(cfg, dict):
            raise ConfigurationError(f"Device '{device_name}' config must be a dict")
        bad = set(cfg) - _ALLOWED
        if bad:
            raise ConfigurationError(
                f"Device '{device_name}' has unknown keys: {sorted(bad)}. Allowed: {sorted(_ALLOWED)}"
            )
        out = dict(cfg)
        dt = self._normalized_device_type(out.pop("device_type", None))
        if dt is not None:
            out["device_type"] = dt
        if out.get("site") is not None:
            self._parse_site(out["site"])
        return out

    def _load_device_system(
        self, config_yaml_file: Optional[str], module_params: Optional[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Load ``device_system`` from YAML (via ``render_config_file``) and/or module params.

        Same structural idea as ``DeviceConfigManager._load_device_configs``: list of
        ``{portal_device_name: settings}`` entries collapsed to one map.
        """
        path = self._str(config_yaml_file) or None
        cfg = self.render_config_file(path) or {} if path else {}

        raw = cfg.get(_YAML_KEY)
        by_name: Dict[str, Dict[str, Any]] = {}
        if raw is None:
            pass
        elif not isinstance(raw, list):
            raise ConfigurationError(f"'{_YAML_KEY}' must be a list of device entries")
        else:
            for entry in raw:
                if not isinstance(entry, dict) or not entry:
                    raise ConfigurationError(
                        f"Each entry in '{_YAML_KEY}' must be a non-empty dict keyed by portal device name"
                    )
                for dev, c in entry.items():
                    by_name[dev] = c if isinstance(c, dict) else {}

        mp = module_params or {}
        portal = self._str(mp.get("device"))
        if not path and not portal:
            raise ConfigurationError("Provide system_config_file and/or device (portal device name).")

        if not path:
            row: Dict[str, Any] = {}
            if mp.get("device_type") is not None:
                row["device_type"] = mp["device_type"]
            for k in _UPDATE_KEYS:
                if mp.get(k) is not None:
                    row[k] = mp[k]
            by_name[portal] = row

        target = self._str(mp.get("device"))
        ov: Dict[str, Any] = {}
        if mp.get("device_type") is not None:
            ov["device_type"] = mp["device_type"]
        for k in _UPDATE_KEYS:
            if mp.get(k) is not None:
                ov[k] = mp[k]
        if target and ov:
            if target in by_name:
                merged = dict(by_name[target])
                merged.update(ov)
                by_name[target] = merged
            else:
                by_name[target] = dict(ov)

        return {name: self._validate_cfg(name, c) for name, c in by_name.items()}

    def _device_not_found_msg(self, device_name: str) -> str:
        return (
            f"Device '{device_name}' is not found in the current enterprise: "
            f"{self.gsdk.enterprise_info['company_name']}. Please check device name."
        )

    def _site_in_payload(self, payload: Dict[str, Any], branch_key: str) -> bool:
        b = self._as_dict((payload or {}).get(branch_key))
        return bool(self._site_name(b))

    def _iter_payloads(
        self, by_name: Dict[str, Dict[str, Any]]
    ) -> Iterator[Tuple[int, str, str, Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
        """Yield device_id, device_name, branch_key, payload, before_branch, after_branch (for --diff)."""
        for device_name, cfg in by_name.items():
            device_id = self.gsdk.get_device_id(device_name)
            if device_id is None:
                raise DeviceNotFoundError(self._device_not_found_msg(device_name))

            gcs = self.gsdk.get_device_info(device_id)
            if gcs is None:
                raise ConfigurationError(f"Failed to retrieve device info for device_id={device_id}")

            try:
                info_dict = gcs.to_dict()
            except Exception:
                info_dict = gcs

            d = self._unwrap_device(self._to_dict(info_dict))
            dtype = self._resolve_device_type(device_name, d, cfg)
            branch_key = "core" if dtype == "core" else "edge"

            nested = self._as_dict(d.get(branch_key))
            current = self._system_branch_from_device_get(d, branch_key, nested)
            updates = {k: cfg[k] for k in _UPDATE_KEYS if k in cfg}
            merged = self._merge_branch(current, updates)
            payload = self._build_payload(dtype, merged)
            # Full merged branch for diff (matches idempotency tuple); PUT body may omit unchanged keys
            after_branch = {k: merged[k] for k in ("name", "regionName", "site") if k in merged}
            site_nm = self._site_name(after_branch)
            if site_nm:
                self.get_site_id(site_nm)

            before_branch = dict(self._as_dict(current))
            yield device_id, device_name, branch_key, payload, before_branch, after_branch

    def apply_device_system(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> dict:
        by_name = self._load_device_system(config_yaml_file, module_params)
        if not by_name:
            LOG.info("%s No '%s' entries to process", _LOG_PREFIX, _YAML_KEY)
            return {
                "changed": False,
                "configured_devices": [],
                "skipped_devices": [],
                "diff_plan": [],
                "skipped_no_site": [],
                "aborted_pushes_due_to_no_site": False,
                "would_configure_devices": [],
                "no_input": True,
            }

        result: Dict[str, Any] = {
            "changed": False,
            "configured_devices": [],
            "skipped_devices": [],
            "diff_plan": [],
            "skipped_no_site": [],
            "aborted_pushes_due_to_no_site": False,
            "would_configure_devices": [],
        }
        to_push: Dict[int, Dict[str, Any]] = {}
        configured: List[str] = []
        diff_plan: List[Dict[str, Any]] = []

        for device_id, device_name, branch_key, payload, before_b, after_b in self._iter_payloads(by_name):
            if self._branch_tuple(after_b) == self._branch_tuple(before_b):
                LOG.info("%s ✓ No changes needed for %s (ID: %s), skipping", _LOG_PREFIX, device_name, device_id)
                result["skipped_devices"].append(device_name)
                continue

            # API rejects put_device_config when the device has no site in the portal and the
            # payload also omits site (see portal error: Site name not set on device).
            if not self._site_name(before_b) and not self._site_in_payload(payload, branch_key):
                LOG.warning(
                    "%s Not pushing config for %s (ID: %s): no site on device from GET and desired "
                    "edge/core payload has no site; set site: {name: ...} in YAML or assign a site in the portal first",
                    _LOG_PREFIX,
                    device_name,
                    device_id,
                )
                result["skipped_no_site"].append(device_name)
                continue

            to_push[device_id] = {"device_id": device_id, "payload": payload}
            configured.append(device_name)
            diff_plan.append({"device": device_name, "branch": branch_key, "before": before_b, "after": after_b})

        if result["skipped_no_site"] and to_push:
            # Do not apply other devices in this run; module will fail so the play does not
            # succeed on a partial/ambiguous batch.
            would = list(configured)
            LOG.error(
                "%s Aborting %d pending config push(es) for: %s — first resolve device(s) with no "
                "site in the portal and no site in the desired config: %s",
                _LOG_PREFIX,
                len(would),
                would,
                result["skipped_no_site"],
            )
            to_push = {}
            configured = []
            diff_plan = []
            result["aborted_pushes_due_to_no_site"] = True
            result["would_configure_devices"] = would

        if not to_push:
            return result

        LOG.info("%s Pushing payload for %d device(s)...", _LOG_PREFIX, len(to_push))
        self.execute_concurrent_tasks(self.gsdk.put_device_config_raw, to_push)
        result["changed"] = True
        result["configured_devices"] = configured
        result["diff_plan"] = diff_plan
        return result

    def configure(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> dict:
        return self.apply_device_system(config_yaml_file=config_yaml_file, module_params=module_params)

    def deconfigure(self, config_yaml_file: str) -> dict:
        raise ConfigurationError(
            "Deconfigure is not supported for device system settings. "
            "Use configure with the desired name, regionName, and site values."
        )
