from libs.portal_utils import PortalUtils
from libs.edge_templates import EdgeTemplates
from libs.logger import setup_logger

LOG = setup_logger()

class EdgeUtils(PortalUtils):

    def __init__(self, base_url=None, username=None, password=None, **kwargs):
        super().__init__(base_url=base_url, username=username, password=password, **kwargs)
        self.template = EdgeTemplates(self.templates)

    def global_prefix_set(self, config_payload, action="add", **kwargs):
        """
        Updates the global_prefix_sets section of configuration payload(config_payload) 
        using a rendered template.

        Args:
            config_payload (dict): The main configuration payload dict to be updated.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional key-value pairs required for rendering the template.

        Returns:
            None: The global_prefix_sets section in config_payload dict is updated.
        """
        LOG.debug(f"global_prefix_set : {action.upper()} Global Prefix Set {kwargs.get('name')}")
        global_prefix_set = self.template._global_prefix_set(action=action, **kwargs)
        config_payload['global_prefix_sets'].update(global_prefix_set)

    def global_bgp_filter(self, config_payload, action="add", **kwargs):
        """
        Updates the routing_policies section of the configuration payload(config_payload) 
        using the rendered template.

        Args:
            config_payload (dict): The configuration dictionary that holds routing policies.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional parameters used for rendering the template.

        Returns:
            None: The routing_policies section in config_payload is updated in-place.
        """
        LOG.debug(f"global_bgp_filter : {action.upper()} Global BGP Filter {kwargs.get('name')}")
        global_bgp_filter = self.template._global_bgp_filter(action=action, **kwargs)
        config_payload['routing_policies'].update(global_bgp_filter)
    
    def edge_bgp_peering(self, config_payload, action="add", **kwargs):
        """
        Updates the edge_bgp_peering section of configuration payload(config_payload) 
        using a rendered template.

        Args:
            config_payload (dict): Dictionary to be updated with BGP peering configuration.
            action (str, optional): Action to perform, either "add" or "delete". Defaults to "add".
            **kwargs: Additional parameters used for rendering the BGP peering configuration.

        Returns:
            None: The edge_bgp_peering section in config_payload is modified in-place.
        """
        global_ids = {}
        LOG.info(f"edge_bgp_peering : config_payload {config_payload}")
        if kwargs.get("route_policies"):
            for policy_name in kwargs.get("route_policies"):
                global_ids[policy_name] = self.get_global_routing_policy_id(policy_name)
                LOG.debug(f"edge_bgp_peering : Global ID for {policy_name} : {global_ids[policy_name]}")
        LOG.debug(f"edge_bgp_peering : {action.upper()} BGP Peering :\n {kwargs}")
        bgp_peering = self.template._edge_bgp_peering(action=action, global_ids=global_ids, **kwargs)
        config_payload.update(bgp_peering)
    
    def edge_interface(self, config_payload, action="add", **kwargs):
        """
        Updates the edge interfaces/circuits section of the configuration payload(config_payload)
        using a rendered template.

        Args:
            config_payload (dict): Dictionary to be updated with interface and circuit data.
            action (str, optional): Action to perform, either "add" or "default_lan" or "delete". 
            Defaults to "add".
            **kwargs: Additional parameters passed to the template renderer.

        Returns:
            None: The interfaces and circuits section in config_payload is modified in-place.
        """
        LOG.debug(f"edge_interfaces : {action.upper()} Edge Interfaces :\n {kwargs}")
        interface = self.template._edge_interface(action=action, **kwargs)
        config_payload["interfaces"].update(interface.get("interfaces"))
        if interface.get('circuits'):
            config_payload['circuits'].update(interface.get("circuits"))
    