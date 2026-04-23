# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for ConfigUtils (mocked I/O: portal client, templates)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils import ConfigUtils
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_validate_required_params_passes(_mock_client, _mock_tmpl) -> None:
    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    cu._validate_required_params(  # pylint: disable=protected-access
        {"name": "n1", "extra": 1}, ["name"]
    )


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_validate_required_params_missing(_mock_client, _mock_tmpl) -> None:
    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    with pytest.raises(ConfigurationError, match="Missing required parameters"):
        cu._validate_required_params(  # pylint: disable=protected-access
            {"extra": 1},
            ["name", "role"],
        )


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_prefix_set_add(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_global_prefix_set.return_value = {"pfx-a": {"id": 1}}
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"global_prefix_sets": {}}
    cu.global_prefix_set(payload, action="add", name="pfx-a", region="us")
    assert "pfx-a" in payload["global_prefix_sets"]
    template.render_global_prefix_set.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_bgp_filter_delete(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_global_bgp_filter.return_value = {}
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"routing_policies": {"bgp-1": {"k": 1}}}
    cu.global_bgp_filter(payload, action="delete", name="bgp-1")
    assert payload["routing_policies"]["bgp-1"] == {}


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_device_interface_merges_interfaces(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_interface.return_value = {
        "interfaces": {"eth0": {"enabled": True}},
    }
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"interfaces": {}}
    cu.device_interface(payload, action="add", name="eth0")
    assert "eth0" in payload["interfaces"]


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_lag_interfaces_prefers_lag_interfaces(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_lag_interfaces.return_value = {
        "lagInterfaces": {"bnd0": {"members": []}},
    }
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"lagInterfaces": {}}
    cu.lag_interfaces(payload, action="add", name="bnd0")
    assert "bnd0" in payload["lagInterfaces"]


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_lag_interfaces_falls_back_to_interfaces(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_lag_interfaces.return_value = {
        "interfaces": {"eth0": {}},
    }
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"interfaces": {}}
    cu.lag_interfaces(payload, action="add", name="bnd0")
    assert "eth0" in payload["interfaces"]


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_graphiant_filter_add(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_global_graphiant_filter.return_value = {"gf-1": {"k": 1}}
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"routing_policies": {}}
    cu.global_graphiant_filter(payload, action="add", name="gf-1", region="us")
    assert "gf-1" in payload["routing_policies"]


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_device_bgp_peering_resolves_route_policies(_mock_client, mock_tmpl_class) -> None:
    client = MagicMock()
    client.return_value = client
    client.get_global_routing_policy_id.side_effect = lambda n: 42 if n == "p1" else 99
    _mock_client.return_value = client

    template = MagicMock()
    template.render_bgp_peering.return_value = {"neighbors": {"n1": {}}}
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {}
    cu.device_bgp_peering(
        payload, action="add", segments="s1", route_policies=["p1", "p2"]
    )
    template.render_bgp_peering.assert_called_once()
    call_kw = template.render_bgp_peering.call_args[1]
    assert call_kw["global_ids"] == {"p1": 42, "p2": 99}


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_device_bgp_peering_missing_policy(_mock_client, mock_tmpl_class) -> None:
    client = MagicMock()
    client.get_global_routing_policy_id.return_value = None
    _mock_client.return_value = client
    mock_tmpl_class.return_value = MagicMock()

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    with pytest.raises(ConfigurationError, match="not found"):
        cu.device_bgp_peering(
            {}, action="add", segments="s1", route_policies=["missing"]
        )


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_vrrp_interfaces_creates_interfaces_dict(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_vrrp_interfaces.return_value = {"interfaces": {"eth0": {"v": 1}}}
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {}
    cu.vrrp_interfaces(payload, action="add", name="eth0")
    assert "eth0" in payload["interfaces"]


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_device_circuit_add(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_circuit.return_value = {"circuits": {"c1": {}}}
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"circuits": {}}
    cu.device_circuit(payload, action="add", circuit="c1", site="s1")
    assert "c1" in payload["circuits"]


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_syslog_lan_segment_to_vrf(_mock_client, mock_tmpl_class) -> None:
    client = MagicMock()
    client.get_lan_segment_id.return_value = 7
    _mock_client.return_value = client
    template = MagicMock()
    template.render_syslog_service.return_value = {"sl-1": {}}
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"syslog_servers": {}}
    kwargs: dict = {
        "name": "sl-1",
        "target": {"lanSegment": "ls-a"},
    }
    cu.global_syslog(payload, action="add", **kwargs)
    template.render_syslog_service.assert_called_once()
    re_kw = template.render_syslog_service.call_args[1]
    assert re_kw["target"].get("vrfId") == 7
    assert "lanSegment" not in re_kw["target"]


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_ipfix_lan_segment_to_vrf(_mock_client, mock_tmpl_class) -> None:
    client = MagicMock()
    client.get_lan_segment_id.return_value = 9
    _mock_client.return_value = client
    template = MagicMock()
    template.render_ipfix_service.return_value = {"ip-1": {}}
    mock_tmpl_class.return_value = template

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"ipfix_exporters": {}}
    cu.global_ipfix(
        payload, action="add", name="ip-1", exporter={"lanSegment": "ls-b"}
    )
    ex = template.render_ipfix_service.call_args[1]["exporter"]
    assert ex.get("vrfId") == 9
    assert "lanSegment" not in ex


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_ntp_add_with_optional_ids(_mock_client, mock_tmpl_class) -> None:
    _mock_client.return_value = MagicMock()
    mock_tmpl_class.return_value = MagicMock()

    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"ntps": {}}
    cu.global_ntp(
        payload,
        action="add",
        name="n1",
        domains=["a.example.com"],
        globalId=5,
        isGlobalSync=True,
    )
    assert payload["ntps"]["n1"]["config"]["globalId"] == 5
    assert payload["ntps"]["n1"]["config"]["isGlobalSync"] is True


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_ntp_delete(_mock_client, mock_tmpl_class) -> None:
    _mock_client.return_value = MagicMock()
    mock_tmpl_class.return_value = MagicMock()
    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"ntps": {"n1": {"config": {}}}}
    cu.global_ntp(payload, action="delete", name="n1")
    assert payload["ntps"]["n1"] == {}


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_vpn_profile_add(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_vpn_profile.return_value = {"vpn_profiles": {"v1": {"a": 1}}}
    mock_tmpl_class.return_value = template
    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"vpn_profiles": {}}
    cu.global_vpn_profile(payload, action="add", name="v1", region="r1")
    assert "v1" in payload["vpn_profiles"]


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_site_list_add(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_site_list.return_value = {"sl-1": {}}
    mock_tmpl_class.return_value = template
    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"site_lists": {}}
    cu.global_site_list(payload, action="add", name="sl-1", sites=[])
    assert "sl-1" in payload["site_lists"]


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_snmp_delete(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    mock_tmpl_class.return_value = template
    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    payload: dict = {"snmps": {"s1": {"a": 1}}}
    cu.global_snmp(payload, action="delete", name="s1")
    assert payload["snmps"]["s1"] == {}


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_utils.ConfigTemplates")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient")
def test_global_prefix_set_template_error(_mock_client, mock_tmpl_class) -> None:
    template = MagicMock()
    template.render_global_prefix_set.side_effect = ValueError("bad")
    mock_tmpl_class.return_value = template
    cu = ConfigUtils(base_url="https://api.example.com", username="u", password="p")
    with pytest.raises(ConfigurationError, match="Global prefix set processing failed"):
        cu.global_prefix_set(
            {"global_prefix_sets": {}}, action="add", name="p1", region="r"
        )
