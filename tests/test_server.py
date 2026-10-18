"""起動設定"""
import app as pictag


def test_server_listens_on_localhost_by_default():
    assert pictag.server_options({})["host"] == "127.0.0.1"


def test_server_host_can_be_overridden_for_lan():
    assert pictag.server_options({"PICTAG_HOST": "0.0.0.0"})["host"] == "0.0.0.0"


def test_server_keeps_port_and_debug():
    options = pictag.server_options({})
    assert options["port"] == 5000
    assert options["debug"] is True
