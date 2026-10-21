"""マーキング（排他の列 A〜H、複数可の列 ★●▲■◆♥♣♠）。作業用の印で、キャプションには書き出さない

中では番号（0〜7）で持ち、見せる記号は marks.py の表で決める（記号を差し替えても、保存したデータは変わらない）
"""
import json

import pytest

from helpers import caption_of, make_images
from marks import auto_marks_of, matches_pattern

ONE = list("ABCDEFGH")
MANY = ["★", "●", "▲", "■", "◆", "♥", "♣", "♠"]
AUTO = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧"]
SMILE = {"section": "girl", "key": "looks", "phrase": "smile"}


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
    res = set_mark(api, [0, 1], 0)
    assert res["success"] and [r["mark"] for r in res["rows"]] == [0, 0]
    set_mark(api, [1], 7)
    assert marks(tool, "mark") == {"a.png": "0", "b.png": "7", "c.png": ""}
    set_mark(api, [0], None)
    assert marks(tool, "mark") == {"a.png": "", "b.png": "7", "c.png": ""}


def test_multi_marks_toggle_and_keep_number_order(api, tool, imgs):
    api.load(imgs)
    set_marks(api, [0, 1], 2)
    set_marks(api, [0], 7)
    res = set_marks(api, [0], 0)
    assert res["rows"][0]["marks"] == [0, 2, 7]
    set_marks(api, [0, 1], 2, on=False)
    assert marks(tool, "marks") == {"a.png": "0,7", "b.png": "", "c.png": ""}


@pytest.mark.parametrize("url, payload", [
    ("/set_mark", {"rows": [0], "mark": 8}),  # 0〜7 の外
    ("/set_mark", {"rows": [0], "mark": "A"}),  # 記号ではなく番号で
    ("/set_mark", {"rows": [0], "mark": True}),  # 真偽は番号ではない
    ("/set_mark", {"rows": [99], "mark": 0}),
    ("/set_marks", {"rows": [0], "mark": -1, "on": True}),
    ("/set_marks", {"rows": [0], "mark": 0, "on": "yes"}),
    ("/set_marks", {"rows": "0", "mark": 0, "on": True}),
])
def test_bad_mark_requests_are_rejected(api, tool, imgs, url, payload):
    api.load(imgs)
    res = api.post(url, payload)
    assert res["success"] is False and res["message"]
    assert set(marks(tool, "mark").values()) == {""} and set(marks(tool, "marks").values()) == {""}


def test_marks_survive_save_and_reload_as_numbers(api, tool, imgs, base_dir):
    api.load(imgs)
    set_mark(api, [0], 1)
    set_marks(api, [0], 6)
    set_marks(api, [0], 3)
    api.save()
    table = json.loads((base_dir / "data_out" / "proj" / "table.json").read_text(encoding="utf-8"))
    assert table["rows"][0]["mark"] == 1 and table["rows"][0]["marks"] == [3, 6]
    assert "mark" not in table["rows"][1] and "marks" not in table["rows"][1]  # 無い行は書かない

    api.open_project("proj")
    assert marks(tool, "mark")["a.png"] == "1" and marks(tool, "marks")["a.png"] == "3,6"


def test_old_tables_with_symbols_are_read_as_numbers(api, tool, imgs, base_dir):
    # 0.4.4 までの table.json は記号（A〜D・★●▲■）で持っていた。読むときに番号へ直す（記号の表を変えても読めるように、昔の表で）
    api.load(imgs)
    api.save()
    path = base_dir / "data_out" / "proj" / "table.json"
    table = json.loads(path.read_text(encoding="utf-8"))
    table["rows"][0].update({"mark": "B", "marks": "★■"})
    table["rows"][1].update({"mark": "D"})
    path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")

    api.open_project("proj")
    assert marks(tool, "mark") == {"a.png": "1", "b.png": "3", "c.png": ""}
    assert marks(tool, "marks") == {"a.png": "0,3", "b.png": "", "c.png": ""}


def test_marks_are_not_written_to_captions(api, tool, imgs):
    api.load(imgs)
    api.write(0, "looks: standing")
    set_mark(api, [0], 0)
    set_marks(api, [0], 0)
    api.save()
    assert (tool.captions_dir / "a.caption").read_text(encoding="utf-8") == caption_of("looks: standing")


def test_clear_marks_clears_one_column_on_every_row(api, tool, imgs):
    api.load(imgs)
    set_mark(api, [0, 1, 2], 3)
    set_marks(api, [0, 2], 1)
    assert api.post("/clear_marks", {"column": "mark"})["success"]
    assert set(marks(tool, "mark").values()) == {""}
    assert marks(tool, "marks") == {"a.png": "1", "b.png": "", "c.png": "1"}
    api.post("/clear_marks", {"column": "marks"})
    assert set(marks(tool, "marks").values()) == {""}
    assert api.post("/clear_marks", {"column": "girl"})["success"] is False


