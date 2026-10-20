"""Qwen（ComfyUI の TextGenerate）で空の欄を下書きする: 送る文面・答えの分け方・空の欄への入れ方・API"""
import re

import pytest

import app as pictag
from helpers import FakeComfy, make_images
from qwen import (INSTRUCTIONS, clear_drafts, fill_section, fill_text, match_section, parse_caption, pick_random_samples,
                  pick_samples, pick_tiered_samples, skeleton, system_prompt, user_prompt)

PICTURE = ["place", "characters", "vibes", "view", "extra"]
SUBJECT = ["looks", "clothes", "body"]


# ---- 送る文面 ----

def test_skeleton_lists_keys_without_values_and_shows_keyless_sections_an_example():
    sections = [("picture", PICTURE), ("action", []), ("girl", SUBJECT), ("else", [])]
    assert skeleton(sections) == ("picture:\n  - place:\n  - characters:\n  - vibes:\n  - view:\n  - extra:\n\n"
                                  "action:\n  - (e.g. boy is sitting.)\n\n"
                                  "girl:\n  - looks:\n  - clothes:\n  - body:\n\n"
                                  "else:\n  - (e.g. dog: brown fur, sitting)")


def test_system_prompt_is_instructions_and_skeleton():
    sections = [("girl", SUBJECT)]
    assert system_prompt(sections) == f"{INSTRUCTIONS}\n\nFormat:\n{skeleton(sections)}"


def test_system_prompt_sends_actions_to_action_and_states_to_each_character():
    # 行動（していること・関わり）だけを action へ、状態（表情・視線・姿勢・見た目・服）は人物の段落へ、と指示する
    prompt = system_prompt([("action", []), ("girl", SUBJECT)])
    assert "Put only actions in action (what the characters are doing and how they interact)" in prompt
    assert "pose, appearance and clothing belong to each character's section, never to action" in prompt


def test_user_prompt_lists_samples_and_asks_for_this_image():
    assert user_prompt(["girl:\n  - looks: sitting", "girl:\n  - looks: standing"]) == (
        "Example captions of other images in the same set:\n\n"
        "girl:\n  - looks: sitting\n\n---\n\ngirl:\n  - looks: standing\n\n---\n\nWrite the caption for this image.")


def test_pick_samples_takes_the_nearest_ten_non_empty_captions_in_table_order():
    captions = [f"c{i}" if i % 3 else "" for i in range(20)]  # 空の行が混ざる
    assert pick_samples(captions) == ["c5", "c7", "c8", "c10", "c11", "c13", "c14", "c16", "c17", "c19"]
    assert pick_samples(["c"] * 9 + [""]) == []  # 10 個に満たなければ渡さない


def test_pick_random_samples_takes_ten_different_non_empty_captions():
    captions = [f"c{i}" if i % 3 else "" for i in range(30)]  # 空でないものは 20 個
    picked = pick_random_samples(captions)
    assert len(set(picked)) == 10 and set(picked) <= set(captions) - {""}
    assert pick_random_samples([f"c{i}" for i in range(9)] + [""]) == []  # 10 個に満たなければ渡さない


def test_pick_tiered_samples_fills_from_the_first_tier_then_the_next():
    # 先の段からランダムに選び、足りない分は次の段から（同じ行は1回）。並びは後の段が先、最初の段が最後（頼む文の直前）
    same = [(i, f"a{i}") for i in range(3)]  # A〜D が同じ（3 行）
    shared = [(0, "a0")] + [(i, f"s{i}") for i in range(3, 8)]  # ★●▲■ を共有（5 行。a0 は前の段で選び済み）
    rest = same + shared[1:] + [(i, f"r{i}") for i in range(8, 30)]
    picked = pick_tiered_samples([same, shared, rest])
    assert len(set(picked)) == 10
    assert sorted(picked[-3:]) == ["a0", "a1", "a2"]
    assert sorted(picked[2:7]) == ["s3", "s4", "s5", "s6", "s7"]
    assert all(p.startswith("r") for p in picked[:2])
    assert pick_tiered_samples([[(0, "a")], [(1, "b"), (2, "")]]) == []  # 全部で 10 個に満たなければ渡さない


