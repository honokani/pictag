import pytest

import app as pictag
from helpers import Api


@pytest.fixture
def base_dir(tmp_path):
    d = tmp_path / "base"
    d.mkdir()
    return d


@pytest.fixture
def tool(base_dir, monkeypatch):
    t = pictag.CaptionTool(base_dir=base_dir)
    monkeypatch.setattr(pictag, "caption_tool", t)
    return t


@pytest.fixture
def client(tool):
    return pictag.app.test_client()


@pytest.fixture
def api(client):
    return Api(client)
