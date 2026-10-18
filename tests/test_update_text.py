"""入力（画像 × 段落の文字列）の更新"""
import json

import pytest

from helpers import make_images


@pytest.fixture
def loaded(api, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100)}))
    return api


def girl(tool):
    return tool.df.set_index("サムネイル")["girl"].to_dict()


def strict_json(data):
    def reject(constant):
        raise ValueError(f"非標準の JSON 値: {constant}")

    return json.loads(data, parse_constant=reject)


def test_update_text_sets_value_and_returns_caption(loaded, tool):
    res = loaded.write(loaded.row_index("b.png"), "looks: standing")
    assert res["success"]
    assert res["caption"] == "girl:\n  - looks: standing"
    assert girl(tool) == {"a.png": "", "b.png": "looks: standing"}


def test_update_text_normalizes_newlines(loaded, tool):
    loaded.write(0, "a\r\nb\rc")
    assert girl(tool)["a.png"] == "a\nb\nc"


def test_update_text_rejects_unknown_section(loaded, tool):
    assert loaded.write(0, "x", section="zzz")["success"] is False
    assert "zzz" not in tool.df.columns


@pytest.mark.parametrize("section", ["サムネイル", "is_dead"])
def test_update_text_rejects_fixed_columns(loaded, tool, section):
    before = tool.df.copy()
    assert loaded.write(0, "x", section=section)["success"] is False
    assert tool.df.equals(before)


def test_update_text_rejects_unknown_row(loaded, tool):
    assert loaded.write(99, "x")["success"] is False
    assert len(tool.df) == 2


@pytest.mark.parametrize("value", [1, None, True, ["a"]])
def test_update_text_rejects_non_text(loaded, tool, value):
    assert loaded.write(0, value)["success"] is False
    assert girl(tool) == {"a.png": "", "b.png": ""}


def test_table_data_is_strict_json_after_bad_updates(loaded, client):
    loaded.write(0, "x", section="zzz")
    loaded.write(99, "x")
    body = strict_json(client.get("/get_table_data").data)
    assert [r["texts"]["girl"] for r in body["data"]] == ["", ""]
