# -*- coding: utf-8 -*-
# Copyright (c) Graphiant, Inc. | GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt)
"""Unit tests for graphiant_macsec module (mocked Ansible + connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ansible_collections.graphiant.naas.plugins.modules import graphiant_macsec


def test_module_params_from_ansible() -> None:
    mp = graphiant_macsec._module_params_from_ansible(
        {
            "device": " edge-1 ",
            "interfaces": {
                "LAG1": {"enabled": True},
            },
        }
    )
    assert mp["device"] == "edge-1"
    assert mp["interfaces"]["LAG1"]["enabled"] is True


@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_macsec.get_graphiant_connection")
@patch("ansible_collections.graphiant.naas.plugins.modules.graphiant_macsec.AnsibleModule")
def test_main_requires_device_or_file(mock_module_cls, mock_conn) -> None:
    module = MagicMock()
    module.params = {
        "host": "https://api.example.com",
        "username": "u",
        "password": "p",
        "access_token": None,
        "macsec_config_file": None,
        "device": "",
        "interfaces": None,
        "vault_devices_macsec_psk": {},
        "operation": "configure",
        "state": "present",
        "detailed_logs": False,
    }
    module.check_mode = False
    mock_module_cls.return_value = module

    graphiant_macsec.main()
    module.fail_json.assert_called_once()
    assert "macsec_config_file" in module.fail_json.call_args.kwargs["msg"]
