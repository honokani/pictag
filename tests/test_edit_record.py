"""行ごとの「最後に書き換えた時刻」（edited_at）: 📍（続きへ）と、あとで作る書き漏らし探しに使う。保存で table.json に書く"""
import json

import pytest

from helpers import make_images


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100), "c.png": (100, 100)})


def edited(api):
    return {r["サムネイル"]: r["edited_at"] for r in api.rows()}


def choose(api, rows, phrase):
    return api.post("/set_choice", {"rows": rows, "section": "picture", "key": "view", "phrase": phrase,
                                    "group": ["from front", "from side", "from behind"], "on": True})


def test_writing_a_row_records_when_it_was_edited(api, imgs):
    # その行の欄を書き換えると、その行に時刻が付く（ほかの行は空のまま）。同じ中身を送り直しても変わらない
    api.load(imgs)
    assert set(edited(api).values()) == {""}
    a = api.row_index("a.png")
    assert api.write(a, "looks: smile")["edited_at"]
    first = edited(api)["a.png"]
    assert first and edited(api)["b.png"] == ""
    api.write(a, "looks: smile")
    assert edited(api)["a.png"] == first
    api.write(api.row_index("b.png"), "looks: sitting")
    assert edited(api)["b.png"] > first  # 後で書いた行ほど大きい（📍 は一番大きい行へ）


def test_bulk_input_and_buttons_on_several_rows_are_not_recorded(api, imgs):
    # 一括入力と、選んだ複数行へのボタンは、まとめての作業なので数えない。ボタンを1行だけに押したときは、その行の書き換えとして数える
    api.load(imgs)
    rows = [api.row_index("a.png"), api.row_index("b.png")]
    assert api.post("/add_phrase", {"rows": rows, "section": "girl", "text": "looks: smile"})["success"]
    assert choose(api, rows, "from front")["success"]
    assert set(edited(api).values()) == {""}
    assert choose(api, rows[:1], "from side")["success"]
    assert edited(api)["a.png"] and edited(api)["b.png"] == ""


def test_edit_records_are_saved_in_the_table_and_read_back(api, imgs, base_dir):
    api.load(imgs)
    api.write(api.row_index("a.png"), "looks: smile")
    stamp = edited(api)["a.png"]
    api.save()
    rows = json.loads((base_dir / "data_out" / "proj" / "table.json").read_text(encoding="utf-8"))["rows"]
    assert [r.get("edited_at") for r in rows] == [stamp, None, None]  # 記録のある行だけ書く
    api.open_project("proj")
    assert edited(api) == {"a.png": stamp, "b.png": "", "c.png": ""}
    api.load(imgs)  # 画像フォルダから読み直しても引き継ぐ
    assert edited(api)["a.png"] == stamp


def test_edited_at_cannot_be_a_section_name(api, imgs):
    api.load(imgs)
    assert api.add_section("edited_at")["success"] is False
