"""
Site-to-Site VPN Manager for Graphiant Playbooks.

This module handles Site-to-Site VPN configuration management for Graphiant Playbooks.
"""

from typing import Dict, Any
from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class SiteToSiteVpnManager(BaseManager):
    """
    Manages Site-to-Site VPN configurations.

    Handles the configuration and deconfiguration of Site-to-Site VPN connections,
    supporting both static and BGP routing.
    """

    def configure(self, config_yaml_file: str) -> None:
        """
        Configure Site-to-Site VPN (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing Site-to-Site VPN configurations
        """
        self.configure_site_to_site_vpn(config_yaml_file)

    def deconfigure(self, config_yaml_file: str) -> None:
        """
        Deconfigure Site-to-Site VPN (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing Site-to-Site VPN configurations
        """
        self.deconfigure_site_to_site_vpn(config_yaml_file)

    def _load_vault_secrets(self) -> tuple:
        """
        Load vault secrets from vault_secrets.yml file.

        Note: This method attempts to load vault secrets, but if the file is encrypted
        with Ansible Vault, it will need to be decrypted by Ansible before the module runs.
        The playbook's vars_files directive handles vault decryption.

        Returns:
            tuple: (vault_keys dict, vault_md5_passwords dict)
        """
        import os
        import yaml
        vault_keys = {}
        vault_md5_passwords = {}

        # Try to find vault_secrets.yml in the config directory
        vault_file_paths = [
            os.path.join(self.config_utils.config_path, "vault_secrets.yml"),
            os.path.join(os.path.dirname(self.config_utils.config_path), "vault_secrets.yml"),
        ]

        # Also try relative to current working directory
        cwd_vault = os.path.join(os.getcwd(), "ansible_collections", "graphiant", "naas", "configs", "vault_secrets.yml")
        if os.path.exists(cwd_vault):
            vault_file_paths.append(cwd_vault)

        vault_file = None
        for path in vault_file_paths:
            if os.path.exists(path):
                vault_file = path
                break

        if vault_file:
            try:
                # Use simple YAML loading (vault file should be decrypted by Ansible before module runs)
                # If encrypted, this will fail gracefully and fall back to config_data
                with open(vault_file, 'r', encoding='utf-8') as f:
                    vault_data = yaml.safe_load(f)
                    if vault_data:
                        vault_keys = vault_data.get('vault_site_to_site_vpn_keys', {})
                        vault_md5_passwords = vault_data.get('vault_bgp_md5_passwords', {})
                        LOG.debug("Loaded vault secrets from: %s", vault_file)
            except yaml.YAMLError as e:
                # File might be encrypted - that's okay, will fall back to config_data
                LOG.debug("Could not parse vault file %s (may be encrypted): %s", vault_file, str(e))
            except Exception as e:
                LOG.warning("Could not load vault secrets from %s: %s", vault_file, str(e))
        else:
            LOG.debug("vault_secrets.yml not found, will try to get vault variables from config data")

        # Ensure they are dictionaries
        if not isinstance(vault_keys, dict):
            vault_keys = {}
        if not isinstance(vault_md5_passwords, dict):
            vault_md5_passwords = {}

        return vault_keys, vault_md5_passwords

    def _inject_vault_secrets(self, vpn_config: Dict[str, Any], vpn_config_data: Dict[str, Any]) -> None:
        """
        Automatically inject presharedKey and md5Password from vault variables.

        Args:
            vpn_config: VPN configuration dictionary to modify
            vpn_config_data: Full config data (may also contain vault variables as fallback)
        """
        vpn_name = vpn_config.get('name')
        if not vpn_name:
            return

        # First try to load from vault_secrets.yml file (preferred method)
        vault_keys, vault_md5_passwords = self._load_vault_secrets()

        # Fallback: Get vault variables from config data (if playbook injected them)
        if not vault_keys:
            vault_keys = vpn_config_data.get('vault_site_to_site_vpn_keys', {})
        if not vault_md5_passwords:
            vault_md5_passwords = vpn_config_data.get('vault_bgp_md5_passwords', {})

        # Ensure vault_keys and vault_md5_passwords are dictionaries
        if not isinstance(vault_keys, dict):
            vault_keys = {}
        if not isinstance(vault_md5_passwords, dict):
            vault_md5_passwords = {}

        # Debug: Log available vault keys for troubleshooting
        LOG.debug("Available vault_site_to_site_vpn_keys: %s", list(vault_keys.keys()) if vault_keys else "none")
        LOG.debug("Available vault_bgp_md5_passwords: %s", list(vault_md5_passwords.keys()) if vault_md5_passwords else "none")

        # Auto-inject presharedKey if not already set or is a placeholder/Jinja2 expression
        preshared_key = vpn_config.get('presharedKey')
        needs_preshared_key = (
            'presharedKey' not in vpn_config or
            not preshared_key or
            (isinstance(preshared_key, str) and ('{{' in str(preshared_key) or not preshared_key.strip()))
        )

        if needs_preshared_key:
            if vpn_name in vault_keys and vault_keys[vpn_name]:
                vpn_config['presharedKey'] = vault_keys[vpn_name]
                LOG.info("Auto-injected presharedKey for VPN '%s' from vault", vpn_name)
            else:
                LOG.warning(
                    "No presharedKey found for VPN '%s' in vault (key: '%s'). "
                    "VPN may fail to configure. Ensure vault_site_to_site_vpn_keys['%s'] is set in vault_secrets.yml",
                    vpn_name, vpn_name, vpn_name
                )

        # Auto-inject md5Password for BGP routing if not already set
        if 'routing' in vpn_config and isinstance(vpn_config.get('routing'), dict) and 'bgp' in vpn_config['routing']:
            bgp_config = vpn_config['routing']['bgp']
            md5_password = bgp_config.get('md5Password')

            # Determine if we need to inject md5Password
            # Inject if: not present, None, empty string, whitespace-only, or contains Jinja2 template syntax
            needs_md5_password = (
                'md5Password' not in bgp_config or
                md5_password is None or
                (isinstance(md5_password, str) and ('{{' in md5_password or not md5_password.strip()))
            )

            if needs_md5_password:
                if vpn_name in vault_md5_passwords and vault_md5_passwords[vpn_name]:
                    vault_password = vault_md5_passwords[vpn_name]
                    # Ensure we have a non-empty string
                    if vault_password and str(vault_password).strip():
                        bgp_config['md5Password'] = str(vault_password).strip()
                        LOG.info("Auto-injected md5Password for VPN '%s' from vault", vpn_name)
                    else:
                        bgp_config['md5Password'] = None
                        LOG.warning("md5Password for VPN '%s' in vault is empty, setting to null", vpn_name)
                else:
                    # If md5Password was explicitly set to None/empty, keep it as None
                    # Otherwise, if it's missing and not in vault, set to None (optional field)
                    if 'md5Password' not in bgp_config:
                        bgp_config['md5Password'] = None
                        LOG.debug("No md5Password in vault for VPN '%s', setting to null (optional field)", vpn_name)
                    else:
                        # Clear empty/whitespace-only values
                        if isinstance(md5_password, str) and not md5_password.strip():
                            bgp_config['md5Password'] = None
                            LOG.debug("Cleared empty md5Password for VPN '%s', setting to null", vpn_name)

    def configure_site_to_site_vpn(self, vpn_config_file: str) -> dict:
        """
        Configure Site-to-Site VPN for multiple devices concurrently.

        Args:
            vpn_config_file: Path to the YAML file containing Site-to-Site VPN configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result = {'changed': False, 'configured_devices': []}

        try:
            # Load Site-to-Site VPN configurations
            vpn_config_data = self.render_config_file(vpn_config_file)
            output_config = {}

            # Process the siteToSiteVpn structure
            site_to_site_vpn_list = vpn_config_data.get("siteToSiteVpn", [])
            if not site_to_site_vpn_list:
                LOG.warning("No siteToSiteVpn configuration found in %s", vpn_config_file)
                return result

            # Process each device's configurations
            for device_entry in site_to_site_vpn_list:
                for device_name, vpn_configs in device_entry.items():
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise DeviceNotFoundError(
                                f"Device '{device_name}' is not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                f"Please check device name and enterprise credentials."
                            )

                        # Initialize device config if not exists
                        if device_id not in output_config:
                            output_config[device_id] = {
                                "device_id": device_id,
                                "edge": {"siteToSiteVpn": {}}
                            }

                        LOG.info("[configure] Processing device: %s (ID: %s)", device_name, device_id)

                        # Process each VPN configuration for this device
                        if not isinstance(vpn_configs, list):
                            vpn_configs = [vpn_configs]

                        for vpn_config in vpn_configs:
                            vpn_name = vpn_config.get('name')
                            if not vpn_name:
                                LOG.warning("Skipping VPN config - missing 'name' field")
                                continue

                            # Automatically inject vault secrets based on VPN name
                            self._inject_vault_secrets(vpn_config, vpn_config_data)

                            LOG.info("Processing Site-to-Site VPN: %s", vpn_name)

                            # Debug: Log md5Password status if BGP routing is present
                            if 'routing' in vpn_config and isinstance(vpn_config.get('routing'), dict) and 'bgp' in vpn_config['routing']:
                                bgp_config = vpn_config['routing']['bgp']
                                md5_status = "set" if bgp_config.get('md5Password') else "not set/null"
                                LOG.debug("VPN '%s' BGP md5Password status: %s", vpn_name, md5_status)
                                if bgp_config.get('md5Password'):
                                    LOG.debug("VPN '%s' BGP md5Password value length: %d", vpn_name, len(str(bgp_config.get('md5Password'))))

                            # Render template for this VPN configuration
                            rendered_payload = self.template.render_template(
                                "site_to_site_vpn_template.yaml",
                                action="add",
                                **vpn_config
                            )

                            # Extract the siteToSiteVpn from rendered payload
                            if 'edge' in rendered_payload and 'siteToSiteVpn' in rendered_payload['edge']:
                                vpn_payload = rendered_payload['edge']['siteToSiteVpn']
                                # Merge into device's siteToSiteVpn config
                                output_config[device_id]["edge"]["siteToSiteVpn"].update(vpn_payload)
                                LOG.info(" ✓ Added Site-to-Site VPN: %s", vpn_name)
                            else:
                                LOG.warning("Unexpected template output structure for VPN: %s", vpn_name)

                    except DeviceNotFoundError:
                        raise
                    except Exception as e:
                        LOG.error("Error configuring device %s: %s", device_name, str(e))
                        raise ConfigurationError(f"Configuration failed for {device_name}: {str(e)}")

            # Execute concurrent configuration push
            if output_config:
                LOG.info("Pushing Site-to-Site VPN configuration to %d device(s)...", len(output_config))
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result['changed'] = True
                result['configured_devices'] = list(output_config)
                LOG.info("Successfully configured Site-to-Site VPN for %s devices", len(output_config))
            else:
                LOG.warning("No valid device configurations found")

            return result

        except Exception as e:
            LOG.error("Error in Site-to-Site VPN configuration: %s", str(e))
            raise ConfigurationError(f"Site-to-Site VPN configuration failed: {str(e)}")

    def deconfigure_site_to_site_vpn(self, vpn_config_file: str) -> dict:
        """
        Deconfigure Site-to-Site VPN for multiple devices concurrently.

        Args:
            vpn_config_file: Path to the YAML file containing Site-to-Site VPN configurations

        Returns:
            dict: Result with 'changed' status and list of deconfigured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result = {'changed': False, 'deconfigured_devices': []}

        try:
            # Load Site-to-Site VPN configurations
            vpn_config_data = self.render_config_file(vpn_config_file)
            output_config = {}

            # Process the siteToSiteVpn structure
            site_to_site_vpn_list = vpn_config_data.get("siteToSiteVpn", [])
            if not site_to_site_vpn_list:
                LOG.warning("No siteToSiteVpn configuration found in %s", vpn_config_file)
                return result

            # Process each device's configurations
            for device_entry in site_to_site_vpn_list:
                for device_name, vpn_configs in device_entry.items():
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise DeviceNotFoundError(
                                f"Device '{device_name}' is not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                f"Please check device name and enterprise credentials."
                            )

                        # Initialize device config if not exists
                        if device_id not in output_config:
                            output_config[device_id] = {
                                "device_id": device_id,
                                "edge": {"siteToSiteVpn": {}}
                            }

                        LOG.info("[deconfigure] Processing device: %s (ID: %s)", device_name, device_id)

                        # Process each VPN configuration for this device
                        if not isinstance(vpn_configs, list):
                            vpn_configs = [vpn_configs]

                        for vpn_config in vpn_configs:
                            vpn_name = vpn_config.get('name')
                            if not vpn_name:
                                LOG.warning("Skipping VPN config - missing 'name' field")
                                continue

                            LOG.info("Deconfiguring Site-to-Site VPN: %s", vpn_name)

                            # Render template for deletion
                            rendered_payload = self.template.render_template(
                                "site_to_site_vpn_template.yaml",
                                action="delete",
                                name=vpn_name
                            )

                            # Extract the siteToSiteVpn from rendered payload
                            if 'edge' in rendered_payload and 'siteToSiteVpn' in rendered_payload['edge']:
                                vpn_payload = rendered_payload['edge']['siteToSiteVpn']
                                # Merge into device's siteToSiteVpn config
                                output_config[device_id]["edge"]["siteToSiteVpn"].update(vpn_payload)
                                LOG.info(" ✓ Removed Site-to-Site VPN: %s", vpn_name)
                            else:
                                LOG.warning("Unexpected template output structure for VPN: %s", vpn_name)

                    except DeviceNotFoundError:
                        raise
                    except Exception as e:
                        LOG.error("Error deconfiguring device %s: %s", device_name, str(e))
                        raise ConfigurationError(f"Deconfiguration failed for {device_name}: {str(e)}")

            # Execute concurrent configuration push
            if output_config:
                LOG.info("Pushing Site-to-Site VPN deconfiguration to %d device(s)...", len(output_config))
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result['changed'] = True
                result['deconfigured_devices'] = list(output_config)
                LOG.info("Successfully deconfigured Site-to-Site VPN for %s devices", len(output_config))
            else:
                LOG.warning("No valid device configurations found")

            return result

        except Exception as e:
            LOG.error("Error in Site-to-Site VPN deconfiguration: %s", str(e))
            raise ConfigurationError(f"Site-to-Site VPN deconfiguration failed: {str(e)}")