# ---- 答えの分け方と、空の欄への入れ方 ----

def test_parse_caption_splits_sections_and_lines():
    text = ("```\npicture:\n  - place: hilltop, dusk\n  - characters: 1 girl\n\naction:\n  - girl waves.\n\n"
            "girl A:\n  - looks: standing\n  clothes: red dress\n```")
    assert parse_caption(text) == [("picture", ["place: hilltop, dusk", "characters: 1 girl"]),
                                   ("action", ["girl waves."]),
                                   ("girl A", ["looks: standing", "clothes: red dress"])]


@pytest.mark.parametrize("name, sections, expected", [
    ("girl", ["picture", "girl", "guy"], "girl"),
    ("girl A", ["picture", "girl", "guy"], "girl"),  # A, B を除いた名前で1つに決まる
    ("girl", ["picture", "girl A", "girl B"], None),  # 決まらない
    ("stick figure", ["picture", "girl"], None),
])
def test_match_section(name, sections, expected):
    assert match_section(name, sections) == expected


def test_fill_text_fills_keys_without_values_and_keeps_the_rest():
    lines = ["place: hilltop, dusk", "characters: 1 girl", "view: from front", "extra: lens flare"]
    # characters は自動で作るので入れない。値のある view は変えない。確定タグの並びの位置に入れる
    assert fill_text("view: from side", lines, PICTURE) == "place: hilltop, dusk\nview: from side\nextra: lens flare"


def test_fill_text_adds_sentences_only_when_there_are_none():
    assert fill_text("", ["girl waves.", "guy smiles."], []) == "girl waves.\nguy smiles."
    assert fill_text("girl sits.", ["girl waves."], []) == "girl sits."


def test_fill_text_treats_none_and_nan_as_no_tag():
    # Qwen がたまに返す「none」「nan」は、タグが無いものとして入れない（大文字・小文字、前後の括弧、文末の . は問わない。ほかの語句は入れる）
    assert fill_text("", ["looks: nan", "clothes: None, red dress", "body: NaN"], SUBJECT) == "clothes: red dress"
    assert fill_text("", ["looks: NONE", "clothes: NAN", "body: (none)"], SUBJECT) == ""
    assert fill_text("", ["none"], []) == ""
    assert fill_text("", ["(none)", "(None)."], []) == ""
    assert fill_text("", ["none.", "girl waves."], []) == "girl waves."


def test_fill_section_returns_what_it_put_in():
    text, added = fill_section("looks: sitting", ["looks: standing", "clothes: red dress", "girl waves."], SUBJECT)
    assert text == "looks: sitting\nclothes: red dress\ngirl waves."
    assert added == {"keys": {"clothes": "red dress"}, "sentences": ["girl waves."]}  # 値のあった looks は入れていない


def test_clear_drafts_removes_only_drafts_left_as_qwen_wrote_them():
    # 前に Qwen が入れて、そのあと直していないキーと文だけを消す（直したもの・自分で書いたものは残す）
    drafted = {"keys": {"looks": "standing", "clothes": "red dress"}, "sentences": ["girl waves."]}
    text = "looks: standing\nclothes: red dress, hat\nbody: long hair\ngirl waves."
    assert clear_drafts(text, drafted) == "clothes: red dress, hat\nbody: long hair"
    assert clear_drafts("girl waves.\nguy smiles.", drafted) == "girl waves.\nguy smiles."  # 文を足していたら残す
    assert clear_drafts("looks: standing", {}) == "looks: standing"


def test_fill_text_adds_keys_outside_the_template_at_the_end():
    assert fill_text("dog: brown fur", ["dog: white fur", "cat: black"], []) == "dog: brown fur\ncat: black"
    assert fill_text("looks: sitting", ["clothes: red dress", "pose: arms up"], SUBJECT) == (
        "looks: sitting\nclothes: red dress\npose: arms up")


