"""
Integration tests for the Graphiant NaaS collection.

Runs against a live Graphiant portal. Requires GRAPHIANT_HOST, GRAPHIANT_USERNAME,
and GRAPHIANT_PASSWORD environment variables.

Run from repo root with PYTHONPATH including the collection module_utils:
  export PYTHONPATH=$PYTHONPATH:$(pwd)/ansible_collections/graphiant/naas/plugins/module_utils
  python ansible_collections/graphiant/naas/tests/test.py
"""
import os
import shutil
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

    def test_configure_global_config_prefix_lists(self):
        """
        Configure Global Config Prefix Lists.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_prefix_sets("sample_global_prefix_lists.yaml")
        result = graphiant_config.global_config.configure("sample_global_prefix_lists.yaml")
        LOG.info("Configure prefix lists result: %s", result)
        result = graphiant_config.global_config.configure("sample_global_prefix_lists.yaml")
        LOG.info("Configure prefix lists result (rerun check): %s", result)

    def test_deconfigure_global_config_prefix_lists(self):
        """
        Deconfigure Global Config Prefix Lists.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_prefix_sets("sample_global_prefix_lists.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_prefix_lists.yaml")
        LOG.info("Deconfigure prefix lists result: %s", result)
        result = graphiant_config.global_config.deconfigure("sample_global_prefix_lists.yaml")
        LOG.info("Deconfigure prefix lists result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure prefix lists idempotency failed"
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed' key"
        assert result['failed'] is False, f"Deconfigure Global prefix lists failed: {result}"

    def test_failure_deconfigure_global_config_prefix_lists(self):
        """
        Test failure to deconfigure Global Config Prefix Lists if objects are in use.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_prefix_sets("sample_global_prefix_lists.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_prefix_lists.yaml")
        LOG.info("Deconfigure prefix lists result: %s", result)
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        assert result['failed'] is True, "Deconfigure Global prefix lists not failed"
        if result['failed']:
            details = result.get('details', {})
            prefix_sets = details.get('prefix_sets', {})
            assert prefix_sets.get('failed_objects'), "When failed is True, details.prefix_sets.failed_objects must be non-empty"

    def test_configure_global_config_bgp_filters(self):
        """
        Configure Global BGP Filters.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_bgp_filters("sample_global_bgp_filters.yaml")
        result = graphiant_config.global_config.configure("sample_global_bgp_filters.yaml")
        LOG.info("Configure BGP filters result: %s", result)
        result = graphiant_config.global_config.configure("sample_global_bgp_filters.yaml")
        LOG.info("Configure BGP filters result (rerun check): %s", result)

    def test_deconfigure_global_config_bgp_filters(self):
        """
        Deconfigure Global Config BGP Filters.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_bgp_filters("sample_global_bgp_filters.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_bgp_filters.yaml")
        LOG.info("Deconfigure BGP filters result: %s", result)
        result = graphiant_config.global_config.deconfigure("sample_global_bgp_filters.yaml")
        LOG.info("Deconfigure BGP filters result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure BGP filters idempotency failed"
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        if result['failed']:
            details = result.get('details', {})
            bgp_filters = details.get('bgp_filters', {})
            assert bgp_filters.get('failed_objects'), "When failed is True, details.bgp_filters.failed_objects must be non-empty"
        assert result['failed'] is False, f"Deconfigure Global BGP filters failed: {result}"

    def test_configure_snmp_service(self):
        """
        Configure Global SNMP Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_snmp_services("sample_global_snmp_services.yaml")
        result = graphiant_config.global_config.configure("sample_global_snmp_services.yaml")
        LOG.info("Configure SNMP service result: %s", result)
        result = graphiant_config.global_config.configure("sample_global_snmp_services.yaml")
        LOG.info("Configure SNMP service result (rerun check): %s", result)

    def test_deconfigure_snmp_service(self):
        """
        Deconfigure Global SNMP Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_snmp_services("sample_global_snmp_services.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_snmp_services.yaml")
        LOG.info("Deconfigure SNMP service result: %s", result)
        result = graphiant_config.global_config.deconfigure("sample_global_snmp_services.yaml")
        LOG.info("Deconfigure SNMP service result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure SNMP service idempotency failed"
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        if result['failed']:
            details = result.get('details', {})
            snmp_services = details.get('snmps', {})
            assert snmp_services.get('failed_objects'), "When failed is True, details.snmp_services.failed_objects must be non-empty"
        assert result['failed'] is False, f"Deconfigure Global SNMP services failed: {result}"

    def test_failure_deconfigure_snmp_service(self):
        """
        Test failure to deconfigure Global SNMP Objects if objects are in use.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_snmp_services("sample_global_snmp_services.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_snmp_services.yaml")
        LOG.info("Deconfigure SNMP service result: %s", result)
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        assert result['failed'] is True, "Deconfigure Global SNMP objects not failed"
        if result['failed']:
            details = result.get('details', {})
            snmp_services = details.get('snmps', {})
            assert snmp_services.get('failed_objects'), "When failed is True, details.snmp_services.failed_objects must be non-empty"

    def test_configure_syslog_service(self):
        """
        Configure Global Syslog Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_syslog_services("sample_global_syslog_servers.yaml")
        result = graphiant_config.global_config.configure("sample_global_syslog_servers.yaml")
        LOG.info("Configure syslog service result: %s", result)
        result = graphiant_config.global_config.configure("sample_global_syslog_servers.yaml")
        LOG.info("Configure syslog service result (rerun check): %s", result)

    def test_deconfigure_syslog_service(self):
        """
        Deconfigure Global Syslog Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_syslog_services(("sample_global_syslog_servers.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_syslog_servers.yaml")
        LOG.info("Deconfigure syslog service result: %s", result)
        result = graphiant_config.global_config.deconfigure("sample_global_syslog_servers.yaml")
        LOG.info("Deconfigure syslog service result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure syslog service idempotency failed"
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        if result['failed']:
            details = result.get('details', {})
            syslog_services = details.get('syslog_services', {})
            assert syslog_services.get('failed_objects'), "When failed is True, details.syslog_services.failed_objects must be non-empty"
        assert result['failed'] is False, f"Deconfigure Global syslog services failed: {result}"

    def test_configure_ipfix_service(self):
        """
        Configure Global IPFIX Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_ipfix_services("sample_global_ipfix_exporters.yaml")
        result = graphiant_config.global_config.configure("sample_global_ipfix_exporters.yaml")
        LOG.info("Configure IPFIX service result: %s", result)
        result = graphiant_config.global_config.configure("sample_global_ipfix_exporters.yaml")
        LOG.info("Configure IPFIX service result (rerun check): %s", result)

    def test_deconfigure_ipfix_service(self):
        """
        Deconfigure Global IPFIX Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_ipfix_services("sample_global_ipfix_exporters.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_ipfix_exporters.yaml")
        LOG.info("Deconfigure IPFIX service result: %s", result)
        result = graphiant_config.global_config.deconfigure("sample_global_ipfix_exporters.yaml")
        LOG.info("Deconfigure IPFIX service result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure IPFIX service idempotency failed"
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        if result['failed']:
            details = result.get('details', {})
            ipfix_services = details.get('ipfix_services', {})
            assert ipfix_services.get('failed_objects'), "When failed is True, details.ipfix_services.failed_objects must be non-empty"
        assert result['failed'] is False, f"Deconfigure Global IPFIX services failed: {result}"

    def test_configure_vpn_profiles(self):
        """
        Configure Global VPN Profile Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_vpn_profiles("sample_global_vpn_profiles.yaml")
        result = graphiant_config.global_config.configure("sample_global_vpn_profiles.yaml")
        LOG.info("Configure VPN profiles result: %s", result)
        result = graphiant_config.global_config.configure("sample_global_vpn_profiles.yaml")
        LOG.info("Configure VPN profiles result (rerun check): %s", result)

    def test_deconfigure_vpn_profiles(self):
        """
        Deconfigure Global VPN Profile Objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_vpn_profiles("sample_global_vpn_profiles.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_vpn_profiles.yaml")
        LOG.info("Deconfigure VPN profiles result: %s", result)
        result = graphiant_config.global_config.deconfigure("sample_global_vpn_profiles.yaml")
        LOG.info("Deconfigure VPN profiles result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure VPN profiles idempotency failed"
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        if result['failed']:
            details = result.get('details', {})
            vpn_profiles = details.get('vpn_profiles', {})
            assert vpn_profiles.get('failed_objects'), "When failed is True, details.vpn_profiles.failed_objects must be non-empty"
        assert result['failed'] is False, f"Deconfigure Global VPN profiles failed: {result}"

    def test_failure_deconfigure_vpn_profiles(self):
        """
        Test failure to deconfigure Global VPN Profiles if objects are in use.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_vpn_profiles("sample_global_vpn_profiles.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_vpn_profiles.yaml")
        LOG.info("Deconfigure VPN profiles result: %s", result)
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        assert result['failed'] is True, "Deconfigure Global VPN profiles not failed"
        if result['failed']:
            details = result.get('details', {})
            vpn_profiles = details.get('vpn_profiles', {})
            assert vpn_profiles.get('failed_objects'), "When failed is True, details.vpn_profiles.failed_objects must be non-empty"

    def test_configure_global_lan_segments(self):
        """
        Configure Global LAN Segments.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.configure_lan_segments("sample_global_lan_segments.yaml")
        result = graphiant_config.global_config.configure("sample_global_lan_segments.yaml")
        LOG.info("Configure Global LAN segments result: %s", result)
        result = graphiant_config.global_config.configure("sample_global_lan_segments.yaml")
        LOG.info("Configure Global LAN segments result (rerun check): %s", result)

    def test_deconfigure_global_lan_segments(self):
        """
        Deconfigure Global LAN Segments.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_lan_segments("sample_global_lan_segments.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_lan_segments.yaml")
        LOG.info("Deconfigure Global LAN segments result: %s", result)
        result = graphiant_config.global_config.deconfigure("sample_global_lan_segments.yaml")
        LOG.info("Deconfigure Global LAN segments result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure Global LAN segments idempotency failed"
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        if result['failed']:
            details = result.get('details', {})
            lan = details.get('lan_segments', {})
            assert lan.get('failed_objects'), "When failed is True, details.lan_segments.failed_objects must be non-empty"
        assert result['failed'] is False, f"Deconfigure Global LAN segments failed: {result}"

    def test_get_lan_segments(self):
        """
        Test login and fetch Lan segments.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        lan_segments = graphiant_config.config_utils.gsdk.get_lan_segments_dict()
        LOG.info("Lan Segments: %s", lan_segments)

    def test_failure_deconfigure_global_lan_segments(self):
        """
        Test failure to deconfigure Global LAN Segments if objects are in use.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        # graphiant_config.global_config.deconfigure_lan_segments("sample_global_lan_segments.yaml")
        result = graphiant_config.global_config.deconfigure("sample_global_lan_segments.yaml")
        LOG.info("Deconfigure Global LAN segments result: %s", result)
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        assert result['failed'] is True, "Deconfigure Global LAN segments not failed"
        if result['failed']:
            details = result.get('details', {})
            lan_segments = details.get('lan_segments', {})
            assert lan_segments.get('failed_objects'), "When failed is True, details.lan_segments.failed_objects must be non-empty"

    def test_configure_global_site_lists(self):
        """
        Configure Global Site Lists.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.global_config.configure_site_lists("sample_global_site_lists.yaml")
        LOG.info("Configure Global Site Lists result: %s", result)
        result = graphiant_config.global_config.configure_site_lists("sample_global_site_lists.yaml")
        LOG.info("Configure Global Site Lists result (idempotency check): %s", result)
        assert result['changed'] is False, "Configure Global Site Lists idempotency failed"

    def test_deconfigure_global_site_lists(self):
        """
        Deconfigure Global Site Lists.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.global_config.deconfigure_site_lists("sample_global_site_lists.yaml")
        LOG.info("Deconfigure Global Site Lists result: %s", result)
        result = graphiant_config.global_config.deconfigure_site_lists("sample_global_site_lists.yaml")
        LOG.info("Deconfigure Global Site Lists result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure Global Site Lists idempotency failed"
        assert 'failed' in result, "Deconfigure Global config result must include top-level 'failed'"
        if result['failed']:
            details = result.get('details', {})
            site_lists = details.get('site_lists', {})
            assert site_lists.get('failed_objects'), "When failed is True, details.site_lists.failed_objects must be non-empty"
        assert result['failed'] is False, f"Deconfigure Global Site Lists failed: {result}"

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
        result = graphiant_config.sites.configure_sites("sample_sites.yaml")
        LOG.info("Configure Sites result: %s", result)
        result = graphiant_config.sites.configure_sites("sample_sites.yaml")
        LOG.info("Configure Sites result (idempotency check): %s", result)
        assert result['changed'] is False, "Configure Sites idempotency failed"

    def test_deconfigure_sites(self):
        """
        Delete Sites (if site exists).
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.sites.deconfigure_sites("sample_sites.yaml")
        LOG.info("Deconfigure Sites result: %s", result)
        result = graphiant_config.sites.deconfigure_sites("sample_sites.yaml")
        LOG.info("Deconfigure Sites result (idempotency check): %s", result)
        assert result['changed'] is False, "Deconfigure Sites idempotency failed"

    def test_configure_sites_and_attach_objects(self):
        """
        Configure Sites: Create sites and attach global objects.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.sites.configure("sample_sites.yaml")
        LOG.info("Configure Sites and attach objects result: %s", result)
        result = graphiant_config.sites.configure("sample_sites.yaml")
        LOG.info("Configure Sites and attach objects result (idempotency check): %s", result)
        assert result['changed'] is False, "Configure Sites and attach objects idempotency failed"

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
        result = graphiant_config.sites.deconfigure("sample_sites.yaml")
        LOG.info("Detach objects and deconfigure sites result: %s", result)
        result = graphiant_config.sites.deconfigure("sample_sites.yaml")
        LOG.info("Detach objects and deconfigure sites result (idempotency check): %s", result)
        assert result['changed'] is False, "Detach objects and deconfigure sites idempotency failed"

    def test_attach_objects_to_sites(self):
        """
        Attach Objects: Attach global system objects to existing sites.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.sites.attach_objects("sample_sites.yaml")
        LOG.info("Attach objects to sites result: %s", result)
        result = graphiant_config.sites.attach_objects("sample_sites.yaml")
        LOG.info("Attach objects to sites result (idempotency check): %s", result)
        assert result['changed'] is False, "Attach objects to sites idempotency failed"

    def test_detach_objects_from_sites(self):
        """
        Detach Objects: Detach global system objects from sites.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.sites.detach_objects("sample_sites.yaml")
        LOG.info("Detach objects from sites result: %s", result)
        result = graphiant_config.sites.detach_objects("sample_sites.yaml")
        LOG.info("Detach objects from sites result (idempotency check): %s", result)
        assert result['changed'] is False, "Detach objects from sites idempotency failed"

    def test_attach_global_system_objects_to_site(self):
        """
        Attach Global System Objects (SNMP, Syslog, IPFIX etc) to Sites.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.sites.attach_objects("sample_site_attachments.yaml")
        LOG.info("Attach global system objects to site result: %s", result)
        result = graphiant_config.sites.attach_objects("sample_site_attachments.yaml")
        LOG.info("Attach global system objects to site result (idempotency check): %s", result)
        assert result['changed'] is False, "Attach global system objects to site idempotency failed"

    def test_detach_global_system_objects_from_site(self):
        """
        Detach Global System Objects (SNMP, Syslog, IPFIX etc) from Sites.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        result = graphiant_config.sites.detach_objects("sample_site_attachments.yaml")
        LOG.info("Detach global system objects from site result: %s", result)
        result = graphiant_config.sites.detach_objects("sample_site_attachments.yaml")
        LOG.info("Detach global system objects from site result (idempotency check): %s", result)
        assert result['changed'] is False, "Detach global system objects from site idempotency failed"

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

    def test_create_site_to_site_vpn(self):
        """
        Create Site-to-Site VPN. Copies vault_secrets.yml.example to vault_secrets.yml,
        encrypts with vault-password-file.sh (uses ANSIBLE_VAULT_PASSPHRASE or 'test-vault-pass' if unset), then creates VPN.
        """
        base_url, username, password = read_config()
        graphiant_config = GraphiantConfig(base_url=base_url, username=username, password=password)
        config_path = graphiant_config.config_utils.config_path

        # Copy example to vault_secrets.yml and encrypt (use ANSIBLE_VAULT_PASSPHRASE or default for tests)
        if not os.environ.get("ANSIBLE_VAULT_PASSPHRASE"):
            os.environ["ANSIBLE_VAULT_PASSPHRASE"] = "test-vault-pass"
        vault_secrets_path = os.path.join(config_path, "vault_secrets.yml")
        example_path = os.path.join(config_path, "vault_secrets.yml.example")
        if not os.path.isfile(example_path):
            raise FileNotFoundError(f"Vault example not found: {example_path}")
        shutil.copy(example_path, vault_secrets_path)
        vault_pass_file = os.path.join(config_path, "vault-password-file.sh")
        if not os.path.isfile(vault_pass_file):
            raise FileNotFoundError(f"Vault password script not found: {vault_pass_file}")
        env = os.environ.copy()
        env["ANSIBLE_VAULT_PASSWORD_FILE"] = os.path.abspath(vault_pass_file)
        enc = subprocess.run(
            ["ansible-vault", "encrypt", vault_secrets_path],
            capture_output=True, text=True, env=env, cwd=config_path, check=False,
        )
        if enc.returncode != 0:
            err = (enc.stderr and enc.stderr.strip()) or "unknown"
            raise RuntimeError(f"ansible-vault encrypt failed: {err}")

        # Decrypt to get vault dicts
        view = subprocess.run(
            ["ansible-vault", "view", vault_secrets_path],
            capture_output=True, text=True, env=env, cwd=config_path, check=False,
        )
        if view.returncode != 0:
            err = (view.stderr and view.stderr.strip()) or "unknown"
            raise RuntimeError(f"ansible-vault view failed: {err}")
        data = yaml.safe_load(view.stdout) or {}
        vault_keys = data.get("vault_site_to_site_vpn_keys") or {}
        vault_md5 = data.get("vault_bgp_md5_passwords") or {}
        if not isinstance(vault_keys, dict):
            vault_keys = {}
        if not isinstance(vault_md5, dict):
            vault_md5 = {}

        result = graphiant_config.site_to_site_vpn.create_site_to_site_vpn(
            "sample_site_to_site_vpn.yaml",
            vault_site_to_site_vpn_keys=vault_keys,
            vault_bgp_md5_passwords=vault_md5,
        )
        LOG.info("Create Site-to-Site VPN result: %s", result)
        result = graphiant_config.site_to_site_vpn.create_site_to_site_vpn(
            "sample_site_to_site_vpn.yaml",
            vault_site_to_site_vpn_keys=vault_keys,
            vault_bgp_md5_passwords=vault_md5,
        )
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

    # Global Configuration Management (Prefix Lists and BGP Filters)
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_config_prefix_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_config_bgp_filters'))  # Pre-req: Configure prefix sets.
    #   Failure is expected as prefix_sets are in use by BGP filters
    suite.addTest(TestGraphiantPlaybooks('test_failure_deconfigure_global_config_prefix_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_config_bgp_filters'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_config_prefix_lists'))

    # LAN Segments Management Tests
    suite.addTest(TestGraphiantPlaybooks('test_get_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_get_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_get_lan_segments'))

    # Global Configuration Management (SNMP, Syslog, IPFIX)
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_lan_segments'))  # Pre-req: Create Lan segments.
    suite.addTest(TestGraphiantPlaybooks('test_configure_snmp_service'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_syslog_service'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_ipfix_service'))
    #   Failure is expected as lan segments are in use by SNMP, Syslog, IPFIX.
    suite.addTest(TestGraphiantPlaybooks('test_failure_deconfigure_global_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_snmp_service'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_syslog_service'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_ipfix_service'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_lan_segments'))

    # Site Management Tests (sample_sites.yaml)
    suite.addTest(TestGraphiantPlaybooks('test_get_sites_details'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_sites'))
    suite.addTest(TestGraphiantPlaybooks('test_get_sites_details'))
    #    Create Lan segments and SNMP system object before attaching SNMP objects to sites.
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_lan_segments'))  # Pre-req: Create Lan segments.
    suite.addTest(TestGraphiantPlaybooks('test_configure_snmp_service'))  # Pre-req: SNMP system object.
    suite.addTest(TestGraphiantPlaybooks('test_attach_objects_to_sites'))
    #   Failure is expected as SNMP objects are in use by sites.
    suite.addTest(TestGraphiantPlaybooks('test_failure_deconfigure_snmp_service'))
    suite.addTest(TestGraphiantPlaybooks('test_detach_objects_from_sites'))
    #   Failure is not expected as SNMP objects are not in use by sites.
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_snmp_service'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_sites'))
    suite.addTest(TestGraphiantPlaybooks('test_get_sites_details'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_snmp_service'))  # Pre-req: SNMP system object.
    suite.addTest(TestGraphiantPlaybooks('test_configure_sites_and_attach_objects'))
    suite.addTest(TestGraphiantPlaybooks('test_detach_objects_and_deconfigure_sites'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_snmp_service'))

    # Global Configuration Management (Site Lists)
    suite.addTest(TestGraphiantPlaybooks('test_get_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_sites'))  # Pre-req: Create sites.
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_get_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_global_site_lists'))
    suite.addTest(TestGraphiantPlaybooks('test_get_global_site_lists'))

    # Global Configuration Management (VPN Profiles)
    suite.addTest(TestGraphiantPlaybooks('test_configure_vpn_profiles'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_vpn_profiles'))

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
    #    Failure is expected as VPN profiles are in use by Site-to-Site VPNs.
    suite.addTest(TestGraphiantPlaybooks('test_failure_deconfigure_vpn_profiles'))
    suite.addTest(TestGraphiantPlaybooks('test_delete_site_to_site_vpn'))
    suite.addTest(TestGraphiantPlaybooks('test_deconfigure_vpn_profiles'))

    # Site Management Tests (sample_site_attachments.yaml) Attach/Detatch Objects (SNMP, Syslog, IPFIX ) to Sites.
    suite.addTest(TestGraphiantPlaybooks('test_configure_global_lan_segments'))
    suite.addTest(TestGraphiantPlaybooks('test_configure_snmp_service'))  # Pre-req: SNMP system object.
    suite.addTest(TestGraphiantPlaybooks('test_configure_syslog_service'))  # Pre-req: Syslog system object.
    suite.addTest(TestGraphiantPlaybooks('test_configure_ipfix_service'))  # Pre-req: IPFIX system object.
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
