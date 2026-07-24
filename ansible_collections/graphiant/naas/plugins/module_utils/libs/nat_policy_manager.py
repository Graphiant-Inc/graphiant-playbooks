"""
NAT Policy Manager for Graphiant Playbooks.

Manages device-level NAT policy objects under:
  edge.natPolicy.natRulesets
- Build raw device-config payload in Python from a structured YAML file
- Idempotency: compare intended rulesets to current device state; skip push when already matched
- Check mode: read device state, skip writes, accurate ``changed``; ``diff_plan`` for ``--diff``
- Deconfigure: delete only the rulesets listed in the YAML by setting ruleset=null per key
- Per-object state in YAML: ruleset or rule ``state: absent`` sends ``ruleset: null`` or ``rule: null``

LAN segment association (per-segment NAT ruleset reference):
  edge.segments.<segment>.natRuleset.ruleset -> ruleset name (string)
- attach_to_lan_segments / detach_from_lan_segments with optional ``segments`` in YAML
- Configure workflow: ``configure`` (rulesets) then ``attach_to_lan_segments`` (segments)
- Deconfigure workflow: ``detach_from_lan_segments`` (segments) then ``deconfigure`` (rulesets)
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple

from .base_manager import BaseManager
from .device_config_common import (
    as_dict,
    fetch_device_by_name,
    load_device_list_yaml_config,
    new_apply_result,
    push_device_config_raw,
    unwrap_device,
)
from .logger import setup_logger
from .exceptions import ConfigurationError

LOG = setup_logger()

NAT_POLICY_KEYS = ("natPolicy", "nat_policy")
NAT_RULESETS_KEYS = ("natRulesets", "nat_rulesets", "natPolicyRulesets", "nat_policy_rulesets")
NAT_RULESET_KEYS = ("natRuleset", "nat_ruleset")
RULESET_REF_KEYS = ("ruleset", "name", "rulesetName", "ruleset_name", "id")
_STATE_CHOICES = frozenset({"present", "absent"})
_LOG_PREFIX = "[nat-policy]"
_YAML_KEY = "natPolicyObject"


class NatPolicyManager(BaseManager):
    """
    Manage NAT policy rulesets and LAN-segment ruleset references via raw device-config payloads.
    """

    @classmethod
    def _device_dict(cls, device_info_dict: Any) -> Dict[str, Any]:
        return unwrap_device(as_dict(device_info_dict))

    @staticmethod
    def _validate_device_cfg(device_name: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(cfg, dict):
            raise ConfigurationError(f"Device '{device_name}' config must be a dict")
        return cfg

    @staticmethod
    def _row_from_params(mp: Dict[str, Any]) -> Dict[str, Any]:
        row: Dict[str, Any] = {}
        for key in ("natRulesets", "segments"):
            if mp.get(key) is not None:
                row[key] = mp[key]
        return row

    def _load_devices(
        self,
        config_yaml_file: Optional[str],
        module_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        return load_device_list_yaml_config(
            _YAML_KEY,
            config_yaml_file,
            module_params,
            self.render_config_file,
            missing_input_error="nat_policy_config_file or module_params with 'device' is required.",
            build_row_from_params=self._row_from_params,
            validate_device_cfg=self._validate_device_cfg,
        )

    @staticmethod
    def _first_present(mapping: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
        if not isinstance(mapping, dict):
            return None
        for key in keys:
            if key in mapping:
                return mapping.get(key)
        return None

    @classmethod
    def _normalize(cls, obj: Any) -> Any:
        if obj is None:
            return None
        if hasattr(obj, "to_dict"):
            try:
                return cls._normalize(obj.to_dict())
            except Exception:  # nosec B110
                pass
        if isinstance(obj, dict):
            return {str(k): cls._normalize(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
        if isinstance(obj, list):
            return [cls._normalize(v) for v in obj]
        if isinstance(obj, (str, int, float, bool)):
            return obj
        return str(obj)

    @classmethod
    def _is_effectively_null(cls, obj: Any) -> bool:
        if obj is None:
            return True
        if isinstance(obj, dict):
            return all(cls._is_effectively_null(v) for v in obj.values())
        return False

    @classmethod
    def _desired_matches_existing(cls, desired: Any, existing: Any) -> bool:
        if isinstance(desired, dict):
            if not isinstance(existing, dict):
                if cls._is_effectively_null(desired) and existing is None:
                    return True
                return False
            for key, desired_value in desired.items():
                existing_value = existing.get(key)
                if existing_value is None and key not in existing:
                    if cls._is_effectively_null(desired_value):
                        continue
                    return False
                if not cls._desired_matches_existing(desired_value, existing_value):
                    return False
            return True
        if isinstance(desired, list):
            return cls._normalize(desired) == cls._normalize(existing)
        return cls._normalize(desired) == cls._normalize(existing)

    @classmethod
    def _normalized_state(cls, value: Any, *, context: str) -> str:
        if value is None:
            return "present"
        state = str(value).strip().lower()
        if state not in _STATE_CHOICES:
            raise ConfigurationError(f"{context}: 'state' must be 'present' or 'absent'")
        return state

    @staticmethod
    def _coerce_ruleset_ref(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, dict):
            for key in RULESET_REF_KEYS:
                if key in value:
                    ref = value[key]
                    if ref is not None:
                        return str(ref).strip() or None
            return None
        ref = str(value).strip()
        return None if not ref or ref.lower() in ("none", "null") else ref

    @staticmethod
    def _ruleset_name_from_entry(entry: Any) -> Optional[str]:
        if not isinstance(entry, dict):
            return None
        ruleset_body = entry.get("ruleset")
        if isinstance(ruleset_body, dict):
            name = NatPolicyManager._first_present(ruleset_body, RULESET_REF_KEYS)
        else:
            name = NatPolicyManager._first_present(entry, RULESET_REF_KEYS)
        return str(name).strip() if name else None

    @staticmethod
    def _coerce_existing_rules_map(rules: Any) -> Dict[str, Any]:
        if isinstance(rules, dict):
            return rules
        if not isinstance(rules, list):
            return {}
        out: Dict[str, Any] = {}
        for item in rules:
            if not isinstance(item, dict):
                continue
            rule_obj = item.get("rule") if isinstance(item.get("rule"), dict) else item
            seq = rule_obj.get("seq") if isinstance(rule_obj, dict) else None
            if seq is None:
                continue
            out[str(seq).strip()] = item if "rule" in item else {"rule": rule_obj}
        return out

    @classmethod
    def _coerce_existing_ruleset_body(cls, ruleset: Any, ruleset_name: str) -> Any:
        if not isinstance(ruleset, dict):
            return ruleset
        out = dict(ruleset)
        out.setdefault("name", ruleset_name)
        if "rules" in out:
            out["rules"] = cls._coerce_existing_rules_map(out.get("rules"))
        return out

    @staticmethod
    def _existing_ruleset_from_entry(existing_entry: Any) -> Any:
        if not isinstance(existing_entry, dict):
            return None
        if "ruleset" in existing_entry:
            return existing_entry.get("ruleset")
        if any(k in existing_entry for k in ("name", "rules")):
            return existing_entry
        return None

    @staticmethod
    def _existing_rule_from_entry(existing_entry: Any) -> Any:
        if not isinstance(existing_entry, dict):
            return None
        if "rule" in existing_entry:
            return existing_entry.get("rule")
        if any(k in existing_entry for k in ("seq", "type", "originalSrcIpPrefix")):
            return existing_entry
        return None

    @classmethod
    def _rules_from_yaml(cls, rules_cfg: Any) -> Dict[str, Any]:
        """
        Build the API rules map.

        YAML may use the raw API dict shape:
          "10": { rule: { seq: 10, type: OneToOne, ... } }

        or the simpler list shape:
          - seq: 10
            type: OneToOne
            ...

        Per-rule lifecycle (under ``configure``):
          - seq: 10
            state: absent
        sends ``{"10": {"rule": null}}`` (delete that rule only).
        """
        if rules_cfg is None:
            return {}

        if isinstance(rules_cfg, dict):
            out: Dict[str, Any] = {}
            for raw_key, raw_val in rules_cfg.items():
                key = str(raw_key).strip()
                if not key:
                    raise ConfigurationError("rules dict keys must be non-empty sequence numbers")
                if not isinstance(raw_val, dict):
                    raise ConfigurationError(f"rules['{key}'] must be a dict")
                entry = dict(raw_val)
                if entry.get("rule") is None and "rule" in entry:
                    out[key] = {"rule": None}
                    continue
                rule_obj = entry.get("rule") if "rule" in entry else entry
                if not isinstance(rule_obj, dict):
                    raise ConfigurationError(f"rules['{key}'] must be a dict")
                state = cls._normalized_state(entry.get("state") or rule_obj.get("state"), context=f"rule {key}")
                if state == "absent":
                    out[key] = {"rule": None}
                    continue
                cleaned_rule = {k: v for k, v in rule_obj.items() if k != "state"}
                out[key] = {"rule": cleaned_rule} if "rule" in entry else {"rule": cleaned_rule}
            return out

        if isinstance(rules_cfg, list):
            out = {}
            for entry in rules_cfg:
                if not isinstance(entry, dict):
                    raise ConfigurationError("rules list items must be dicts")
                rule_obj = entry.get("rule") if "rule" in entry else dict(entry)
                if not isinstance(rule_obj, dict):
                    raise ConfigurationError("rules list item 'rule' must be a dict")
                seq = rule_obj.get("seq")
                if seq is None:
                    raise ConfigurationError("rules list item missing 'seq'")
                key = str(seq).strip()
                state = cls._normalized_state(entry.get("state") or rule_obj.get("state"), context=f"rule seq {key}")
                if state == "absent":
                    out[key] = {"rule": None}
                    continue
                cleaned_rule = {k: v for k, v in rule_obj.items() if k != "state"}
                out[key] = {"rule": cleaned_rule}
            return out

        raise ConfigurationError("'rules' must be a dict or list")

    def _normalize_ruleset_body(self, ruleset: Any) -> Any:
        if not isinstance(ruleset, dict):
            return ruleset
        out = dict(ruleset)
        if "rules" in out:
            out["rules"] = self._rules_from_yaml(out.get("rules"))
        return out

    def _rulesets_from_yaml(self, nr_cfg: Any, operation: str) -> Dict[str, Any]:
        """
        Build the natRulesets map for the device-config API.

        Supported YAML shapes:
        - dict keyed by ruleset name -> ``{ruleset: {...}}`` or the inner ruleset body
        - list of dicts with ``name`` (configure) or list of strings / ``{name: ...}`` (deconfigure)
        """
        if nr_cfg is None:
            return {}

        if isinstance(nr_cfg, dict):
            out: Dict[str, Any] = {}
            for raw_key, v in nr_cfg.items():
                key = str(raw_key).strip()
                if not key:
                    raise ConfigurationError("natRulesets dict keys must be non-empty strings")
                if operation == "deconfigure":
                    out[key] = {"ruleset": None}
                    continue
                if not isinstance(v, dict):
                    raise ConfigurationError(f"natRulesets['{key}'] must be a dict")
                v = dict(v)
                rs_state = self._normalized_state(v.pop("state", None), context=f"ruleset '{key}'")
                if rs_state == "absent":
                    out[key] = {"ruleset": None}
                    continue
                ruleset_body = v.get("ruleset") if "ruleset" in v else v
                if not isinstance(ruleset_body, dict):
                    raise ConfigurationError(f"natRulesets['{key}'].ruleset must be a dict or null")
                normalized = self._normalize_ruleset_body(dict(ruleset_body))
                normalized.setdefault("name", key)
                out[key] = {"ruleset": normalized}
            return out

        if isinstance(nr_cfg, list):
            out = {}
            for entry in nr_cfg:
                if operation == "deconfigure":
                    if isinstance(entry, str):
                        k = entry.strip()
                        if k:
                            out[k] = {"ruleset": None}
                    elif isinstance(entry, dict):
                        n = entry.get("name")
                        if not n:
                            raise ConfigurationError("natRulesets list entry missing 'name' for deconfigure")
                        out[str(n).strip()] = {"ruleset": None}
                    else:
                        raise ConfigurationError("natRulesets list entries must be str or dict for deconfigure")
                    continue
                if not isinstance(entry, dict):
                    raise ConfigurationError("natRulesets list items must be dicts with a 'name' field")
                n = entry.get("name")
                if not n:
                    raise ConfigurationError("natRulesets list entry missing 'name'")
                name = str(n).strip()
                rs_state = self._normalized_state(entry.get("state"), context=f"ruleset '{name}'")
                if rs_state == "absent":
                    out[name] = {"ruleset": None}
                    continue
                body = {k: val for k, val in entry.items() if k not in ("name", "state")}
                normalized = self._normalize_ruleset_body({"name": name, **body})
                out[name] = {"ruleset": normalized}
            return out

        raise ConfigurationError("'natRulesets' must be a dict or list")

    def _extract_rulesets_from_device(self, device_info_dict: Any) -> Dict[str, Any]:
        d = self._device_dict(device_info_dict)
        edge = as_dict(d.get("edge"))
        for container in (edge, d):
            np_source = self._first_present(container, NAT_POLICY_KEYS)
            np = as_dict(np_source)
            rs = self._first_present(np, NAT_RULESETS_KEYS)
            if rs is not None:
                return self._coerce_rulesets_map(rs)
        return {}

    @staticmethod
    def _coerce_rulesets_map(rulesets: Any) -> Dict[str, Any]:
        if not rulesets:
            return {}
        if isinstance(rulesets, dict):
            mapped: Dict[str, Any] = dict(rulesets)
            for key, entry in rulesets.items():
                name = NatPolicyManager._ruleset_name_from_entry(entry)
                if name:
                    mapped.setdefault(name, entry)
                elif isinstance(key, str):
                    mapped.setdefault(key.strip(), entry)
            return mapped
        if isinstance(rulesets, list):
            out: Dict[str, Any] = {}
            for item in rulesets:
                if not isinstance(item, dict):
                    continue
                name = NatPolicyManager._ruleset_name_from_entry(item)
                if name:
                    out[str(name).strip()] = item
            return out
        return {}

    @staticmethod
    def _find_segment_object(device_dict: Dict[str, Any], seg_name: str) -> Optional[Dict[str, Any]]:
        if not isinstance(device_dict, dict):
            return None
        edge = device_dict.get("edge") or {}
        segments = None
        if isinstance(edge, dict):
            for key in ("segments", "lanSegments", "lan_segments"):
                if key in edge:
                    segments = edge.get(key)
                    break
        if segments is None:
            for key in ("segments", "lanSegments", "lan_segments"):
                if key in device_dict:
                    segments = device_dict.get(key)
                    break
        if isinstance(segments, dict):
            seg_obj = segments.get(seg_name)
            return seg_obj if isinstance(seg_obj, dict) else None
        if isinstance(segments, list):
            for item in segments:
                if isinstance(item, dict) and item.get("name") == seg_name:
                    return item
        return None

    @classmethod
    def _nat_ruleset_ref_from_segment(cls, seg_obj: Optional[Dict[str, Any]]) -> Optional[str]:
        if not seg_obj:
            return None
        nr = cls._first_present(seg_obj, NAT_RULESET_KEYS)
        if nr is not None:
            return cls._coerce_ruleset_ref(nr)
        return None

    @staticmethod
    def _ruleset_refs_match(desired_ref: Any, existing_ref: Optional[str]) -> bool:
        desired = str(desired_ref).strip()
        existing = (existing_ref or "").strip()
        return desired == existing or bool(desired and existing.endswith(f"-{desired}"))

    def _segments_payload_from_yaml(self, segments_cfg: Any, operation: str) -> Dict[str, Any]:
        if segments_cfg is None:
            return {}
        if not isinstance(segments_cfg, dict):
            raise ConfigurationError("'segments' must be a dict keyed by LAN segment name")

        out: Dict[str, Any] = {}
        for raw_seg, raw_val in segments_cfg.items():
            seg = str(raw_seg).strip()
            if not seg:
                raise ConfigurationError("segments dict keys must be non-empty segment names")

            if operation == "detach_from_lan_segments":
                out[seg] = {"natRuleset": {"ruleset": None}}
                continue

            if isinstance(raw_val, str):
                name = raw_val.strip()
                if not name:
                    raise ConfigurationError(f"segments['{seg}']: ruleset name must be non-empty")
                out[seg] = {"natRuleset": {"ruleset": name}}
            elif isinstance(raw_val, dict):
                val = dict(raw_val)
                seg_state = self._normalized_state(val.pop("state", None), context=f"segment '{seg}'")
                if seg_state == "absent":
                    out[seg] = {"natRuleset": {"ruleset": None}}
                elif "natRuleset" in val:
                    out[seg] = val
                elif "ruleset" in val:
                    out[seg] = {"natRuleset": val}
                else:
                    raise ConfigurationError(
                        f"segments['{seg}']: expected string ruleset name, "
                        f"or dict with 'natRuleset' / 'ruleset' / 'state' keys"
                    )
            else:
                raise ConfigurationError(f"segments['{seg}']: value must be a string or dict")

        return out

    def _nat_rulesets_need_update(self, desired_rs: Dict[str, Any], device_info_dict: Any) -> bool:
        existing_rs = self._extract_rulesets_from_device(device_info_dict)
        LOG.info("%s existing natRulesets keys: %s", _LOG_PREFIX, list(existing_rs.keys()))
        LOG.info("%s desired natRulesets keys: %s", _LOG_PREFIX, list(desired_rs.keys()))

        for rs_id, desired_entry in desired_rs.items():
            if not isinstance(desired_entry, dict):
                return True
            desired_ruleset = desired_entry.get("ruleset")
            existing_entry = existing_rs.get(rs_id) if isinstance(existing_rs, dict) else None
            existing_ruleset = self._existing_ruleset_from_entry(existing_entry)
            existing_ruleset = self._coerce_existing_ruleset_body(existing_ruleset, str(rs_id))

            if desired_ruleset is None:
                if existing_ruleset is not None:
                    LOG.info("%s Ruleset %s exists and will be deleted", _LOG_PREFIX, rs_id)
                    return True
                continue

            desired_rules = desired_ruleset.get("rules") if isinstance(desired_ruleset, dict) else None
            if isinstance(desired_rules, dict) and desired_rules:
                existing_rules = (existing_ruleset or {}).get("rules") or {}
                if not isinstance(existing_rules, dict):
                    existing_rules = self._coerce_existing_rules_map(existing_rules)
                for rule_key, desired_rule_entry in desired_rules.items():
                    desired_rule = desired_rule_entry.get("rule") if isinstance(desired_rule_entry, dict) else None
                    existing_rule_entry = existing_rules.get(rule_key)
                    existing_rule = self._existing_rule_from_entry(existing_rule_entry)
                    if desired_rule is None:
                        if existing_rule is not None:
                            LOG.info("%s Rule %s exists and will be deleted", _LOG_PREFIX, rule_key)
                            return True
                        continue
                    if not self._desired_matches_existing(desired_rule, existing_rule):
                        LOG.info("%s Rule %s differs", _LOG_PREFIX, rule_key)
                        return True
                desired_meta = {k: v for k, v in desired_ruleset.items() if k != "rules"}
                existing_meta = {k: v for k, v in (existing_ruleset or {}).items() if k != "rules"}
                if not self._desired_matches_existing(desired_meta, existing_meta):
                    LOG.info("%s Ruleset %s metadata differs", _LOG_PREFIX, rs_id)
                    return True
                continue

            if not self._desired_matches_existing(desired_ruleset, existing_ruleset):
                LOG.info("%s Ruleset %s differs", _LOG_PREFIX, rs_id)
                return True

        return False

    def _segment_attachments_need_update(self, desired_segments: Dict[str, Any], device_info_dict: Any) -> bool:
        d = self._device_dict(device_info_dict)
        for seg_name, seg_body in desired_segments.items():
            if not isinstance(seg_body, dict):
                return True
            nr = seg_body.get("natRuleset") or seg_body.get("nat_ruleset")
            desired_ref: Any = None
            if isinstance(nr, dict):
                desired_ref = nr.get("ruleset")

            existing_seg = self._find_segment_object(d, str(seg_name))
            if existing_seg is None:
                LOG.info("%s LAN segment %s not found; pushing desired update", _LOG_PREFIX, seg_name)
                return True
            existing_ref = self._nat_ruleset_ref_from_segment(existing_seg)

            if desired_ref is None:
                if existing_ref is not None:
                    return True
                continue
            if not self._ruleset_refs_match(desired_ref, existing_ref):
                LOG.info(
                    "%s LAN segment %s natRuleset ref differs (desired=%r, existing=%r)",
                    _LOG_PREFIX,
                    seg_name,
                    desired_ref,
                    existing_ref,
                )
                return True
        return False

    def _prune_absent_noops(self, rulesets_map: Dict[str, Any], device_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Remove absent rulesets/rules that don't exist on the device (no-ops)."""
        existing_rs = self._extract_rulesets_from_device({"device": device_dict})
        out: Dict[str, Any] = {}
        for rs_id, desired_entry in rulesets_map.items():
            if not isinstance(desired_entry, dict):
                out[rs_id] = desired_entry
                continue
            desired_ruleset = desired_entry.get("ruleset")
            existing_entry = existing_rs.get(rs_id) if isinstance(existing_rs, dict) else None
            existing_ruleset = self._existing_ruleset_from_entry(existing_entry)

            if desired_ruleset is None:
                if existing_ruleset is None:
                    LOG.info("%s Ruleset %s absent on device, skipping delete no-op", _LOG_PREFIX, rs_id)
                    continue
                out[rs_id] = desired_entry
                continue

            if not isinstance(desired_ruleset, dict):
                out[rs_id] = desired_entry
                continue

            desired_rules = desired_ruleset.get("rules")
            if not isinstance(desired_rules, dict) or not desired_rules:
                out[rs_id] = desired_entry
                continue

            existing_ruleset = self._coerce_existing_ruleset_body(existing_ruleset, rs_id)
            existing_rules = (existing_ruleset or {}).get("rules") or {}
            if not isinstance(existing_rules, dict):
                existing_rules = self._coerce_existing_rules_map(existing_rules)

            pruned_rules: Dict[str, Any] = {}
            for rule_key, rule_entry in desired_rules.items():
                desired_rule = rule_entry.get("rule") if isinstance(rule_entry, dict) else None
                if desired_rule is None:
                    existing_rule = self._existing_rule_from_entry(existing_rules.get(rule_key))
                    if existing_rule is None:
                        LOG.info(
                            "%s Rule %s in ruleset %s absent on device, skipping delete no-op",
                            _LOG_PREFIX,
                            rule_key,
                            rs_id,
                        )
                        continue
                pruned_rules[rule_key] = rule_entry

            pruned_ruleset = dict(desired_ruleset)
            pruned_ruleset["rules"] = pruned_rules
            out[rs_id] = {"ruleset": pruned_ruleset}
        return out

    def _prune_absent_segment_noops(self, segments_map: Dict[str, Any], device_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Remove absent-ruleset segments that are already detached on the device (no-ops)."""
        d = self._device_dict({"device": device_dict})
        out: Dict[str, Any] = {}
        for seg_name, seg_body in segments_map.items():
            if not isinstance(seg_body, dict):
                out[seg_name] = seg_body
                continue
            nr = seg_body.get("natRuleset") or seg_body.get("nat_ruleset")
            desired_ref: Any = None
            if isinstance(nr, dict):
                desired_ref = nr.get("ruleset")
            if desired_ref is not None:
                out[seg_name] = seg_body
                continue
            existing_seg = self._find_segment_object(d, str(seg_name))
            existing_ref = self._nat_ruleset_ref_from_segment(existing_seg)
            if existing_ref is None:
                LOG.info(
                    "%s Segment %s already has no natRuleset on device, skipping detach no-op",
                    _LOG_PREFIX,
                    seg_name,
                )
                continue
            out[seg_name] = seg_body
        return out

    def _find_segments_referencing_ruleset(self, device_dict: Dict[str, Any], ruleset_name: str) -> List[str]:
        """Return names of LAN segments whose natRuleset references the given ruleset."""
        d = self._device_dict({"device": device_dict})
        segments = None
        edge = as_dict(d.get("edge"))
        if isinstance(edge, dict):
            for key in ("segments", "lanSegments", "lan_segments"):
                if key in edge:
                    segments = edge.get(key)
                    break
        if segments is None:
            for key in ("segments", "lanSegments", "lan_segments"):
                if key in d:
                    segments = d.get(key)
                    break
        if segments is None:
            return []
        affected: List[str] = []
        if isinstance(segments, list):
            for item in segments:
                if not isinstance(item, dict):
                    continue
                seg_name = item.get("name")
                existing_ref = self._nat_ruleset_ref_from_segment(item)
                if seg_name and existing_ref and self._ruleset_refs_match(ruleset_name, existing_ref):
                    affected.append(str(seg_name))
        elif isinstance(segments, dict):
            for seg_name, seg_obj in segments.items():
                if not isinstance(seg_obj, dict):
                    continue
                existing_ref = self._nat_ruleset_ref_from_segment(seg_obj)
                if existing_ref and self._ruleset_refs_match(ruleset_name, existing_ref):
                    affected.append(str(seg_name))
        return affected

    def _payload_differs(self, desired_payload: Dict[str, Any], device_info_dict: Any) -> bool:
        desired_edge = (desired_payload or {}).get("edge") or {}
        desired_segments = desired_edge.get("segments") or {}
        desired_np = desired_edge.get("natPolicy") or {}
        desired_rs = desired_np.get("natRulesets") or {}
        if isinstance(desired_segments, dict) and desired_segments:
            if self._segment_attachments_need_update(desired_segments, device_info_dict):
                return True
        if isinstance(desired_rs, dict) and desired_rs:
            if self._nat_rulesets_need_update(desired_rs, device_info_dict):
                return True
        return False

    def _ruleset_rules_snapshot(self, ruleset: Any) -> Dict[str, Any]:
        if not isinstance(ruleset, dict):
            return {}
        rules = ruleset.get("rules") or {}
        if not isinstance(rules, dict):
            rules = self._coerce_existing_rules_map(rules)
        out_rules: Dict[str, Any] = {}
        for rule_key, entry in sorted(rules.items(), key=lambda kv: str(kv[0])):
            rule_body = self._existing_rule_from_entry(entry)
            out_rules[str(rule_key)] = self._normalize(rule_body)
        snapshot: Dict[str, Any] = {"rules": out_rules}
        meta = {k: v for k, v in ruleset.items() if k != "rules"}
        if meta:
            snapshot["_meta"] = self._normalize(meta)
        return snapshot

    def _nat_policy_diff(
        self, device_dict: Dict[str, Any], payload: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
        desired_edge = as_dict(payload.get("edge"))
        before: Dict[str, Any] = {}
        after: Dict[str, Any] = {}

        desired_segments = desired_edge.get("segments")
        if isinstance(desired_segments, dict) and desired_segments:
            d = self._device_dict({"device": device_dict})
            before_segs: Dict[str, Any] = {}
            after_segs: Dict[str, Any] = {}
            for seg_name in sorted(desired_segments.keys()):
                existing_seg = self._find_segment_object(d, str(seg_name))
                before_segs[seg_name] = {"ruleset": self._nat_ruleset_ref_from_segment(existing_seg)}
                seg_body = as_dict(desired_segments[seg_name])
                nr = as_dict(seg_body.get("natRuleset") or seg_body.get("nat_ruleset"))
                after_segs[seg_name] = {"ruleset": nr.get("ruleset")}
            before["segments"] = before_segs
            after["segments"] = after_segs

        desired_np = as_dict(desired_edge.get("natPolicy"))
        desired_rs = desired_np.get("natRulesets")
        if isinstance(desired_rs, dict) and desired_rs:
            existing_rs = self._extract_rulesets_from_device({"device": device_dict})
            before_rs: Dict[str, Any] = {}
            after_rs: Dict[str, Any] = {}
            for key in sorted(desired_rs.keys()):
                existing_entry = existing_rs.get(key) if isinstance(existing_rs, dict) else None
                existing_ruleset = self._existing_ruleset_from_entry(existing_entry)
                existing_ruleset = self._coerce_existing_ruleset_body(existing_ruleset, str(key))

                desired_entry = as_dict(desired_rs[key])
                desired_ruleset = desired_entry.get("ruleset")

                if desired_ruleset is None:
                    if existing_ruleset is not None:
                        before_rs[key] = self._ruleset_rules_snapshot(existing_ruleset)
                        after_rs[key] = None
                elif existing_ruleset is None:
                    before_rs[key] = None
                    after_rs[key] = self._ruleset_rules_snapshot(desired_ruleset)
                else:
                    diff_before: Dict[str, Any] = {}
                    diff_after: Dict[str, Any] = {}
                    desired_rules = desired_ruleset.get("rules") if isinstance(desired_ruleset, dict) else {}
                    existing_rules = (existing_ruleset or {}).get("rules") or {}
                    if not isinstance(existing_rules, dict):
                        existing_rules = self._coerce_existing_rules_map(existing_rules)
                    if isinstance(desired_rules, dict):
                        before_rules: Dict[str, Any] = {}
                        after_rules: Dict[str, Any] = {}
                        for rule_key, desired_rule_entry in sorted(desired_rules.items(), key=lambda kv: str(kv[0])):
                            if not isinstance(desired_rule_entry, dict):
                                continue
                            desired_rule = desired_rule_entry.get("rule")
                            existing_rule_entry = existing_rules.get(rule_key)
                            existing_rule = self._existing_rule_from_entry(existing_rule_entry)
                            if desired_rule is None:
                                if existing_rule is not None:
                                    before_rules[str(rule_key)] = self._normalize(existing_rule)
                                    after_rules[str(rule_key)] = None
                            elif existing_rule is None or not self._desired_matches_existing(
                                desired_rule, existing_rule
                            ):
                                before_rules[str(rule_key)] = self._normalize(existing_rule) if existing_rule else None
                                after_rules[str(rule_key)] = self._normalize(desired_rule)
                        if before_rules or after_rules:
                            diff_before["rules"] = before_rules
                            diff_after["rules"] = after_rules
                    if diff_before or diff_after:
                        before_rs[key] = diff_before or None
                        after_rs[key] = diff_after or None

            before["natRulesets"] = before_rs
            after["natRulesets"] = after_rs

        if before or after:
            branch = (
                "edge"
                if "segments" in before and "natRulesets" in before
                else ("edge.segments" if "segments" in before else "edge.natPolicy.natRulesets")
            )
            return before, after, branch
        return before, after, "edge"

    def _iter_device_payloads(
        self,
        config_yaml_file: Optional[str],
        operation: str,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Tuple[int, str, Dict[str, Any], Dict[str, Any]]]:
        if operation not in (
            "configure",
            "deconfigure",
            "attach_to_lan_segments",
            "detach_from_lan_segments",
        ):
            raise ConfigurationError(f"Unsupported operation '{operation}'")

        enterprise = self.gsdk.enterprise_info["company_name"]
        by_name = self._load_devices(config_yaml_file, module_params)
        if not by_name:
            source = config_yaml_file or "module_params"
            LOG.info("%s No '%s' entries to process in %s", _LOG_PREFIX, _YAML_KEY, source)
            return

        for device_name, device_cfg in by_name.items():
            device_id, device_dict = fetch_device_by_name(self.gsdk, device_name, enterprise)

            if operation in ("attach_to_lan_segments", "detach_from_lan_segments"):
                seg_cfg = device_cfg.get("segments")
                segments_map = self._segments_payload_from_yaml(seg_cfg, operation=operation)
                if not segments_map:
                    LOG.info("%s No 'segments' for %s, skipping", _LOG_PREFIX, device_name)
                    continue
                if not getattr(self.gsdk, "check_mode", False):
                    segments_map = self._prune_absent_segment_noops(segments_map, device_dict)
                    if not segments_map:
                        LOG.info(
                            "%s No effective segment changes for %s after pruning absent no-ops, skipping",
                            _LOG_PREFIX,
                            device_name,
                        )
                        continue
                payload: Dict[str, Any] = {"edge": {"segments": segments_map}}
            else:
                nr_cfg = device_cfg.get("natRulesets")
                rulesets_map = self._rulesets_from_yaml(nr_cfg, operation=operation)
                if not rulesets_map:
                    LOG.info("%s No natRulesets for %s, skipping", _LOG_PREFIX, device_name)
                    continue
                if not getattr(self.gsdk, "check_mode", False):
                    rulesets_map = self._prune_absent_noops(rulesets_map, device_dict)
                    if not rulesets_map:
                        LOG.info(
                            "%s No effective changes for %s after pruning absent no-ops, skipping",
                            _LOG_PREFIX,
                            device_name,
                        )
                        continue
                # Refuse to delete a ruleset that is still attached to LAN segments.
                deleted_rulesets = [
                    rs for rs, v in rulesets_map.items() if isinstance(v, dict) and v.get("ruleset") is None
                ]
                for rs_name in deleted_rulesets:
                    if getattr(self.gsdk, "check_mode", False):
                        continue
                    attached_segs = self._find_segments_referencing_ruleset(device_dict, rs_name)
                    if attached_segs:
                        raise ConfigurationError(
                            f"[{device_name}] Ruleset '{rs_name}' is still attached to LAN "
                            f"segment(s): {attached_segs}. Detach it first by running "
                            f"attach_to_lan_segments with 'state: absent' on those segments, "
                            f"or use the detach_from_lan_segments operation."
                        )
                payload = {"edge": {"natPolicy": {"natRulesets": rulesets_map}}}

            if "description" in device_cfg:
                payload["description"] = device_cfg.get("description", "")
            if "configurationMetadata" in device_cfg:
                meta = device_cfg.get("configurationMetadata")
                payload["configurationMetadata"] = meta if isinstance(meta, dict) else {"name": ""}

            yield device_id, device_name, payload, device_dict

    def apply_nat_policy(
        self,
        config_yaml_file: Optional[str],
        operation: str,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> dict:
        result = new_apply_result()
        to_push: Dict[int, Dict[str, Any]] = {}
        configured_devices: List[str] = []
        diff_plan: List[Dict[str, Any]] = []

        for device_id, device_name, payload, device_dict in self._iter_device_payloads(
            config_yaml_file, operation=operation, module_params=module_params
        ):
            differs = self._payload_differs(payload, {"device": device_dict})
            if not differs:
                LOG.info("%s ✓ No changes needed for %s (ID: %s), skipping", _LOG_PREFIX, device_name, device_id)
                result["skipped_devices"].append(device_name)
                continue

            before, after, branch = self._nat_policy_diff(device_dict, payload)
            to_push[device_id] = {"device_id": device_id, "payload": payload}
            configured_devices.append(device_name)
            diff_plan.append({"device": device_name, "branch": branch, "before": before, "after": after})

        result["diff_plan"] = diff_plan
        if not to_push:
            return result

        push_device_config_raw(
            self.execute_concurrent_tasks,
            self.gsdk.put_device_config_raw,
            to_push,
            log_prefix=_LOG_PREFIX,
        )

        result["changed"] = True
        result["configured_devices"] = configured_devices
        return result

    def configure(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> dict:
        return self.apply_nat_policy(config_yaml_file, operation="configure", module_params=module_params)

    def deconfigure(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> dict:
        return self.apply_nat_policy(config_yaml_file, operation="deconfigure", module_params=module_params)

    def attach_to_lan_segments(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> dict:
        return self.apply_nat_policy(config_yaml_file, operation="attach_to_lan_segments", module_params=module_params)

    def detach_from_lan_segments(
        self,
        config_yaml_file: Optional[str] = None,
        module_params: Optional[Dict[str, Any]] = None,
    ) -> dict:
        return self.apply_nat_policy(
            config_yaml_file, operation="detach_from_lan_segments", module_params=module_params
        )