def test_table_data_has_marks_as_numbers_and_their_symbols(api, imgs):
    api.load(imgs)
    set_mark(api, [0], 0)
    set_marks(api, [0], 4)
    body = api.table()
    assert body["mark_choices"] == {"one": ONE, "many": MANY, "auto": AUTO}  # 番号の順の記号
    assert [(r["mark"], r["marks"]) for r in body["data"]] == [(0, [4]), (None, []), (None, [])]
    assert body["sections"] == ["picture", "action", "girl", "guy"]


@pytest.mark.parametrize("name", ["mark", "marks"])
def test_mark_column_names_are_reserved(api, tool, imgs, name):
    api.load(imgs)
    assert api.add_section(name)["success"] is False


# ---- 自動のマーク（①〜⑧。語句を設定すると、その語句のある行に付く。行には持たない） ----

def set_auto(api, index, mark):
    return api.post("/set_auto_mark", {"index": index, "mark": mark})


def test_auto_marks_are_set_per_project_and_saved_in_the_table(api, imgs, base_dir):
    # 設定は「A, B を除いた段落の名前・キー・語句」。プロジェクトごとに table.json へ保存する
    api.load(imgs)
    assert api.table()["auto_marks"] == [None] * 8
    res = set_auto(api, 2, {"section": " girl ", "key": "looks", "phrase": " smile "})
    assert res["success"] and res["auto_marks"] == [None, None, SMILE] + [None] * 5
    api.save()
    path = base_dir / "data_out" / "proj" / "table.json"
    assert json.loads(path.read_text(encoding="utf-8"))["auto_marks"][2] == SMILE

    api.open_project("proj")
    assert api.table()["auto_marks"][2] == SMILE
    assert set_auto(api, 2, None)["auto_marks"] == [None] * 8  # 外す


def test_tables_without_auto_marks_have_none_set(api, imgs, base_dir):
    api.load(imgs)
    api.save()
    path = base_dir / "data_out" / "proj" / "table.json"
    table = json.loads(path.read_text(encoding="utf-8"))
    del table["auto_marks"]  # 0.4.4 までの table.json には無い
    path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    api.open_project("proj")
    assert api.table()["auto_marks"] == [None] * 8


@pytest.mark.parametrize("payload", [
    {"index": 8, "mark": SMILE},  # 0〜7 の外
    {"index": True, "mark": SMILE},  # 真偽は番号ではない
    {"index": 0, "mark": {**SMILE, "key": "a,b"}},  # キーにカンマは使えない（キーなしは空）
    {"index": 0, "mark": {**SMILE, "phrase": " "}},
    {"index": 0, "mark": {**SMILE, "section": ""}},
    {"index": 0, "mark": "smile"},
])
def test_bad_auto_mark_requests_are_rejected(api, imgs, payload):
    api.load(imgs)
    res = api.post("/set_auto_mark", payload)
    assert res["success"] is False and res["message"]
    assert api.table()["auto_marks"] == [None] * 8


@pytest.mark.parametrize("pattern, phrase, expected", [
    ("smile", "smile", True),
    ("smile", "slight smile", False),  # 語句そのもの
    ("girl spread arms", "girl spread arms.", True),  # 文末の . は外して比べる
    ("girl spread arms.", "girl spread arms", True),
    ("*girl spread arms*", "girl spread arms wildly.", True),  # * は何文字でも
    ("*hair", "black hair", True),
    ("*hair", "hair clip", False),
    ("a*c", "abc", True),
    ("a.c", "abc", False),  # * のほかの記号は文字のまま
])
def test_word_mark_patterns(pattern, phrase, expected):
    assert matches_pattern(pattern, phrase) is expected


def test_word_marks_of_a_row_look_at_the_key_in_sections_of_the_same_name():
    # 単語のマーク: 設定した語句が、A, B を除いた名前の段落のそのキー（キーなしは文）の語句に合えば付く
    marks = [{"section": "girl", "key": "looks", "phrase": "smile"}, None,
             {"section": "action", "key": "", "phrase": "*spread arms*"},
             {"section": "guy", "key": "looks", "phrase": "smile"},
             {"section": "girl", "key": "body", "phrase": "smile"}] + [None] * 3
    texts = {"girl A": "looks: standing, smile", "action": "girl spread arms wide.", "guy": "looks: sitting"}
    assert auto_marks_of(texts, marks) == [0, 2]


def test_word_marks_can_be_set_for_sections_without_keys(api, imgs):
    # action など確定タグの無い段落は、キーなし（空）で文に合わせる
    api.load(imgs)
    res = set_auto(api, 0, {"section": "action", "key": "", "phrase": "*spread arms*"})
    assert res["success"], res
    assert res["auto_marks"][0] == {"section": "action", "key": "", "phrase": "*spread arms*"}
