"""
Site Manager for Graphiant Playbooks.

This module handles site management operations including
attachment and detachment of global system objects to/from sites.
"""

from typing import Dict, Any, Union
from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError, SiteNotFoundError, ValidationError

LOG = setup_logger()


class SiteManager(BaseManager):
    """
    Manages site operations and global object attachments.

    Handles the attachment and detachment of global system objects
    (SNMP, Syslog, IPFIX, VPN profiles) to/from specific sites.
    """

    def configure(self, config_yaml_file: str) -> None:
        """
        Configure sites: create sites and attach global system objects.

        Args:
            config_yaml_file: Path to the YAML file containing site configurations

        Raises:
            ConfigurationError: If configuration processing fails
            SiteNotFoundError: If any site cannot be found
            ValidationError: If configuration data is invalid
        """
        # Step 1: Create sites if they don't exist
        self._manage_sites(config_yaml_file, operation="create")

        # Step 2: Attach global objects to sites
        self._manage_site_objects(config_yaml_file, operation="attach")

    def deconfigure(self, config_yaml_file: str) -> None:
        """
        Deconfigure sites: detach global system objects and delete sites.

        Args:
            config_yaml_file: Path to the YAML file containing site configurations

        Raises:
            ConfigurationError: If configuration processing fails
            SiteNotFoundError: If any site cannot be found
            ValidationError: If configuration data is invalid
        """
        # Step 1: Detach global objects from sites
        self._manage_site_objects(config_yaml_file, operation="detach")

        # Step 2: Delete sites
        self._manage_sites(config_yaml_file, operation="delete")

    def configure_sites(self, config_yaml_file: str) -> None:
        """
        Create sites (idempotent - only creates if site doesn't exist).

        Args:
            config_yaml_file: Path to the YAML file containing site configurations

        Raises:
            ConfigurationError: If configuration processing fails
            ValidationError: If configuration data is invalid
        """
        self._manage_sites(config_yaml_file, operation="create")

    def deconfigure_sites(self, config_yaml_file: str) -> None:
        """
        Delete sites (idempotent - only deletes if site exists).

        Args:
            config_yaml_file: Path to the YAML file containing site configurations

        Raises:
            ConfigurationError: If configuration processing fails
            ValidationError: If configuration data is invalid
        """
        self._manage_sites(config_yaml_file, operation="delete")

    def _manage_sites(self, config_yaml_file: str, operation: str) -> None:
        """
        Manage sites (create or delete).

        Args:
            config_yaml_file: Path to the YAML file containing site configurations
            operation: Operation to perform - "create" or "delete"

        Raises:
            ConfigurationError: If configuration processing fails
            ValidationError: If configuration data is invalid
        """
        try:
            config_data = self.render_config_file(config_yaml_file)

            if 'sites' not in config_data:
                LOG.info("No sites configuration found in %s, skipping site %s", config_yaml_file, operation)
                return

            processed_sites = 0

            for site_config in config_data.get('sites'):
                try:
                    site_name = site_config.get('name')
                    if not site_name:
                        raise ValidationError("Site configuration must include 'name' field")

                    if operation == "create":
                        self._create_site_if_not_exists(site_config)
                    elif operation == "delete":
                        self._delete_site_if_exists(site_name)

                    processed_sites += 1
                    LOG.info("Successfully %sd site: %s", operation, site_name)

                except Exception as e:
                    LOG.error("Error %sing site '%s': %s", operation, site_name, str(e))
                    raise ConfigurationError(f"Failed to {operation} site {site_name}: {str(e)}")

            LOG.info("Successfully %sd %s sites", operation, processed_sites)

        except Exception as e:
            LOG.error("Error in site %s operation: %s", operation, str(e))
            raise ConfigurationError(f"Site {operation} operation failed: {str(e)}")

    def _create_site_if_not_exists(self, site_config: dict) -> None:
        """
        Create a site if it doesn't already exist (idempotent).

        Args:
            site_config: Site configuration dictionary

        Raises:
            ConfigurationError: If site creation fails
        """
        site_name = site_config.get('name')

        # Check if site already exists using v1/sites/details
        if self.gsdk.site_exists(site_name):
            existing_site_id = self.gsdk.get_site_id(site_name)
            LOG.info("Site '%s' already exists with ID: %s, skipping creation", site_name, existing_site_id)
            return

        try:
            # Prepare site data for creation (simple site creation only)
            site_data = {
                "site": {
                    "name": site_name,
                    "location": site_config.get('location', {})
                }
            }

            # Create the site
            created_site = self.gsdk.create_site(site_data)
            LOG.info("Successfully created site '%s' with ID: %s", site_name, created_site.id)

        except Exception as e:
            error_msg = str(e)
            # Handle "already exists" errors gracefully
            if "already exists" in error_msg.lower() or "already created" in error_msg.lower():
                LOG.info("Site '%s' already exists, skipping creation: %s", site_name, error_msg)
                return
            else:
                LOG.error("Failed to create site '%s': %s", site_name, error_msg)
                raise ConfigurationError(f"Site creation failed for {site_name}: {error_msg}")

    def _delete_site_if_exists(self, site_name: str) -> None:
        """
        Delete a site if it exists (idempotent).

        Args:
            site_name: Name of the site to delete

        Raises:
            ConfigurationError: If site deletion fails
        """
        try:
            # Check if site exists using v1/sites/details
            if not self.gsdk.site_exists(site_name):
                LOG.info("Site '%s' does not exist, skipping deletion", site_name)
                return

            # Get site ID for deletion
            site_id = self.gsdk.get_site_id(site_name)

            # Delete the site
            success = self.gsdk.delete_site(site_id)
            if success:
                LOG.info("Successfully deleted site '%s' with ID: %s", site_name, site_id)
            else:
                raise ConfigurationError(f"Failed to delete site '{site_name}' with ID: {site_id}")

        except Exception as e:
            LOG.error("Failed to delete site '%s': %s", site_name, str(e))
            raise ConfigurationError(f"Site deletion failed for {site_name}: {str(e)}")

    def attach_objects(self, config_yaml_file: str) -> None:
        """
        Attach global system objects to sites.

        Args:
            config_yaml_file: Path to the YAML file containing site attachment configurations
        """
        self._manage_site_objects(config_yaml_file, operation="attach")

    def detach_objects(self, config_yaml_file: str) -> None:
        """
        Detach global system objects from sites.

        Args:
            config_yaml_file: Path to the YAML file containing site attachment configurations
        """
        self._manage_site_objects(config_yaml_file, operation="detach")

    def _manage_site_objects(self, config_yaml_file: str, operation: str) -> None:
        """
        Manage global system objects on sites (attach or detach).

        Args:
            config_yaml_file: Path to the YAML file containing site management definitions
            operation: Operation to perform - "attach" or "detach"

        Raises:
            ConfigurationError: If configuration processing fails
            SiteNotFoundError: If any site cannot be found
            ValidationError: If configuration data is invalid
        """
        try:
            config_data = self.render_config_file(config_yaml_file)

            if 'site_attachments' not in config_data:
                LOG.info("No site attachments configuration found in %s, skipping object %s", config_yaml_file, operation)
                return

            default_operation = 'Attach' if operation.lower().startswith("attach") else 'Detach'
            processed_sites = 0

            for site_config in config_data.get('site_attachments'):
                try:
                    # Get the site name from the first (and only) key in the site config
                    site_name = list(site_config.keys())[0]
                    site_data = site_config[site_name]

                    site_id = self.get_site_id(site_name)
                    site_payload = {"site": {"name": site_name}}

                    # Process SNMP operations
                    if 'snmp_servers' in site_data:
                        site_payload['site']['snmpOps'] = {}
                        for snmp_name in site_data.get('snmp_servers'):
                            site_payload['site']['snmpOps'][snmp_name] = default_operation

                    # Process Syslog operations
                    if 'syslog_servers' in site_data:
                        site_payload['site']['syslogServerOpsV2'] = {}
                        for syslog_config in site_data.get('syslog_servers'):
                            self._process_syslog_config(site_payload, syslog_config, default_operation)

                    # Process IPFIX operations
                    if 'ipfix_exporters' in site_data:
                        site_payload['site']['ipfixExporterOpsV2'] = {}
                        for ipfix_config in site_data.get('ipfix_exporters'):
                            self._process_ipfix_config(site_payload, ipfix_config, default_operation)

                    # Execute the site configuration
                    self.gsdk.post_site_config(site_id=site_id, site_config=site_payload)
                    processed_sites += 1

                    LOG.info("Successfully %s global objects for site: %s (ID: %s)",
                             default_operation.lower(), site_name, site_id)

                except SiteNotFoundError:
                    LOG.error("Site '%s' not found, skipping %s operation", site_name, operation)
                    raise
                except Exception as e:
                    error_msg = str(e)
                    # Handle "already attached" errors gracefully
                    if operation.lower().startswith("attach") and (
                            "already attached" in error_msg.lower() or "already exists" in error_msg.lower()):
                        LOG.info("Object already %sed to site '%s', skipping: %s",
                                 default_operation.lower(), site_name, error_msg)
                        processed_sites += 1
                        continue
                    # Handle "already detached","not attached" and "not found" errors gracefully for detach operations
                    elif operation.lower().startswith("detach") and (
                            "already detached" in error_msg.lower() or
                            "not attached" in error_msg.lower() or "not found" in error_msg.lower()):
                        LOG.info("Object not attached to site '%s', skipping %s: %s",
                                 site_name, default_operation.lower(), error_msg)
                        processed_sites += 1
                        continue
                    else:
                        LOG.error("Error %sing objects for site '%s': %s", default_operation.lower(), site_name, error_msg)
                        raise ConfigurationError(f"Failed to {operation.lower()} objects for {site_name}: {error_msg}")

            LOG.info("Successfully %sed global objects for %s sites", default_operation.lower(), processed_sites)

        except Exception as e:
            LOG.error("Error in site %s operation: %s", operation, str(e))
            raise ConfigurationError(f"Site {operation} operation failed: {str(e)}")

    def _process_syslog_config(self, site_payload: Dict[str, Any],
                               syslog_config: Union[str, Dict], default_operation: str) -> None:
        """
        Process syslog configuration for site attachment/detachment.

        Args:
            site_payload: The site payload dictionary to update
            syslog_config: Syslog configuration (string or dict)
            default_operation: The operation to perform (Attach/Detach)
        """
        if isinstance(syslog_config, str):
            # Backward compatibility: simple string format
            syslog_name = syslog_config
            site_payload['site']['syslogServerOpsV2'][syslog_name] = {
                "operation": default_operation
            }
        else:
            # New format: object with interface specification
            syslog_name = syslog_config.get('name')
            interface = syslog_config.get('interface')

            if not syslog_name:
                raise ValidationError("Syslog configuration must include 'name' field")

            site_payload['site']['syslogServerOpsV2'][syslog_name] = {
                "operation": default_operation,
                "interface": {
                    "interface": interface
                }
            }

    def _process_ipfix_config(self, site_payload: Dict[str, Any],
                              ipfix_config: Union[str, Dict], default_operation: str) -> None:
        """
        Process IPFIX configuration for site attachment/detachment.

        Args:
            site_payload: The site payload dictionary to update
            ipfix_config: IPFIX configuration (string or dict)
            default_operation: The operation to perform (Attach/Detach)
        """
        if isinstance(ipfix_config, str):
            # Backward compatibility: simple string format
            ipfix_name = ipfix_config
            site_payload['site']['ipfixExporterOpsV2'][ipfix_name] = {
                "operation": default_operation
            }
        else:
            # New format: object with interface specification
            ipfix_name = ipfix_config.get('name')
            interface = ipfix_config.get('interface')

            if not ipfix_name:
                raise ValidationError("IPFIX configuration must include 'name' field")

            site_payload['site']['ipfixExporterOpsV2'][ipfix_name] = {
                "operation": default_operation,
                "interface": {
                    "interface": interface
                }
            }