# ---- API（偽の ComfyUI で） ----

ANSWER = ("picture:\n  - place: hilltop\n  - characters: 1 girl\n  - view: from side\n\naction:\n  - girl waves.\n\n"
          "girl A:\n  - looks: standing\n  - clothes: red dress\n\nstick figure:\n  - looks: none")


@pytest.fixture
def comfy():
    fake = FakeComfy(ANSWER)
    yield fake
    fake.close()


@pytest.fixture
def qwen_api(api, comfy, tmp_path, monkeypatch):
    """qwen 版で開いたプロジェクト proj: r00〜r11 の 12 枚。r00〜r09 の girl が見本（looks: pose0〜9）"""
    monkeypatch.setitem(pictag.app.config, "QWEN_URL", comfy.url)
    api.load(make_images(tmp_path / "imgs" / "proj", {f"r{i:02}.png": (100, 100) for i in range(12)}))
    for i in range(10):
        api.write(api.row_index(f"r{i:02}.png"), f"looks: pose{i}")
    return api


def test_qwen_fill_sends_format_samples_and_image_then_fills_empty_keys(qwen_api, comfy, tool):
    assert qwen_api.table()["qwen"] is True
    row = qwen_api.row_index("r10.png")
    qwen_api.write(row, "looks: sitting")
    res = qwen_api.qwen_fill(row)
    assert res["success"], res
    texts = res["row"]["texts"]
    assert texts["picture"] == "place: hilltop\nview: from side"  # characters は自動なので入れない
    assert texts["action"] == "girl waves."
    assert texts["girl"] == "looks: sitting\nclothes: red dress"  # girl A → girl。値のあった looks は変えない
    assert res["filled"] == ["picture", "action", "girl"]
    assert res["row"]["qwen_hint"] == ANSWER  # 表に無い段落（stick figure）も、答えにはそのまま残る

    inputs = comfy.prompts[0]["prompt"]["tg"]["inputs"]
    assert "girl:\n  - looks:\n  - clothes:\n  - body:" in inputs["system_prompt"]
    assert all(f"looks: pose{i}" in inputs["prompt"] for i in range(10))  # 上の 10 行のキャプションが見本
    assert inputs["max_length"] > 507  # キャプションの上限より長く書ける
    assert b'filename="proj_r10.jpg"' in comfy.uploads[0] and b"\xff\xd8\xff" in comfy.uploads[0]  # JPEG で送る
    assert (tool.data_work_target / "qwen" / "r10.txt").read_text(encoding="utf-8") == ANSWER


ANSWER2 = ("picture:\n  - place: beach\n\naction:\n  - girl runs.\n\n"
           "girl:\n  - looks: sitting\n  - clothes: blue coat")


def test_pressing_again_replaces_only_the_previous_draft(qwen_api, comfy):
    # 押し直したら、前に Qwen が入れてそのあと直していない欄だけを、新しい答えで置き換える（開き直しても覚えている）
    row = qwen_api.row_index("r10.png")
    qwen_api.qwen_fill(row)  # picture: place・view、action、girl: looks・clothes
    qwen_api.save()
    qwen_api.open_project("proj")
    qwen_api.write(row, "looks: standing\nclothes: red dress, hat")  # clothes だけ直す
    comfy.answer = ANSWER2
    res = qwen_api.qwen_fill(row)
    assert res["success"], res
    texts = res["row"]["texts"]
    assert texts["girl"] == "looks: sitting\nclothes: red dress, hat"  # 直していない looks は置き換え、直した clothes は残す
    assert texts["action"] == "girl runs."
    assert texts["picture"] == "place: beach"  # 新しい答えに無い view は、前の下書きごと消える


