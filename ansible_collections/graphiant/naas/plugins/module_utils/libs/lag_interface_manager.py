"""
LAG Interfaces Manager for Graphiant Playbooks.

This module handles LAG (Link Aggregation Group) interface configuration management
for Graphiant Edge/Gateway devices.
"""

from .base_manager import BaseManager
from .exceptions import ConfigurationError
from .logger import setup_logger

LOG = setup_logger()


class LagInterfaceManager(BaseManager):

    def configure(self, config_yaml_file: str) -> dict:  # pylint: disable=arguments-renamed
        """
        Configure LAG interfaces for multiple devices concurrently.
        This method calls the configure method to handle all configurations in a single API call per device.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary. Typically includes:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of configured device IDs.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        return self.configure_lag_interfaces(config_yaml_file, action="add")

    def deconfigure(self, config_yaml_file: str) -> dict:  # pylint: disable=arguments-renamed
        """
        Deconfigure LAG interfaces for multiple devices concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary. Typically includes:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        return self.deconfigure_lag_interfaces(config_yaml_file)

    def add_lag_members(self, config_yaml_file: str) -> dict:
        """
        Add Interface members to an existing LAG for multiple devices concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary. Typically includes:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        return self.configure_lag_interfaces(config_yaml_file, action="add_lag_members")

    def remove_lag_members(self, config_yaml_file: str) -> dict:
        """
        Remove Interface members from an existing LAG for multiple devices concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary. Typically includes:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        return self.configure_lag_interfaces(config_yaml_file, action="remove_lag_members")

    def update_lacp_configs(self, config_yaml_file: str) -> dict:
        """
        Update LACP parameters(mode/timer) for one or more LAGs across devices concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary. Typically includes:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        return self.configure_lag_interfaces(config_yaml_file, action="update_lacp_configs")

    def add_lag_subinterfaces(self, config_yaml_file: str) -> dict:
        """
        Add/configure VLAN subinterfaces under a LAG for multiple devices concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary. Typically includes:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        return self.configure_lag_interfaces(config_yaml_file, action="add")

    def delete_lag_subinterfaces(self, config_yaml_file: str) -> dict:
        """
        Delete VLAN subinterfaces under a LAG for multiple devices concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary. Typically includes:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        return self.configure_lag_interfaces(config_yaml_file, action="delete")

    def configure_lag_interfaces(self, config_yaml_file: str, action: str = "add") -> dict:
        """
        Configure/update LAG interfaces for multiple devices concurrently.

        Supported actions (template-dependent):
            - add
            - add_lag_members
            - remove_lag_members
            - update_lacp_configs
            - delete (typically used for subinterfaces)

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.
            action: Action string passed through to the template renderer / config builder.

        Returns:
            dict: Result dictionary. Typically includes:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of configured device IDs.

        Raises:
            ConfigurationError: If configuration processing fails.
            DeviceNotFoundError: If any device cannot be found (via underlying SDK/helper).
        """
        try:
            result = {'changed': False, 'configured_devices': []}

            config_data = self.render_config_file(config_yaml_file)
            output_config = {}
            device_configs = {}

            if 'lagInterfaces' not in config_data:
                LOG.warning("No LAG interfaces configuration found in %s", config_yaml_file)
                return result

            for device_info in config_data.get("lagInterfaces"):
                for device_name, config_list in device_info.items():
                    device_configs[device_name] = config_list

            for device_name, configs in device_configs.items():
                for config in configs:
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise ConfigurationError(
                                f"Device '{device_name}' is not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                "Please check device name and enterprise credentials."
                            )
                        output_config[device_id] = {
                            "device_id": device_id,
                            "edge": {"lagInterfaces": {}}
                        }

                        # Get the interface IDs for the interface members
                        gcs_device_info = self.gsdk.get_device_info(device_id)
                        config['interfaceMemberIds'] = []
                        for interface_info in gcs_device_info.device.interfaces:
                            if interface_info.name in config.get('lagMembers', []):
                                config['interfaceMemberIds'].append(interface_info.id)

                        self.config_utils.lag_interfaces(output_config[device_id]["edge"], action=action, **config)

                        LOG.info("[configure] Processing device: %s (ID: %s)", device_name, device_id)
                    except Exception as e:
                        LOG.error("Error configuring LAG interfaces: %s", str(e))
                        raise ConfigurationError(f"LAG interface configuration failed: {str(e)}")
            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                LOG.info("Successfully configured LAG interfaces for %s devices", len(output_config))
            else:
                LOG.warning("No LAG interface configurations to apply")
        except Exception as e:
            LOG.error("Error in LAG interface configuration: %s", str(e))
            raise ConfigurationError(f"LAG interface configuration failed: {str(e)}")

    def deconfigure_lag_interfaces(self, config_yaml_file: str) -> dict:
        """
        Deletes all the subinterfaces and then Deconfigure (remove) LAG interfaces for multiple devices concurrently.

        Args:
            config_yaml_file: Path to the YAML file containing LAG interface configurations.

        Returns:
            dict: Result dictionary. Typically includes:
                - changed (bool): Whether changes were applied.
                - configured_devices (list): List of affected device IDs.

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        try:
            result = {'changed': False, 'configured_devices': []}

            config_data = self.render_config_file(config_yaml_file)
            output_config = {}
            delete_lag_config = {}
            device_configs = {}

            if 'lagInterfaces' not in config_data:
                LOG.warning("No LAG interfaces configuration found in %s", config_yaml_file)
                return result

            for device_info in config_data.get("lagInterfaces"):
                for device_name, config_list in device_info.items():
                    device_configs[device_name] = config_list

            for device_name, configs in device_configs.items():
                for config in configs:
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise ConfigurationError(
                                f"Device '{device_name}' is not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                "Please check device name and enterprise credentials."
                            )
                        output_config[device_id] = {
                            "device_id": device_id,
                            "edge": {"lagInterfaces": {}}
                        }

                        delete_lag_config[device_id] = {
                            "device_id": device_id,
                            "edge": {"interfaces": {}}
                        }
                        # Get the interface IDs for the interface members
                        gcs_device_info = self.gsdk.get_device_info(device_id)
                        config['interfaceMemberIds'] = []
                        for interface_info in gcs_device_info.device.interfaces:
                            if interface_info.name in config.get('lagMembers', []):
                                config['interfaceMemberIds'].append(interface_info.id)

                        self.config_utils.lag_interfaces(output_config[device_id]["edge"], action="delete", **config)
                        self.config_utils.lag_interfaces(delete_lag_config[device_id]["edge"], action="delete_lag", **config)

                        LOG.info("[deconfigure] Processing device: %s (ID: %s)", device_name, device_id)
                    except Exception as e:
                        LOG.error("Error deconfiguring LAG interfaces: %s", str(e))
                        raise ConfigurationError(f"LAG interface deconfiguration failed: {str(e)}")
            if output_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                LOG.info("Successfully deconfigured LAG interfaces and subinterfaces for %s devices", len(output_config))
            else:
                LOG.warning("No configurations to deconfigure")
            if delete_lag_config:
                self.execute_concurrent_tasks(self.gsdk.put_device_config, delete_lag_config)
                LOG.info("Successfully deleted LAG interfaces for %s devices", len(delete_lag_config))
            else:
                LOG.warning("No LAG interface configurations to delete")
        except Exception as e:
            LOG.error("Error in LAG interface deconfiguration: %s", str(e))
            raise ConfigurationError(f"LAG interface deconfiguration failed: {str(e)}")
