"""使用中の語句（辞書）と保存（JSON・Krea2 形式のキャプション txt）"""
import json

import pytest

from helpers import make_images


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100)})


def test_dictionary_lists_phrases_in_use_including_unsaved_edits(api, imgs):
    api.load(imgs)
    api.write(api.row_index("a.png"), "body: long hair\ngirl walks a dog")
    api.write(api.row_index("b.png"), "body: long hair")
    assert api.phrases() == {("girl", "body", "long hair"): 2, ("girl", "", "girl walks a dog"): 1}


def test_dictionary_includes_saved_projects(api, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)}))
    api.add_section("dog")
    api.write(0, "fur: brown", section="dog")
    api.save()

    api.load(make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)}))
    api.write(0, "looks: standing")
    assert api.phrases() == {("dog", "fur", "brown"): 1, ("girl", "looks", "standing"): 1}


def test_phrase_disappears_when_no_image_uses_it(api, imgs):
    api.load(imgs)
    api.write(0, "body: long hair")
    api.save()
    api.write(0, "")
    assert api.phrases() == {}
    api.save()
    assert api.phrases() == {}


def test_save_writes_krea2_captions_with_lf(api, tool, imgs):
    api.load(imgs)
    row = api.row_index("a.png")
    api.write(row, "place: classroom", section="picture")
    api.write(row, "girl walks a dog", section="action")
    api.write(row, "body: long hair, black hair")
    api.save()

    assert (tool.captions_dir / "a.caption").read_bytes() == (
        b"picture:\n  - place: classroom\n  - characters: 1 girl\n\naction:\n  - girl walks a dog\n\n"
        b"girl:\n  - body: long black hair")
    assert (tool.captions_dir / "b.caption").read_bytes() == b""


def test_save_writes_readable_json(api, imgs, base_dir):
    api.load(imgs)
    api.write(api.row_index("a.png"), "looks: standing")
    api.save()

    table = json.loads((base_dir / "data_out" / "proj" / "table.json").read_text(encoding="utf-8"))
    assert table == {"sections": ["picture", "action", "girl", "guy"],
                     "rows": [{"image": "a.png", "is_dead": False, "texts": {"girl": "looks: standing"}},
                              {"image": "b.png", "is_dead": False, "texts": {}}],
                     "auto_marks": [None] * 8}  # 自動のマーク ①〜⑧ の語句の設定（どれも設定なし）


def test_unreadable_table_is_not_opened(api, tool, imgs, base_dir):
    api.load(imgs)
    api.save()
    (base_dir / "data_out" / "proj" / "table.json").write_text("{broken", encoding="utf-8")
    other = make_images(imgs.parent / "other", {"z.png": (100, 100)})
    api.load(other)

    res = api.open_project("proj")
    assert res["success"] is False and res["message"]
    assert tool.image_dir == other.resolve()
    assert (base_dir / "data_out" / "proj" / "table.json").read_text(encoding="utf-8") == "{broken"


DEFAULT_TEMPLATES = {"picture": ["place", "characters", "vibes", "view", "extra"], "subject": ["looks", "clothes", "body"]}


def test_words_of_sentences_are_in_dictionary(api, imgs):
    api.load(imgs)
    api.write(0, "girl spread arms\nguy grab girl's waist", section="action")
    assert api.words() == {("action", w): 1 for w in ["girl", "spread", "arms", "guy", "grab", "girl's", "waist"]}


def test_dictionary_has_default_templates(api, imgs):
    api.load(imgs)
    assert api.dictionary()["templates"] == DEFAULT_TEMPLATES
    assert api.table()["templates"] == DEFAULT_TEMPLATES


def test_freeze_keeps_phrases_and_words_after_they_are_unused(api, imgs, base_dir):
    api.load(imgs)
    api.write(0, "body: long hair")
    api.write(0, "girl spread arms", section="action")

    res = api.post("/freeze")
    assert res["success"] and res["added"] == 5, res  # 語句 2 + 単語 3
    api.write(0, "")
    api.write(0, "", section="action")
    assert api.phrases() == {("girl", "body", "long hair"): 0, ("action", "", "girl spread arms"): 0}
    assert api.words() == {("action", "girl"): 0, ("action", "spread"): 0, ("action", "arms"): 0}

    shared = json.loads((base_dir / "data_work" / "shared.json").read_text(encoding="utf-8"))
    assert shared["templates"] == DEFAULT_TEMPLATES
    assert {"section": "girl", "key": "body", "phrase": "long hair"} in shared["phrases"]


def test_freeze_twice_adds_nothing_new(api, imgs):
    api.load(imgs)
    api.write(0, "body: long hair")
    api.post("/freeze")
    assert api.post("/freeze")["added"] == 0


def test_shared_dictionary_is_used_by_other_projects(api, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)}))
    api.write(0, "body: long hair")
    api.post("/freeze")
    api.write(0, "")
    api.save()

    api.load(make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)}))
    assert api.phrases() == {("girl", "body", "long hair"): 0}


def test_caption_files_use_caption_extension(api, tool, imgs):
    api.load(imgs)
    api.write(0, "looks: standing")
    api.save()
    assert sorted(p.name for p in tool.captions_dir.iterdir()) == ["a.caption", "b.caption"]


def test_hint_comes_from_same_name_txt_next_to_the_image(api, tool, imgs, base_dir):
    (imgs / "a.txt").write_text("1girl, solo, smile\n", encoding="utf-8")
    api.load(imgs)
    a, b = api.rows()
    assert a["hint"] == "1girl, solo, smile\n"
    assert b["hint"] == ""

    # hint は保存にもキャプションにも入らない
    api.save()
    table = json.loads((base_dir / "data_out" / "proj" / "table.json").read_text(encoding="utf-8"))
    assert "hint" not in json.dumps(table)
    assert (tool.captions_dir / "a.caption").read_text(encoding="utf-8") == ""
    assert (imgs / "a.txt").read_text(encoding="utf-8") == "1girl, solo, smile\n"


def test_unreadable_bytes_in_hint_do_not_break_loading(api, imgs):
    (imgs / "a.txt").write_bytes(b"\xff\xfe broken \x80")
    assert api.load(imgs)["success"]
    assert "broken" in api.rows()[0]["hint"]