def test_qwen_answer_stays_for_hint_by_qwen_after_reopening(qwen_api):
    qwen_api.qwen_fill(qwen_api.row_index("r10.png"))
    qwen_api.save()
    qwen_api.open_project("proj")
    r10 = next(r for r in qwen_api.rows() if r["サムネイル"] == "r10.png")
    assert r10["qwen_hint"] == ANSWER


def test_qwen_fill_needs_ten_samples_above(qwen_api, comfy):
    res = qwen_api.qwen_fill(qwen_api.row_index("r05.png"))
    assert res["success"] is False and "10" in res["message"]
    assert comfy.prompts == []


def test_qwen_fill_random_takes_samples_from_the_whole_project(qwen_api, comfy):
    # 🎲: その行と削除済みを除く、キャプションのある行からランダムに 10 個（下の行も）
    row = qwen_api.row_index("r05.png")
    assert qwen_api.qwen_fill(row, mode="random")["success"] is False  # ほかの行は r00〜r04・r06〜r09 の 9 行だけ
    qwen_api.write(qwen_api.row_index("r11.png"), "looks: pose11")
    res = qwen_api.qwen_fill(row, mode="random")
    assert res["success"], res
    used = sorted(int(i) for i in re.findall(r"looks: pose(\d+)", comfy.prompts[0]["prompt"]["tg"]["inputs"]["prompt"]))
    assert used == [0, 1, 2, 3, 4, 6, 7, 8, 9, 11]  # ほかに 10 行なので全部。その行（5）は入らない


def test_qwen_fill_mark_takes_rows_with_the_same_marks_first(qwen_api, comfy):
    # 🔖: A〜D が同じ行 → ★●▲■ を共有する行 → ほかの行からランダム、の順に 10 個（A〜D が同じ行が頼む文の直前）
    qwen_api.write(qwen_api.row_index("r11.png"), "looks: pose11")  # その行のほかに 11 行
    index = {i: qwen_api.row_index(f"r{i:02}.png") for i in range(12)}
    qwen_api.post("/set_mark", {"rows": [index[1], index[2], index[10]], "mark": "A"})
    qwen_api.post("/set_mark", {"rows": [index[4]], "mark": "B"})
    qwen_api.post("/set_marks", {"rows": [index[3], index[10]], "mark": "★", "on": True})
    res = qwen_api.qwen_fill(index[10], mode="mark")
    assert res["success"], res
    used = [int(i) for i in re.findall(r"looks: pose(\d+)", comfy.prompts[0]["prompt"]["tg"]["inputs"]["prompt"])]
    assert len(set(used)) == 10 and 10 not in used
    assert sorted(used[-2:]) == [1, 2] and used[-3] == 3  # A の行が最後、その前に ★ の行


def test_qwen_fill_rejects_an_unknown_mode(qwen_api, comfy):
    assert qwen_api.qwen_fill(qwen_api.row_index("r10.png"), mode="zzz")["success"] is False
    assert comfy.prompts == []


def test_qwen_fill_reports_when_comfyui_is_not_reachable(qwen_api, monkeypatch):
    monkeypatch.setitem(pictag.app.config, "QWEN_URL", "http://127.0.0.1:9")  # 誰も待っていないポート
    res = qwen_api.qwen_fill(qwen_api.row_index("r10.png"))
    assert res["success"] is False and "ComfyUI" in res["message"]


def test_qwen_fill_reports_a_failed_run(qwen_api, comfy):
    comfy.status = "error"
    res = qwen_api.qwen_fill(qwen_api.row_index("r10.png"))
    assert res["success"] is False and "out of memory" in res["message"]


def test_without_the_qwen_option_there_is_no_qwen(api, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100)}))
    assert api.table()["qwen"] is False
    assert api.qwen_fill(0)["success"] is False


@pytest.mark.parametrize("argv, expected", [
    ([], None),
    (["--qwen"], "http://127.0.0.1:8189"),
    (["--qwen", "--comfyui-url", "http://127.0.0.1:9000/"], "http://127.0.0.1:9000"),
])
def test_qwen_option(argv, expected):
    assert pictag.qwen_url(argv) == expected
