"""
VRRP on Interfaces Manager for Graphiant Playbooks.

This module handles VRRP interface configuration management for Graphiant Playbooks.

VRRP configuration is applied to both main interfaces and subinterfaces (VLANs).
"""

from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class VRRPInterfaceManager(BaseManager):
    """
    Manages VRRP on interfaces configurations.

    Handles the configuration and deconfiguration of VRRP interfaces,
    including both main interfaces and VLAN subinterfaces.
    """

    def configure(self, config_yaml_file: str) -> None:
        """
        Configure VRRP interfaces (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing VRRP configurations
        """
        self.configure_vrrp_interfaces(config_yaml_file)

    def deconfigure(self, config_yaml_file: str) -> None:
        """
        Deconfigure VRRP interfaces (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing VRRP configurations
        """
        self.deconfigure_vrrp_interfaces(config_yaml_file)

    def configure_vrrp_interfaces(self, vrrp_config_file: str) -> dict:
        """
        Configure VRRP interfaces for multiple devices concurrently.
        This method combines all VRRP configurations in a single API call per device.

        Args:
            vrrp_config_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status and list of configured devices
            Note: Always returns changed=True when devices are configured since we push
            via PUT API. True idempotency would require comparing current vs desired state.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result = {'changed': False, 'configured_devices': []}

        try:
            # Load VRRP configurations
            vrrp_config_data = self.render_config_file(vrrp_config_file)
            output_config = {}

            # Collect all device configurations first
            device_configs = {}

            # Collect VRRP configurations per device
            for device_info in vrrp_config_data.get("vrrp_config"):
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": []}
                device_configs[device_name]["interfaces"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(f"Device '{device_name}' is not found in the current enterprise: "
                                                 f"{self.gsdk.enterprise_info['company_name']}. "
                                                 f"Please check device name and enterprise credentials.")
                    output_config[device_id] = {
                        "device_id": device_id,
                        "edge": {"interfaces": {}}
                    }

                    # Collect interface names referenced in this device's VRRP configurations
                    referenced_interfaces = set()
                    for vrrp_config in configs.get("interfaces", []):
                        # Check main interface for interface reference
                        if vrrp_config.get('interface_name'):
                            referenced_interfaces.add(vrrp_config['interface_name'])
                        # Check subinterfaces for interface references
                        if vrrp_config.get('vlan'):
                            referenced_interfaces.add(vrrp_config['vlan'])

                    LOG.info("[configure] Processing device: %s (ID: %s)", device_name, device_id)
                    LOG.info("Referenced interfaces: %s", list(referenced_interfaces))

                    # Process VRRP for this device
                    vrrp_configured = 0
                    for config in configs.get("interfaces", []):
                        # Check if this interface has any VRRP configuration
                        if config.get('vrrp_ipv4') or config.get('vrrp_ipv6'):
                            LOG.info(" ✓ Found VRRP configuration for interface: %s", config.get('interface_name'))
                            self.config_utils.vrrp_interfaces(
                                output_config[device_id]["edge"],
                                action="add",
                                **config
                            )
                            vrrp_configured += 1
                            LOG.info(" ✓ To configure VRRP for interface: %s", config.get('interface_name'))
                        else:
                            LOG.info(" ✗ Skipping interface '%s' - no VRRP configuration", config.get('interface_name'))

                    LOG.info("Device %s summary: %s VRRP interfaces to be configured", device_name, vrrp_configured)
                    LOG.info("Final config for %s: %s", device_name, output_config[device_id]['edge'])

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error configuring device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Configuration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result['changed'] = True
                result['configured_devices'] = list(output_config.keys())
                LOG.info("Successfully configured VRRP interfaces for %s devices", len(output_config))
            else:
                LOG.warning("No valid device configurations found")

            return result

        except Exception as e:
            LOG.error("Error in VRRP interface configuration: %s", str(e))
            raise ConfigurationError(f"VRRP interface configuration failed: {str(e)}")

    def deconfigure_vrrp_interfaces(self, vrrp_config_file: str) -> dict:
        """
        Deconfigure VRRP interfaces for multiple devices concurrently.

        Args:
            vrrp_config_file: Path to the YAML file containing VRRP configurations

        Returns:
            dict: Result with 'changed' status and list of deconfigured devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result = {'changed': False, 'deconfigured_devices': []}

        try:
            # Load VRRP configurations
            vrrp_config_data = self.render_config_file(vrrp_config_file)
            output_config = {}

            # Collect all device configurations first
            device_configs = {}

            # Collect VRRP configurations per device
            for device_info in vrrp_config_data.get("vrrp_config"):
                for device_name, config_list in device_info.items():
                    if device_name not in device_configs:
                        device_configs[device_name] = {"interfaces": []}
                    device_configs[device_name]["interfaces"] = config_list

            # Process each device's configurations
            for device_name, configs in device_configs.items():
                try:
                    device_id = self.gsdk.get_device_id(device_name)
                    if device_id is None:
                        raise ConfigurationError(f"Device '{device_name}' is not found in the current enterprise: "
                                                 f"{self.gsdk.enterprise_info['company_name']}. "
                                                 f"Please check device name and enterprise credentials.")
                    output_config[device_id] = {
                        "device_id": device_id,
                        "edge": {"interfaces": {}}
                    }

                    LOG.info("[deconfigure] Processing device: %s (ID: %s)", device_name, device_id)

                    # Process VRRP removal for this device
                    vrrp_deconfigured = 0
                    for config in configs.get("interfaces", []):
                        LOG.info(" ✓ Removing VRRP configuration for interface: %s", config.get('interface_name'))
                        self.config_utils.vrrp_interfaces(
                            output_config[device_id]["edge"],
                            action="delete",
                            **config
                        )
                        vrrp_deconfigured += 1
                        LOG.info(" ✓ To deconfigure VRRP for interface: %s", config.get('interface_name'))

                    LOG.info("Device %s summary: %s VRRP interfaces to be deconfigured", device_name, vrrp_deconfigured)

                except DeviceNotFoundError:
                    LOG.error("Device not found: %s", device_name)
                    raise
                except Exception as e:
                    LOG.error("Error deconfiguring device %s: %s", device_name, str(e))
                    raise ConfigurationError(f"Deconfiguration failed for {device_name}: {str(e)}")

            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result['changed'] = True
                result['deconfigured_devices'] = list(output_config.keys())
                LOG.info("Successfully deconfigured VRRP interfaces for %s devices", len(output_config))
            else:
                LOG.warning("No valid device configurations found")

            return result

        except Exception as e:
            LOG.error("Error in VRRP interface deconfiguration: %s", str(e))
            raise ConfigurationError(f"VRRP interface deconfiguration failed: {str(e)}")
