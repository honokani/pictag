"""セル（チェックボックス）の更新と表データ"""
import json

import pytest

from helpers import col, make_images


@pytest.fixture
def loaded(api, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100)}))
    api.add("A")
    return api


def strict_json(data):
    def reject(constant):
        raise ValueError(f"非標準の JSON 値: {constant}")

    return json.loads(data, parse_constant=reject)


def test_update_cell_sets_value(loaded, tool):
    assert loaded.set(loaded.row_index("b.png"), "A")["success"]
    assert tool.df.set_index("サムネイル")[col("A")].to_dict() == {"a.png": False, "b.png": True}


def test_update_cell_rejects_unknown_column(loaded, tool):
    assert loaded.set(0, "ZZZ")["success"] is False
    assert col("ZZZ") not in tool.df.columns


@pytest.mark.parametrize("column", ["サムネイル", "is_dead"])
def test_update_cell_rejects_fixed_columns(loaded, tool, column):
    before = tool.df.copy()
    assert loaded.set(0, column)["success"] is False
    assert tool.df.equals(before)


def test_update_cell_rejects_unknown_row(loaded, tool):
    assert loaded.set(99, "A")["success"] is False
    assert len(tool.df) == 2


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_update_cell_rejects_non_bool(loaded, tool, value):
    assert loaded.set(0, "A", value)["success"] is False
    assert tool.df[col("A")].tolist() == [False, False]


def test_table_data_is_strict_json_after_bad_updates(loaded, client):
    loaded.set(0, "ZZZ")
    loaded.set(99, "A")
    body = strict_json(client.get("/get_table_data").data)
    assert [r[col("A")] for r in body["data"]] == [False, False]
