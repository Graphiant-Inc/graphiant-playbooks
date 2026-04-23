# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for PortalUtils (I/O and executor mocked where needed)."""

from __future__ import annotations

import os
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils as portal_mod
from ansible_collections.graphiant.naas.plugins.module_utils.libs.exceptions import ConfigurationError
from ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils import PortalUtils


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.ThreadPoolExecutor")
def test_concurrent_task_execution_submits(
    m_tpe: MagicMock, m_client: MagicMock
) -> None:
    done_f = Future()
    done_f.set_result(1)
    m_ex = MagicMock()
    m_ex.submit.return_value = done_f
    ctx = m_tpe.return_value
    ctx.__enter__.return_value = m_ex
    ctx.__exit__.return_value = None

    p = PortalUtils("https://h", "u", "p")
    p.concurrent_task_execution(
        lambda **kwargs: 0, {"a": {"x": 1}, "b": {"y": 2}}
    )
    assert m_ex.submit.call_count == 2


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_wait_checked_raises_aggregated_exception(m_client: MagicMock) -> None:
    f = Future()
    f.set_exception(RuntimeError("e1"))
    with pytest.raises(Exception, match="futures failed"):
        PortalUtils.wait_checked([f])  # pylint: disable=protected-access


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_render_config_file(
    m_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "configs"
    cdir.mkdir()
    (cdir / "a.yaml").write_text("k: 1", encoding="utf-8")
    tdir = tmp_path / "templates"
    tdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_CONFIGS_PATH", str(cdir))
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    p = PortalUtils("https://h", "u", "p")
    out = p.render_config_file("a.yaml")
    assert out == {"k": 1}


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_render_config_file_path_traversal(
    m_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "safe"
    cdir.mkdir()
    tdir = tmp_path / "t"
    tdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_CONFIGS_PATH", str(cdir))
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    p = PortalUtils("https://h", "u", "p")
    with pytest.raises(ConfigurationError, match="Path traversal"):
        p.render_config_file("../nope.yaml")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.os.path.exists", return_value=False)
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_find_collection_root_none_when_nothing_on_disk(
    m_client: MagicMock, m_exists: MagicMock
) -> None:
    obj = object.__new__(PortalUtils)
    r = PortalUtils._find_collection_root(obj)  # pylint: disable=protected-access
    assert r is None
    assert m_exists.call_count >= 1


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_render_config_file_not_found(
    m_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "configs"
    cdir.mkdir()
    tdir = tmp_path / "t"
    tdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_CONFIGS_PATH", str(cdir))
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    p = PortalUtils("https://h", "u", "p")
    with pytest.raises(ConfigurationError, match="File not found"):
        p.render_config_file("missing.yaml")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_render_config_file_absolute_path(
    m_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tdir = tmp_path / "t"
    tdir.mkdir()
    cdir = tmp_path / "c"
    cdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    f = cdir / "abs.yaml"
    f.write_text("k: 2", encoding="utf-8")
    p = PortalUtils("https://h", "u", "p")
    p.config_path = str(cdir) + os.sep
    out = p.render_config_file(str(f))
    assert out == {"k": 2}


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_render_config_file_jinja2_template_error(
    m_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "c"
    cdir.mkdir()
    tdir = tmp_path / "t"
    tdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_CONFIGS_PATH", str(cdir))
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    (cdir / "bad.j2").write_text("{{ broken", encoding="utf-8")
    p = PortalUtils("https://h", "u", "p")
    with pytest.raises(ConfigurationError, match="Jinja2 template error|Error rendering Jinja2"):
        p.render_config_file("bad.j2")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_render_config_file_jinja2_generic_error_after_template_constructed(
    m_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "c"
    cdir.mkdir()
    tdir = tmp_path / "t"
    tdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_CONFIGS_PATH", str(cdir))
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    (cdir / "x.yaml").write_text("k: 1", encoding="utf-8")
    p = PortalUtils("https://h", "u", "p")
    with patch.object(portal_mod, "Template") as m_t:
        m_inst = MagicMock()
        m_t.return_value = m_inst
        m_inst.render.side_effect = RuntimeError("other")
        with pytest.raises(ConfigurationError, match="Error rendering Jinja2 template"):
            p.render_config_file("x.yaml")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.HAS_JINJA2", False)
def test_render_config_file_import_error_no_jinja2(
    m_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "c"
    cdir.mkdir()
    tdir = tmp_path / "t"
    tdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_CONFIGS_PATH", str(cdir))
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    p = PortalUtils("https://h", "u", "p")
    with pytest.raises(ImportError, match="Jinja2"):
        p.render_config_file("a.yaml")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.yaml.safe_load", side_effect=yaml.YAMLError("plain"))
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_render_config_file_yaml_error_no_problemmark(
    m_client: MagicMock, m_safe, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "c"
    cdir.mkdir()
    tdir = tmp_path / "t"
    tdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_CONFIGS_PATH", str(cdir))
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    (cdir / "y.yaml").write_text("a: 1", encoding="utf-8")
    p = PortalUtils("https://h", "u", "p")
    with pytest.raises(ConfigurationError, match="YAML parsing error"):
        p.render_config_file("y.yaml")
    m_safe.assert_called_once()


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_render_config_file_yaml_error_with_problemmark(
    m_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "c"
    cdir.mkdir()
    tdir = tmp_path / "t"
    tdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_CONFIGS_PATH", str(cdir))
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    (cdir / "z.yaml").write_text("k: [\n  x: 1", encoding="utf-8")
    p = PortalUtils("https://h", "u", "p")
    with pytest.raises(ConfigurationError, match="line |YAML syntax error"):
        p.render_config_file("z.yaml")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.HAS_YAML", False)
def test_render_config_file_import_error_no_yaml(
    m_client: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cdir = tmp_path / "c"
    cdir.mkdir()
    tdir = tmp_path / "t"
    tdir.mkdir()
    monkeypatch.setenv("GRAPHIANT_CONFIGS_PATH", str(cdir))
    monkeypatch.setenv("GRAPHIANT_TEMPLATES_PATH", str(tdir))
    p = PortalUtils("https://h", "u", "p")
    with pytest.raises(ImportError, match="PyYAML"):
        p.render_config_file("a.yaml")


@patch("ansible_collections.graphiant.naas.plugins.module_utils.libs.portal_utils.GraphiantPortalClient", autospec=True)
def test_wait_checked_skips_none(m_client: MagicMock) -> None:
    f = Future()
    f.set_result(1)
    PortalUtils.wait_checked([None, f, None])  # pylint: disable=protected-access
    assert f.done()
