"""マーキング（排他の列 A〜D、複数可の列 ★●▲■）。作業用の印で、キャプションには書き出さない"""
import json

import pytest

from helpers import caption_of, make_images


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100), "c.png": (100, 100)})


def marks(tool, column):
    return tool.df.set_index("サムネイル")[column].to_dict()


def set_mark(api, rows, mark):
    return api.post("/set_mark", {"rows": rows, "mark": mark})


def set_marks(api, rows, mark, on=True):
    return api.post("/set_marks", {"rows": rows, "mark": mark, "on": on})


def test_set_and_clear_exclusive_mark(api, tool, imgs):
    api.load(imgs)
    res = set_mark(api, [0, 1], "A")
    assert res["success"] and [r["mark"] for r in res["rows"]] == ["A", "A"]
    set_mark(api, [1], "C")
    assert marks(tool, "mark") == {"a.png": "A", "b.png": "C", "c.png": ""}
    set_mark(api, [0], "")
    assert marks(tool, "mark") == {"a.png": "", "b.png": "C", "c.png": ""}


def test_multi_marks_toggle_and_keep_symbol_order(api, tool, imgs):
    api.load(imgs)
    set_marks(api, [0, 1], "▲")
    res = set_marks(api, [0], "★")
    assert res["rows"][0]["marks"] == "★▲"
    set_marks(api, [0, 1], "▲", on=False)
    assert marks(tool, "marks") == {"a.png": "★", "b.png": "", "c.png": ""}


@pytest.mark.parametrize("url, payload", [
    ("/set_mark", {"rows": [0], "mark": "E"}),
    ("/set_mark", {"rows": [99], "mark": "A"}),
    ("/set_marks", {"rows": [0], "mark": "A", "on": True}),
    ("/set_marks", {"rows": [0], "mark": "★", "on": "yes"}),
    ("/set_marks", {"rows": "0", "mark": "★", "on": True}),
])
def test_bad_mark_requests_are_rejected(api, tool, imgs, url, payload):
    api.load(imgs)
    res = api.post(url, payload)
    assert res["success"] is False and res["message"]
    assert set(marks(tool, "mark").values()) == {""} and set(marks(tool, "marks").values()) == {""}


def test_marks_survive_save_and_reload(api, tool, imgs, base_dir):
    api.load(imgs)
    set_mark(api, [0], "B")
    set_marks(api, [0], "■")
    api.save()
    table = json.loads((base_dir / "data_out" / "proj" / "table.json").read_text(encoding="utf-8"))
    assert table["rows"][0]["mark"] == "B" and table["rows"][0]["marks"] == "■"

    api.open_project("proj")
    assert marks(tool, "mark")["a.png"] == "B" and marks(tool, "marks")["a.png"] == "■"


def test_marks_are_not_written_to_captions(api, tool, imgs):
    api.load(imgs)
    api.write(0, "looks: standing")
    set_mark(api, [0], "A")
    set_marks(api, [0], "★")
    api.save()
    assert (tool.captions_dir / "a.caption").read_text(encoding="utf-8") == caption_of("looks: standing")


def test_clear_marks_clears_one_column_on_every_row(api, tool, imgs):
    api.load(imgs)
    set_mark(api, [0, 1, 2], "D")
    set_marks(api, [0, 2], "●")
    assert api.post("/clear_marks", {"column": "mark"})["success"]
    assert set(marks(tool, "mark").values()) == {""}
    assert marks(tool, "marks") == {"a.png": "●", "b.png": "", "c.png": "●"}
    api.post("/clear_marks", {"column": "marks"})
    assert set(marks(tool, "marks").values()) == {""}
    assert api.post("/clear_marks", {"column": "girl"})["success"] is False


def test_table_data_has_marks_and_choices(api, imgs):
    api.load(imgs)
    set_mark(api, [0], "A")
    body = api.table()
    assert body["mark_choices"] == {"one": ["A", "B", "C", "D"], "many": ["★", "●", "▲", "■"]}
    assert [(r["mark"], r["marks"]) for r in body["data"]] == [("A", ""), ("", ""), ("", "")]
    assert body["sections"] == ["picture", "action", "girl", "guy"]


@pytest.mark.parametrize("name", ["mark", "marks"])
def test_mark_column_names_are_reserved(api, tool, imgs, name):
    api.load(imgs)
    assert api.add_section(name)["success"] is False
