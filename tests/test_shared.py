"""共用辞書の管理（画面の「共用辞書」タブの API）。入力は映画の有名なシーン（tests/scenes.py）"""
import json

import app as pictag
from scenes import load_scenes

COUPLES = ["titanic.png", "roman_holiday.png", "lalaland.png"]


def movies(tmp_path):
    return tmp_path / "imgs" / "movies"


def shared_of(base_dir):
    return json.loads((base_dir / "data_work" / "shared.json").read_text(encoding="utf-8"))


def entry(api, key, phrase):
    """辞書の「キー: 語句」を段落ごとに {段落: (使用回数, 共用辞書に入っているか)}"""
    return {p["section"]: (p["count"], p["shared"]) for p in api.dictionary()["phrases"]
            if (p["key"], p["phrase"]) == (key, phrase)}


def girl_texts(api):
    return {r["サムネイル"]: r["texts"]["girl"] for r in api.rows()}


# ---- 登録 ----

def test_register_puts_the_key_phrase_of_every_section_using_it(api, tmp_path, base_dir):
    load_scenes(api, movies(tmp_path), COUPLES)
    res = api.post("/register_entries", {"phrases": [{"key": "looks", "phrase": "standing"}]})
    assert res["success"], res
    assert entry(api, "looks", "standing") == {"girl": (2, True), "guy": (2, True)}
    assert entry(api, "looks", "sitting") == {"girl": (1, False), "guy": (1, False)}
    assert {"section": "guy", "key": "looks", "phrase": "standing"} in shared_of(base_dir)["phrases"]


