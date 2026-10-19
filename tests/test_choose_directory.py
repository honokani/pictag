"""フォルダを選ぶ窓（参照…）。窓そのものは開かず、開く関数・プロセスの起動を差し替えて確かめる"""
import subprocess
import sys
from pathlib import Path

import pytest

import app as pictag


def test_choose_directory_returns_the_chosen_folder(api, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(pictag, "ask_directory", lambda initial: calls.append(initial) or "C:/photos/movies")
    res = api.post("/choose_directory", {"initial": str(tmp_path)})
    assert res == {"success": True, "path": str(Path("C:/photos/movies"))}
    assert calls == [str(tmp_path)]  # 入力欄のフォルダから選び始める


def test_cancel_returns_an_empty_path_and_a_missing_initial_folder_is_dropped(api, monkeypatch):
    calls = []
    monkeypatch.setattr(pictag, "ask_directory", lambda initial: calls.append(initial) or "")
    assert api.post("/choose_directory", {"initial": "Z:/no/such/folder"}) == {"success": True, "path": ""}
    assert calls == [""]


def test_the_window_opens_only_for_this_pc(client, monkeypatch):
    monkeypatch.setattr(pictag, "ask_directory", lambda initial: pytest.fail("窓を開いてはいけない"))
    body = client.post("/choose_directory", json={}, environ_base={"REMOTE_ADDR": "192.168.1.20"}).get_json()
    assert body["success"] is False and "パスを入力" in body["message"]


def test_a_failing_window_is_reported(api, monkeypatch):
    def broken(initial):
        raise RuntimeError("ModuleNotFoundError: No module named 'tkinter'")

    monkeypatch.setattr(pictag, "ask_directory", broken)
    res = api.post("/choose_directory", {})
    assert res["success"] is False and "tkinter" in res["message"]


def test_ask_directory_opens_the_window_in_another_process(monkeypatch):
    seen = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        return subprocess.CompletedProcess(args, 0, stdout="C:/photos/movies\n", stderr="")

    monkeypatch.setattr(pictag.subprocess, "run", fake_run)
    assert pictag.ask_directory("C:/photos") == "C:/photos/movies"
    assert seen["args"][0] == sys.executable and seen["args"][-1] == "C:/photos"


def test_ask_directory_raises_with_the_last_error_line(monkeypatch):
    def fake_run(args, **kwargs):
        stderr = "Traceback (most recent call last):\nModuleNotFoundError: No module named 'tkinter'\n"
        return subprocess.CompletedProcess(args, 1, stdout="", stderr=stderr)

    monkeypatch.setattr(pictag.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="No module named 'tkinter'"):
        pictag.ask_directory("")
