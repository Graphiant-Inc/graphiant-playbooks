# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for ConfigTemplates (Jinja2 env mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import yaml
from jinja2 import TemplateNotFound, TemplateSyntaxError

from ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates import ConfigTemplates
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError, TemplateError


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_get_available_templates(m_env, _m_loader) -> None:
    m_env.return_value = MagicMock()
    ct = ConfigTemplates("/tmp/collection/templates")
    m = ct.get_available_templates()
    assert m["interface"] == "interface_template.yaml"
    assert m["site_list"] == "global_site_lists_template.yaml"


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_render_by_type_unknown(m_env, _m_loader) -> None:
    m_env.return_value = MagicMock()
    ct = ConfigTemplates("/tmp/t")
    with pytest.raises(TemplateError, match="Unknown template type"):
        ct.render_by_type("not_a_real_type_ever")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_validate_template_true(m_env, _m_loader) -> None:
    tmpl = MagicMock()
    m_env.return_value = MagicMock()
    m_env.return_value.get_template.return_value = tmpl
    ct = ConfigTemplates("/tmp/t")
    assert ct.validate_template("x.yaml") is True
    tmpl.render.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_validate_template_false(m_env, _m_loader) -> None:
    m_env.return_value = MagicMock()
    m_env.return_value.get_template.side_effect = OSError("no")
    ct = ConfigTemplates("/tmp/t")
    assert ct.validate_template("x.yaml") is False


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.map_vpn_profiles")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_render_vpn_profile_applies_map_vpn_profiles(
    m_env, _m_loader, m_map: MagicMock,
) -> None:
    m_map.side_effect = lambda x: x
    m_env.return_value = MagicMock()
    ct = ConfigTemplates("/tmp/t")
    with patch.object(
        ct,
        "render_by_type",
        return_value={"vpn_profiles": {"v": 1}},
    ) as m_rb:
        out = ct.render_vpn_profile(vpn_profiles=[{"name": "a"}])
    m_map.assert_called_once()
    m_rb.assert_called_once()
    assert out == {"vpn_profiles": {"v": 1}}


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.HAS_JINJA2", False)
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.HAS_YAML", True)
def test_render_template_import_error_no_jinja(m_env, _m_loader) -> None:
    m_env.return_value = MagicMock()
    ct = ConfigTemplates("/tmp/t")
    with pytest.raises(ImportError, match="Jinja2"):
        ct.render_template("any.yaml", a=1)


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.HAS_JINJA2", True)
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.HAS_YAML", False)
def test_render_template_import_error_no_yaml(m_env, _m_loader) -> None:
    m_env.return_value = MagicMock()
    ct = ConfigTemplates("/tmp/t")
    with pytest.raises(ImportError, match="PyYAML"):
        ct.render_template("any.yaml", a=1)


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_init_fails_wrapped_as_template_error(m_env, m_loader) -> None:
    m_env.side_effect = OSError("bad path")
    with pytest.raises(TemplateError, match="Failed to initialize template environment"):
        ConfigTemplates("/nope/that/does/not/matter")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_render_template_not_found(m_env, _m_loader) -> None:
    env = MagicMock()
    env.get_template.side_effect = TemplateNotFound("missing.j2")
    m_env.return_value = env
    ct = ConfigTemplates("/tmp/t")
    with pytest.raises(TemplateError, match="not found"):
        ct.render_template("missing.j2")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_render_template_syntax_error(m_env, _m_loader) -> None:
    tmpl = MagicMock()
    tmpl.render.side_effect = TemplateSyntaxError("bad", 1, 1, "")
    env = MagicMock()
    env.get_template.return_value = tmpl
    m_env.return_value = env
    ct = ConfigTemplates("/tmp/t")
    with pytest.raises(TemplateError, match="Syntax error"):
        ct.render_template("bad.j2", x=1)


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.yaml.safe_load")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_render_template_yaml_error(m_env, _m_loader, m_safe) -> None:
    tmpl = MagicMock()
    tmpl.render.return_value = "k: 1"
    env = MagicMock()
    env.get_template.return_value = tmpl
    m_env.return_value = env
    m_safe.side_effect = yaml.YAMLError("parse fail")
    ct = ConfigTemplates("/tmp/t")
    with pytest.raises(ConfigurationError, match="YAML parsing error"):
        ct.render_template("x.j2", k=1)
    m_safe.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_render_template_unexpected_get_template_error(m_env, _m_loader) -> None:
    env = MagicMock()
    env.get_template.side_effect = RuntimeError("weird")
    m_env.return_value = env
    ct = ConfigTemplates("/tmp/t")
    with pytest.raises(TemplateError, match="Unexpected error rendering"):
        ct.render_template("x.j2")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.map_vpn_profiles")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.FileSystemLoader")
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.config_templates.Environment")
def test_render_vpn_profile_template_error(
    m_env, _m_loader, m_map: MagicMock
) -> None:
    m_env.return_value = MagicMock()
    ct = ConfigTemplates("/tmp/t")
    with patch.object(ct, "render_by_type", side_effect=ValueError("x")):
        with pytest.raises(TemplateError, match="Error in VPN profile rendering"):
            # No vpn_profiles key so map is skipped; failure comes from render_by_type
            ct.render_vpn_profile()
    m_map.assert_not_called()