def test_register_words_of_sentences(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    assert api.post("/register_entries", {"words": ["spread", "waist"]})["success"]
    words = {w["word"]: w["shared"] for w in api.dictionary()["words"]}
    assert words["spread"] and words["waist"] and not words["arms"]


def test_register_fails_for_a_phrase_nobody_uses(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    res = api.post("/register_entries", {"phrases": [{"key": "looks", "phrase": "flying"}]})
    assert not res["success"] and "flying" in res["message"]


def test_add_a_new_phrase_by_hand(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    res = api.post("/add_entry", {"section": "girl", "key": "looks", "phrase": " kneeling "})
    assert res["success"], res
    assert entry(api, "looks", "kneeling") == {"girl": (0, True)}


def test_add_works_before_a_project_is_opened(api, base_dir):
    assert api.post("/add_entry", {"section": "picture", "key": "place", "phrase": "ship bow"})["success"]
    assert shared_of(base_dir)["phrases"] == [{"section": "picture", "key": "place", "phrase": "ship bow"}]


def test_add_rejects_a_phrase_with_a_comma(api):
    res = api.post("/add_entry", {"section": "girl", "key": "looks", "phrase": "standing, sitting"})
    assert not res["success"] and "カンマ" in res["message"]


# ---- 削除 ----

def test_unregister_keeps_a_phrase_in_use_and_drops_an_unused_one(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    api.post("/register_entries", {"phrases": [{"key": "looks", "phrase": "standing"}]})
    api.post("/add_entry", {"section": "girl", "key": "looks", "phrase": "kneeling"})

    res = api.post("/unregister_entries", {"phrases": [{"key": "looks", "phrase": "standing"},
                                                       {"key": "looks", "phrase": "kneeling"}]})
    assert res["success"], res
    assert entry(api, "looks", "standing") == {"girl": (1, False), "guy": (1, False)}  # 使っているので候補には残る
    assert entry(api, "looks", "kneeling") == {}


def test_unregister_words(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    api.post("/register_entries", {"words": ["spread"]})
    assert api.post("/unregister_entries", {"words": ["spread"]})["success"]
    assert {w["word"]: w["shared"] for w in api.dictionary()["words"]}["spread"] is False


# ---- 改名 ----

def test_rename_replaces_in_shared_and_in_the_open_project(api, tmp_path, base_dir):
    rows = load_scenes(api, movies(tmp_path), ["titanic.png", "roman_holiday.png"])
    api.write(rows["roman_holiday.png"], "looks: standnig, smile\nclothes: white blouse")
    api.post("/register_entries", {"phrases": [{"key": "looks", "phrase": "standnig"}]})

    res = api.post("/rename_entry", {"key": "looks", "old": "standnig", "new": "standing", "in_project": True})
    assert res["success"] and res["changed"] == 1, res
    assert girl_texts(api)["roman_holiday.png"] == "looks: standing, smile\nclothes: white blouse"
    assert entry(api, "looks", "standnig") == {}
    assert entry(api, "looks", "standing") == {"girl": (2, True), "guy": (1, False)}
    assert {"section": "girl", "key": "looks", "phrase": "standnig"} not in shared_of(base_dir)["phrases"]


def test_rename_can_leave_the_project_inputs_alone(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    api.post("/register_entries", {"phrases": [{"key": "looks", "phrase": "smile"}]})

    res = api.post("/rename_entry", {"key": "looks", "old": "smile", "new": "grin", "in_project": False})
    assert res["success"] and res["changed"] == 0, res
    assert "smile" in girl_texts(api)["titanic.png"]
    assert entry(api, "looks", "grin") == {"girl": (0, True)}
    assert entry(api, "looks", "smile") == {"girl": (1, False)}


def test_rename_a_phrase_that_is_only_used_in_the_project(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    res = api.post("/rename_entry", {"key": "clothes", "old": "cardigan", "new": "shawl", "in_project": True})
    assert res["success"] and res["changed"] == 1, res
    assert girl_texts(api)["titanic.png"] == "looks: standing, eyes closed, smile\nclothes: long dress, shawl\nbody: red/long hair"
    assert entry(api, "clothes", "shawl") == {"girl": (1, False)}


def test_rename_rejects_unknown_same_or_bad_names(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    for old, new in [("flying", "soaring"), ("smile", "smile"), ("smile", "smile, grin")]:
        res = api.post("/rename_entry", {"key": "looks", "old": old, "new": new, "in_project": True})
        assert not res["success"] and res["message"], (old, new)
    assert "smile" in girl_texts(api)["titanic.png"]


# ---- キーを移す ----

def test_move_phrases_in_sections_of_the_same_name_and_in_shared(api, tmp_path):
    # A, B を除いた名前が同じ段落（dog A・dog B）の全行と、共用辞書のその段落の語句を移す。ほかの段落（girl）は変えない
    rows = load_scenes(api, movies(tmp_path), ["titanic.png", "lady_and_tramp.png"])
    api.write(rows["titanic.png"], "looks: lying, smile")
    api.post("/register_entries", {"phrases": [{"key": "looks", "phrase": "lying"}]})

    res = api.post("/move_phrases", {"section": "dog", "from_key": "looks", "to_key": "body", "phrases": ["lying"]})
    assert res["success"] and res["changed"] == 1, res
    texts = {r["サムネイル"]: r["texts"] for r in api.rows()}
    assert texts["lady_and_tramp.png"]["dog A"] == "body: tan fur, long ears, lying"
    assert texts["lady_and_tramp.png"]["dog B"] == "body: gray/scruffy fur, lying"
    assert texts["titanic.png"]["girl"] == "looks: lying, smile"
    assert entry(api, "body", "lying") == {"dog A": (1, True), "dog B": (1, True)}
    assert entry(api, "looks", "lying") == {"girl": (1, True)}


def test_move_phrases_rejects_the_same_key_unknown_phrases_or_bad_names(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    for payload in [{"section": "girl", "from_key": "looks", "to_key": "looks", "phrases": ["smile"]},  # 同じキー
                    {"section": "girl", "from_key": "looks", "to_key": "body", "phrases": ["flying"]},  # どこにも無い
                    {"section": "cat", "from_key": "looks", "to_key": "body", "phrases": ["smile"]},  # 無い段落
                    {"section": "girl", "from_key": "looks", "to_key": "", "phrases": ["smile"]},  # 移す先のキーが無い
                    {"section": "girl", "from_key": "looks", "to_key": "body", "phrases": []}]:  # 語句が無い
        res = api.post("/move_phrases", payload)
        assert not res["success"] and res["message"], payload
    assert girl_texts(api)["titanic.png"].startswith("looks: standing, eyes closed, smile\n")


# ---- 「1つだけ」のグループ ----

def test_group_registers_its_phrases_and_is_listed(api, tmp_path, base_dir):
    load_scenes(api, movies(tmp_path), ["titanic.png", "roman_holiday.png", "lady_and_tramp.png"])
    assert api.dictionary()["groups"] == []

    res = api.post("/group_phrases", {"key": "looks", "phrases": ["standing", "sitting", "lying"]})
    assert res["success"], res
    assert api.dictionary()["groups"] == [{"key": "looks", "phrases": ["standing", "sitting", "lying"]}]
    assert shared_of(base_dir)["groups"] == [{"key": "looks", "phrases": ["standing", "sitting", "lying"]}]
    assert entry(api, "looks", "lying") == {"dog A": (1, True), "dog B": (1, True)}  # 使っている段落で共用辞書に入る


def test_group_needs_two_known_phrases_of_one_key(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    for key, phrases in [("looks", ["standing"]), ("", ["girl spread arms", "guy hold girl's waist from behind"]),
                         ("looks", ["standing", "flying"])]:
        res = api.post("/group_phrases", {"key": key, "phrases": phrases})
        assert not res["success"] and res["message"], (key, phrases)
    assert api.dictionary()["groups"] == []


def test_ungroup_takes_phrases_out(api, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png", "roman_holiday.png", "lady_and_tramp.png"])
    api.post("/group_phrases", {"key": "looks", "phrases": ["standing", "sitting", "lying"]})
    assert api.post("/ungroup_phrases", {"phrases": [{"key": "looks", "phrase": "lying"}]})["success"]
    assert api.dictionary()["groups"] == [{"key": "looks", "phrases": ["standing", "sitting"]}]


def test_bulk_add_skips_rows_that_have_a_group_mate(api, tmp_path):
    rows = load_scenes(api, movies(tmp_path), ["titanic.png", "roman_holiday.png", "singin_rain.png"])
    api.post("/group_phrases", {"key": "looks", "phrases": ["standing", "sitting"]})

    res = api.bulk_add(list(rows.values()), "looks: sitting")
    assert res["success"] and res["skipped"] == 1, res
    girl = girl_texts(api)
    assert girl["titanic.png"].startswith("looks: standing, eyes closed, smile\n")  # standing があるので足さない
    assert girl["roman_holiday.png"].startswith("looks: sitting, smile\n")
    assert girl["singin_rain.png"] == "looks: sitting"


def test_groups_and_registrations_survive_a_restart(api, tmp_path, base_dir):
    load_scenes(api, movies(tmp_path), ["titanic.png", "roman_holiday.png"])
    api.post("/group_phrases", {"key": "looks", "phrases": ["standing", "sitting"]})
    fresh = pictag.CaptionTool(base_dir=base_dir)
    assert fresh.shared["groups"] == [{"key": "looks", "phrases": ["standing", "sitting"]}]
    assert {"section": "girl", "key": "looks", "phrase": "sitting"} in fresh.shared["phrases"]


def test_shared_file_without_groups_still_loads(base_dir):
    (base_dir / "data_work").mkdir()
    (base_dir / "data_work" / "shared.json").write_text(json.dumps(
        {"phrases": [{"section": "girl", "key": "looks", "phrase": "standing"}], "words": []}), encoding="utf-8")
    fresh = pictag.CaptionTool(base_dir=base_dir)
    assert fresh.shared["groups"] == []
    assert fresh.shared["phrases"] == [{"section": "girl", "key": "looks", "phrase": "standing"}]


# ---- 場面がそのままキャプションになる ----

TITANIC_CAPTION = "\n".join([
    "picture:",
    "  - place: ship bow, open ocean, sunset",
    "  - characters: 1 girl + 1 guy",
    "  - vibes: romantic, windy",
    "  - view: from side, third-person POV",
    "",
    "action:",
    "  - girl spread arms, guy hold girl's waist from behind",
    "",
    "girl:",
    "  - looks: standing, eyes closed, smile",
    "  - clothes: long dress, cardigan",
    "  - body: red/long hair",
    "",
    "guy:",
    "  - looks: standing",
    "  - clothes: white shirt, suspenders",
    "  - body: blonde/short hair",
])


def test_a_scene_becomes_a_krea2_caption(api, tool, tmp_path):
    load_scenes(api, movies(tmp_path), ["titanic.png"])
    api.save()
    assert (tool.captions_dir / "titanic.caption").read_text(encoding="utf-8") == TITANIC_CAPTION


def test_scenes_with_lettered_subjects(api, tool, tmp_path):
    load_scenes(api, movies(tmp_path), ["lady_and_tramp.png", "shining.png"])
    api.save()
    tramp = (tool.captions_dir / "lady_and_tramp.caption").read_text(encoding="utf-8")
    shining = (tool.captions_dir / "shining.caption").read_text(encoding="utf-8")
    assert "  - characters: 2 dogs (dog A, dog B)\n" in tramp
    assert "  - characters: 2 girls (girl A, girl B)\n" in shining
    assert "\n\ngirl B:\n  - looks: standing, staring\n" in shining
