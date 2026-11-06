import shutil
from pathlib import Path

import pytest

import app as pictag
from helpers import Api


@pytest.fixture(autouse=True)
def trash(tmp_path, monkeypatch):
    """画像削除のごみ箱の代わり（テストでは本物のごみ箱を使わない）。ごみ箱へ移したファイルは tmp_path/trash に入る"""
    d = tmp_path / "trash"
    d.mkdir()
    monkeypatch.setattr(pictag, "trash", lambda path: shutil.move(path, d / Path(path).name))
    return d


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
