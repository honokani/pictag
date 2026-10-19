"""段落（大kind）と、複数行への一括入力"""
import json

import pytest

import app as pictag
from helpers import caption_of, make_images, word_tokenizer
from tokens import TokenCounter

DEFAULT_SECTIONS = ["picture", "action", "girl", "guy"]


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100)})


def sections(tool):
    return pictag.section_names(tool.df)


def texts(tool, section="girl"):
    return tool.df.set_index("サムネイル")[section].to_dict()


def test_first_project_starts_with_default_sections(api, tool, imgs):
    api.load(imgs)
    assert sections(tool) == DEFAULT_SECTIONS
    assert texts(tool) == {"a.png": "", "b.png": ""}


def test_new_project_does_not_bring_subjects_of_other_projects(api, tool, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)}))
    assert api.add_section("dog")["success"]
    api.save()

    api.load(make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)}))
    assert sections(tool) == DEFAULT_SECTIONS


def test_existing_project_keeps_its_subjects(api, tool, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)}))
    api.add_section("dog")
    assert api.post("/remove_section", {"name": "girl"})["success"]
    assert api.post("/remove_section", {"name": "guy"})["success"]
    api.save()
    api.load(make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)}))
    api.save()

    api.open_project("proj_a")
    assert sections(tool) == ["picture", "action", "dog"]


@pytest.mark.parametrize("name", ["picture", "action"])
def test_fixed_sections_cannot_be_removed_or_renamed(api, tool, imgs, name):
    api.load(imgs)
    res = api.post("/remove_section", {"name": name})
    assert res["success"] is False and res["message"]
    res = api.post("/rename_section", {"old": name, "new": "x"})
    assert res["success"] is False and res["message"]
    assert sections(tool) == DEFAULT_SECTIONS


def test_fixed_sections_come_first_even_if_missing_in_saved_table(api, tool, imgs, base_dir):
    saved = {"sections": ["girl", "action"],
             "rows": [{"image": "a.png", "is_dead": False, "texts": {"girl": "looks: standing"}}]}
    (base_dir / "data_out" / "proj").mkdir(parents=True)
    (base_dir / "data_out" / "proj" / "table.json").write_text(json.dumps(saved), encoding="utf-8")
    api.load(imgs)
    assert sections(tool) == ["picture", "action", "girl"]
    assert texts(tool)["a.png"] == "looks: standing"


@pytest.mark.parametrize("name", ["picture", "action", "", "is_dead", "a:b"])
def test_add_section_rejects_duplicate_or_bad_names_with_reason(api, tool, imgs, name):
    api.load(imgs)
    res = api.add_section(name)
    assert res["success"] is False and res["message"]
    assert sections(tool) == DEFAULT_SECTIONS


def test_add_section_needs_loaded_project(api, tool):
    assert api.add_section("dog")["success"] is False


def test_rename_section_keeps_texts(api, tool, imgs):
    api.load(imgs)
    api.write(api.row_index("a.png"), "looks: standing")
    assert api.post("/rename_section", {"old": "girl", "new": "girl A"})["success"]
    assert sections(tool) == ["picture", "action", "girl A", "guy"]
    assert texts(tool, "girl A")["a.png"] == "looks: standing"


def test_rename_section_to_existing_name_is_rejected(api, tool, imgs):
    api.load(imgs)
    res = api.post("/rename_section", {"old": "girl", "new": "action"})
    assert res["success"] is False and res["message"]
    assert sections(tool) == DEFAULT_SECTIONS


def test_removed_subject_stays_removed_after_save(api, tool, imgs):
    api.load(imgs)
    assert api.post("/remove_section", {"name": "girl"})["success"]
    api.save()
    api.open_project("proj")
    assert sections(tool) == ["picture", "action", "guy"]


def test_bulk_add_and_remove_phrase(api, tool, imgs):
    api.load(imgs)
    api.write(api.row_index("a.png"), "body: long hair")
    rows = [api.row_index("a.png"), api.row_index("b.png")]

    res = api.bulk_add(rows, "body: black hair")
    assert res["success"], res
    assert texts(tool) == {"a.png": "body: long hair, black hair", "b.png": "body: black hair"}
    assert [r["caption"] for r in res["rows"]] == [caption_of("body: long hair, black hair"), caption_of("body: black hair")]

    api.bulk_remove(rows, "body: long hair")
    assert texts(tool) == {"a.png": "body: black hair", "b.png": "body: black hair"}


def test_bulk_add_several_phrases_at_once(api, tool, imgs):
    api.load(imgs)
    api.bulk_add([0, 1], "looks: full body shot, standing")
    assert texts(tool) == {"a.png": "looks: full body shot, standing", "b.png": "looks: full body shot, standing"}


@pytest.mark.parametrize("payload", [
    {"rows": [0], "section": "zzz", "text": "a"},
    {"rows": [99], "section": "girl", "text": "a"},
    {"rows": [0], "section": "girl", "text": ""},
    {"rows": "0", "section": "girl", "text": "a"},
])
def test_bulk_add_rejects_bad_requests(api, tool, imgs, payload):
    api.load(imgs)
    res = api.post("/add_phrase", payload)
    assert res["success"] is False
    assert texts(tool) == {"a.png": "", "b.png": ""}


