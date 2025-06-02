from libs.edge_utils import EdgeUtils
from libs.logger import setup_logger

LOG = setup_logger()

class Edge(EdgeUtils):

    def __init__(self, base_url=None, username=None, password=None, **kwargs):
        super().__init__(base_url=base_url, username=username, password=password, **kwargs)

    def configure_global_prefix(self, yaml_file):
        """
        Configures Global prefix sets based on the provided YAML configuration file.

        This method reads the configuration file, parses the global prefix set entries,
        and constructs the payload using the Jinja2 templates and configure
        the global prefixes using the GCSDK APIs.

        Args:
            yaml_file (str): Path to the YAML file containing the global prefix set definitions.

        Returns:
            None
        """
        config_data = self.render_config_file(yaml_file=yaml_file)
        final_config_payload = {"global_config": {}}
        config_payload = {}
        if 'global_prefix_sets' in config_data:
            config_payload.update({'global_prefix_sets': {}})
            for prefix_config in config_data.get('global_prefix_sets'):
                self.global_prefix_set(config_payload, action="add", **prefix_config)
            final_config_payload["global_config"].update(config_payload)
        LOG.debug(f"configure_routing_prefixes: final_config_payload {final_config_payload}")
        self.concurrent_task_execution(self.gcsdk.patch_global_config, final_config_payload)
    
    def deconfigure_global_prefix(self, yaml_file):
        """
        Removes Global prefix sets based on the provided YAML configuration file.

        This method reads the YAML file, extracts global prefix set configurations, and
        constructs a payload using the Jinja2 templates to delete them from the system 
        using the GCSDK APIs.

        Args:
            yaml_file (str): Path to the YAML file containing the global 
            prefix set definitions to be removed.

        Returns:
            None
        """
        config_data = self.render_config_file(yaml_file=yaml_file)
        final_config_payload = {"global_config": {}}
        config_payload = {}
        if 'global_prefix_sets' in config_data:
            config_payload.update({'global_prefix_sets': {}})
            for prefix_config in config_data.get('global_prefix_sets'):
                self.global_prefix_set(config_payload, action="delete", **prefix_config)
            final_config_payload["global_config"].update(config_payload)
        LOG.debug(f"configure_routing_prefixes: final_config_payload {final_config_payload}")
        self.concurrent_task_execution(self.gcsdk.patch_global_config, final_config_payload)

    def configure_global_bgp_routing_policies(self, yaml_file):
        """
        Configures Global BGP routing filter policies using the provided YAML configuration file.

        This method parses the input YAML file to extract BGP routing filter policy definitions,
        builds the appropriate payload using the templates, and applies the configuration 
        via the GCSDK APIs.

        Args:
            yaml_file (str): Path to the YAML file containing routing policy definitions.

        Returns:
            None
        """
        config_data = self.render_config_file(yaml_file=yaml_file)
        final_config_payload = {"global_config": {}}
        config_payload = {}
        if 'routing_policies' in config_data:
            config_payload.update({'routing_policies': {}})
            for policy_config in config_data.get('routing_policies'):
                self.global_bgp_filter(config_payload, action="add", **policy_config)
            final_config_payload["global_config"].update(config_payload)
        LOG.debug(f"configure_global_bgp_routing_policies: \
                  final_config_payload {final_config_payload}")
        self.concurrent_task_execution(self.gcsdk.patch_global_config, final_config_payload)

    def deconfigure_global_bgp_routing_policies(self, yaml_file):
        """
        Removes Global BGP routing filter policies using the provided YAML configuration file.

        This method parses the input YAML file to extract BGP routing policy definitions
        and constructs the payload using the templates to remove the specified policies 
        using the GCSDK APIs.

        Args:
            yaml_file (str): Path to the YAML file containing routing policy definitions.

        Returns:
            None
        """
        config_data = self.render_config_file(yaml_file=yaml_file)
        final_config_payload = {"global_config": {}}
        config_payload = {}
        if 'routing_policies' in config_data:
            config_payload.update({'routing_policies': {}})
            for policy_config in config_data.get('routing_policies'):
                self.global_bgp_filter(config_payload, action="delete", **policy_config)
            final_config_payload["global_config"].update(config_payload)
        LOG.debug(f"configure_global_bgp_routing_policies: \
                  final_config_payload {final_config_payload}")
        self.concurrent_task_execution(self.gcsdk.patch_global_config, final_config_payload)

    def configure_bgp_peers(self, yaml_file):
        """
        Configures BGP peers based on the provided YAML configuration file 
        concurrently across multiple devices

        This method parses the input YAML file to extract BGP Peers definition
        and constructs the payload using the templates and apply the configurations 
        concurrently across multiple devices using the GCSDK APIs.

        Args:
            yaml_file (str): Path to the YAML file containing the BGP peering configurations.

        Returns:
            None
        """
        config_data = self.render_config_file(yaml_file=yaml_file)
        final_config_payload = {}
        if 'bgp_peering' in config_data:
            for device_config in config_data.get('bgp_peering'):
                for device_name, config in device_config.items():
                    device_id = self.get_device_id(device_name=device_name)
                    config_payload = {}
                    self.edge_bgp_peering(config_payload, **config)
                    final_config_payload[device_id] = {"device_id": device_id, 
                                                       "edge": config_payload}
        LOG.debug(f"configure_bgp_peers: final_config_payload {final_config_payload}")
        self.concurrent_task_execution(self.gcsdk.put_device_config, final_config_payload)

    def detach_policies_from_bgp_peers(self, yaml_file):
        """
        Detach routing filter policies from BGP peers based on the provided YAML configuration 
        file.

        This method parses the input YAML file to extract BGP Peers and policy definition
        and constructs the payload using the templates to detach the policies and apply the 
        configurations concurrently across multiple devices using the GCSDK APIs.
        
        Args:
            yaml_file (str): Path to the YAML file containing the BGP peering configurations.

        Returns:
            None
        """
        config_data = self.render_config_file(yaml_file=yaml_file)
        final_config_payload = {}
        if 'bgp_peering' in config_data:
            for device_config in config_data.get('bgp_peering'):
                for device_name, config in device_config.items():
                    device_id = self.get_device_id(device_name=device_name)
                    config_payload = {}
                    self.edge_bgp_peering(config_payload, action="unlink", **config)
                    final_config_payload[device_id] = {"device_id": device_id, 
                                                       "edge": config_payload}
        LOG.debug(f"detach_policies_from_bgp_peers: final_config_payload {final_config_payload}")
        self.concurrent_task_execution(self.gcsdk.put_device_config, final_config_payload)

    def deconfigure_bgp_peers(self, yaml_file):
        """
        Deconfigures BGP peers provided in configuration YAML file and 
        apply them concurrently using GCSDK APIs across multiple devices.
        
        Args:
            yaml_file (str): Path to the YAML configuration file containing BGP peer 
            configurations to be removed.
        
        Returns:
            None
        """
        config_data = self.render_config_file(yaml_file=yaml_file)
        final_config_payload = {}
        if 'bgp_peering' in config_data:
            for device_config in config_data.get('bgp_peering'):
                for device_name, config in device_config.items():
                    device_id = self.get_device_id(device_name=device_name)
                    config_payload = {}
                    self.edge_bgp_peering(config_payload, action="delete", **config)
                    final_config_payload[device_id] = {"device_id": device_id, 
                                                       "edge": config_payload}
        LOG.debug(f"deconfigure_bgp_peers: final_config_payload {final_config_payload}")
        self.concurrent_task_execution(self.gcsdk.put_device_config, final_config_payload)

    def configure_interfaces(self, yaml_file):
        """
        Configures the interfaces/sub-interfaces for multiple devices concurrently 
        as specified in the provided YAML file.
        
        Args:
            yaml_file (str): Path to the YAML file containing interface configurations.
        
        Returns:
            None
        """
        config_data = self.render_config_file(yaml_file=yaml_file)
        output_config = {}
        if 'interfaces' in config_data:
            for device_info in config_data.get("interfaces"):
                for device_name, config_list in device_info.items():
                    if device_id := self.get_device_id(device_name=device_name):
                        device_config = {"interfaces": {}, "circuits": {}}
                        for config in config_list:
                            self.edge_interface(device_config, action="add", **config)
                        output_config[device_id] = {"device_id": device_id, 
                                                    "edge": device_config}
                    else:
                        LOG.error(f"configure_interfaces : \
                                  {device_name} unable to fetch device-id")
                        return
        self.concurrent_task_execution(self.gcsdk.put_device_config, output_config)

    def deconfigure_interfaces(self, yaml_file):
        """
        Configures the interfaces/sub-interfaces into default_lan for multiple devices 
        concurrently as specified in the provided YAML file.
        
        Args:
            yaml_file (str): Path to the YAML file containing interface configurations.
        
        Returns:
            None
        """
        config_data = self.render_config_file(yaml_file=yaml_file)
        output_config = {}
        default_lan = f'default-{self.get_enterprise_id()}'
        if 'interfaces' in config_data:
            for device_info in config_data.get("interfaces"):
                for device_name, config_list in device_info.items():
                    if device_id := self.get_device_id(device_name=device_name):
                        device_config = {"interfaces": {}, "circuits": {}}
                        for config in config_list:
                            self.edge_interface(device_config, action="default_lan",
                                                default_lan=default_lan, **config)
                        output_config[device_id] = {"device_id": device_id, 
                                                    "edge": device_config}
                    else:
                        LOG.error(f"deconfigure_interfaces : \
                                  {device_name} unable to fetch device-id")
                        return
        self.concurrent_task_execution(self.gcsdk.put_device_config, output_config)
