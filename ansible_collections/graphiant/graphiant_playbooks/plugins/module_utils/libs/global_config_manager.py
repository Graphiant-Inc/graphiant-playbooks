"""
Global Configuration Manager for Graphiant Playbooks.

This module handles global configuration management including
prefix sets, routing policies, SNMP, syslog, IPFIX, and VPN profiles.
"""

from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError

LOG = setup_logger()


class GlobalConfigManager(BaseManager):
    """
    Manages global configuration objects.

    Handles the configuration and deconfiguration of global objects
    such as prefix sets, routing policies, and system services.
    """

    def configure(self, config_yaml_file: str) -> None:
        """
        Configure global objects based on the provided YAML file.

        This method handles the configuration of all global objects including:
        - Prefix sets (global_prefix_sets)
        - BGP filters (routing_policies)
        - SNMP global objects (snmps)
        - Syslog global objects (syslog_servers)
        - IPFIX global objects (ipfix_exporters)
        - VPN profile global objects (vpn_profiles)
        - LAN segments (lan_segments)
        - Site lists (site_lists)

        Args:
            config_yaml_file: Path to the YAML file containing global configurations

        Raises:
            ConfigurationError: If configuration processing fails
        """
        try:
            config_data = self.render_config_file(config_yaml_file)

            # Configure prefix sets
            if 'global_prefix_sets' in config_data:
                self.configure_prefix_sets(config_yaml_file)

            # Configure routing policies (BGP filters)
            if 'routing_policies' in config_data:
                self.configure_bgp_filters(config_yaml_file)

            # Configure SNMP global objects (SNMPv3 NoAuthNoPriv, SNMPv3 AuthNoPriv, SNMPv3 AuthPriv, SNMPv2c)
            if 'snmps' in config_data:
                self.configure_snmp_services(config_yaml_file)

            # Configure syslog global objects (Global Syslog Server)
            if 'syslog_servers' in config_data:
                self.configure_syslog_services(config_yaml_file)

            # Configure IPFIX global objects (Global IPFIX Exporter)
            if 'ipfix_exporters' in config_data:
                self.configure_ipfix_services(config_yaml_file)

            # Configure VPN profiles (Global VPN Profile)
            if 'vpn_profiles' in config_data:
                self.configure_vpn_profiles(config_yaml_file)

            # Configure LAN segments (Global LAN Segments)
            if 'lan_segments' in config_data:
                self.configure_lan_segments(config_yaml_file)

            # Configure site lists (Global Site Lists)
            if 'site_lists' in config_data:
                self.configure_site_lists(config_yaml_file)

        except Exception as e:
            LOG.error("Error in global configuration: %s", str(e))
            raise ConfigurationError(f"Global configuration failed: {str(e)}")

    def deconfigure(self, config_yaml_file: str) -> None:
        """
        Deconfigure global objects based on the provided YAML file.

        This method handles the deconfiguration of all global objects including:
        - Prefix sets (global_prefix_sets)
        - BGP filters (routing_policies)
        - SNMP global objects (snmps)
        - Syslog global objects (syslog_servers)
        - IPFIX global objects (ipfix_exporters)
        - VPN profile global objects (vpn_profiles)
        - LAN segments (lan_segments)
        - Site lists (site_lists)

        Args:
            config_yaml_file: Path to the YAML file containing global configurations

        Raises:
            ConfigurationError: If configuration processing fails
        """
        try:
            config_data = self.render_config_file(config_yaml_file)

            # Deconfigure prefix sets (Global Prefix Sets)
            if 'global_prefix_sets' in config_data:
                self.deconfigure_prefix_sets(config_yaml_file)

            # Deconfigure routing policies (BGP filters)
            if 'routing_policies' in config_data:
                self.deconfigure_bgp_filters(config_yaml_file)

            # Deconfigure SNMP global objects (SNMPv3 NoAuthNoPriv, SNMPv3 AuthNoPriv, SNMPv3 AuthPriv, SNMPv2c)
            if 'snmps' in config_data:
                self.deconfigure_snmp_services(config_yaml_file)

            # Deconfigure syslog global objects (Global Syslog Server)
            if 'syslog_servers' in config_data:
                self.deconfigure_syslog_services(config_yaml_file)

            # Deconfigure IPFIX global objects (Global IPFIX Exporter)
            if 'ipfix_exporters' in config_data:
                self.deconfigure_ipfix_services(config_yaml_file)

            # Deconfigure VPN profile global objects (Global VPN Profile)
            if 'vpn_profiles' in config_data:
                self.deconfigure_vpn_profiles(config_yaml_file)

            # Deconfigure LAN segments (Global LAN Segments)
            if 'lan_segments' in config_data:
                self.deconfigure_lan_segments(config_yaml_file)

            # Deconfigure site lists (Global Site Lists)
            if 'site_lists' in config_data:
                self.deconfigure_site_lists(config_yaml_file)

        except Exception as e:
            LOG.error("Error in global deconfiguration: %s", str(e))
            raise ConfigurationError(f"Global deconfiguration failed: {str(e)}")

    def configure_prefix_sets(self, config_yaml_file: str) -> None:
        """Configure global prefix sets.

        Args:
            config_yaml_file: Path to the YAML file containing prefix set configurations
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            prefix_sets = config_data.get('global_prefix_sets', [])

            if not prefix_sets:
                LOG.info("No prefix sets found in configuration file")
                return

            config_payload = {"global_prefix_sets": {}}

            for prefix_config in prefix_sets:
                self.config_utils.global_prefix_set(config_payload, action="add", **prefix_config)

            LOG.info("Configure prefix sets payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s prefix sets", len(prefix_sets))
        except Exception as e:
            LOG.error("Failed to configure prefix sets: %s", e)
            raise ConfigurationError(f"Prefix sets configuration failed: {e}")

    def deconfigure_prefix_sets(self, config_yaml_file: str) -> None:
        """Deconfigure global prefix sets.

        Args:
            config_yaml_file: Path to the YAML file containing prefix set configurations to remove
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            prefix_sets = config_data.get('global_prefix_sets', [])

            if not prefix_sets:
                LOG.info("No prefix sets found in configuration file")
                return

            config_payload = {"global_prefix_sets": {}}

            for prefix_config in prefix_sets:
                self.config_utils.global_prefix_set(config_payload, action="delete", **prefix_config)

            LOG.info("Deconfigure prefix sets payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully deconfigured %s prefix sets", len(prefix_sets))
        except Exception as e:
            LOG.error("Failed to deconfigure prefix sets: %s", e)
            raise ConfigurationError(f"Prefix sets deconfiguration failed: {e}")

    def configure_bgp_filters(self, config_yaml_file: str) -> None:
        """Configure global BGP filters.

        Args:
            config_yaml_file: Path to the YAML file containing BGP filter configurations
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            routing_policies = config_data.get('routing_policies', [])

            if not routing_policies:
                LOG.info("No BGP filters found in configuration file")
                return

            config_payload = {"routing_policies": {}}

            for policy_config in routing_policies:
                self.config_utils.global_bgp_filter(config_payload, action="add", **policy_config)

            LOG.info("Configure BGP filters payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s BGP filters", len(routing_policies))
        except Exception as e:
            LOG.error("Failed to configure BGP filters: %s", e)
            raise ConfigurationError(f"BGP filters configuration failed: {e}")

    def deconfigure_bgp_filters(self, config_yaml_file: str) -> None:
        """Deconfigure global BGP filters.

        Args:
            config_yaml_file: Path to the YAML file containing BGP filter configurations to remove
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            routing_policies = config_data.get('routing_policies', [])

            if not routing_policies:
                LOG.info("No BGP filters found in configuration file")
                return

            config_payload = {"routing_policies": {}}

            for policy_config in routing_policies:
                self.config_utils.global_bgp_filter(config_payload, action="delete", **policy_config)

            LOG.info("Deconfigure BGP filters payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully deconfigured %s BGP filters", len(routing_policies))
        except Exception as e:
            LOG.error("Failed to deconfigure BGP filters: %s", e)
            raise ConfigurationError(f"BGP filters deconfiguration failed: {e}")

    def configure_snmp_services(self, config_yaml_file: str) -> None:
        """Configure global SNMP services.

        Args:
            config_yaml_file: Path to the YAML file containing SNMP service configurations
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            snmp_services = config_data.get('snmps', [])

            if not snmp_services:
                LOG.info("No SNMP services found in configuration file")
                return

            config_payload = {"snmps": {}}

            for snmp_config in snmp_services:
                self.config_utils.global_snmp(config_payload, action="add", **snmp_config)

            LOG.debug("Configure SNMP services payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s SNMP global objects", len(snmp_services))
        except Exception as e:
            LOG.error("Failed to configure SNMP services: %s", e)
            raise ConfigurationError(f"SNMP services configuration failed: {e}")

    def deconfigure_snmp_services(self, config_yaml_file: str) -> None:
        """Deconfigure global SNMP services.

        Args:
            config_yaml_file: Path to the YAML file containing SNMP service configurations to remove
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            snmp_services = config_data.get('snmps', [])

            if not snmp_services:
                LOG.info("No SNMP services found in configuration file")
                return

            config_payload = {"snmps": {}}

            for snmp_config in snmp_services:
                self.config_utils.global_snmp(config_payload, action="delete", **snmp_config)

            LOG.debug("Deconfigure SNMP services payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully deconfigured %s SNMP global objects", len(snmp_services))
        except Exception as e:
            LOG.error("Failed to deconfigure SNMP services: %s", e)
            raise ConfigurationError(f"SNMP services deconfiguration failed: {e}")

    def configure_syslog_services(self, config_yaml_file: str) -> None:
        """Configure global syslog services.

        Args:
            config_yaml_file: Path to the YAML file containing syslog service configurations
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            syslog_services = config_data.get('syslog_servers', [])

            if not syslog_services:
                LOG.info("No syslog services found in configuration file")
                return

            config_payload = {"syslog_servers": {}}

            for syslog_config in syslog_services:
                self.config_utils.global_syslog(config_payload, action="add", **syslog_config)

            LOG.debug("Configure syslog services payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s syslog global objects", len(syslog_services))
        except Exception as e:
            LOG.error("Failed to configure syslog services: %s", e)
            raise ConfigurationError(f"Syslog services configuration failed: {e}")

    def deconfigure_syslog_services(self, config_yaml_file: str) -> None:
        """Deconfigure global syslog services.

        Args:
            config_yaml_file: Path to the YAML file containing syslog service configurations to remove
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            syslog_services = config_data.get('syslog_servers', [])

            if not syslog_services:
                LOG.info("No syslog services found in configuration file")
                return

            config_payload = {"syslog_servers": {}}

            for syslog_config in syslog_services:
                self.config_utils.global_syslog(config_payload, action="delete", **syslog_config)

            LOG.debug("Deconfigure syslog services payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully deconfigured %s syslog global objects", len(syslog_services))
        except Exception as e:
            LOG.error("Failed to deconfigure syslog services: %s", e)
            raise ConfigurationError(f"Syslog services deconfiguration failed: {e}")

    def configure_ipfix_services(self, config_yaml_file: str) -> None:
        """Configure global IPFIX services.

        Args:
            config_yaml_file: Path to the YAML file containing IPFIX service configurations
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            ipfix_services = config_data.get('ipfix_exporters', [])

            if not ipfix_services:
                LOG.info("No IPFIX services found in configuration file")
                return

            config_payload = {"ipfix_exporters": {}}

            for ipfix_config in ipfix_services:
                self.config_utils.global_ipfix(config_payload, action="add", **ipfix_config)

            LOG.debug("Configure IPFIX services payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s IPFIX global objects", len(ipfix_services))
        except Exception as e:
            LOG.error("Failed to configure IPFIX services: %s", e)
            raise ConfigurationError(f"IPFIX services configuration failed: {e}")

    def deconfigure_ipfix_services(self, config_yaml_file: str) -> None:
        """Deconfigure global IPFIX services.

        Args:
            config_yaml_file: Path to the YAML file containing IPFIX service configurations to remove
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            ipfix_services = config_data.get('ipfix_exporters', [])

            if not ipfix_services:
                LOG.info("No IPFIX services found in configuration file")
                return

            config_payload = {"ipfix_exporters": {}}

            for ipfix_config in ipfix_services:
                self.config_utils.global_ipfix(config_payload, action="delete", **ipfix_config)

            LOG.debug("Deconfigure IPFIX services payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully deconfigured %s IPFIX global objects", len(ipfix_services))
        except Exception as e:
            LOG.error("Failed to deconfigure IPFIX services: %s", e)
            raise ConfigurationError(f"IPFIX services deconfiguration failed: {e}")

    def configure_vpn_profiles(self, config_yaml_file: str) -> None:
        """Configure global VPN profiles.

        Args:
            config_yaml_file: Path to the YAML file containing VPN profile configurations
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            vpn_profiles = config_data.get('vpn_profiles', [])

            if not vpn_profiles:
                LOG.info("No VPN profiles found in configuration file")
                return

            config_payload = {"vpn_profiles": {}}

            for vpn_config in vpn_profiles:
                self.config_utils.global_vpn_profile(config_payload, action="add", **vpn_config)

            LOG.info("Configure VPN profiles payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully configured %s VPN profiles", len(vpn_profiles))
        except Exception as e:
            LOG.error("Failed to configure VPN profiles: %s", e)
            raise ConfigurationError(f"VPN profiles configuration failed: {e}")

    def deconfigure_vpn_profiles(self, config_yaml_file: str) -> None:
        """Deconfigure global VPN profiles.

        Args:
            config_yaml_file: Path to the YAML file containing VPN profile configurations to remove
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            vpn_profiles = config_data.get('vpn_profiles', [])

            if not vpn_profiles:
                LOG.info("No VPN profiles found in configuration file")
                return

            config_payload = {"vpn_profiles": {}}

            for vpn_config in vpn_profiles:
                self.config_utils.global_vpn_profile(config_payload, action="delete", **vpn_config)

            LOG.debug("Deconfigure VPN profiles payload: %s", config_payload)
            self.gsdk.patch_global_config(**config_payload)
            LOG.info("Successfully deconfigured %s VPN profiles", len(vpn_profiles))
        except Exception as e:
            LOG.error("Failed to deconfigure VPN profiles: %s", e)
            raise ConfigurationError(f"VPN profiles deconfiguration failed: {e}")

    def configure_lan_segments(self, config_yaml_file: str) -> None:
        """Configure global LAN segments.

        Args:
            config_yaml_file: Path to the YAML file containing LAN segment configurations
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            lan_segments = config_data.get('lan_segments', [])

            if not lan_segments:
                LOG.info("No LAN segments found in configuration file")
                return

            # Get existing LAN segments to check if they already exist
            existing_segments = self.gsdk.get_global_lan_segments()
            existing_names = {segment.name for segment in existing_segments}

            for segment_config in lan_segments:
                segment_name = segment_config.get('name')
                segment_description = segment_config.get('description', '')

                if segment_name in existing_names:
                    LOG.info("LAN segment '%s' already exists, skipping creation", segment_name)
                else:
                    LOG.info("Creating LAN segment: %s", segment_name)
                    response = self.gsdk.post_global_lan_segments(
                        name=segment_name,
                        description=segment_description
                    )
                    LOG.info("Successfully created LAN segment '%s' with ID: %s", segment_name, response.id)

            LOG.info("Successfully processed %s LAN segments", len(lan_segments))
        except Exception as e:
            LOG.error("Failed to configure LAN segments: %s", e)
            raise ConfigurationError(f"LAN segment configuration failed: {e}")

    def deconfigure_lan_segments(self, config_yaml_file: str) -> None:
        """Deconfigure global LAN segments.

        Args:
            config_yaml_file: Path to the YAML file containing LAN segment configurations to remove
        """
        try:
            config_data = self.render_config_file(config_yaml_file)
            lan_segments = config_data.get('lan_segments', [])

            if not lan_segments:
                LOG.info("No LAN segments found in configuration file")
                return

            # Get existing LAN segments to find IDs for deletion
            existing_segments = self.gsdk.get_global_lan_segments()
            segments_by_name = {segment.name: segment for segment in existing_segments}

            deleted_count = 0
            skipped_count = 0

            for segment_config in lan_segments:
                segment_name = segment_config.get('name')

                if segment_name in segments_by_name:
                    segment = segments_by_name[segment_name]
                    # Check if segment has any references before deletion
                    if segment.site_list_references == 0 and segment.edge_references == 0 and \
                            segment.associated_interfaces == 0:
                        LOG.info("Deleting LAN segment '%s' (ID: %s) - no references found", segment_name, segment.id)
                        try:
                            success = self.gsdk.delete_global_lan_segments(segment.id)
                            if success:
                                LOG.info("Successfully deleted LAN segment '%s'", segment_name)
                                deleted_count += 1
                            else:
                                LOG.warning("Failed to delete LAN segment '%s'", segment_name)
                                skipped_count += 1
                        except Exception as delete_error:
                            LOG.warning("Failed to delete LAN segment '%s': %s", segment_name, delete_error)
                            skipped_count += 1
                    else:
                        LOG.error("Cannot delete LAN segment '%s' - has references: siteListReferences=%s, edgeReferences=%s, associatedInterfaces=%s",
                                  segment_name, segment.site_list_references, segment.edge_references, segment.associated_interfaces)
                        skipped_count += 1
                else:
                    LOG.info("LAN segment '%s' not found, skipping deletion", segment_name)
                    skipped_count += 1

            LOG.info("LAN segments deconfiguration completed: %s deleted, %s skipped", deleted_count, skipped_count)
        except Exception as e:
            LOG.error("Failed to deconfigure LAN segments: %s", e)
            raise ConfigurationError(f"LAN segment deconfiguration failed: {e}")

    def configure_site_lists(self, config_yaml_file: str) -> None:
        """
        Configure global site lists from YAML file.
        Args:
            config_yaml_file: Path to the YAML file containing site list configurations
        """
        try:
            LOG.info("Configuring global site lists from %s", config_yaml_file)

            # Load and parse YAML configuration
            try:
                config_data = self.config_utils.render_config_file(config_yaml_file)
            except ConfigurationError as e:
                # Re-raise configuration errors with better context
                raise ConfigurationError(f"Configuration file error: {str(e)}")
            if not config_data or 'site_lists' not in config_data:
                LOG.info("No site_lists configuration found in YAML file")
                return

            site_lists = config_data['site_lists']
            if not isinstance(site_lists, list):
                raise ConfigurationError("Configuration error: 'site_lists' must be a list. "
                                         "Please check your YAML file structure.")

            created_count = 0
            skipped_count = 0

            for site_list_config in site_lists:
                site_list_name = site_list_config.get('name')
                if not site_list_name:
                    raise ConfigurationError("Configuration error: Each site list must have a 'name' field. "
                                             "Please check your YAML file structure.")

                # Check if site list already exists
                existing_site_list_id = self.gsdk.get_site_list_id(site_list_name)
                if existing_site_list_id:
                    LOG.info("Site list '%s' already exists (ID: %s), skipping creation", site_list_name, existing_site_list_id)
                    skipped_count += 1
                    continue

                # Get site IDs for the sites in the site list
                site_names = site_list_config.get('sites', [])
                site_ids = []

                for site_name in site_names:
                    site_id = self.gsdk.get_site_id(site_name)
                    if site_id:
                        site_ids.append(site_id)
                        LOG.info("Added site '%s' (ID: %s) to site list '%s'", site_name, site_id, site_list_name)
                    else:
                        raise ConfigurationError(f"Site '{site_name}' not found for site list '{site_list_name}'. "
                                                 "Please ensure all sites exist before creating site lists.")

                if not site_ids:
                    LOG.warning("No valid sites found for site list '%s', skipping creation", site_list_name)
                    skipped_count += 1
                    continue

                # Use template approach for consistency with other global config methods
                config_payload = {"site_lists": {}}
                self.config_utils.global_site_list(
                    config_payload,
                    action="add",
                    name=site_list_name,
                    description=site_list_config.get('description', ''),
                    site_ids=site_ids
                )

                # Create the site list using the generated payload
                site_list_payload = config_payload['site_lists'][site_list_name]
                self.gsdk.create_global_site_list(site_list_payload)
                LOG.info("Successfully created site list '%s'", site_list_name)
                created_count += 1

            LOG.info("Site lists configuration completed: %s created, %s skipped", created_count, skipped_count)
        except ConfigurationError:
            raise
        except Exception as e:
            LOG.error("Failed to configure site lists: %s", e)
            raise ConfigurationError(f"Site list configuration failed: {e}")

    def deconfigure_site_lists(self, config_yaml_file: str) -> None:
        """
        Deconfigure global site lists from YAML file.
        """
        try:
            LOG.info("Deconfiguring global site lists from %s", config_yaml_file)

            # Load and parse YAML configuration
            config_data = self.config_utils.render_config_file(config_yaml_file)
            if not config_data or 'site_lists' not in config_data:
                LOG.info("No site_lists configuration found in YAML file")
                return

            site_lists = config_data['site_lists']
            if not isinstance(site_lists, list):
                raise ConfigurationError("Configuration error: 'site_lists' must be a list. "
                                         "Please check your YAML file structure.")

            deleted_count = 0
            skipped_count = 0

            for site_list_config in site_lists:
                site_list_name = site_list_config.get('name')
                if not site_list_name:
                    raise ConfigurationError("Configuration error: Each site list must have a 'name' field. "
                                             "Please check your YAML file structure.")

                # Check if site list exists
                site_list_id = self.gsdk.get_site_list_id(site_list_name)
                if not site_list_id:
                    LOG.info("Site list '%s' not found, skipping deletion", site_list_name)
                    skipped_count += 1
                    continue

                # Check if site list is in use
                site_list_details = self.gsdk.get_global_site_list(site_list_id)
                if (hasattr(site_list_details,
                            'site_list_references') and site_list_details.site_list_references > 0) or \
                   (hasattr(site_list_details, 'edge_references') and site_list_details.edge_references > 0) or \
                   (hasattr(site_list_details, 'policy_references') and site_list_details.policy_references > 0):
                    LOG.error("Cannot delete site list '%s' - has references: "
                              "siteListReferences=%s, edgeReferences=%s, policyReferences=%s",
                              site_list_name,
                              getattr(site_list_details, 'site_list_references', 0),
                              getattr(site_list_details, 'edge_references', 0),
                              getattr(site_list_details, 'policy_references', 0))
                    raise ConfigurationError(f"Site list '{site_list_name}' "
                                             "cannot be deleted because it has active references. "
                                             "Please remove all references before deletion.")

                # Delete the site list
                self.gsdk.delete_global_site_list(site_list_id)
                LOG.info("Successfully deleted site list '%s' (ID: %s)", site_list_name, site_list_id)
                deleted_count += 1

            LOG.info("Site lists deconfiguration completed: %s deleted, %s skipped", deleted_count, skipped_count)
        except ConfigurationError:
            # Re-raise configuration errors (reference issues, SDK errors)
            raise
        except Exception as e:
            LOG.error("Unexpected error during site list deconfiguration: %s", e)
            raise ConfigurationError(f"Site list deconfiguration failed: {e}")
