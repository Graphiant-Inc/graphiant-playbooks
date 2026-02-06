import os
import subprocess
import unittest
import yaml
from libs.graphiant_config import GraphiantConfig
from libs.logger import setup_logger

LOG = setup_logger()


def read_config():
    """
    Read configuration from environment variables.

    Required environment variables:
        - GRAPHIANT_HOST: Graphiant API endpoint (e.g., https://api.graphiant.com)
        - GRAPHIANT_USERNAME: Graphiant API username
        - GRAPHIANT_PASSWORD: Graphiant API password

    Returns:
        tuple: (host, username, password)

    Raises:
        ValueError: If any required environment variable is not set
    """
    host = os.getenv('GRAPHIANT_HOST')
    username = os.getenv('GRAPHIANT_USERNAME')
    password = os.getenv('GRAPHIANT_PASSWORD')

    if not host:
        raise ValueError("GRAPHIANT_HOST environment variable is required")
    if not username:
        raise ValueError("GRAPHIANT_USERNAME environment variable is required")
    if not password:
        raise ValueError("GRAPHIANT_PASSWORD environment variable is required")

    return host, username, password


class TestGraphiantPlaybooks(unittest.TestCase):

    def test_get_login_token(self):
        """
        Test login and fetch token.
        """
        base_url, username, password = read_config()
        GraphiantConfig(base_url=base_url, username=username, password=password)

    def test_get_enterprise_id(self):
        """
        Test login and fetch enterprise id.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        enterprise_id = graphiant_config.config_utils.gsdk.get_enterprise_id()
        LOG.info("Enterprise ID: %s", enterprise_id)

    def test_configure_global_lan_segments(self):
        """
        Configure Global LAN Segments.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_lan_segments("sample_global_lan_segments.yaml")
        graphiant_config.global_config.configure("sample_global_lan_segments.yaml")

    def test_deconfigure_global_lan_segments(self):
        """
        Deconfigure Global LAN Segments.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_lan_segments("sample_global_lan_segments.yaml")
        graphiant_config.global_config.deconfigure("sample_global_lan_segments.yaml")

    def test_get_lan_segments(self):
        """
        Test login and fetch Lan segments.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        lan_segments = graphiant_config.config_utils.gsdk.get_lan_segments_dict()
        LOG.info("Lan Segments: %s", lan_segments)

    def test_configure_global_site_lists(self):
        """
        Configure Global Site Lists.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.global_config.configure_site_lists("sample_global_site_lists.yaml")

    def test_deconfigure_global_site_lists(self):
        """
        Deconfigure Global Site Lists.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.global_config.deconfigure_site_lists("sample_global_site_lists.yaml")

    def test_get_global_site_lists(self):
        """
        Test getting global site lists.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        site_lists = graphiant_config.config_utils.gsdk.get_global_site_lists()
        LOG.info("Global Site Lists: %s found", len(site_lists))
        for site_list in site_lists:
            LOG.info("Site List: %s (ID: %s)", site_list.name, site_list.id)

    def test_configure_sites(self):
        """
        Create Sites (if site doesn't exist).
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.sites.configure_sites("sample_sites.yaml")

    def test_deconfigure_sites(self):
        """
        Delete Sites (if site exists).
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.sites.deconfigure_sites("sample_sites.yaml")

    def test_configure_sites_and_attach_objects(self):
        """
        Configure Sites: Create sites and attach global objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.sites.configure("sample_sites.yaml")

    def test_get_sites_details(self):
        """
        Test getting detailed site information using v1/sites/details API.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        sites_details = graphiant_config.config_utils.gsdk.get_sites_details()
        LOG.info("Sites Details: %s sites found", len(sites_details))
        for site in sites_details:
            LOG.info(
                "Site: %s (ID: %s, Edges: %s, Segments: %s)",
                site.name,
                site.id,
                site.edge_count,
                site.segment_count,
            )

    def test_detach_objects_and_deconfigure_sites(self):
        """
        Deconfigure Sites: Detach global objects and delete sites.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.sites.deconfigure("sample_sites.yaml")

    def test_attach_objects_to_sites(self):
        """
        Attach Objects: Attach global system objects to existing sites.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.sites.attach_objects("sample_sites.yaml")

    def test_detach_objects_from_sites(self):
        """
        Detach Objects: Detach global system objects from sites.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.sites.detach_objects("sample_sites.yaml")

    def test_configure_wan_circuits_interfaces(self):
        """
        Configure WAN circuits and wan interfaces for multiple devices in a single operation.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.interfaces.configure_wan_circuits_interfaces(
            circuit_config_file="sample_circuit_config.yaml",
            interface_config_file="sample_interface_config.yaml"
        )
        LOG.info("Configure WAN circuits and interfaces result: %s", result)
        result = graphiant_config.interfaces.configure_wan_circuits_interfaces(
            circuit_config_file="sample_circuit_config.yaml",
            interface_config_file="sample_interface_config.yaml"
        )
        LOG.info("Configure WAN circuits and interfaces result (rerun check): %s", result)

    def test_configure_circuits(self):
        """
        Configure Circuits for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.interfaces.configure_circuits(
            circuit_config_file="sample_circuit_config.yaml",
            interface_config_file="sample_interface_config.yaml")
        LOG.info("Configure Circuits result: %s", result)
        result = graphiant_config.interfaces.configure_circuits(
            circuit_config_file="sample_circuit_config.yaml",
            interface_config_file="sample_interface_config.yaml")
        LOG.info("Configure Circuits result (rerun check): %s", result)

    def test_deconfigure_circuits(self):
        """
        Deconfigure Circuits staticRoutes for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.interfaces.deconfigure_circuits(
            interface_config_file="sample_interface_config.yaml",
            circuit_config_file="sample_circuit_config.yaml")
        LOG.info("Deconfigure Circuits result: %s", result)
        result = graphiant_config.interfaces.deconfigure_circuits(
            interface_config_file="sample_interface_config.yaml",
            circuit_config_file="sample_circuit_config.yaml")
        LOG.info("Deconfigure Circuits result (rerun check): %s", result)
        assert result['changed'] is False, "Deconfigure circuits idempotency failed"

    def test_deconfigure_wan_circuits_interfaces(self):
        """
        Deconfigure WAN circuits and interfaces for multiple devices in a single operation.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.interfaces.deconfigure_wan_circuits_interfaces(
            interface_config_file="sample_interface_config.yaml",
            circuit_config_file="sample_circuit_config.yaml"
        )
        LOG.info("Deconfigure WAN circuits and interfaces result: %s", result)
        result = graphiant_config.interfaces.deconfigure_wan_circuits_interfaces(
            interface_config_file="sample_interface_config.yaml",
            circuit_config_file="sample_circuit_config.yaml"
        )
        LOG.info("Deconfigure WAN circuits and interfaces result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure WAN circuits and interfaces idempotency failed"

    def test_configure_lan_interfaces(self):
        """
        Configure LAN interfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.interfaces.configure_lan_interfaces("sample_interface_config.yaml")
        LOG.info("Configure LAN interfaces result: %s", result)
        result = graphiant_config.interfaces.configure_lan_interfaces("sample_interface_config.yaml")
        LOG.info("Configure LAN interfaces result (rerun check): %s", result)

    def test_deconfigure_lan_interfaces(self):
        """
        Deconfigure LAN interfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.interfaces.deconfigure_lan_interfaces("sample_interface_config.yaml")
        LOG.info("Deconfigure LAN interfaces result: %s", result)
        result = graphiant_config.interfaces.deconfigure_lan_interfaces("sample_interface_config.yaml")
        LOG.info("Deconfigure LAN interfaces result (rerun check): %s", result)
        assert result['changed'] is False, "Deconfigure LAN interfaces idempotency failed"

    def test_configure_interfaces(self):
        """
        Configure Interfaces of all types.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.interfaces.configure_interfaces(
            interface_config_file="sample_interface_config.yaml",
            circuit_config_file="sample_circuit_config.yaml")
        LOG.info("Configure Interfaces result: %s", result)
        result = graphiant_config.interfaces.configure_interfaces(
            interface_config_file="sample_interface_config.yaml",
            circuit_config_file="sample_circuit_config.yaml")
        LOG.info("Configure Interfaces result (rerun check): %s", result)

    def test_deconfigure_interfaces(self):
        """
        Deconfigure Interfaces (i.e Reset parent interface to default lan and delete subinterfaces)
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.interfaces.deconfigure_interfaces(
            interface_config_file="sample_interface_config.yaml",
            circuit_config_file="sample_circuit_config.yaml")
        LOG.info("Deconfigure Interfaces result: %s", result)
        result = graphiant_config.interfaces.deconfigure_interfaces(
            interface_config_file="sample_interface_config.yaml",
            circuit_config_file="sample_circuit_config.yaml")
        LOG.info("Deconfigure Interfaces result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure Interfaces idempotency failed"

    def test_configure_vrrp_interfaces(self):
        """
        Configure VRRP (Virtual Router Redundancy Protocol) on interfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.vrrp_interfaces.configure("sample_vrrp_config.yaml")
        LOG.info("Configure VRRP interfaces result: %s", result)
        result = graphiant_config.vrrp_interfaces.configure("sample_vrrp_config.yaml")
        LOG.info("Configure VRRP interfaces result (rerun check): %s", result)

    def test_deconfigure_vrrp_interfaces(self):
        """
        Deconfigure VRRP (Virtual Router Redundancy Protocol) from interfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.vrrp_interfaces.deconfigure("sample_vrrp_config.yaml")
        LOG.info("Deconfigure VRRP interfaces result: %s", result)
        result = graphiant_config.vrrp_interfaces.deconfigure("sample_vrrp_config.yaml")
        LOG.info("Deconfigure VRRP interfaces result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure VRRP interfaces idempotency failed"

    def test_enable_vrrp_interfaces(self):
        """
        Enable existing VRRP (Virtual Router Redundancy Protocol) configurations on interfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.vrrp_interfaces.enable_vrrp_interfaces("sample_vrrp_config.yaml")
        LOG.info("Enable VRRP interfaces result: %s", result)
        result = graphiant_config.vrrp_interfaces.enable_vrrp_interfaces("sample_vrrp_config.yaml")
        LOG.info("Enable VRRP interfaces result (idempotency check): %s", result)
        assert result['changed'] is False, "Enable VRRP interfaces idempotency failed"

    def test_configure_lag_interfaces(self):
        """
        Configure LAG (Link Aggregation Group) on interfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.lag_interfaces.configure("sample_lag_interface_config.yaml")
        LOG.info("Configure LAG interfaces result: %s", result)
        result = graphiant_config.lag_interfaces.configure("sample_lag_interface_config.yaml")
        LOG.info("Configure LAG interfaces result (rerun check): %s", result)

    def test_update_lacp_configs(self):
        """
        Update LACP configurations for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.lag_interfaces.update_lacp_configs("sample_lag_interface_config.yaml")
        LOG.info("Update LACP configurations result: %s", result)
        result = graphiant_config.lag_interfaces.update_lacp_configs("sample_lag_interface_config.yaml")
        LOG.info("Update LACP configurations result (idempotency check): %s", result)
        assert result['changed'] is False, "Update LACP configurations idempotency failed"

    def test_add_lag_members(self):
        """
        Add LAG members to interfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.lag_interfaces.add_lag_members("sample_lag_interface_config.yaml")
        LOG.info("Add LAG members result: %s", result)
        result = graphiant_config.lag_interfaces.add_lag_members("sample_lag_interface_config.yaml")
        LOG.info("Add LAG members result (idempotency check): %s", result)
        assert result['changed'] is False, "Add LAG members idempotency failed"

    def test_remove_lag_members(self):
        """
        Remove LAG members from interfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.lag_interfaces.remove_lag_members("sample_lag_interface_config.yaml")
        LOG.info("Remove LAG members result: %s", result)
        result = graphiant_config.lag_interfaces.remove_lag_members("sample_lag_interface_config.yaml")
        LOG.info("Remove LAG members result (idempotency check): %s", result)
        assert result['changed'] is False, "Remove LAG members idempotency failed"

    def test_delete_lag_subinterfaces(self):
        """
        Delete LAG subinterfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.lag_interfaces.delete_lag_subinterfaces("sample_lag_interface_config.yaml")
        LOG.info("Delete LAG subinterfaces result: %s", result)
        result = graphiant_config.lag_interfaces.delete_lag_subinterfaces("sample_lag_interface_config.yaml")
        LOG.info("Delete LAG subinterfaces result (idempotency check): %s", result)
        assert result['changed'] is False, "Delete LAG subinterfaces idempotency failed"

    def test_deconfigure_lag_interfaces(self):
        """
        Deconfigure LAG (Link Aggregation Group) from interfaces for multiple devices.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.lag_interfaces.deconfigure("sample_lag_interface_config.yaml")
        LOG.info("Deconfigure LAG interfaces result: %s", result)
        result = graphiant_config.lag_interfaces.deconfigure("sample_lag_interface_config.yaml")
        LOG.info("Deconfigure LAG interfaces result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure LAG interfaces idempotency failed"

    def test_configure_global_config_prefix_lists(self):
        """
        Configure Global Config Prefix Lists.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_prefix_sets("sample_global_prefix_lists.yaml")
        graphiant_config.global_config.configure("sample_global_prefix_lists.yaml")

    def test_deconfigure_global_config_prefix_lists(self):
        """
        Deconfigure Global Config Prefix Lists.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_prefix_sets("sample_global_prefix_lists.yaml")
        graphiant_config.global_config.deconfigure("sample_global_prefix_lists.yaml")

    def test_configure_global_config_bgp_filters(self):
        """
        Configure Global BGP Filters.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_bgp_filters("sample_global_bgp_filters.yaml")
        graphiant_config.global_config.configure("sample_global_bgp_filters.yaml")

    def test_deconfigure_global_config_bgp_filters(self):
        """
        Deconfigure Global Config BGP Filters.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_bgp_filters("sample_global_bgp_filters.yaml")
        graphiant_config.global_config.deconfigure("sample_global_bgp_filters.yaml")

    def test_configure_bgp_peering(self):
        """
        Configure BGP Peering.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.bgp.configure("sample_bgp_peering.yaml")

    def test_deconfigure_bgp_peering(self):
        """
        Deconfigure BGP Peering.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.bgp.deconfigure("sample_bgp_peering.yaml")

    def test_detach_policies_from_bgp_peers(self):
        """
        Detach policies from BGP peers.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.bgp.detach_policies("sample_bgp_peering.yaml")

    def test_configure_snmp_service(self):
        """
        Configure Global SNMP Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_snmp_services("sample_global_snmp_services.yaml")
        graphiant_config.global_config.configure("sample_global_snmp_services.yaml")

    def test_deconfigure_snmp_service(self):
        """
        Deconfigure Global SNMP Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_snmp_services("sample_global_snmp_services.yaml")
        graphiant_config.global_config.deconfigure("sample_global_snmp_services.yaml")

    def test_configure_syslog_service(self):
        """
        Configure Global Syslog Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_syslog_services("sample_global_syslog_servers.yaml")
        graphiant_config.global_config.configure("sample_global_syslog_servers.yaml")

    def test_deconfigure_syslog_service(self):
        """
        Deconfigure Global Syslog Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_syslog_services(("sample_global_syslog_servers.yaml")
        graphiant_config.global_config.deconfigure("sample_global_syslog_servers.yaml")

    def test_configure_ipfix_service(self):
        """
        Configure Global IPFIX Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_ipfix_services("sample_global_ipfix_exporters.yaml")
        graphiant_config.global_config.configure("sample_global_ipfix_exporters.yaml")

    def test_deconfigure_ipfix_service(self):
        """
        Deconfigure Global IPFIX Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_ipfix_services("sample_global_ipfix_exporters.yaml")
        graphiant_config.global_config.deconfigure("sample_global_ipfix_exporters.yaml")

    def test_configure_vpn_profiles(self):
        """
        Configure Global VPN Profile Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_vpn_profiles("sample_global_vpn_profiles.yaml")
        graphiant_config.global_config.configure("sample_global_vpn_profiles.yaml")

    def test_deconfigure_vpn_profiles(self):
        """
        Deconfigure Global VPN Profile Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_vpn_profiles("sample_global_vpn_profiles.yaml")
        graphiant_config.global_config.deconfigure("sample_global_vpn_profiles.yaml")

    def test_attach_global_system_objects_to_site(self):
        """
        Attach Global System Objects (SNMP, Syslog, IPFIX etc) to Sites.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.sites.attach_objects("sample_site_attachments.yaml")

    def test_detach_global_system_objects_from_site(self):
        """
        Detach Global System Objects (SNMP, Syslog, IPFIX etc) from Sites.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.sites.detach_objects("sample_site_attachments.yaml")

    def test_create_data_exchange_services(self):
        """
        Create Data Exchange Services.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.data_exchange.create_services("de_workflows_configs/sample_data_exchange_services.yaml")

    def test_get_data_exchange_services_summary(self):
        """
        Get Data Exchange Services Summary.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.data_exchange.get_services_summary()

    def test_delete_data_exchange_services(self):
        """
        Delete Data Exchange Services.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.data_exchange.delete_services("de_workflows_configs/sample_data_exchange_services.yaml")

    def test_create_data_exchange_customers(self):
        """
        Create Data Exchange Customers.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.data_exchange.create_customers("de_workflows_configs/sample_data_exchange_customers.yaml")

    def test_get_data_exchange_customers_summary(self):
        """
        Get Data Exchange Customers Summary.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.data_exchange.get_customers_summary()

    def test_delete_data_exchange_customers(self):
        """
        Delete Data Exchange Customers.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.data_exchange.delete_customers("de_workflows_configs/sample_data_exchange_customers.yaml")

    def test_match_data_exchange_service_to_customers(self):
        """
        Match Data Exchange Service to Customer.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        graphiant_config.data_exchange.match_service_to_customers(
            "de_workflows_configs/sample_data_exchange_matches.yaml")

    def test_accept_data_exchange_invitation_dry_run(self):
        """
        Accept Data Exchange Service Invitation (Workflow 4).
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)

        # Test accept_invitation with configuration file
        config_file = "de_workflows_configs/sample_data_exchange_acceptance.yaml"
        matches_file = (
            "de_workflows/output/sample_data_exchange_matches_responses_latest.json"
        )

        LOG.info("Testing accept_invitation with config: %s", config_file)
        result = graphiant_config.data_exchange.accept_invitation(config_file, matches_file, dry_run=True)
        LOG.info("Accept invitation result: %s", result)

    def test_show_validated_payload_for_device_config(self):
        """
        Show validated payload for device configuration.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.device_config.show_validated_payload(
            config_yaml_file="sample_device_config_payload.yaml"
        )
        LOG.info("Show validated payload result: %s", result)

    def test_configure_device_config(self):
        """
        Configure device configuration.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.device_config.configure(
            config_yaml_file="sample_device_config_with_template.yaml",
            template_file="device_config_template.yaml")
        LOG.info("Configure device configuration result: %s", result)

    def _prepare_s2s_vault_secrets(self, config_path: str) -> None:
        """
        Decrypt configs/vault_secrets.yml and write vault_site_to_site_vpn_secrets.yml
        so the test can run without executing the playbook. Uses ~/.vault_pass or
        ANSIBLE_VAULT_PASSWORD_FILE and runs ansible-vault view (requires ansible-vault on PATH).
        """
        config_path = config_path.rstrip("/")
        vault_secrets_path = os.path.join(config_path, "vault_secrets.yml")
        vault_pass_file = os.environ.get(
            "ANSIBLE_VAULT_PASSWORD_FILE",
            os.path.expanduser("~/.vault_pass"),
        )
        if not os.path.isfile(vault_secrets_path):
            raise FileNotFoundError(
                f"Vault file not found: {vault_secrets_path}. "
                "Create and encrypt it (see configs/vault_secrets.yml.example)."
            )
        if not os.path.isfile(vault_pass_file):
            raise FileNotFoundError(
                f"Vault password file not found: {vault_pass_file}. "
                "Set ANSIBLE_VAULT_PASSWORD_FILE or create ~/.vault_pass."
            )
        env = os.environ.copy()
        env["ANSIBLE_VAULT_PASSWORD_FILE"] = os.path.abspath(vault_pass_file)
        result = subprocess.run(
            ["ansible-vault", "view", vault_secrets_path],
            capture_output=True,
            text=True,
            env=env,
            cwd=config_path,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ansible-vault view failed: {result.stderr or result.stdout or 'unknown'}. "
                "Ensure ansible-vault is on PATH (e.g. pip install ansible-core)."
            )
        decrypted_bytes = result.stdout.encode("utf-8")
        data = yaml.safe_load(decrypted_bytes.decode("utf-8"))
        vault_keys = (data or {}).get("vault_site_to_site_vpn_keys") or {}
        vault_md5 = (data or {}).get("vault_bgp_md5_passwords") or {}
        out_path = os.path.join(config_path, "vault_site_to_site_vpn_secrets.yml")
        with open(out_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {"vault_site_to_site_vpn_keys": vault_keys, "vault_bgp_md5_passwords": vault_md5},
                f, default_flow_style=False, sort_keys=False,
            )
        LOG.info("Prepared %s from vault for test (no playbook run needed)", out_path)

    def test_create_site_to_site_vpn(self):
        """
        Create Site-to-Site VPN. Decrypts configs/vault_secrets.yml via ansible-vault view
        (~/.vault_pass or ANSIBLE_VAULT_PASSWORD_FILE) and writes vault_site_to_site_vpn_secrets.yml
        so the manager injects vault values. No playbook run required. Requires ansible-vault on PATH.
        """
        # Prefer workspace configs when running from source (so vault_secrets.yml is found)
        if "GRAPHIANT_CONFIGS_PATH" not in os.environ:
            _workspace_configs = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "configs")
            )
            if os.path.isdir(_workspace_configs):
                os.environ["GRAPHIANT_CONFIGS_PATH"] = _workspace_configs
                LOG.info("Using workspace configs for test: %s", _workspace_configs)
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        self._prepare_s2s_vault_secrets(graphiant_config.config_utils.config_path)
        result = graphiant_config.site_to_site_vpn.create_site_to_site_vpn("sample_site_to_site_vpn.yaml")
        LOG.info("Create Site-to-Site VPN result: %s", result)
        result = graphiant_config.site_to_site_vpn.create_site_to_site_vpn("sample_site_to_site_vpn.yaml")
        LOG.info("Create Site-to-Site VPN result (idempotency check): %s", result)
        assert result['changed'] is False, "Create Site-to-Site VPN idempotency failed"

    def test_delete_site_to_site_vpn(self):
        """
        Delete Site-to-Site VPN. Second run is idempotent: no VPNs to delete (already absent),
        so changed=False and no API push.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.site_to_site_vpn.delete_site_to_site_vpn("sample_site_to_site_vpn.yaml")
        LOG.info("Delete Site-to-Site VPN result: %s", result)
        result2 = graphiant_config.site_to_site_vpn.delete_site_to_site_vpn("sample_site_to_site_vpn.yaml")
        LOG.info("Delete Site-to-Site VPN result (idempotency check): %s", result2)
        assert result2['changed'] is False, "Delete Site-to-Site VPN idempotency failed"


if __name__ == '__main__':
    suite = unittest.TestSuite()
    suite.addTest(TestGraphiantPlaybooks('test_get_login_token'))
    suite.addTest(TestGraphiantPlaybooks('test_get_enterprise_id'))

    # LAN Segments Management Tests
    suite.addTest(TestGraphiantPlaybooks('test_get_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_get_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_get_lan_segments'))

    # Site Management Tests
    suite.addTest(TestGraphiantPlaybooks('test_get_sites_details'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_sites'))
    suite.addTest(TestGraphiantPlaybooks('test_get_sites_details'))

    suite.addTest(TestGraphiantPlaybooks('test_configure_global_lan_segments'))  # Pre-req: Create Lan segments.
    suite.addTest(TestGraphiantPlaybooks('test_configure_snmp_service'))  # Pre-req: SNMP system object.

    suite.addTest(TestGraphiantPlaybooks('test_attach_objects_to_sites'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_sites_and_attach_objects'))
    suite.addTest(TestGraphiantPlaybooks('test_detach_objects_from_sites'))
    suite.addTest(TestGraphiantPlaybooks('test_detach_objects_and_deconfigure_sites'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_sites'))
    suite.addTest(TestGraphiantPlaybooks('test_get_sites_details'))

    # Global Configuration Management (Site Lists)
    suite.addTest(TestGraphiantPlaybooks('test_get_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_sites'))  # Pre-req: Create sites.
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_get_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_get_global_site_lists'))

    # Global Configuration Management (VPN Profiles)
    suite.addTest(TestGraphiantPlaybooks('test_configure_vpn_profiles'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_vpn_profiles'))

    # Global Configuration Management (Prefix Lists and BGP Filters)
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_config_prefix_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_config_bgp_filters'))

    # Global Configuration Management (SNMP, Syslog, IPFIX)
    suite.addTest(TestGraphiantPlaybooks('test_configure_snmp_service'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_syslog_service'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_ipfix_service'))

    # Device Interface Configuration Management
    suite.addTest(TestGraphiantPlaybooks('test_configure_lan_interfaces'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_lan_interfaces'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_wan_circuits_interfaces'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_circuits'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_circuits'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_wan_circuits_interfaces'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_interfaces'))
    # suite.addTest(TestGraphiantPlaybooks('test_deconfigure_interfaces'))

    # VRRP Interface Configuration Management
    suite.addTest(TestGraphiantPlaybooks('test_configure_vrrp_interfaces'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_vrrp_interfaces'))
    suite.addTest(TestGraphiantPlaybooks('test_enable_vrrp_interfaces'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_vrrp_interfaces'))

    # LAG Interface Configuration Management
    suite.addTest(TestGraphiantPlaybooks('test_configure_lag_interfaces'))
    suite.addTest(TestGraphiantPlaybooks('test_update_lacp_configs'))
    suite.addTest(TestGraphiantPlaybooks('test_remove_lag_members'))
    suite.addTest(TestGraphiantPlaybooks('test_add_lag_members'))
    suite.addTest(TestGraphiantPlaybooks('test_delete_lag_subinterfaces'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_lag_interfaces'))

    # Global Configuration Management and BGP Peering
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_config_prefix_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_config_bgp_filters'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_bgp_peering'))
    suite.addTest(TestGraphiantPlaybooks('test_detach_policies_from_bgp_peers'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_bgp_peering'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_config_bgp_filters'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_config_prefix_lists'))

    # Site-to-Site VPN Management
    suite.addTest(TestGraphiantPlaybooks('test_configure_vpn_profiles'))
    suite.addTest(TestGraphiantPlaybooks('test_create_site_to_site_vpn'))  # Pre-req: Configure interfaces and circuits and VPN Profiles
    suite.addTest(TestGraphiantPlaybooks('test_delete_site_to_site_vpn'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_vpn_profiles'))

    # Global Configuration Management and Attaching System Objects (SNMP, Syslog, IPFIX etc) to Sites
    suite.addTest(TestGraphiantPlaybooks('test_configure_snmp_service'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_syslog_service'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_ipfix_service'))
    suite.addTest(TestGraphiantPlaybooks('test_attach_global_system_objects_to_site'))
    suite.addTest(TestGraphiantPlaybooks('test_detach_global_system_objects_from_site'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_snmp_service'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_syslog_service'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_ipfix_service'))

    # Data Exchange Tests
    suite.addTest(TestGraphiantPlaybooks('test_create_data_exchange_services'))
    suite.addTest(TestGraphiantPlaybooks('test_get_data_exchange_services_summary'))
    suite.addTest(TestGraphiantPlaybooks('test_create_data_exchange_customers'))
    suite.addTest(TestGraphiantPlaybooks('test_get_data_exchange_customers_summary'))
    suite.addTest(TestGraphiantPlaybooks('test_match_data_exchange_service_to_customers'))
    suite.addTest(TestGraphiantPlaybooks('test_get_data_exchange_customers_summary'))
    suite.addTest(TestGraphiantPlaybooks('test_get_data_exchange_services_summary'))
    # suite.addTest(TestGraphiantPlaybooks('test_accept_data_exchange_invitation_dry_run'))
    suite.addTest(TestGraphiantPlaybooks('test_delete_data_exchange_customers'))
    suite.addTest(TestGraphiantPlaybooks('test_delete_data_exchange_services'))

    # To deconfigure all interfaces
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_interfaces'))

    # Device Configuration Management Tests
    suite.addTest(TestGraphiantPlaybooks('test_show_validated_payload_for_device_config'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_device_config'))

    runner = unittest.TextTestRunner(verbosity=2).run(suite)
