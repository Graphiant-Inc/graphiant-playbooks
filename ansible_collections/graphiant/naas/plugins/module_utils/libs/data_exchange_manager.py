"""
Data Exchange Manager for Graphiant Playbooks.

This module provides functionality for managing Data Exchange workflows including:
- Create New Services
- Create New Customers
- Match Services to Customers

Deconfigure workflow consistency (with global_config_manager, site_manager):
- Idempotency: delete_customers/delete_services skip when customer/service not found.
  match_service_to_customers and accept_invitation report 'failed' and raise when failures > 0.
- Result shape: delete_* return changed, deleted, skipped (no 'failed'); match_* returns
  matched, skipped, failed and raises if failed non-empty; accept_* raises if total_failed > 0.
- Logging: "Attempting to delete ..." with target names, then "Deconfigure completed: ..."
  with explicit lists (aligned with global_config and site_manager).
"""

from __future__ import annotations

import ipaddress
import os
from typing import Any, Dict, Optional, Set

try:
    from tabulate import tabulate

    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError
from .device_config_common import redact_sensitive_for_log

# Required dependencies - checked when functions are called
# Don't raise at module level to allow import test to pass

LOG = setup_logger()


class DataExchangeManager(BaseManager):
    """
    Manager for Data Exchange workflows and operations.
    """

    def configure(self, config_yaml_file: str) -> dict:
        """
        Configure Data Exchange resources based on the provided YAML file.
        This is the main entry point for Data Exchange configuration.

        Args:
            config_yaml_file: Path to the YAML configuration file

        Returns:
            dict: Result with 'changed' status and details of operations performed
        """
        result: Dict[str, Any] = {"changed": False, "details": {}}

        LOG.info("Configuring Data Exchange resources from %s", config_yaml_file)

        # Create services first
        services_result = self.create_services(config_yaml_file)
        if services_result.get("changed"):
            result["changed"] = True
        result["details"]["services"] = services_result

        # Create customers
        customers_result = self.create_customers(config_yaml_file)
        if customers_result.get("changed"):
            result["changed"] = True
        result["details"]["customers"] = customers_result

        # Match services to customers
        matches_result = self.match_service_to_customers(config_yaml_file)
        if matches_result.get("changed"):
            result["changed"] = True
        result["details"]["matches"] = matches_result

        LOG.info("Data Exchange configuration completed (changed: %s)", result["changed"])
        return result

    def deconfigure(self, config_yaml_file: str) -> dict:
        """
        Deconfigure Data Exchange resources based on the provided YAML file.
        This is the main entry point for Data Exchange deconfiguration.

        Args:
            config_yaml_file: Path to the YAML configuration file

        Returns:
            dict: Result with 'changed' status and details of operations performed
        """
        result: Dict[str, Any] = {"changed": False, "details": {}}

        LOG.info("Deconfiguring Data Exchange resources from %s", config_yaml_file)

        # Delete customers first (they depend on services)
        customers_result = self.delete_customers(config_yaml_file)
        if customers_result.get("changed"):
            result["changed"] = True
        result["details"]["customers"] = customers_result

        # Delete services
        services_result = self.delete_services(config_yaml_file)
        if services_result.get("changed"):
            result["changed"] = True
        result["details"]["services"] = services_result

        LOG.info("Data Exchange deconfiguration completed (changed: %s)", result["changed"])
        return result

    def create_services(self, config_yaml_file: str, diff_mode: bool = False) -> dict:
        """
        Create new Data Exchange services from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file
            diff_mode (bool): When True, fetch existing service details to detect prefixTags
                (and, for client_to_server, natTranslationMode) drift and populate diff_plan.
                Only set when the caller requested --diff output.

        Returns:
            dict: Result with 'changed' status and lists of created/skipped items
        """
        result: Dict[str, Any] = {"changed": False, "created": [], "skipped": [], "drifted": [], "diff_plan": []}

        try:
            LOG.info("Creating Data Exchange service from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or "data_exchange_services" not in config_data:
                LOG.info("No data_exchange_services configuration found in YAML file")
                return result

            services = config_data["data_exchange_services"]
            if not isinstance(services, list):
                raise ConfigurationError("Configuration error: 'data_exchange_services' must be a list.")

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            # Fetch Graphiant routing policy (filter) names once for validation across all services
            existing_routing_policy_names = None
            try:
                summaries = self.gsdk.get_global_routing_policy_summaries()
                existing_routing_policy_names = {s.get("name") for s in summaries if s.get("name")}
                LOG.info(
                    "create_services: Loaded %s Graphiant routing policies for validation",
                    len(existing_routing_policy_names),
                )
            except Exception as e:
                LOG.warning("create_services: Could not fetch global routing policy summaries: %s", e)

            # Cache LAN segment site/device maps across services in this run (see
            # _validate_sites_and_devices_for_lan_segment)
            site_map_cache: Dict[int, dict] = {}

            for service_config in services:
                service_name = service_config.get("serviceName")
                LOG.info("--------------------------------")
                LOG.info("create_services: Creating service '%s'", service_name)
                if not service_name:
                    raise ConfigurationError("Configuration error: Each service must have a 'serviceName' field.")

                # Check if service already exists
                existing_service = self.gsdk.get_data_exchange_service_by_name(service_name)
                if existing_service:
                    LOG.info(
                        "Service '%s' already exists (ID: %s), skipping creation", service_name, existing_service.id
                    )
                    # Drift detection: only when --diff requested (avoids extra API calls otherwise)
                    service_type = service_config.get("type", "peering_service")
                    policy_config = service_config.get("policy") or {}
                    desired_prefix_tags = policy_config.get("prefixTags") or []
                    has_nat_mode = service_type == "client_to_server" and bool(policy_config.get("natTranslationMode"))
                    if diff_mode and (desired_prefix_tags or has_nat_mode):
                        try:
                            current_details_dict = self.gsdk.get_data_exchange_service_details(
                                existing_service.id, type=service_type
                            )
                            current_inner_policy = (current_details_dict.get("policy") or {}).get("policy") or {}
                            current_prefix_tags = current_inner_policy.get("prefixTags") or []

                            drifted = False
                            if desired_prefix_tags and self._normalize_prefix_tags(
                                current_prefix_tags
                            ) != self._normalize_prefix_tags(desired_prefix_tags):
                                LOG.info(
                                    "Service '%s' has drifted prefixTags (use update_services to apply)",
                                    service_name,
                                )
                                result["diff_plan"].append(
                                    {
                                        "device": service_name,
                                        "branch": "prefixTags (existing - use update_services to apply)",
                                        "before": {"prefixTags": current_prefix_tags},
                                        "after": {"prefixTags": desired_prefix_tags},
                                    }
                                )
                                drifted = True

                            if has_nat_mode:
                                # Resolve device names to IDs so the comparison lines up with the
                                # already-ID-keyed natTranslationMode returned by the API
                                self._resolve_nat_translation_device_ids(policy_config, service_name)
                                desired_nat_mode = policy_config.get("natTranslationMode") or {}
                                current_nat_mode = current_inner_policy.get("natTranslationMode") or {}
                                if self._normalize_nat_translation_mode(
                                    current_nat_mode
                                ) != self._normalize_nat_translation_mode(desired_nat_mode):
                                    LOG.info(
                                        "Service '%s' has drifted natTranslationMode (use update_services to apply)",
                                        service_name,
                                    )
                                    result["diff_plan"].append(
                                        {
                                            "device": service_name,
                                            "branch": ("natTranslationMode (existing - use update_services to apply)"),
                                            "before": {"natTranslationMode": current_nat_mode},
                                            "after": {"natTranslationMode": desired_nat_mode},
                                        }
                                    )
                                    drifted = True

                            if drifted:
                                result["drifted"].append(service_name)
                        except Exception as e:
                            LOG.warning("Could not fetch details for drift detection on '%s': %s", service_name, e)
                    result["skipped"].append(service_name)
                    continue

                if "policy" in service_config:
                    lan_segment_names_by_id: Dict[int, str] = {}
                    # Resolve LAN segment ID if provided by name
                    if "serviceLanSegment" in service_config["policy"]:
                        lan_segment_name = service_config["policy"]["serviceLanSegment"]
                        if isinstance(lan_segment_name, str):
                            lan_segment_id = self.gsdk.get_lan_segment_id(lan_segment_name)
                            if lan_segment_id:
                                service_config["policy"]["serviceLanSegment"] = lan_segment_id
                                lan_segment_names_by_id[lan_segment_id] = lan_segment_name
                            else:
                                raise ConfigurationError(
                                    f"LAN segment '{lan_segment_name}' not found for service '{service_name}'."
                                )

                    # Resolve site or site list IDs if provided by names
                    site_names_by_id: Dict[int, str] = {}
                    device_names_by_id: Dict[int, str] = {}
                    self._resolve_site_ids(service_config["policy"], service_name, name_map=site_names_by_id)
                    self._resolve_site_list_ids(service_config["policy"], service_name)
                    # Resolve device names to device IDs in globalObjectOps (for routingPolicyOps / Graphiant filters)
                    self._resolve_global_object_ops_device_ids(service_config["policy"], service_name)
                    # Resolve device names to device IDs in natTranslationMode (client_to_server NAT pools)
                    self._resolve_nat_translation_device_ids(
                        service_config["policy"], service_name, name_map=device_names_by_id
                    )
                    # Validate that referenced Graphiant routing policy (filter) names exist
                    self._validate_global_object_ops_routing_policies(
                        service_config["policy"], service_name, existing_policy_names=existing_routing_policy_names
                    )
                    # Validate NAT pool prefixes aren't reused across devices ("Duplicate entry" in the API/UI)
                    self._validate_nat_pool_prefixes_unique(
                        service_config["policy"], service_name, device_names_by_id=device_names_by_id
                    )
                    # Validate prefixTags/NAT pool prefixes are properly-aligned CIDR network addresses
                    self._validate_service_prefixes_are_cidr(service_config["policy"], service_name)
                    if service_config.get("type") == "client_to_server":
                        # Validate sites belong to the LAN segment, and NAT edge devices belong to those sites
                        self._validate_sites_and_devices_for_lan_segment(
                            service_config["policy"],
                            service_name,
                            site_map_cache=site_map_cache,
                            site_names_by_id=site_names_by_id,
                            device_names_by_id=device_names_by_id,
                            lan_segment_names_by_id=lan_segment_names_by_id,
                        )

                # Create service directly
                LOG.info("Service configuration: %s", service_config)
                LOG.info("create_data_exchange_services: Creating service '%s'", service_name)
                result["diff_plan"].append(
                    {
                        "device": service_name,
                        "branch": "create",
                        "before": {},
                        "after": service_config,
                    }
                )
                self.gsdk.create_data_exchange_services(service_config)
                LOG.info("Successfully created service '%s'", service_name)
                result["created"].append(service_name)
                result["changed"] = True

            LOG.info(
                "Data Exchange service creation completed: %s created, %s skipped (changed: %s)",
                len(result["created"]),
                len(result["skipped"]),
                result["changed"],
            )
            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to create Data Exchange service: %s", e)
            raise ConfigurationError(f"Data Exchange service creation failed: {e}")

    def update_services(self, config_yaml_file: str) -> dict:
        """
        Update existing Data Exchange services from YAML configuration.

        Only ``prefixTags`` can be updated. The service must already exist.
        At least one prefix must remain after the update.

        Args:
            config_yaml_file (str): Path to the YAML configuration file.
                Each service entry requires ``serviceName`` and ``policy.prefixTags``.

        Returns:
            dict: Result with 'changed' status and lists of updated/skipped items
        """
        result: Dict[str, Any] = {"changed": False, "updated": [], "skipped": [], "diff_plan": []}

        try:
            LOG.info("Updating Data Exchange services from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or "data_exchange_services" not in config_data:
                LOG.info("No data_exchange_services configuration found in YAML file")
                return result

            services = config_data["data_exchange_services"]
            if not isinstance(services, list):
                raise ConfigurationError("Configuration error: 'data_exchange_services' must be a list.")

            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            for service_config in services:
                service_name = service_config.get("serviceName")
                LOG.info("--------------------------------")
                LOG.info("update_services: Updating service '%s'", service_name)
                if not service_name:
                    raise ConfigurationError("Configuration error: Each service must have a 'serviceName' field.")

                # Service must exist to be updated
                existing_service = self.gsdk.get_data_exchange_service_by_name(service_name)
                if not existing_service:
                    raise ConfigurationError(
                        f"Service '{service_name}' not found. " "Use create_services to create new services."
                    )
                service_id = existing_service.id
                service_type = service_config.get("type", "peering_service")

                # Get current service details for comparison and payload construction
                current_details_dict = self.gsdk.get_data_exchange_service_details(service_id, type=service_type)
                current_outer_policy = current_details_dict.get("policy") or {}
                current_inner_policy = current_outer_policy.get("policy") or {}
                current_prefix_tags = current_inner_policy.get("prefixTags") or []

                desired_policy = service_config.get("policy") or {}
                # Desired prefixTags from config
                desired_prefix_tags = desired_policy.get("prefixTags") or []

                if service_type == "client_to_server":
                    self._update_client_to_server_service(
                        service_name,
                        service_id,
                        current_inner_policy,
                        current_prefix_tags,
                        desired_policy,
                        desired_prefix_tags,
                        result,
                    )
                    continue

                if not desired_prefix_tags:
                    raise ConfigurationError(
                        f"Service '{service_name}': 'policy.prefixTags' is required for update_services "
                        "and must contain at least one entry."
                    )

                # Validate: at least one prefix must remain
                if len(desired_prefix_tags) == 0:
                    raise ConfigurationError(
                        f"Service '{service_name}': At least one prefix must remain after update. "
                        "Removing all prefixes is not allowed."
                    )

                self._validate_cidr_prefixes(
                    [t.get("prefix") for t in desired_prefix_tags if isinstance(t, dict)],
                    service_name,
                    "prefixTags",
                )

                # Normalize for idempotency comparison
                def _norm(tags):
                    return sorted(
                        [{"prefix": t.get("prefix", ""), "tag": t.get("tag", "") or ""} for t in tags],
                        key=lambda x: x["prefix"],
                    )

                if _norm(current_prefix_tags) == _norm(desired_prefix_tags):
                    LOG.info("Service '%s' prefixTags unchanged, skipping update", service_name)
                    result["skipped"].append(service_name)
                    continue

                # Record diff for --diff mode
                result["diff_plan"].append(
                    {
                        "device": service_name,
                        "branch": "prefixTags",
                        "before": {"prefixTags": current_prefix_tags},
                        "after": {"prefixTags": desired_prefix_tags},
                    }
                )

                # Build PUT payload using current service state + desired prefixTags
                current_sites = current_inner_policy.get("sites") or []
                site_for_put = [
                    {"sites": s.get("sites") or [], "siteLists": s.get("siteLists") or []} for s in current_sites
                ]

                update_payload = {
                    "policy": {
                        "serviceLanSegment": current_inner_policy.get("serviceLanSegment"),
                        "sites": site_for_put,
                        "description": current_inner_policy.get("description", ""),
                        "prefixTags": desired_prefix_tags,
                        "globalObjectOps": {},
                    },
                }

                LOG.info("update_services: Update payload for '%s': %s", service_name, update_payload)
                self.gsdk.edit_data_exchange_service(service_id, update_payload)
                LOG.info("Successfully updated service '%s' (ID: %s)", service_name, service_id)
                result["updated"].append(service_name)
                result["changed"] = True

            LOG.info(
                "Data Exchange service update completed: %s updated, %s skipped (changed: %s)",
                len(result["updated"]),
                len(result["skipped"]),
                result["changed"],
            )
            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to update Data Exchange service: %s", e)
            raise ConfigurationError(f"Data Exchange service update failed: {e}")

    @staticmethod
    def _normalize_prefix_tags(tags) -> list:
        return sorted(
            [{"prefix": t.get("prefix", ""), "tag": t.get("tag", "") or ""} for t in (tags or [])],
            key=lambda x: x["prefix"],
        )

    @staticmethod
    def _normalize_nat_translation_mode(nat_mode) -> dict:
        normalized: Dict[str, Any] = {}
        for translation_type in ("centralized", "decentralized"):
            block = (nat_mode or {}).get(translation_type)
            if not isinstance(block, dict):
                continue
            prefixes = block.get("prefixes") or {}
            normalized[translation_type] = {
                str(device_id): sorted((device_prefixes or {}).get("prefixes") or [])
                for device_id, device_prefixes in prefixes.items()
            }
        return normalized

    def _update_client_to_server_service(
        self,
        service_name: str,
        service_id: int,
        current_inner_policy: dict,
        current_prefix_tags: list,
        desired_policy: dict,
        desired_prefix_tags: list,
        result: Dict[str, Any],
    ) -> None:
        """
        Apply an update_services change for a client_to_server service.

        Only prefixTags and/or natTranslationMode (NAT pools) can be changed; at least one
        must be provided. Unlike peering_service, sites are kept under the "sites" key
        (plural) and the PUT body has no "id"/"type" (see edit_data_exchange_service).

        Known API limitation (confirmed against the portal UI, not something this code can
        work around): once an IP is added to a device's NAT pool, it cannot be removed via
        this PUT — sending a natTranslationMode with a prefix missing from the current pool
        does not delete it server-side. Only adding new prefixes is supported.
        """
        desired_nat_mode = desired_policy.get("natTranslationMode")
        device_names_by_id: Dict[int, str] = {}
        if desired_nat_mode:
            self._resolve_nat_translation_device_ids(desired_policy, service_name, name_map=device_names_by_id)
            # Validate NAT pool prefixes aren't reused across devices ("Duplicate entry" in the API/UI)
            self._validate_nat_pool_prefixes_unique(desired_policy, service_name, device_names_by_id=device_names_by_id)

        if not desired_prefix_tags and not desired_nat_mode:
            raise ConfigurationError(
                f"Service '{service_name}': update_services requires at least one of "
                "'policy.prefixTags' or 'policy.natTranslationMode' for client_to_server services."
            )

        # Validate prefixTags/NAT pool prefixes are properly-aligned CIDR network addresses
        self._validate_service_prefixes_are_cidr(
            {"prefixTags": desired_prefix_tags, "natTranslationMode": desired_nat_mode}, service_name
        )

        current_nat_mode = current_inner_policy.get("natTranslationMode") or {}
        prefix_tags_changed = bool(desired_prefix_tags) and self._normalize_prefix_tags(
            current_prefix_tags
        ) != self._normalize_prefix_tags(desired_prefix_tags)
        nat_mode_changed = bool(desired_nat_mode) and self._normalize_nat_translation_mode(
            current_nat_mode
        ) != self._normalize_nat_translation_mode(desired_nat_mode)

        if not prefix_tags_changed and not nat_mode_changed:
            LOG.info("Service '%s' unchanged, skipping update", service_name)
            result["skipped"].append(service_name)
            return

        if nat_mode_changed:
            # Validate new NAT edge devices belong to the service's existing sites/LAN segment
            self._validate_sites_and_devices_for_lan_segment(
                {
                    "serviceLanSegment": current_inner_policy.get("serviceLanSegment"),
                    "sites": current_inner_policy.get("sites") or [],
                    "natTranslationMode": desired_nat_mode,
                },
                service_name,
                device_names_by_id=device_names_by_id,
            )

        if prefix_tags_changed:
            result["diff_plan"].append(
                {
                    "device": service_name,
                    "branch": "prefixTags",
                    "before": {"prefixTags": current_prefix_tags},
                    "after": {"prefixTags": desired_prefix_tags},
                }
            )
        if nat_mode_changed:
            result["diff_plan"].append(
                {
                    "device": service_name,
                    "branch": "natTranslationMode",
                    "before": {"natTranslationMode": current_nat_mode},
                    "after": {"natTranslationMode": desired_nat_mode},
                }
            )

        update_payload = {
            "policy": {
                "serviceLanSegment": current_inner_policy.get("serviceLanSegment"),
                "sites": current_inner_policy.get("sites") or [],
                "description": current_inner_policy.get("description", ""),
                "prefixTags": desired_prefix_tags if prefix_tags_changed else current_prefix_tags,
                "natTranslationMode": desired_nat_mode if nat_mode_changed else current_nat_mode,
            },
        }

        LOG.info("update_services: Update payload for '%s': %s", service_name, update_payload)
        self.gsdk.edit_data_exchange_service(service_id, update_payload)
        LOG.info("Successfully updated service '%s' (ID: %s)", service_name, service_id)
        result["updated"].append(service_name)
        result["changed"] = True

    def _resolve_site_ids(
        self, policy_config: dict, service_name: str, name_map: Optional[Dict[int, str]] = None
    ) -> None:
        """
        Resolve site names to site IDs in the policy configuration.

        ``site`` (singular) is the peering_service key; ``sites`` (plural) is the
        client_to_server key. Both wrap the same list of {sites, siteLists} entries.

        Args:
            policy_config (dict): Policy configuration to update
            service_name (str): Service name for error reporting
            name_map: Optional dict populated with {site_id: site_name} for each name resolved,
                so callers can render friendly names in later error messages (e.g.
                _validate_sites_and_devices_for_lan_segment).
        """
        for key in ("site", "sites"):
            site_entries = policy_config.get(key)
            if not isinstance(site_entries, list):
                continue
            for site_entry in site_entries:
                if "sites" in site_entry and isinstance(site_entry["sites"], list):
                    resolved_site_ids = []
                    for site_name in site_entry["sites"]:
                        if isinstance(site_name, str):
                            site_id = self.gsdk.get_site_id(site_name)
                            if site_id:
                                resolved_site_ids.append(site_id)
                                if name_map is not None:
                                    name_map[site_id] = site_name
                            else:
                                raise ConfigurationError(f"Site '{site_name}' not found for service '{service_name}'.")
                        else:
                            resolved_site_ids.append(site_name)  # Already an ID
                    site_entry["sites"] = resolved_site_ids

    def _resolve_site_list_ids(self, policy_config: dict, service_name: str) -> None:
        """
        Resolve site list names to site list IDs in the policy configuration.

        ``site`` (singular) is the peering_service key; ``sites`` (plural) is the
        client_to_server key. Both wrap the same list of {sites, siteLists} entries.

        Args:
            policy_config (dict): Policy configuration to update
            service_name (str): Service name for error reporting
        """
        for key in ("site", "sites"):
            site_entries = policy_config.get(key)
            if not isinstance(site_entries, list):
                continue
            for site_entry in site_entries:
                if "siteLists" in site_entry and isinstance(site_entry["siteLists"], list):
                    resolved_site_list_ids = []
                    for site_list_name in site_entry["siteLists"]:
                        if isinstance(site_list_name, str):
                            site_list_id = self.gsdk.get_site_list_id(site_list_name)
                            if site_list_id:
                                resolved_site_list_ids.append(site_list_id)
                            else:
                                raise ConfigurationError(
                                    f"Site list '{site_list_name}' not found " f"for service '{service_name}'."
                                )
                        else:
                            resolved_site_list_ids.append(site_list_name)  # Already an ID
                    site_entry["siteLists"] = resolved_site_list_ids

    def _resolve_nat_translation_device_ids(
        self, policy_config: dict, service_name: str, name_map: Optional[Dict[int, str]] = None
    ) -> None:
        """
        Resolve device names to device IDs in policy.natTranslationMode (client_to_server services).

        natTranslationMode.centralized/decentralized.prefixes keys are device names (e.g.
        "edge-1-sdktest"); the API expects edge device IDs as keys, each mapped to
        {"prefixes": [...]} NAT pool prefixes for that device.

        Args:
            policy_config (dict): Policy configuration to update (modified in place).
            service_name (str): Service name for error reporting.
            name_map: Optional dict populated with {device_id: device_name} for each name
                resolved, so callers can render friendly names in later error messages (e.g.
                _validate_sites_and_devices_for_lan_segment).
        """
        nat_mode = policy_config.get("natTranslationMode")
        if not isinstance(nat_mode, dict):
            return
        for translation_type in ("centralized", "decentralized"):
            translation = nat_mode.get(translation_type)
            if not isinstance(translation, dict):
                continue
            prefixes = translation.get("prefixes")
            if not isinstance(prefixes, dict):
                continue
            resolved = {}
            for device_name, device_prefixes in prefixes.items():
                device_id = self.gsdk.get_device_id(str(device_name))
                if device_id is None:
                    raise ConfigurationError(
                        f"Device '{device_name}' not found for service '{service_name}' "
                        f"(natTranslationMode.{translation_type}.prefixes keys must be device names)."
                    )
                if name_map is not None:
                    name_map[device_id] = str(device_name)
                resolved[str(device_id)] = device_prefixes
            translation["prefixes"] = resolved

    def _validate_nat_pool_prefixes_unique(
        self, policy_config: dict, service_name: str, device_names_by_id: Optional[Dict[int, str]] = None
    ) -> None:
        """
        Validate that no NAT pool prefix is reused across more than one edge device.

        The API (and portal UI) rejects reusing the same NAT pool prefix on more than one
        device with "Duplicate entry, IP address already configured." — catch it client-side
        with a clearer, per-prefix message before submitting.

        Args:
            policy_config (dict): Resolved policy configuration (natTranslationMode device
                keys already resolved to device IDs — see _resolve_nat_translation_device_ids).
            service_name (str): Service name for error reporting.
            device_names_by_id: Optional {device_id: device_name} map for friendlier error
                messages; falls back to the raw device ID when a name isn't known.
        """
        nat_mode = policy_config.get("natTranslationMode")
        if not isinstance(nat_mode, dict):
            return
        devices_by_prefix: Dict[str, Set[int]] = {}
        for translation_type in ("centralized", "decentralized"):
            block = nat_mode.get(translation_type)
            if not isinstance(block, dict):
                continue
            for device_id_str, device_prefixes in (block.get("prefixes") or {}).items():
                try:
                    device_id = int(device_id_str)
                except (TypeError, ValueError):
                    continue
                for prefix in (device_prefixes or {}).get("prefixes") or []:
                    devices_by_prefix.setdefault(prefix, set()).add(device_id)

        duplicates = {prefix: devs for prefix, devs in devices_by_prefix.items() if len(devs) > 1}
        if duplicates:
            details = "; ".join(
                f"'{prefix}' used by {[self._label(d, device_names_by_id) for d in sorted(devs)]}"
                for prefix, devs in sorted(duplicates.items())
            )
            raise ConfigurationError(
                f"Service '{service_name}': NAT pool prefix(es) must be unique across devices: {details}."
            )

    @staticmethod
    def _validate_cidr_prefixes(prefixes: list, service_name: str, context: str) -> None:
        """
        Validate that each prefix is a properly-aligned CIDR network address (host bits zero),
        matching the portal UI's own validation: "Invalid prefix. Please make sure the network
        address of CIDR is provided." A prefix like "162.131.7.69/31" is a valid host address
        within a /31 block, but not the block's network address (162.131.7.68/31) — the API
        rejects it even though the address itself is usable.

        Args:
            prefixes (list): Prefix strings to validate (e.g. ["162.131.7.68/31"]).
            service_name (str): Service name for error reporting.
            context (str): Where these prefixes came from, for error reporting (e.g.
                "prefixTags" or "natTranslationMode.centralized").
        """
        for prefix in prefixes or []:
            if not isinstance(prefix, str):
                continue
            try:
                ipaddress.ip_network(prefix, strict=True)
            except ValueError:
                try:
                    corrected = str(ipaddress.ip_network(prefix, strict=False))
                    hint = f" (e.g. '{corrected}')"
                except ValueError:
                    hint = ""
                raise ConfigurationError(
                    f"Service '{service_name}': invalid {context} prefix '{prefix}'. Please make sure the "
                    f"network address of the CIDR is provided{hint}."
                )

    def _validate_service_prefixes_are_cidr(self, policy_config: dict, service_name: str) -> None:
        """
        Validate policy.prefixTags and any natTranslationMode NAT pool prefixes are properly
        aligned CIDR network addresses (see _validate_cidr_prefixes).

        Args:
            policy_config (dict): Policy configuration (natTranslationMode device keys may be
                names or already-resolved IDs; not relevant here, only the prefix lists are checked).
            service_name (str): Service name for error reporting.
        """
        prefix_tags = [t.get("prefix") for t in (policy_config.get("prefixTags") or []) if isinstance(t, dict)]
        self._validate_cidr_prefixes(prefix_tags, service_name, "prefixTags")

        nat_mode = policy_config.get("natTranslationMode")
        if not isinstance(nat_mode, dict):
            return
        for translation_type in ("centralized", "decentralized"):
            block = nat_mode.get(translation_type)
            if not isinstance(block, dict):
                continue
            for device_prefixes in (block.get("prefixes") or {}).values():
                self._validate_cidr_prefixes(
                    (device_prefixes or {}).get("prefixes") or [],
                    service_name,
                    f"natTranslationMode.{translation_type}",
                )

    def _resolve_global_object_ops_device_ids(self, policy_config: dict, service_name: str) -> None:
        """
        Resolve device names to device IDs in policy.globalObjectOps.

        globalObjectOps keys are device names (e.g. "edge-1-sdktest"); the API expects
        device IDs as keys. Each value can contain routingPolicyOps to attach Graphiant
        filters (e.g. "Policy-DC1-Primary": "Attach") per device.

        Args:
            policy_config (dict): Policy configuration to update (modified in place).
            service_name (str): Service name for error reporting.
        """
        if "globalObjectOps" not in policy_config or not isinstance(policy_config["globalObjectOps"], dict):
            return
        ops = policy_config["globalObjectOps"]
        resolved = {}
        for device_name, device_ops in ops.items():
            # Config file uses device names; resolve to device ID
            device_id = self.gsdk.get_device_id(str(device_name))
            if device_id is None:
                raise ConfigurationError(
                    f"Device '{device_name}' not found for service '{service_name}' "
                    "(globalObjectOps keys must be device names)."
                )
            resolved[str(device_id)] = device_ops
        policy_config["globalObjectOps"] = resolved

    def _validate_global_object_ops_routing_policies(
        self, policy_config: dict, service_name: str, existing_policy_names=None
    ) -> None:
        """
        Validate that all Graphiant routing policy (filter) names referenced in
        policy.globalObjectOps.routingPolicyOps exist in the portal.

        Args:
            policy_config: Policy config containing globalObjectOps.
            service_name: Service name for error reporting.
            existing_policy_names: Optional set of policy names that exist in the portal.
                When provided, the API is not called (caller should fetch once and reuse).
        Raises ConfigurationError if any policy name is missing.
        """
        if "globalObjectOps" not in policy_config or not isinstance(policy_config["globalObjectOps"], dict):
            return
        policy_names: Set[str] = set()
        for device_ops in policy_config["globalObjectOps"].values():
            if not isinstance(device_ops, dict):
                continue
            rops = device_ops.get("routingPolicyOps") or {}
            if isinstance(rops, dict):
                policy_names.update(rops.keys())
        if not policy_names:
            return
        if existing_policy_names is not None:
            existing_names = existing_policy_names
        else:
            try:
                summaries = self.gsdk.get_global_routing_policy_summaries()
                existing_names = {s.get("name") for s in summaries if s.get("name")}
            except Exception as e:
                LOG.warning("Could not fetch global routing policy summaries for validation: %s", e)
                return
        missing = sorted(policy_names - existing_names)
        if missing:
            raise ConfigurationError(
                f"Graphiant routing policy (filter) not found for service '{service_name}': {', '.join(missing)}. "
                "Create the filter with graphiant_global_config (configure_graphiant_filters) "
                "or ensure the policy name exists in the portal."
            )

    @staticmethod
    def _label(entity_id: int, names_by_id: Optional[Dict[int, str]]) -> str:
        """Render "name (id)" if a name is known, else just "id", for error messages."""
        name = (names_by_id or {}).get(entity_id)
        return f"'{name}' ({entity_id})" if name else str(entity_id)

    def _validate_sites_and_devices_for_lan_segment(
        self,
        policy_config: dict,
        service_name: str,
        site_map_cache: Optional[Dict[int, dict]] = None,
        site_names_by_id: Optional[Dict[int, str]] = None,
        device_names_by_id: Optional[Dict[int, str]] = None,
        lan_segment_names_by_id: Optional[Dict[int, str]] = None,
    ) -> None:
        """
        Validate that configured sites belong to the LAN segment, and that any edge devices
        referenced in natTranslationMode belong to one of the configured sites.

        Requires policy_config["serviceLanSegment"] and site IDs under policy_config["site"]/
        ["sites"] to already be resolved to IDs (see _resolve_site_ids), and any
        natTranslationMode device keys to already be resolved to device IDs (see
        _resolve_nat_translation_device_ids).

        Args:
            policy_config (dict): Resolved policy configuration.
            service_name (str): Service name for error reporting.
            site_map_cache: Optional dict of {lan_segment_id: site/device map} shared across
                services being processed in the same run, to avoid refetching per service.
            site_names_by_id, device_names_by_id, lan_segment_names_by_id: Optional
                {id: name} maps (as populated by _resolve_site_ids/_resolve_nat_translation_device_ids
                and the caller's LAN segment resolution) used to render names instead of raw
                IDs in error messages. IDs with no known name fall back to the raw ID.

        Raises ConfigurationError on a mismatch.
        """
        lan_segment_id = policy_config.get("serviceLanSegment")
        if not isinstance(lan_segment_id, int):
            return

        selected_site_ids: Set[int] = set()
        for key in ("site", "sites"):
            for entry in policy_config.get(key) or []:
                for site_id in entry.get("sites") or []:
                    if isinstance(site_id, int):
                        selected_site_ids.add(site_id)
        if not selected_site_ids:
            return

        if site_map_cache is not None and lan_segment_id in site_map_cache:
            site_map = site_map_cache[lan_segment_id]
        else:
            site_map = self.gsdk.get_lan_segment_site_device_map(lan_segment_id)
            if site_map_cache is not None:
                site_map_cache[lan_segment_id] = site_map

        site_ids_on_segment = ((site_map.get("lanSegmentIds") or {}).get(str(lan_segment_id)) or {}).get(
            "siteIds"
        ) or {}
        devices_by_site: Dict[int, Set[int]] = {}
        # Device hostnames from the API response, used as a fallback name source below when
        # the device wasn't resolved from a config name (e.g. it was given as a raw ID).
        hostname_by_device_id: Dict[int, str] = {}
        for site_id_str, site_data in site_ids_on_segment.items():
            device_ids = set()
            for entry in site_data.get("lanSegmentExists") or []:
                device_id = entry.get("deviceId")
                device_ids.add(device_id)
                if device_id is not None and entry.get("hostname"):
                    hostname_by_device_id[device_id] = entry["hostname"]
            devices_by_site[int(site_id_str)] = device_ids
        device_labels_by_id = {**hostname_by_device_id, **(device_names_by_id or {})}

        lan_segment_label = self._label(lan_segment_id, lan_segment_names_by_id)

        missing_sites = sorted(selected_site_ids - devices_by_site.keys())
        if missing_sites:
            site_labels = [self._label(sid, site_names_by_id) for sid in missing_sites]
            raise ConfigurationError(
                f"Service '{service_name}': site(s) {site_labels} are not part of LAN segment {lan_segment_label}."
            )

        nat_mode = policy_config.get("natTranslationMode")
        if not isinstance(nat_mode, dict):
            return
        referenced_device_ids: Set[int] = set()
        for translation_type in ("centralized", "decentralized"):
            block = nat_mode.get(translation_type)
            if not isinstance(block, dict):
                continue
            for device_id_str in block.get("prefixes") or {}:
                try:
                    referenced_device_ids.add(int(device_id_str))
                except (TypeError, ValueError):
                    continue
        if not referenced_device_ids:
            return

        allowed_device_ids: Set[int] = set()
        for site_id in selected_site_ids:
            allowed_device_ids.update(devices_by_site.get(site_id) or set())

        invalid_devices = sorted(referenced_device_ids - allowed_device_ids)
        if invalid_devices:
            device_labels = [self._label(did, device_labels_by_id) for did in invalid_devices]
            site_labels = [self._label(sid, site_names_by_id) for sid in sorted(selected_site_ids)]
            raise ConfigurationError(
                f"Service '{service_name}': edge device(s) {device_labels} in natTranslationMode do not belong "
                f"to the selected site(s) {site_labels} for LAN segment {lan_segment_label}."
            )

    def get_services_summary(self) -> Dict[str, Any]:
        """
        Get summary of all Data Exchange services.

        Returns:
            dict: Services summary response
        """
        try:
            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            LOG.info("Retrieving Data Exchange services summary")
            response = self.gsdk.get_data_exchange_services_summary()

            # Display services in a nice table format
            if response.info:
                service_table = []
                for service in response.info:
                    # Get publisher/subscriber role
                    role = "Publisher" if getattr(service, "is_publisher", False) else "Subscriber"

                    # Get matched customers count
                    matched_customers = getattr(service, "matched_customers", 0)

                    service_table.append(
                        [
                            service.id,
                            service.name,
                            getattr(service, "type", "") or "",
                            service.status,
                            role,
                            matched_customers,
                        ]
                    )

                LOG.info(
                    "Services Summary:\n%s",
                    tabulate(
                        service_table,
                        headers=["ID", "Service Name", "Type", "Status", "Role", "Customers"],
                        tablefmt="grid",
                    ),
                )

            return response.to_dict()
        except Exception as e:
            LOG.error("Failed to retrieve services summary: %s", e)
            raise ConfigurationError(f"Failed to retrieve services summary: {e}")

    def get_service_by_name(self, service_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific Data Exchange service by name.

        Args:
            service_name (str): Name of the service to retrieve

        Returns:
            dict or None: Service details if found, None otherwise
        """
        try:
            LOG.info("Retrieving Data Exchange service '%s'", service_name)
            service = self.gsdk.get_data_exchange_service_by_name(service_name)
            return service
        except Exception as e:
            LOG.error("Failed to retrieve service '%s': %s", service_name, e)
            raise ConfigurationError(f"Failed to retrieve service '{service_name}': {e}")

    def create_customers(self, config_yaml_file: str, diff_mode: bool = False) -> dict:
        """
        Create a new Data Exchange customer from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file
            diff_mode (bool): When True, fetch existing customer details to detect email
                drift and populate diff_plan. Only set when the caller requested --diff output.

        Returns:
            dict: Result with 'changed' status and lists of created/skipped items
        """
        result: Dict[str, Any] = {"changed": False, "created": [], "skipped": [], "drifted": [], "diff_plan": []}

        try:
            LOG.info("Creating Data Exchange customer from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or "data_exchange_customers" not in config_data:
                LOG.info("No data_exchange_customers configuration found in YAML file")
                return result

            customers = config_data["data_exchange_customers"]
            if not isinstance(customers, list):
                raise ConfigurationError("Configuration error: 'data_exchange_customers' must be a list.")

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            for customer_config in customers:
                customer_name = customer_config.get("name")
                LOG.info("--------------------------------")
                LOG.info("create_customers: Creating customer '%s'", customer_name)
                if not customer_name:
                    raise ConfigurationError("Configuration error: Each customer must have a 'name' field.")

                # Check if customer already exists
                existing_customer = self.gsdk.get_data_exchange_customer_by_name(customer_name)
                if existing_customer:
                    LOG.info(
                        "Customer '%s' already exists (ID: %s), skipping creation", customer_name, existing_customer.id
                    )
                    # Drift detection: only when --diff requested (avoids extra API call otherwise)
                    # "adminEmail" (singular) is the legacy key; "adminEmails" (plural) matches
                    # the current API field name directly — both are accepted.
                    invite_config = customer_config.get("invite") or {}
                    desired_emails = invite_config.get("adminEmail") or invite_config.get("adminEmails") or []
                    if diff_mode and desired_emails:
                        try:
                            current_details = self.gsdk.get_data_exchange_customer_details(existing_customer.id)
                            current_emails = current_details.get("emails") or []
                            if sorted(current_emails) != sorted(desired_emails):
                                LOG.info(
                                    "Customer '%s' has drifted emails (use update_customers to apply)",
                                    customer_name,
                                )
                                result["diff_plan"].append(
                                    {
                                        "device": customer_name,
                                        "branch": "adminEmail (existing - use update_customers to apply)",
                                        "before": {"adminEmail": current_emails},
                                        "after": {"adminEmail": desired_emails},
                                    }
                                )
                                result["drifted"].append(customer_name)
                        except Exception as e:
                            LOG.warning("Could not fetch details for drift detection on '%s': %s", customer_name, e)
                    result["skipped"].append(customer_name)
                    continue

                # Create customer directly
                LOG.info("Customer configuration: %s", customer_config)
                LOG.info("create_data_exchange_customers: Creating customer '%s'", customer_name)
                result["diff_plan"].append(
                    {
                        "device": customer_name,
                        "branch": "create",
                        "before": {},
                        "after": customer_config,
                    }
                )
                self.gsdk.create_data_exchange_customers(customer_config)
                LOG.info("Successfully created customer '%s'", customer_name)
                result["created"].append(customer_name)
                result["changed"] = True

            LOG.info(
                "Data Exchange customer creation completed: %s created, %s skipped (changed: %s)",
                len(result["created"]),
                len(result["skipped"]),
                result["changed"],
            )
            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to create Data Exchange customer: %s", e)
            raise ConfigurationError(f"Data Exchange customer creation failed: {e}")

    def update_customers(self, config_yaml_file: str) -> dict:
        """
        Update existing Data Exchange customers from YAML configuration.

        Only ``invite.adminEmails`` (the email list; ``invite.adminEmail``, singular, is
        accepted as a legacy alias) can be updated. The customer must already exist.
        Supports check mode and diff output.

        Args:
            config_yaml_file (str): Path to the YAML configuration file.
                Each customer entry requires ``name`` and ``invite.adminEmails``.

        Returns:
            dict: Result with 'changed' status and lists of updated/skipped items
        """
        result: Dict[str, Any] = {"changed": False, "updated": [], "skipped": [], "diff_plan": []}

        try:
            LOG.info("Updating Data Exchange customers from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or "data_exchange_customers" not in config_data:
                LOG.info("No data_exchange_customers configuration found in YAML file")
                return result

            customers = config_data["data_exchange_customers"]
            if not isinstance(customers, list):
                raise ConfigurationError("Configuration error: 'data_exchange_customers' must be a list.")

            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            for customer_config in customers:
                customer_name = customer_config.get("name")
                LOG.info("--------------------------------")
                LOG.info("update_customers: Updating customer '%s'", customer_name)
                if not customer_name:
                    raise ConfigurationError("Configuration error: Each customer must have a 'name' field.")

                # Customer must exist to be updated
                existing_customer = self.gsdk.get_data_exchange_customer_by_name(customer_name)
                if not existing_customer:
                    raise ConfigurationError(
                        f"Customer '{customer_name}' not found. " "Use create_customers to create new customers."
                    )
                customer_id = existing_customer.id

                # Desired emails from config. "adminEmail" (singular) is the legacy key;
                # "adminEmails" (plural) matches the current API field name directly — both
                # are accepted.
                invite_config = customer_config.get("invite") or {}
                desired_emails = invite_config.get("adminEmail") or invite_config.get("adminEmails") or []
                if not desired_emails:
                    raise ConfigurationError(
                        f"Customer '{customer_name}': 'invite.adminEmail' (or 'invite.adminEmails') is required for "
                        "update_customers and must contain at least one email address."
                    )

                # Get current customer details for comparison
                current_details = self.gsdk.get_data_exchange_customer_details(customer_id)
                current_emails = current_details.get("emails") or []
                num_sites = current_details.get("numSites", 0)

                # Normalize for idempotency comparison
                if sorted(current_emails) == sorted(desired_emails):
                    LOG.info("Customer '%s' emails unchanged, skipping update", customer_name)
                    result["skipped"].append(customer_name)
                    continue

                # Record diff
                result["diff_plan"].append(
                    {
                        "device": customer_name,
                        "branch": "adminEmail",
                        "before": {"adminEmail": current_emails},
                        "after": {"adminEmail": desired_emails},
                    }
                )

                # Build PUT payload
                update_payload = {
                    "id": customer_id,
                    "status": "",
                    "invite": {
                        "adminEmail": desired_emails,
                        "maximumNumberOfSites": num_sites,
                    },
                }

                LOG.info("update_customers: Update payload for '%s': %s", customer_name, update_payload)
                self.gsdk.edit_data_exchange_customer(customer_id, update_payload)
                LOG.info("Successfully updated customer '%s' (ID: %s)", customer_name, customer_id)
                result["updated"].append(customer_name)
                result["changed"] = True

            LOG.info(
                "Data Exchange customer update completed: %s updated, %s skipped (changed: %s)",
                len(result["updated"]),
                len(result["skipped"]),
                result["changed"],
            )
            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to update Data Exchange customer: %s", e)
            raise ConfigurationError(f"Data Exchange customer update failed: {e}")

    def get_customers_summary(self) -> Dict[str, Any]:
        if not HAS_TABULATE:
            raise ImportError("tabulate is required for this method. Install it with: pip install tabulate")
        """
        Get summary of all Data Exchange customers.

        Returns:
            dict: Customers summary response
        """
        try:
            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            LOG.info("Retrieving Data Exchange customers summary")
            response = self.gsdk.get_data_exchange_customers_summary()

            # Display customers in a nice table format
            if response.customers:
                customer_table = []
                for customer in response.customers:
                    # Get customer type (Non-Graphiant or Graphiant)
                    customer_type = "Non-Graphiant" if customer.type == "non_graphiant_peer" else "Graphiant"

                    # Get matched services count
                    matched_services = getattr(customer, "matched_services", 0)

                    customer_table.append(
                        [customer.id, customer.name, customer_type, customer.status, matched_services]
                    )

                LOG.info(
                    "Customers Summary:\n%s",
                    tabulate(
                        customer_table,
                        headers=["ID", "Customer Name", "Customer Type", "Status", "Matched Services"],
                        tablefmt="grid",
                    ),
                )

            return response.to_dict()
        except Exception as e:
            LOG.error("Failed to retrieve customers summary: %s", e)
            raise ConfigurationError(f"Failed to retrieve customers summary: {e}")

    def get_customer_by_name(self, customer_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific Data Exchange customer by name.

        Args:
            customer_name (str): Name of the customer to retrieve

        Returns:
            dict or None: Customer details if found, None otherwise
        """
        try:
            LOG.info("Retrieving Data Exchange customer '%s'", customer_name)
            customer = self.gsdk.get_data_exchange_customer_by_name(customer_name)
            return customer
        except Exception as e:
            LOG.error("Failed to retrieve customer '%s': %s", customer_name, e)
            raise ConfigurationError(f"Failed to retrieve customer '{customer_name}': {e}")

    def delete_customers(self, config_yaml_file: str) -> dict:
        """
        Delete Data Exchange customers from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file

        Returns:
            dict: Result with 'changed' status and lists of deleted/skipped items
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": []}

        try:
            LOG.info("Deleting Data Exchange customers from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or "data_exchange_customers" not in config_data:
                LOG.info("No data_exchange_customers configuration found in YAML file")
                return result

            customers = config_data["data_exchange_customers"]
            if not isinstance(customers, list):
                raise ConfigurationError("Configuration error: 'data_exchange_customers' must be a list.")

            customer_names = [c.get("name") for c in customers if c.get("name")]
            LOG.info("Attempting to delete Data Exchange customers: %s", customer_names)
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            for customer_config in customers:
                customer_name = customer_config.get("name")
                LOG.info("--------------------------------")
                LOG.info("delete_customers: Deleting customer '%s'", customer_name)
                if not customer_name:
                    raise ConfigurationError("Configuration error: Each customer must have a 'name' field.")

                # Get customer ID
                customer = self.gsdk.get_data_exchange_customer_by_name(customer_name)
                if not customer:
                    LOG.info("Customer '%s' not found, skipping deletion", customer_name)
                    result["skipped"].append(customer_name)
                    continue

                # Delete customer directly
                LOG.info("delete_data_exchange_customer: Deleting customer '%s'", customer_name)
                self.gsdk.delete_data_exchange_customer(customer.id)
                LOG.info("Successfully deleted customer '%s' (ID: %s)", customer_name, customer.id)
                result["deleted"].append(customer_name)
                result["changed"] = True

            LOG.info(
                "Data Exchange customer deletion completed: %s deleted, %s skipped (changed: %s)",
                len(result["deleted"]),
                len(result["skipped"]),
                result["changed"],
            )
            LOG.info("Deconfigure completed: deleted=%s, skipped=%s", result["deleted"], result["skipped"])
            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to delete Data Exchange customers: %s", e)
            raise ConfigurationError(f"Data Exchange customer deletion failed: {e}")

    def delete_services(self, config_yaml_file: str) -> dict:
        """
        Delete Data Exchange services from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file

        Returns:
            dict: Result with 'changed' status and lists of deleted/skipped items
        """
        result: Dict[str, Any] = {"changed": False, "deleted": [], "skipped": []}

        try:
            LOG.info("Deleting Data Exchange services from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or "data_exchange_services" not in config_data:
                LOG.info("No data_exchange_services configuration found in YAML file")
                return result

            services = config_data["data_exchange_services"]
            if not isinstance(services, list):
                raise ConfigurationError("Configuration error: 'data_exchange_services' must be a list.")

            service_names = [s.get("serviceName") for s in services if s.get("serviceName")]
            LOG.info("Attempting to delete Data Exchange services: %s", service_names)
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            for service_config in services:
                service_name = service_config.get("serviceName")
                LOG.info("--------------------------------")
                LOG.info("delete_services: Deleting service '%s'", service_name)
                if not service_name:
                    raise ConfigurationError("Configuration error: Each service must have a 'serviceName' field.")

                # Get service ID
                service = self.gsdk.get_data_exchange_service_by_name(service_name)
                if not service:
                    LOG.info("Service '%s' not found, skipping deletion", service_name)
                    result["skipped"].append(service_name)
                    continue

                # Delete service directly
                LOG.info("delete_data_exchange_service: Deleting service '%s'", service_name)
                self.gsdk.delete_data_exchange_service(service.id)
                LOG.info("Successfully deleted service '%s' (ID: %s)", service_name, service.id)
                result["deleted"].append(service_name)
                result["changed"] = True

            LOG.info(
                "Data Exchange service deletion completed: %s deleted, %s skipped (changed: %s)",
                len(result["deleted"]),
                len(result["skipped"]),
                result["changed"],
            )
            LOG.info("Deconfigure completed: deleted=%s, skipped=%s", result["deleted"], result["skipped"])
            return result

        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to delete Data Exchange services: %s", e)
            raise ConfigurationError(f"Data Exchange service deletion failed: {e}")

    def get_service_details(self, service_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a specific Data Exchange service.

        Args:
            service_id (int): ID of the service to retrieve

        Returns:
            dict: Service details response
        """
        try:
            LOG.info("Retrieving Data Exchange service details for ID: %s", service_id)
            response = self.gsdk.get_data_exchange_service_details(service_id)
            return response
        except Exception as e:
            LOG.error("Failed to retrieve service details for ID %s: %s", service_id, e)
            raise ConfigurationError(f"Failed to retrieve service details for ID {service_id}: {e}")

    def _save_match_service_to_customer_responses(self, match_responses: list, config_yaml_file: str) -> None:
        """
        Save match service to customer responses to JSON files.
        Updates existing entries if they match (customer_name, service_name), otherwise appends new entries.

        Args:
            match_responses (list): List of match response dictionaries
            config_yaml_file (str): Path to the YAML configuration file to determine output directory
        """
        if not match_responses:
            return

        import json
        from datetime import datetime

        # Resolve config file path using the same logic as render_config_file
        # Handle absolute paths
        if os.path.isabs(config_yaml_file):
            resolved_config_file = config_yaml_file
        else:
            # Handle relative paths by concatenating with config_path
            # Security: Normalize path to prevent path traversal attacks
            resolved_config_file = os.path.normpath(os.path.join(self.config_utils.config_path, config_yaml_file))
            # Security: Validate that resolved path is within config_path to prevent path traversal
            config_path_real = os.path.realpath(self.config_utils.config_path)
            resolved_config_file_real = os.path.realpath(resolved_config_file)
            if not resolved_config_file_real.startswith(config_path_real):
                raise ConfigurationError(
                    f"Security: Path traversal detected. Config file path '{config_yaml_file}' "
                    f"resolves outside config directory."
                )

        # Create output directory near the config file (same logic as render_config_file)
        output_dir = os.path.join(os.path.dirname(resolved_config_file), "output")
        os.makedirs(output_dir, exist_ok=True)

        # Generate output filenames based on input config
        base_name = os.path.splitext(os.path.basename(resolved_config_file))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create two files: one with timestamp, one with _latest suffix
        timestamped_file = os.path.join(output_dir, f"{base_name}_responses_{timestamp}.json")
        latest_file = os.path.join(output_dir, f"{base_name}_responses_latest.json")

        # Read existing latest file if it exists
        existing_responses = []
        if os.path.exists(latest_file):
            try:
                with open(latest_file, "r") as f:
                    existing_responses = json.load(f)
                LOG.info("Loaded %s existing entries from %s", len(existing_responses), latest_file)
            except (json.JSONDecodeError, IOError) as e:
                LOG.warning("Could not read existing latest file %s: %s. Starting fresh.", latest_file, e)

        # Create a dictionary for efficient lookup: key = (customer_name, service_name)
        # This allows us to update existing entries or add new ones
        response_dict = {}
        for entry in existing_responses:
            key = (entry.get("customer_name"), entry.get("service_name"))
            if key[0] and key[1]:  # Only add if both keys are present
                response_dict[key] = entry

        # Update or add new match responses
        updated_count = 0
        added_count = 0
        for new_response in match_responses:
            key = (new_response.get("customer_name"), new_response.get("service_name"))
            if key[0] and key[1]:
                if key in response_dict:
                    # Update existing entry
                    response_dict[key].update(new_response)
                    updated_count += 1
                    LOG.debug("Updated entry for customer '%s' and service '%s'", key[0], key[1])
                else:
                    # Add new entry
                    response_dict[key] = new_response
                    added_count += 1
                    LOG.debug("Added new entry for customer '%s' and service '%s'", key[0], key[1])

        # Convert back to list for JSON serialization
        merged_responses = list(response_dict.values())

        # Save responses to both JSON files
        with open(timestamped_file, "w") as f:
            json.dump(merged_responses, f, indent=2)

        with open(latest_file, "w") as f:
            json.dump(merged_responses, f, indent=2)

        LOG.info("Match responses saved to matches_file_with_timestamp: %s", timestamped_file)
        LOG.info("Latest match responses saved to matches_file: %s", latest_file)
        LOG.info(
            "Updated %s existing entries, added %s new entries. Total entries in matches_file: %s",
            updated_count,
            added_count,
            len(merged_responses),
        )

    def match_service_to_customers(self, config_yaml_file: str) -> dict:
        """
        Match Data Exchange services to customers from YAML configuration.

        Args:
            config_yaml_file (str): Path to the YAML configuration file

        Returns:
            dict: Result with 'changed' status and lists of matched/skipped items
        """
        result: Dict[str, Any] = {"changed": False, "matched": [], "skipped": [], "failed": []}

        try:
            LOG.info("Matching Data Exchange services to customers from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            if not config_data or "data_exchange_matches" not in config_data:
                LOG.info("No data_exchange_matches configuration found in YAML file")
                raise ConfigurationError("Configuration error: 'data_exchange_matches' key not found in YAML file.")

            matches = config_data["data_exchange_matches"]
            if not isinstance(matches, list):
                raise ConfigurationError("Configuration error: 'data_exchange_matches' must be a list.")

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            match_responses = []

            for match_config in matches:
                customer_name = match_config.get("customerName")
                service_name = match_config.get("serviceName")
                match_key = f"{service_name}->{customer_name}"
                LOG.info("--------------------------------")
                LOG.info(
                    "match_service_to_customers: Matching service '%s' to customer '%s'", service_name, customer_name
                )
                if not customer_name or not service_name:
                    LOG.error("Configuration error: Each match must have 'customerName' and 'serviceName' fields.")
                    result["failed"].append(match_key)
                    continue

                # Get customer ID
                customer = self.gsdk.get_data_exchange_customer_by_name(customer_name)
                if not customer:
                    LOG.error("Customer '%s' not found in the enterprise.", customer_name)
                    result["failed"].append(match_key)
                    continue

                # Get service ID
                service = self.gsdk.get_data_exchange_service_by_name(service_name)
                if not service:
                    LOG.error("Service '%s' not found in the enterprise.", service_name)
                    result["failed"].append(match_key)
                    continue

                # Check if service is already matched to this customer
                matched_services = self.gsdk.get_matched_services_for_customer(customer.id)
                if matched_services is not None:
                    # Check if this service is already in the matched services list
                    already_matched = False
                    for matched_service in matched_services:
                        if matched_service.name == service_name:
                            LOG.warning(
                                "Service '%s' is already matched to customer '%s'. "
                                "Service ID: %s, Matched Customers: %s. "
                                "Skipping to avoid 'match already exists' error.",
                                service_name,
                                customer_name,
                                matched_service.id,
                                matched_service.matched_customers,
                            )
                            already_matched = True
                            result["skipped"].append(match_key)

                            # Fetch match_id from API and save to matches_file for existing matches
                            # This allows recovery if matches_file is lost
                            matching_customers = self.gsdk.get_matching_customers_for_service(matched_service.id)
                            if matching_customers:
                                for match_info in matching_customers:
                                    if match_info.customer_name == customer_name and match_info.match_id:
                                        LOG.info(
                                            "Retrieved match_id %s for existing match: "
                                            "service '%s' to customer '%s'",
                                            match_info.match_id,
                                            service_name,
                                            customer_name,
                                        )
                                        match_responses.append(
                                            {
                                                "customer_name": customer_name,
                                                "service_name": service_name,
                                                "customer_id": customer.id,
                                                "service_id": matched_service.id,
                                                "match_id": match_info.match_id,
                                                "timestamp": None,
                                                "status": "matched",
                                            }
                                        )
                                        break
                            break

                    if already_matched:
                        continue

                # Use configured service prefixes (user-selected)
                service_prefixes = match_config.get("servicePrefixes", [])
                if not service_prefixes:
                    raise ConfigurationError(
                        f"Configuration error: 'servicePrefixes' must be specified "
                        f"for matching service '{service_name}' to customer '{customer_name}'."
                    )
                self._validate_cidr_prefixes(
                    [p.get("prefix") for p in service_prefixes if isinstance(p, dict)],
                    service_name,
                    "servicePrefixes",
                )

                match_service_config: Dict[str, Any] = {"id": service.id, "servicePrefixes": service_prefixes}
                service_type = getattr(service, "type", None) or "peering_service"
                if service_type == "client_to_server":
                    # client_to_server matches carry the customer's own prefixes directly,
                    # not a producer-side NAT translation (confirmed against the portal
                    # UI's own request for this case: no "nat" field at all).
                    consumer_prefixes = match_config.get("consumerPrefixes", [])
                    if not consumer_prefixes:
                        raise ConfigurationError(
                            f"Configuration error: 'consumerPrefixes' must be specified for matching "
                            f"client_to_server service '{service_name}' to customer '{customer_name}'."
                        )
                    self._validate_cidr_prefixes(consumer_prefixes, service_name, "consumerPrefixes")
                    match_service_config["consumerPrefixes"] = consumer_prefixes
                elif "natTranslationMode" in match_config:
                    # New-shape alternative to "nat" for callers who'd rather write the API
                    # shape directly, e.g. {"peerToPeer": {"prefixes": [{"prefix",
                    # "outsideNatPrefix"}]}} — passed through as-is (see
                    # gsdk.match_service_to_customer for the "nat" translation this replaces).
                    nat_translation_mode = match_config["natTranslationMode"] or {}
                    peer_to_peer_prefixes = [
                        p
                        for p in (nat_translation_mode.get("peerToPeer") or {}).get("prefixes", [])
                        if isinstance(p, dict)
                    ]
                    self._validate_cidr_prefixes(
                        [p.get("prefix") for p in peer_to_peer_prefixes if p.get("prefix")],
                        service_name,
                        "natTranslationMode.peerToPeer.prefixes",
                    )
                    self._validate_cidr_prefixes(
                        [p.get("outsideNatPrefix") for p in peer_to_peer_prefixes if p.get("outsideNatPrefix")],
                        service_name,
                        "natTranslationMode.peerToPeer.prefixes.outsideNatPrefix",
                    )
                    match_service_config["natTranslationMode"] = nat_translation_mode
                else:
                    nat_entries = [n for n in match_config.get("nat", []) if isinstance(n, dict)]
                    self._validate_cidr_prefixes(
                        [n.get("prefix") for n in nat_entries if n.get("prefix")], service_name, "nat"
                    )
                    self._validate_cidr_prefixes(
                        [n.get("outsideNatPrefix") for n in nat_entries if n.get("outsideNatPrefix")],
                        service_name,
                        "nat.outsideNatPrefix",
                    )
                    match_service_config["nat"] = match_config.get("nat", [])

                # Build match configuration for API call
                match_payload = {
                    "id": customer.id,
                    "service": match_service_config,
                }

                try:
                    # Perform the match and capture response
                    LOG.info(
                        "match_service_to_customer: Matching service '%s' to customer '%s'", service_name, customer_name
                    )
                    response = self.gsdk.match_service_to_customer(match_payload)
                except Exception as e:
                    error_msg = str(e)
                    # Handle "match already exists" errors gracefully (SDK 26.1.1+).
                    if "match already exists" in error_msg.lower():
                        LOG.info(
                            "Service '%s' is already matched to customer '%s', skipping match as it already exists.",
                            service_name,
                            customer_name,
                        )
                        result["skipped"].append(match_key)
                        continue
                    else:
                        LOG.error(
                            "Failed to match service '%s' to customer '%s': %s", service_name, customer_name, error_msg
                        )
                        result["failed"].append(match_key)
                        continue

                # Store response data for next workflow
                match_response_data = {
                    "customer_name": customer_name,
                    "service_name": service_name,
                    "customer_id": customer.id,
                    "service_id": service.id,
                    "match_id": response.match_id,
                    "timestamp": response.timestamp if hasattr(response, "timestamp") else None,
                    "status": "matched",
                }
                match_responses.append(match_response_data)
                LOG.info(
                    "Successfully matched service '%s' to customer '%s' with match_id: %s",
                    service_name,
                    customer_name,
                    response.match_id,
                )
                result["matched"].append(match_key)
                result["changed"] = True

            # Save match responses to file for next workflow (skip in check_mode to avoid writing files)
            if not getattr(self.gsdk, "check_mode", False):
                self._save_match_service_to_customer_responses(match_responses, config_yaml_file)
            else:
                LOG.info("[check_mode] Skipping write of matches file (would save %s entries)", len(match_responses))

            LOG.info(
                "Data Exchange service matching completed: %s matched, %s skipped, %s failed (changed: %s)",
                len(result["matched"]),
                len(result["skipped"]),
                len(result["failed"]),
                result["changed"],
            )
            if len(result["failed"]) > 0:
                total = len(result["matched"]) + len(result["skipped"]) + len(result["failed"])
                raise ConfigurationError(
                    f"Data Exchange service to customer matching had {len(result['failed'])} "
                    f"failures out of {total} total"
                )
            return result
        except Exception as e:
            LOG.error("Failed to match Data Exchange services to customers: %s", e)
            raise ConfigurationError(f"Data Exchange service to customer matching failed: {e}")

    @staticmethod
    def _normalize_acceptance_shape(acceptance_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translate the legacy flat accept_invitation config shape into the current API-aligned
        shape (everything nested under a single "policy" dict), so accept_invitation accepts
        either shape without requiring a config migration.

        Legacy shape (pre-26.7.0; see sample_data_exchange_acceptance_legacy.yaml): top-level
        "siteInformation", "nat", "policy" (a list of {lanSegment, consumerPrefixes}),
        "siteToSiteVpn", "globalObjectOps". Detected by "policy" being a list rather than the
        current shape's dict.

        Current shape (see sample_data_exchange_acceptance.yaml): "policy" is a dict containing
        "sites", "consumerLanSegments", "natTranslationMode", "siteToSiteVpn", "globalObjectOps".
        "routingPolicyTable" stays a top-level sibling of "policy" in both shapes.

        Args:
            acceptance_config (dict): One raw entry from data_exchange_acceptances, as loaded
                from YAML (either shape).

        Returns:
            dict: Config in the current policy-nested shape. Returned unchanged if already in
                that shape.
        """
        policy = acceptance_config.get("policy")
        if isinstance(policy, dict):
            return acceptance_config
        if policy is not None and not isinstance(policy, list):
            # Unexpected type — leave as-is so downstream validation raises a clear error.
            return acceptance_config

        legacy_consumer_lan_segments = policy or []
        site_information = acceptance_config.get("siteInformation")
        nat = acceptance_config.get("nat")
        site_to_site_vpn = acceptance_config.get("siteToSiteVpn")
        global_object_ops = acceptance_config.get("globalObjectOps")

        if not (legacy_consumer_lan_segments or site_information or nat or site_to_site_vpn or global_object_ops):
            # No legacy keys present either — likely just a missing "policy"; let downstream
            # validation raise its own clear error rather than guessing here.
            return acceptance_config

        LOG.info(
            "_normalize_acceptance_shape: Detected legacy acceptance config shape for '%s'/'%s'; "
            "translating to the current policy-nested shape (see sample_data_exchange_acceptance.yaml; "
            "sample_data_exchange_acceptance_legacy.yaml documents this legacy shape)",
            acceptance_config.get("customerName"),
            acceptance_config.get("serviceName"),
        )

        new_policy: Dict[str, Any] = {}
        if site_information is not None:
            new_policy["sites"] = site_information
        if legacy_consumer_lan_segments:
            new_policy["consumerLanSegments"] = legacy_consumer_lan_segments
        if nat:
            new_policy["natTranslationMode"] = {
                "peerToPeer": {
                    "prefixes": [{k: v for k, v in item.items() if k in ("prefix", "outsideNatPrefix")} for item in nat]
                }
            }
        if site_to_site_vpn is not None:
            new_policy["siteToSiteVpn"] = site_to_site_vpn
        if global_object_ops is not None:
            new_policy["globalObjectOps"] = global_object_ops

        normalized = {
            k: v
            for k, v in acceptance_config.items()
            if k not in ("siteInformation", "nat", "policy", "siteToSiteVpn", "globalObjectOps")
        }
        normalized["policy"] = new_policy
        return normalized

    def accept_invitation(self, config_yaml_file: str, matches_file=None, vault_bgp_md5=None, vault_psk=None) -> None:
        """
        Accept Data Exchange service invitation (Workflow 4).

        Args:
            config_yaml_file (str): Path to YAML configuration file containing acceptance details
            matches_file (str, optional): Path to matches responses JSON file for match ID lookup
            vault_bgp_md5 (dict, optional): BGP MD5 passwords keyed by customerName (from Ansible Vault)
            vault_psk (dict, optional): IPSec PSKs keyed by customerName → peer name → tunnel (from Ansible Vault)
        """
        try:
            LOG.info("accept_invitation: Loading configuration from %s", config_yaml_file)
            config_data = self.render_config_file(config_yaml_file)

            # All configurations are under 'data_exchange_acceptances' key
            if "data_exchange_acceptances" not in config_data:
                raise ConfigurationError("Configuration file must contain 'data_exchange_acceptances' key")

            acceptances = config_data["data_exchange_acceptances"]

            # Ensure it's always a list
            if not isinstance(acceptances, list):
                raise ConfigurationError("data_exchange_acceptances must be a list of acceptance configurations")

            # Accept either the current policy-nested shape or the legacy flat shape (translated
            # transparently) — see sample_data_exchange_acceptance_legacy.yaml.
            acceptances = [self._normalize_acceptance_shape(a) for a in acceptances]

            # Print current enterprise info
            LOG.info("DataExchangeManager: Current enterprise info: %s", self.gsdk.enterprise_info)

            check_mode = getattr(self.gsdk, "check_mode", False)
            if check_mode:
                LOG.info("accept_invitation: CHECK MODE - API calls will be skipped")

            # Validate gateway requirements before processing acceptances
            self._validate_gateway_requirements_for_acceptances(acceptances)

            # Validate VPN profile existence before processing acceptances
            self._validate_vpn_profiles_for_acceptances(acceptances)

            # Validate that all prefix fields are properly-aligned CIDR network addresses
            self._validate_prefixes_for_acceptances(acceptances)

            # Process acceptances and log results
            result = self._process_multiple_acceptances(
                acceptances,
                matches_file,
                config_yaml_file=config_yaml_file,
                vault_bgp_md5=vault_bgp_md5 or {},
                vault_psk=vault_psk or {},
            )

            # Log summary like other operations
            total_processed = result.get("total_processed", 0)
            total_successful = result.get("total_successful", 0)
            total_accepted = result.get("total_accepted", 0)
            total_skipped = result.get("total_skipped", 0)
            total_failed = total_processed - total_successful

            LOG.info(
                "Data Exchange invitation acceptance completed: %s accepted, %s skipped, %s failed (changed: %s)",
                total_accepted,
                total_skipped,
                total_failed,
                result.get("changed", False),
            )

            # Check if there were any failures
            if total_failed > 0:
                if check_mode:
                    LOG.error(
                        "[CHECK MODE] accept_invitation: %s out of %s invitation acceptances failed",
                        total_failed,
                        total_processed,
                    )
                    raise ConfigurationError(
                        f"[CHECK MODE] Data Exchange invitation acceptance had {total_failed} "
                        f"failures out of {total_processed} total"
                    )
                else:
                    LOG.error(
                        "accept_invitation: %s out of %s invitation acceptances failed", total_failed, total_processed
                    )
                    raise ConfigurationError(
                        f"Data Exchange invitation acceptance had {total_failed} failures "
                        f"out of {total_processed} total"
                    )
            return result
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to accept Data Exchange service invitation: %s", e)
            raise ConfigurationError(f"Data Exchange service acceptance failed: {e}")

    def _validate_gateway_requirements_for_acceptances(self, acceptances, min_gateways=2):
        """
        Validate gateway requirements for all acceptances.

        Args:
            acceptances (list): List of acceptance configurations
            min_gateways (int): Minimum number of gateways required per region
        """
        try:
            LOG.info(
                "_validate_gateway_requirements_for_acceptances: Validating gateway requirements for %s acceptances",
                len(acceptances),
            )

            # Collect unique regions from acceptances
            regions_to_validate = set()
            for acceptance in acceptances:
                site_to_site_vpn = (acceptance.get("policy") or {}).get("siteToSiteVpn") or {}
                if "region" in site_to_site_vpn:
                    regions_to_validate.add(site_to_site_vpn["region"])

            # Validate each region
            for region_name in regions_to_validate:
                edges_summary = self.gsdk.get_edges_summary_filter(region=region_name, role="gateway", status="active")
                if not edges_summary:
                    LOG.error(
                        "_validate_gateway_requirements_for_acceptances: No active gateways found in region %s",
                        region_name,
                    )
                    raise ConfigurationError(f"No active gateways found in region {region_name}")
                else:
                    LOG.info(
                        "_validate_gateway_requirements_for_acceptances: Region %s has %s active gateways",
                        region_name,
                        len(edges_summary),
                    )
                if len(edges_summary) < min_gateways:
                    LOG.error(
                        "_validate_gateway_requirements_for_acceptances: Region %s has only %s "
                        "gateways, minimum %s required",
                        region_name,
                        len(edges_summary),
                        min_gateways,
                    )
                    raise ConfigurationError(
                        f"Region {region_name} has only {len(edges_summary)} gateways,"
                        f"minimum {min_gateways} required"
                    )
                else:
                    LOG.info(
                        "_validate_gateway_requirements_for_acceptances: Region %s meets minimum gateway requirements",
                        region_name,
                    )
                # Validate tunnel terminator connection count for each gateway
                for edge_summary in edges_summary:
                    LOG.info(
                        "_validate_gateway_requirements_for_acceptances: Validating tunnel "
                        "terminator connection count for gateway %s",
                        edge_summary.hostname,
                    )
                    if hasattr(edge_summary, "tt_conn_count") and edge_summary.tt_conn_count:
                        if edge_summary.tt_conn_count < 2:
                            LOG.error(
                                "_validate_gateway_requirements_for_acceptances: Gateway %s has only "
                                "%s tunnel terminators, minimum 2 required",
                                edge_summary.hostname,
                                edge_summary.tt_conn_count,
                            )
                            raise ConfigurationError(
                                f"Gateway {edge_summary.hostname} has only "
                                f"{edge_summary.tt_conn_count} tunnel terminators, "
                                f"minimum 2 required"
                            )
                    else:
                        LOG.error(
                            "_validate_gateway_requirements_for_acceptances: "
                            "Gateway %s does not have any tunnel terminators connected, "
                            "minimum 2 required",
                            edge_summary.hostname,
                        )
                        raise ConfigurationError(
                            f"Gateway {edge_summary.hostname} does not have any "
                            f"tunnel terminators connected, minimum 2 required"
                        )
        except Exception as e:
            LOG.warning("_validate_gateway_requirements_for_acceptances: Gateway validation failed: %s", e)
            raise
            # TODO: Don't fail the entire operation for validation issues ?

    def _validate_vpn_profiles_for_acceptances(self, acceptances):
        """
        Validate VPN profile existence for all acceptances.

        Args:
            acceptances (list): List of acceptance configurations
        """
        try:
            LOG.info(
                "_validate_vpn_profiles_for_acceptances: Validating VPN profiles for %s acceptances", len(acceptances)
            )

            # Collect unique VPN profile names from acceptances
            vpn_profiles_to_validate = set()
            for acceptance in acceptances:
                site_to_site_vpn = (acceptance.get("policy") or {}).get("siteToSiteVpn") or {}
                if site_to_site_vpn:
                    if "ipsecGatewayPeers" in site_to_site_vpn:
                        # New multi-peer structure: vpnProfile is per remote peer
                        for peer in site_to_site_vpn["ipsecGatewayPeers"].get("remotePeers", []):
                            vpn_profile_name = peer.get("vpnProfile")
                            if vpn_profile_name:
                                vpn_profiles_to_validate.add(vpn_profile_name)
                    elif "ipsecGatewayDetails" in site_to_site_vpn:
                        # Legacy single-peer structure
                        ipsec_gateway_details = site_to_site_vpn["ipsecGatewayDetails"]
                        if "vpnProfile" in ipsec_gateway_details:
                            vpn_profile_name = ipsec_gateway_details["vpnProfile"]
                            if vpn_profile_name:
                                vpn_profiles_to_validate.add(vpn_profile_name)

            if not vpn_profiles_to_validate:
                LOG.info("_validate_vpn_profiles_for_acceptances: No VPN profiles found in acceptances")
                raise ConfigurationError("No VPN profiles found in acceptances")

            LOG.info(
                "_validate_vpn_profiles_for_acceptances: Validating %s VPN profiles", len(vpn_profiles_to_validate)
            )
            # Get all VPN profiles from portal
            portal_vpn_profiles = self.gsdk.get_global_ipsec_profiles()
            if not portal_vpn_profiles:
                LOG.error("_validate_vpn_profiles_for_acceptances: No VPN profiles found in portal")
                raise ConfigurationError("No VPN profiles found in portal")

            # Validate each VPN profile
            missing_profiles = []
            for vpn_profile_name in vpn_profiles_to_validate:
                if vpn_profile_name not in portal_vpn_profiles:
                    LOG.error(
                        "_validate_vpn_profiles_for_acceptances: VPN profile '%s' not found in portal", vpn_profile_name
                    )
                    missing_profiles.append(vpn_profile_name)
                else:
                    LOG.info(
                        "_validate_vpn_profiles_for_acceptances: VPN profile '%s' exists in portal", vpn_profile_name
                    )

            if missing_profiles:
                error_msg = f"The following VPN profiles are not found in the portal: " f"{', '.join(missing_profiles)}"
                LOG.error("_validate_vpn_profiles_for_acceptances: %s", error_msg)
                raise ConfigurationError(error_msg)

            LOG.info(
                "_validate_vpn_profiles_for_acceptances: All VPN profiles existence validated "
                "successfully for %s acceptances",
                len(acceptances),
            )
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.warning("_validate_vpn_profiles_for_acceptances: VPN profile validation failed: %s", e)
            raise

    def _validate_prefixes_for_acceptances(self, acceptances) -> None:
        """
        Validate that all prefix fields across acceptances are properly-aligned CIDR network
        addresses (see _validate_cidr_prefixes): policy.natTranslationMode.peerToPeer.prefixes[].
        prefix/outsideNatPrefix, policy.consumerLanSegments[].consumerPrefixes, and
        policy.siteToSiteVpn routing.static.destinationPrefix (both the legacy
        ipsecGatewayDetails and multi-peer ipsecGatewayPeers structures).

        Args:
            acceptances (list): List of acceptance configurations
        """
        for acceptance in acceptances:
            customer_name = acceptance.get("customerName")
            service_name = acceptance.get("serviceName")
            label = (
                f"{service_name}->{customer_name}"
                if service_name and customer_name
                else (customer_name or service_name or "acceptance")
            )
            policy = acceptance.get("policy") or {}

            nat_entries = [
                n
                for n in ((policy.get("natTranslationMode") or {}).get("peerToPeer") or {}).get("prefixes", [])
                if isinstance(n, dict)
            ]
            self._validate_cidr_prefixes(
                [n.get("prefix") for n in nat_entries if n.get("prefix")],
                label,
                "policy.natTranslationMode.peerToPeer.prefixes",
            )
            self._validate_cidr_prefixes(
                [n.get("outsideNatPrefix") for n in nat_entries if n.get("outsideNatPrefix")],
                label,
                "policy.natTranslationMode.peerToPeer.prefixes.outsideNatPrefix",
            )

            for lan_segment_entry in policy.get("consumerLanSegments") or []:
                if isinstance(lan_segment_entry, dict):
                    self._validate_cidr_prefixes(
                        lan_segment_entry.get("consumerPrefixes") or [],
                        label,
                        "policy.consumerLanSegments.consumerPrefixes",
                    )

            site_to_site_vpn = policy.get("siteToSiteVpn") or {}
            if "ipsecGatewayPeers" in site_to_site_vpn:
                for peer in site_to_site_vpn["ipsecGatewayPeers"].get("remotePeers", []) or []:
                    destination_prefixes = ((peer.get("routing") or {}).get("static") or {}).get(
                        "destinationPrefix"
                    ) or []
                    peer_name = peer.get("name", "")
                    self._validate_cidr_prefixes(
                        destination_prefixes,
                        label,
                        f"siteToSiteVpn.ipsecGatewayPeers.remotePeers[{peer_name}].routing.static.destinationPrefix",
                    )
            elif "ipsecGatewayDetails" in site_to_site_vpn:
                destination_prefixes = (
                    (site_to_site_vpn["ipsecGatewayDetails"].get("routing") or {}).get("static") or {}
                ).get("destinationPrefix") or []
                self._validate_cidr_prefixes(
                    destination_prefixes,
                    label,
                    "siteToSiteVpn.ipsecGatewayDetails.routing.static.destinationPrefix",
                )

    def _process_multiple_acceptances(
        self, acceptances_config, matches_file=None, config_yaml_file=None, vault_bgp_md5=None, vault_psk=None
    ):
        """
        Process multiple invitation acceptances from configuration.

        Args:
            acceptances_config (list): List of acceptance configurations
            matches_file (str, optional): Path to matches responses JSON file for match ID lookup
            config_yaml_file (str, optional): Path to the acceptance config file (used for error hints)
            vault_bgp_md5 (dict, optional): BGP MD5 passwords keyed by customerName
            vault_psk (dict, optional): IPSec PSKs keyed by customerName → peer name → tunnel

        Returns:
            dict: Combined results from all acceptances
        """
        try:
            results = []
            total_processed = 0
            total_accepted = 0
            total_skipped = 0
            check_mode = getattr(self.gsdk, "check_mode", False)

            LOG.info("_process_multiple_acceptances: Processing %s invitation acceptances", len(acceptances_config))

            # Pre-fetch all sites, site_lists, regions, and LAN segments once for faster lookups
            LOG.info("_process_multiple_acceptances: Pre-fetching sites, site_lists, regions, and LAN segments")
            sites = self.gsdk.get_sites_details()
            site_lists = self.gsdk.get_global_site_lists()
            regions = self.gsdk.get_regions()
            lan_segments = self.gsdk.get_global_lan_segments()

            # Create lookup dictionaries (name -> id) for O(1) lookups
            sites_lookup = {site.name: site.id for site in sites} if sites else {}
            site_lists_lookup = {site_list.name: site_list.id for site_list in site_lists} if site_lists else {}
            regions_lookup = {region.name: region.id for region in regions} if regions else {}
            lan_segments_lookup = {segment.name: segment.id for segment in lan_segments} if lan_segments else {}

            LOG.info(
                "_process_multiple_acceptances: Pre-fetched %s sites, %s site_lists, %s regions, and %s LAN segments",
                len(sites_lookup),
                len(site_lists_lookup),
                len(regions_lookup),
                len(lan_segments_lookup),
            )

            # Cache of already-linked match_ids per service_id (from matching-customers-summary API)
            # Prefetch per service_id on first use so we skip accept when consumer already exists
            already_linked_match_ids_by_service = {}

            for i, acceptance_config in enumerate(acceptances_config):
                total_processed += 1  # Count every acceptance (including skipped/failed) so total_failed is correct
                try:
                    LOG.info("--------------------------------")
                    LOG.info(
                        "_process_multiple_acceptances: Processing acceptance %s/%s", i + 1, len(acceptances_config)
                    )
                    LOG.info(
                        "_process_multiple_acceptances: Customer: '%s' Service: '%s'",
                        acceptance_config.get("customerName"),
                        acceptance_config.get("serviceName"),
                    )
                    # Inject vault secrets (md5Password, psk) before resolving names to IDs
                    self._inject_vault_secrets(acceptance_config, vault_bgp_md5, vault_psk)
                    # Normalize md5Password to API dict shape {"md5_password": value}
                    self._normalize_bgp_md5_password(acceptance_config)
                    # Resolve names to IDs (returns direct API payload structure)
                    resolved_config = self._resolve_acceptance_names_to_ids(
                        acceptance_config,
                        matches_file,
                        sites_lookup=sites_lookup,
                        site_lists_lookup=site_lists_lookup,
                        regions_lookup=regions_lookup,
                        lan_segments_lookup=lan_segments_lookup,
                        config_yaml_file=config_yaml_file,
                    )

                    # Extract service ID and match ID from resolved configuration
                    service_id = resolved_config["id"]  # Service ID is 'id' in API payload
                    match_id = resolved_config["matchId"]  # Match ID is 'matchId' in API payload

                    # Prefetch matching-customers-summary for this service once, then check if already linked
                    if service_id not in already_linked_match_ids_by_service:
                        info = self.gsdk.get_matching_customers_for_service(service_id)
                        match_ids = set()
                        if info:
                            LOG.info(
                                "_process_multiple_acceptances: get_matching_customers_for_service for service %s: %s",
                                service_id,
                                info,
                            )
                            for item in info:
                                mid = getattr(item, "match_id", None) or getattr(item, "matchId", None)
                                status = getattr(item, "status", None) or getattr(item, "Status", None)
                                # Only treat as already-linked if status is ACTIVE (already accepted).
                                # get_matching_customers_for_service now calls the generic extranet
                                # producer API (graphiant-sdk >= 26.7.0), which appears to use
                                # "EXTRANET_SERVICE_STATUS_ACTIVE" rather than the older
                                # "B2B_PEERING_SERVICE_STATUS_ACTIVE" — check both until confirmed
                                # live against a tenant.
                                if mid is not None and status in (
                                    "B2B_PEERING_SERVICE_STATUS_ACTIVE",
                                    "EXTRANET_SERVICE_STATUS_ACTIVE",
                                ):
                                    match_ids.add(mid)
                        already_linked_match_ids_by_service[service_id] = match_ids
                        LOG.info(
                            "_process_multiple_acceptances: Service %s has %s already-linked customer(s)",
                            service_id,
                            len(match_ids),
                        )

                    if match_id in already_linked_match_ids_by_service[service_id]:
                        LOG.info(
                            "_process_multiple_acceptances: Customer '%s' already linked to service '%s' "
                            "(match_id=%s) - skipping",
                            acceptance_config.get("customerName"),
                            acceptance_config.get("serviceName"),
                            match_id,
                        )
                        results.append(
                            {
                                "customer_name": acceptance_config.get("customerName"),
                                "service_name": acceptance_config.get("serviceName"),
                                "result": {"message": "Consumer already linked to service - skipped (idempotent)"},
                                "status": "skipped",
                            }
                        )
                        total_skipped += 1
                        continue

                    # Validate required fields in resolved configuration. "natTranslationMode" is
                    # intentionally not required here — it's peering_service-only; client_to_server
                    # acceptances omit it entirely (see accept_data_exchange_service).
                    for field in ("id", "policy", "matchId"):
                        if field not in resolved_config or resolved_config[field] is None:
                            raise ConfigurationError(f"Missing required field '{field}' in resolved configuration")
                    resolved_policy_fields = resolved_config["policy"]
                    for field in ("sites", "consumerLanSegments", "siteToSiteVpn"):
                        if field not in resolved_policy_fields or resolved_policy_fields[field] is None:
                            raise ConfigurationError(
                                f"Missing required field 'policy.{field}' in resolved configuration"
                            )

                    # Use the resolved configuration directly as the API payload
                    acceptance_payload = resolved_config

                    LOG.info(
                        "_process_multiple_acceptances: Acceptance payload for '%s' and '%s': %s",
                        acceptance_config.get("customerName"),
                        acceptance_config.get("serviceName"),
                        redact_sensitive_for_log(acceptance_payload),
                    )

                    # Call the acceptance API (gsdk no-ops and logs payload when check_mode is True)
                    response = self.gsdk.accept_data_exchange_service(match_id, acceptance_payload)
                    if callable(getattr(response, "to_dict", None)):
                        result = response.to_dict()
                    else:
                        result: Dict[str, Any] = {
                            "check_mode": True,
                            "message": "API call skipped in check mode",
                            "payload_validated": True,
                            "match_id": match_id,
                            "service_id": service_id,
                        }

                    results.append(
                        {
                            "customer_name": acceptance_config.get("customerName"),
                            "service_name": acceptance_config.get("serviceName"),
                            "result": result,
                            "status": "success" if not check_mode else "check_mode",
                        }
                    )
                    total_accepted += 1

                except Exception as e:
                    error_str = str(e)
                    # Check for "consumer already exists" error - treat as idempotent success
                    if "consumer already exists" in error_str:
                        LOG.info(
                            "_process_multiple_acceptances: Consumer already exists for '%s' and '%s' - "
                            "skipping (idempotent)",
                            acceptance_config.get("customerName"),
                            acceptance_config.get("serviceName"),
                        )
                        results.append(
                            {
                                "customer_name": acceptance_config.get("customerName"),
                                "service_name": acceptance_config.get("serviceName"),
                                "result": {"message": "Consumer already exists - skipped (idempotent)"},
                                "status": "skipped",
                            }
                        )
                        total_skipped += 1  # Count as skipped for idempotency
                    else:
                        LOG.error("_process_multiple_acceptances: Failed to process acceptance %s: %s", i + 1, e)
                        results.append(
                            {
                                "customer_name": acceptance_config.get("customerName"),
                                "service_name": acceptance_config.get("serviceName"),
                                "error": error_str,
                                "status": "failed",
                            }
                        )

            total_successful = total_accepted + total_skipped  # Both are considered successful
            # Report actual or would-change status: in check mode, changed=True when we would have accepted
            changed = total_accepted > 0
            LOG.info(
                "_process_multiple_acceptances: Completed %s/%s acceptances successfully "
                "(%s accepted, %s skipped, changed: %s)",
                total_successful,
                total_processed,
                total_accepted,
                total_skipped,
                changed,
            )

            return {
                "changed": changed,
                "total_processed": total_processed,
                "total_successful": total_successful,
                "total_accepted": total_accepted,
                "total_skipped": total_skipped,
                "results": results,
            }

        except Exception as e:
            LOG.error("Failed to process multiple acceptances: %s", e)
            raise ConfigurationError(f"Multiple acceptance processing failed: {e}")

    def _inject_vault_secrets(self, acceptance_config, vault_bgp_md5, vault_psk):
        """
        Inject md5Password and psk from vault when YAML value is null/absent.
        Precedence: YAML non-null wins; vault fills null/absent; API auto-fills any psk still null after.
        Lookup key = customerName.
        """
        customer_name = acceptance_config.get("customerName", "")
        site_to_site_vpn = (acceptance_config.get("policy") or {}).get("siteToSiteVpn", {})
        ipsec_peers = site_to_site_vpn.get("ipsecGatewayPeers", {})

        # md5Password: YAML wins if non-null, vault fills null/absent
        routing = ipsec_peers.get("routing", {}) if isinstance(ipsec_peers, dict) else {}
        bgp = routing.get("bgp") if isinstance(routing, dict) else None
        if isinstance(bgp, dict) and bgp.get("md5Password") is None:
            vault_md5 = (vault_bgp_md5 or {}).get(customer_name)
            if vault_md5:
                bgp["md5Password"] = {"md5_password": vault_md5}
                LOG.debug("_inject_vault_secrets: Injected md5Password for customer '%s' from vault", customer_name)

        # psk: YAML wins if non-null, vault fills null (API auto-fills remaining nulls via _fill_missing_tunnel_values)
        vault_psk_customer = (vault_psk or {}).get(customer_name, {})
        if vault_psk_customer and isinstance(ipsec_peers, dict):
            for peer in ipsec_peers.get("remotePeers", []):
                peer_name = peer.get("name", "")
                peer_vault = vault_psk_customer.get(peer_name, {})
                for tunnel_key in ("tunnel1", "tunnel2"):
                    tunnel = peer.get(tunnel_key, {})
                    if isinstance(tunnel, dict) and tunnel.get("psk") is None:
                        psk_val = peer_vault.get(tunnel_key)
                        if psk_val:
                            tunnel["psk"] = psk_val
                            LOG.debug(
                                "_inject_vault_secrets: Injected psk for customer '%s' peer '%s' %s from vault",
                                customer_name,
                                peer_name,
                                tunnel_key,
                            )

    def _normalize_bgp_md5_password(self, acceptance_config):
        """
        Normalize md5Password to the API dict shape {"md5_password": value}.

        Accepts a plain string (from YAML) or a dict with either "md5_password" or
        "md5Password" as the key; leaves None untouched.
        """
        site_to_site_vpn = (acceptance_config.get("policy") or {}).get("siteToSiteVpn", {})
        ipsec_peers = site_to_site_vpn.get("ipsecGatewayPeers", {})
        routing = ipsec_peers.get("routing", {}) if isinstance(ipsec_peers, dict) else {}
        bgp = routing.get("bgp") if isinstance(routing, dict) else None
        if not isinstance(bgp, dict):
            return
        md5_val = bgp.get("md5Password")
        if md5_val is None:
            return
        if isinstance(md5_val, str):
            bgp["md5Password"] = {"md5_password": md5_val}
        elif isinstance(md5_val, dict) and "md5_password" not in md5_val:
            # Normalize camelCase key → snake_case
            plain = md5_val.get("md5Password")
            if plain is not None:
                bgp["md5Password"] = {"md5_password": plain}

    def _fill_missing_tunnel_values(self, acceptance_config, region_id, lan_segment_id):
        """
        Fill in missing tunnel configuration values using Graphiant portal APIs.

        Args:
            acceptance_config (dict): The acceptance configuration
            region_id (int): The region ID for subnet allocation
            lan_segment_id (int): The LAN segment ID for subnet allocation

        Returns:
            dict: Updated acceptance configuration with filled values
        """
        try:
            site_to_site_vpn = (acceptance_config.get("policy") or {}).get("siteToSiteVpn", {})

            if "ipsecGatewayPeers" in site_to_site_vpn:
                peers = site_to_site_vpn["ipsecGatewayPeers"].get("remotePeers", [])
                tunnels = [(peer.get(k, {}), k) for peer in peers for k in ("tunnel1", "tunnel2")]
            else:
                gw = site_to_site_vpn.get("ipsecGatewayDetails", {})
                tunnels = [(gw.get(k, {}), k) for k in ("tunnel1", "tunnel2")]

            for tunnel, tunnel_key in tunnels:
                if "insideIpv4Cidr" in tunnel and tunnel["insideIpv4Cidr"] is None:
                    ipv4_subnet = self.gsdk.get_ipsec_inside_subnet(region_id, lan_segment_id, "ipv4")
                    if ipv4_subnet:
                        tunnel["insideIpv4Cidr"] = ipv4_subnet
                        LOG.info("_fill_missing_tunnel_values: Filled %s ipv4Cidr", tunnel_key)
                if "insideIpv6Cidr" in tunnel and tunnel["insideIpv6Cidr"] is None:
                    ipv6_subnet = self.gsdk.get_ipsec_inside_subnet(region_id, lan_segment_id, "ipv6")
                    if ipv6_subnet:
                        tunnel["insideIpv6Cidr"] = ipv6_subnet
                        LOG.info("_fill_missing_tunnel_values: Filled %s ipv6Cidr", tunnel_key)
                if tunnel.get("psk") is None:
                    psk = self.gsdk.get_preshared_key()
                    if psk:
                        tunnel["psk"] = psk
                        LOG.info("_fill_missing_tunnel_values: Filled %s psk", tunnel_key)

            return acceptance_config

        except Exception as e:
            LOG.error("_fill_missing_tunnel_values: Error filling tunnel values: %s", e)
            return acceptance_config

    def _resolve_acceptance_names_to_ids(
        self,
        acceptance_config,
        matches_file=None,
        sites_lookup=None,
        site_lists_lookup=None,
        regions_lookup=None,
        lan_segments_lookup=None,
        config_yaml_file=None,
    ):
        """
        Resolve names to IDs for acceptance configuration.

        Args:
            acceptance_config (dict): Acceptance configuration with names
            matches_file (str, optional): Path to matches responses JSON file for match ID lookup
            sites_lookup (dict, optional): Pre-fetched dictionary mapping site names to IDs
            site_lists_lookup (dict, optional): Pre-fetched dictionary mapping site list names to IDs
            regions_lookup (dict, optional): Pre-fetched dictionary mapping region names to IDs
            lan_segments_lookup (dict, optional): Pre-fetched dictionary mapping LAN segment names to IDs
            config_yaml_file (str, optional): Path to acceptance config file (used for error hints)

        Returns:
            dict: Resolved configuration with IDs
        """
        try:
            customer_name = acceptance_config.get("customerName")
            service_name = acceptance_config.get("serviceName")

            if not customer_name or not service_name:
                raise ConfigurationError("customer_name and service_name are required in acceptance configuration")

            LOG.info(
                "_resolve_acceptance_names_to_ids: Resolving names for customer '%s' and service '%s'",
                customer_name,
                service_name,
            )

            # Get match ID and service ID from customer name and service name combination
            # This is important because a customer can be matched to multiple services
            match_data = self._get_match_id_from_customer_service(customer_name, service_name, matches_file)

            if not match_data:
                if not matches_file:
                    import glob
                    import os

                    config_dir = os.path.dirname(config_yaml_file) if config_yaml_file else None
                    resolved_config_dir = (
                        os.path.join(self.config_utils.config_path, config_dir) if config_dir else None
                    )
                    suggested_dir = os.path.join(config_dir, "output") if config_dir else None
                    # Look for existing *_responses_latest.json files to give a concrete suggestion
                    existing_files = (
                        glob.glob(os.path.join(resolved_config_dir, "output", "*_responses_latest.json"))
                        if resolved_config_dir
                        else []
                    )
                    if existing_files:
                        # Show relative paths (relative to config_dir) for brevity
                        file_suggestions = ", ".join(
                            os.path.join(suggested_dir, os.path.basename(f)) for f in sorted(existing_files)
                        )
                        matches_hint = f"-e matches_file={file_suggestions}"
                    elif suggested_dir:
                        matches_hint = f"-e matches_file={suggested_dir}/<matches>_responses_latest.json"
                    else:
                        matches_hint = "-e matches_file=<path_to_matches_responses_latest.json>"
                    raise ConfigurationError(
                        f"No match found for customer '{customer_name}' and service '{service_name}'. "
                        f"The service is not visible via API in this tenant (it may not have been shared yet "
                        f"or match_id lookup requires the matches file). "
                        f"Provide the matches file saved by the match_service_to_customers step: {matches_hint}"
                    )
                raise ConfigurationError(f"No match found for customer '{customer_name}' and service '{service_name}'")

            match_id = match_data.get("match_id")
            service_id = match_data.get("service_id")

            if not match_id or not service_id:
                raise ConfigurationError(
                    f"Invalid match data for customer " f"'{customer_name}' and service '{service_name}'"
                )

            policy_config = acceptance_config.get("policy") or {}

            # Resolve site names to IDs using pre-fetched lookup or API call
            site_names = (policy_config.get("sites") or [{}])[0].get("sites", [])
            site_ids = []
            for site_name in site_names:
                if sites_lookup and site_name in sites_lookup:
                    site_id = sites_lookup[site_name]
                else:
                    site_id = self.gsdk.get_site_id(site_name)
                if site_id:
                    site_ids.append(site_id)
                else:
                    raise ConfigurationError(f"Site '{site_name}' not found")

            # Resolve site list names to IDs using pre-fetched lookup or API call
            site_list_names = (policy_config.get("sites") or [{}])[0].get("siteLists", [])
            site_list_ids = []
            for site_list_name in site_list_names:
                if site_lists_lookup and site_list_name in site_lists_lookup:
                    site_list_id = site_lists_lookup[site_list_name]
                else:
                    site_list_id = self.gsdk.get_site_list_id(site_list_name)
                if site_list_id:
                    site_list_ids.append(site_list_id)
                else:
                    raise ConfigurationError(f"Site list '{site_list_name}' not found")

            # Resolve LAN segment name to ID using pre-fetched lookup or API call
            lan_segment_name = (policy_config.get("consumerLanSegments") or [{}])[0].get("lanSegment")
            lan_segment_id = None
            if lan_segment_name:
                if lan_segments_lookup and lan_segment_name in lan_segments_lookup:
                    lan_segment_id = lan_segments_lookup[lan_segment_name]
                else:
                    lan_segment_id = self.gsdk.get_lan_segment_id(lan_segment_name)
                if not lan_segment_id:
                    raise ConfigurationError(f"LAN segment '{lan_segment_name}' not found")

            # Resolve region name to ID using pre-fetched lookup or API call
            source_site_to_site_vpn = policy_config.get("siteToSiteVpn") or {}
            region_name = source_site_to_site_vpn.get("region")
            region_id = None
            if region_name:
                if regions_lookup and region_name in regions_lookup:
                    region_id = regions_lookup[region_name]
                else:
                    region_id = self.gsdk.get_region_id_by_name(region_name)
                if not region_id:
                    raise ConfigurationError(f"Region '{region_name}' not found")

            # Build resolved acceptance configuration in API payload format
            # Update siteToSiteVpn to include resolved regionId and emails
            site_to_site_vpn = source_site_to_site_vpn.copy()
            if region_id:
                site_to_site_vpn["regionId"] = region_id
            # Ensure emails are included in siteToSiteVpn
            if "emails" in source_site_to_site_vpn:
                site_to_site_vpn["emails"] = source_site_to_site_vpn.get("emails", [])

            resolved_policy: Dict[str, Any] = {
                "sites": [{"sites": site_ids, "siteLists": site_list_ids}],
                "consumerLanSegments": {
                    str(lan_segment_id): {
                        "consumerPrefixes": (policy_config.get("consumerLanSegments") or [{}])[0].get(
                            "consumerPrefixes", []
                        )
                    }
                },
                "siteToSiteVpn": site_to_site_vpn,
                "globalObjectOps": policy_config.get("globalObjectOps", {}),
            }
            nat_translation_mode = policy_config.get("natTranslationMode")
            if nat_translation_mode:
                resolved_policy["natTranslationMode"] = nat_translation_mode

            resolved_config = {
                "id": service_id,  # Service ID for API payload
                "policy": resolved_policy,
                "routingPolicyTable": acceptance_config.get("routingPolicyTable", []),
                "matchId": match_id,
            }

            # Resolve device names to device IDs in globalObjectOps (Graphiant filter attachment)
            context_name = f"{customer_name}/{service_name}"
            global_object_ops_like = {"globalObjectOps": resolved_policy["globalObjectOps"]}
            self._resolve_global_object_ops_device_ids(global_object_ops_like, context_name)
            self._validate_global_object_ops_routing_policies(global_object_ops_like, context_name)
            resolved_policy["globalObjectOps"] = global_object_ops_like["globalObjectOps"]

            # Fill in missing tunnel values using Graphiant portal APIs
            resolved_config = self._fill_missing_tunnel_values(resolved_config, region_id, lan_segment_id)

            LOG.info(
                "_resolve_acceptance_names_to_ids: Resolved service_id=%s, match_id=%s, region_id=%s",
                service_id,
                match_id,
                region_id,
            )
            return resolved_config

        except Exception as e:
            LOG.error("Failed to resolve names to IDs: %s", e)
            raise ConfigurationError(f"Name resolution failed: {e}")

    def _get_match_id_from_customer_service(self, customer_name, service_name, matches_file=None):
        """
        Get match ID and service ID from customer name and service name.
        Reads from matches_file (mandatory). If match_id is missing but service_id exists,
        uses API to lookup match_id.

        Args:
            customer_name (str): Customer name
            service_name (str): Service name
            matches_file (str): Path to matches responses JSON file (mandatory)

        Returns:
            dict: Dictionary containing match_id and service_id, or None if not found
        """
        import json
        import os

        # Step 1: If matches_file is not provided, try to find service_id via API
        if not matches_file:
            LOG.info(
                "_get_match_id_from_customer_service: No matches_file provided, "
                "trying to find service via API for customer '%s' and service '%s'",
                customer_name,
                service_name,
            )
            # Try to get service by name - may exist if other invitations were already accepted
            service = self.gsdk.get_data_exchange_service_by_name(service_name)
            if service:
                LOG.info(
                    "_get_match_id_from_customer_service: Found service '%s' with ID %s via API",
                    service_name,
                    service.id,
                )
                return self._lookup_match_id_from_api(customer_name, service_name, service.id)
            else:
                LOG.error(
                    "_get_match_id_from_customer_service: Service '%s' not found via API and "
                    "no matches_file provided",
                    service_name,
                )
                return None

        # Step 2: Read from matches_file
        try:
            # Apply path resolution logic for provided path
            if os.path.isabs(matches_file):
                # Absolute path - use as is
                resolved_matches_file = matches_file
            else:
                # Relative path - resolve using config_path (same as render_config_file)
                # Security: Normalize path to prevent path traversal attacks
                resolved_matches_file = os.path.normpath(os.path.join(self.config_utils.config_path, matches_file))
                # Security: Validate that resolved path is within config_path to prevent path traversal
                config_path_real = os.path.realpath(self.config_utils.config_path)
                matches_file_real = os.path.realpath(resolved_matches_file)
                if not matches_file_real.startswith(config_path_real):
                    raise ConfigurationError(
                        "Security: Path traversal detected. Matches file path resolves outside config directory."
                    )

            if not os.path.exists(resolved_matches_file):
                LOG.error("_get_match_id_from_customer_service: Matches file not found at %s", resolved_matches_file)
                return None

            LOG.info("_get_match_id_from_customer_service: Reading matches from %s", resolved_matches_file)
            with open(resolved_matches_file, "r") as f:
                matches_data = json.load(f)

            # Find matching customer and service
            for match in matches_data:
                if match.get("customer_name") == customer_name and match.get("service_name") == service_name:
                    match_id = match.get("match_id")
                    service_id = match.get("service_id")

                    # If both match_id and service_id exist, return them
                    if match_id and service_id:
                        LOG.info(
                            "_get_match_id_from_customer_service: Found match_id %s and service_id %s "
                            "for customer '%s' and service '%s' from matches_file",
                            match_id,
                            service_id,
                            customer_name,
                            service_name,
                        )
                        return {"match_id": match_id, "service_id": service_id}

                    # If only service_id exists (no match_id), use API to get match_id
                    if service_id and not match_id:
                        LOG.info(
                            "_get_match_id_from_customer_service: Found service_id %s but no match_id "
                            "for customer '%s' and service '%s', looking up match_id via API...",
                            service_id,
                            customer_name,
                            service_name,
                        )
                        return self._lookup_match_id_from_api(customer_name, service_name, service_id)

                    LOG.warning(
                        "_get_match_id_from_customer_service: Entry found but missing service_id "
                        "for customer '%s' and service '%s'",
                        customer_name,
                        service_name,
                    )
                    return None

            # No match found in matches_file, try API as fallback
            LOG.info(
                "_get_match_id_from_customer_service: No match found in matches_file for "
                "customer '%s' and service '%s', trying API lookup...",
                customer_name,
                service_name,
            )
            service = self.gsdk.get_data_exchange_service_by_name(service_name)
            if service:
                LOG.info(
                    "_get_match_id_from_customer_service: Found service '%s' with ID %s via API",
                    service_name,
                    service.id,
                )
                return self._lookup_match_id_from_api(customer_name, service_name, service.id)
            else:
                LOG.warning("_get_match_id_from_customer_service: Service '%s' not found via API", service_name)
                return None

        except Exception as e:
            LOG.error("_get_match_id_from_customer_service: Error reading matches file: %s", e)
            return None

    def _lookup_match_id_from_api(self, customer_name, service_name, service_id):
        """
        Lookup match_id from API using service_id.

        Args:
            customer_name (str): Customer name
            service_name (str): Service name
            service_id (int): Service ID

        Returns:
            dict: Dictionary containing match_id and service_id, or None if not found
        """
        try:
            LOG.info(
                "_lookup_match_id_from_api: Looking up match_id via API for "
                "customer '%s', service '%s', service_id %s",
                customer_name,
                service_name,
                service_id,
            )

            # Get matching customers for this service (includes match_id)
            matching_customers = self.gsdk.get_matching_customers_for_service(service_id)
            if matching_customers:
                for match_info in matching_customers:
                    if match_info.customer_name == customer_name and match_info.match_id:
                        LOG.info(
                            "_lookup_match_id_from_api: Found match_id %s for customer '%s' "
                            "and service '%s' via API",
                            match_info.match_id,
                            customer_name,
                            service_name,
                        )
                        return {"match_id": match_info.match_id, "service_id": service_id}

            LOG.warning(
                "_lookup_match_id_from_api: No match found via API for customer '%s' and service '%s'",
                customer_name,
                service_name,
            )
            return None

        except Exception as e:
            LOG.error("_lookup_match_id_from_api: Error during API lookup: %s", e)
            return None

    def get_service_health(self, service_name, is_provider=False):
        """
        Get service health monitoring information.

        Args:
            service_name (str): The service name
            is_provider (bool): Whether this is a provider view

        Returns:
            dict: Service health data
        """
        try:
            LOG.info("get_service_health: Retrieving health for service %s", service_name)

            # Get service ID from service name
            service_id = self.gsdk.get_data_exchange_service_id_by_name(service_name)
            if not service_id:
                raise ConfigurationError(f"Service '{service_name}' not found")

            LOG.info("get_service_health: Found service ID %s for service '%s'", service_id, service_name)
            response = self.gsdk.get_service_health(service_id, is_provider)

            if response and hasattr(response, "service_health"):
                health_table = []
                for health in response.service_health:
                    health_table.append(
                        [
                            health.customer_name,
                            health.overall_health,
                            health.producer_prefix_health.health,
                            health.customer_prefix_health.health,
                        ]
                    )

                LOG.info(
                    "Service Health:\n%s",
                    tabulate(
                        health_table,
                        headers=["Customer", "Overall", "Producer Prefixes", "Customer Prefixes"],
                        tablefmt="grid",
                    ),
                )

            return response.to_dict() if response else {}

        except Exception as e:
            LOG.error("Failed to retrieve service health: %s", e)
            raise ConfigurationError(f"Service health retrieval failed: {e}")