def test_table_data_has_texts_caption_and_tokens(api, imgs, monkeypatch):
    monkeypatch.setattr(pictag, "token_counter", TokenCounter(word_tokenizer()))
    api.load(imgs)
    api.write(api.row_index("a.png"), "looks: standing")

    body = api.table()
    assert body["sections"] == DEFAULT_SECTIONS
    assert body["token_limit"] == 507
    a, b = body["data"]
    assert a["texts"] == {"picture": "", "action": "", "girl": "looks: standing", "guy": ""}  # 空の guy は出力しない
    assert a["caption"] == "picture:\n  - characters: 1 girl\n\ngirl:\n  - looks: standing"
    assert a["tokens"] == 13  # picture / : / - / characters / : / 1 / girl / girl / : / - / looks / : / standing
    assert b["tokens"] == 0


def test_tokens_are_null_until_tokenizer_is_ready(api, imgs, monkeypatch):
    monkeypatch.setattr(pictag, "token_counter", TokenCounter())
    api.load(imgs)
    assert [r["tokens"] for r in api.rows()] == [None, None]


CAMERA = ["from front", "from side", "from behind"]
VERTICAL = ["from above", "eye level", "from below"]
SHOTS = ["close-up", "portrait", "medium shot", "long shot"]


def test_adding_the_same_subject_names_them_with_letters(api, tool, imgs):
    api.load(imgs)
    api.write(api.row_index("a.png"), "looks: standing")
    assert api.add_section("girl")["success"]
    assert sections(tool) == ["picture", "action", "girl A", "girl B", "guy"]  # 同じ種類は隣に並べる
    assert texts(tool, "girl A")["a.png"] == "looks: standing"
    api.add_section("guy")  # guy は最初からある
    api.add_section("guy")
    assert sections(tool) == ["picture", "action", "girl A", "girl B", "guy A", "guy B", "guy C"]


def test_caption_has_characters_of_subjects_with_text(api, imgs):
    api.load(imgs)
    api.add_section("dog")
    row = api.row_index("a.png")
    api.write(row, "place: classroom", section="picture")
    api.write(row, "looks: standing")
    res = api.write(row, "looks: sitting", section="dog")
    assert res["characters"] == "1 girl + 1 dog"
    assert res["caption"] == ("picture:\n  - place: classroom\n  - characters: 1 girl + 1 dog\n\n"
                              "girl:\n  - looks: standing\n\ndog:\n  - looks: sitting")
    a, b = api.rows()
    assert a["characters"] == "1 girl + 1 dog"
    assert b["characters"] == "" and b["caption"] == ""


def test_set_choice_keeps_one_phrase_per_group_on_rows(api, tool, imgs):
    api.load(imgs)
    rows = [api.row_index("a.png"), api.row_index("b.png")]

    def choose(phrase, group, on=True):
        return api.post("/set_choice", {"rows": rows, "section": "picture", "key": "view",
                                        "phrase": phrase, "group": group, "on": on})

    assert choose("from front", CAMERA)["success"]
    assert choose("from behind", CAMERA)["success"]
    res = choose("from above", VERTICAL)
    assert [r["texts"]["picture"] for r in res["rows"]] == ["view: from behind, from above"] * 2
    choose("from behind", CAMERA, on=False)
    assert texts(tool, "picture") == {"a.png": "view: from above", "b.png": "view: from above"}


@pytest.mark.parametrize("payload", [
    {"phrase": "from up", "group": CAMERA, "on": True},
    {"phrase": "from front", "group": CAMERA, "on": "yes"},
    {"phrase": "from front", "group": "from front", "on": True},
    {"phrase": "from front", "group": CAMERA, "on": True, "section": "zzz"},
])
def test_set_choice_rejects_bad_requests(api, tool, imgs, payload):
    api.load(imgs)
    res = api.post("/set_choice", {"rows": [0], "section": "picture", "key": "view", **payload})
    assert res["success"] is False
    assert texts(tool, "picture") == {"a.png": "", "b.png": ""}


def test_table_data_has_view_choices_for_current_subjects(api, imgs):
    api.load(imgs)  # 新規プロジェクトの人物は girl と guy
    body = api.table()
    assert body["auto_keys"] == ["characters"]
    assert body["view_choices"]["camera"] == [CAMERA, VERTICAL, SHOTS]
    assert set(body["view_choices"]["camera_emoji"]) == {*CAMERA, *VERTICAL, *SHOTS}
    assert body["view_choices"]["targeted"] == ["close-up"]  # 後ろに対象を書ける（close-up face）
    assert [c["phrase"] for c in body["view_choices"]["pov"]] == ["third-person POV", "girl POV", "guy POV"]


def test_choice_replaces_close_up_with_a_target(api, tool, imgs):
    api.load(imgs)
    api.write(0, "view: close-up face, from below", section="picture")
    api.post("/set_choice", {"rows": [0], "section": "picture", "key": "view",
                             "phrase": "portrait", "group": SHOTS, "on": True})
    assert texts(tool, "picture")["a.png"] == "view: from below, portrait"


def test_choice_keeps_free_text_on_the_view_line(api, tool, imgs):
    api.load(imgs)
    api.write(0, "view: focus on hands", section="picture")
    api.post("/set_choice", {"rows": [0], "section": "picture", "key": "view",
                             "phrase": "close-up", "group": SHOTS, "on": True})
    assert texts(tool, "picture")["a.png"] == "view: focus on hands, close-up"
    api.post("/set_choice", {"rows": [0], "section": "picture", "key": "view",
                             "phrase": "medium shot", "group": SHOTS, "on": True})  # ショットの大きさは1つだけ
    assert texts(tool, "picture")["a.png"] == "view: focus on hands, medium shot"
    api.post("/set_choice", {"rows": [0], "section": "picture", "key": "view",
                             "phrase": "medium shot", "group": SHOTS, "on": False})
    assert texts(tool, "picture")["a.png"] == "view: focus on hands"
