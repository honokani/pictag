"""Qwen（ComfyUI の TextGenerate）で空の欄を下書きする: 送る文面・答えの分け方・空の欄への入れ方・API"""
import re

import pytest

import app as pictag
from helpers import FakeComfy, make_images
from qwen import (INSTRUCTIONS, SAMPLE_COUNT, clear_drafts, fill_section, keep_word_marks, match_section, parse_caption,
                  pick_random_samples, pick_samples, pick_tiered_samples, skeleton, system_prompt, user_prompt,
                  written_skeleton)

PICTURE = ["place", "characters", "vibes", "view", "extra"]
SUBJECT = ["looks", "clothes", "body"]


def fill_text(text, lines, keys):
    """fill_section で入れたあとの入力（入れたものは見ない）"""
    return fill_section(text, lines, keys)[0]


# ---- 送る文面 ----

def test_skeleton_lists_keys_without_values_and_shows_keyless_sections_an_example():
    sections = [("picture", PICTURE), ("action", []), ("girl", SUBJECT), ("else", [])]
    assert skeleton(sections) == ("picture:\n  - place:\n  - characters:\n  - vibes:\n  - view:\n  - extra:\n\n"
                                  "action:\n  - (e.g. boy is sitting.)\n\n"
                                  "girl:\n  - looks:\n  - clothes:\n  - body:\n\n"
                                  "else:\n  - (e.g. dog: brown fur, sitting)")


def test_skeleton_takes_the_sentence_example():
    # 文の例は、プロジェクトで多い方の動詞の形に合わせて渡せる（else の例は変わらない）
    assert skeleton([("action", []), ("else", [])], "(e.g. boy sits.)") == (
        "action:\n  - (e.g. boy sits.)\n\nelse:\n  - (e.g. dog: brown fur, sitting)")


def test_system_prompt_is_instructions_and_skeleton():
    sections = [("girl", SUBJECT)]
    assert system_prompt(sections) == f"{INSTRUCTIONS}\n\nFormat:\n{skeleton(sections)}"


def test_system_prompt_sends_actions_to_action_and_states_to_each_character():
    # 行動（していること・姿勢（girl is standing.）・関わり）だけを action へ、状態（表情・視線・見た目・服）は人物の段落へ、と指示する
    prompt = system_prompt([("action", []), ("girl", SUBJECT)])
    assert "Put only actions in action (what the characters are doing, including their posture, and how they interact)" in prompt
    assert "Expressions, gaze, appearance and clothing belong to each character's section, never to action" in prompt


def test_user_prompt_lists_samples_and_asks_for_this_image():
    assert user_prompt(["girl:\n  - looks: sitting", "girl:\n  - looks: standing"]) == (
        "Example captions of other images in the same set:\n\n"
        "girl:\n  - looks: sitting\n\n---\n\ngirl:\n  - looks: standing\n\n---\n\nWrite the caption for this image.")


def test_user_prompt_sends_what_is_written_and_asks_to_fill_in_the_rest():
    # 書いてあるもの（written_skeleton）があれば頼む文の前に置き、書いてあるものは変えずに、空いている所を埋めてと頼む
    assert user_prompt(["girl:\n  - looks: sitting"], "girl:\n  - looks: smile\n  - clothes:") == (
        "Example captions of other images in the same set:\n\n"
        "girl:\n  - looks: sitting\n\n---\n\n"
        "Part of the caption for this image is already written. Keep what is written as it is, "
        "and fill in the empty parts by looking at the image:\n\n"
        "girl:\n  - looks: smile\n  - clothes:\n\n"
        "Write the caption for this image.")


def test_written_skeleton_puts_what_is_written_into_the_skeleton():
    # 書いてある語句はそのキーに（同じキーの行はまとめる）、値の無いキーは空のまま。確定タグに無いキーと文は後ろに。
    # 何も書いていない段落は、キーだけ（キーの無い段落は名前だけ）
    sections = [("picture", PICTURE, "view: from side, guy POV"), ("action", [], "girl waves."),
                ("girl", SUBJECT, "pose: kneeling\nlooks: smile\nlooks: looking at viewer"), ("guy", SUBJECT, ""),
                ("else", [], "")]
    assert written_skeleton(sections) == (
        "picture:\n  - place:\n  - characters:\n  - vibes:\n  - view: from side, guy POV\n  - extra:\n\n"
        "action:\n  - girl waves.\n\n"
        "girl:\n  - looks: smile, looking at viewer\n  - clothes:\n  - body:\n  - pose: kneeling\n\n"
        "guy:\n  - looks:\n  - clothes:\n  - body:\n\n"
        "else:")


def test_written_skeleton_is_empty_when_nothing_is_written():
    # 語句の無い行（view: だけ）は、書いていないのと同じ
    assert written_skeleton([("picture", PICTURE, "view:\n "), ("action", [], ""), ("girl", SUBJECT, "")]) == ""


def test_pick_samples_takes_the_nearest_ten_non_empty_captions_in_table_order():
    captions = [f"c{i}" if i % 3 else "" for i in range(20)]  # 空の行が混ざる
    assert pick_samples(captions, count=10) == ["c5", "c7", "c8", "c10", "c11", "c13", "c14", "c16", "c17", "c19"]
    assert pick_samples(["c1", "", "c2"], count=10) == ["c1", "c2"]  # 足りなければある分だけ（足りない分は公開の例）


def test_pick_random_samples_takes_ten_different_non_empty_captions():
    captions = [f"c{i}" if i % 3 else "" for i in range(30)]  # 空でないものは 20 個
    picked = pick_random_samples(captions, count=10)
    assert len(set(picked)) == 10 and set(picked) <= set(captions) - {""}
    assert sorted(pick_random_samples([f"c{i}" for i in range(9)] + [""], count=10)) == [f"c{i}" for i in range(9)]  # ある分だけ


def test_pick_tiered_samples_fills_from_the_first_tier_then_the_next():
    # 先の段からランダムに選び、足りない分は次の段から（同じ行は1回）。並びは後の段が先、最初の段が最後（頼む文の直前）
    same = [(i, f"a{i}") for i in range(3)]  # 最初の段（3 行）
    shared = [(0, "a0")] + [(i, f"s{i}") for i in range(3, 8)]  # 次の段（5 行。a0 は前の段で選び済み）
    rest = same + shared[1:] + [(i, f"r{i}") for i in range(8, 30)]
    picked = pick_tiered_samples([[same], [shared], [rest]], count=10)
    assert len(set(picked)) == 10
    assert sorted(picked[-3:]) == ["a0", "a1", "a2"]
    assert sorted(picked[2:7]) == ["s3", "s4", "s5", "s6", "s7"]
    assert all(p.startswith("r") for p in picked[:2])
    assert pick_tiered_samples([[[(0, "a")]], [[(1, "b"), (2, "")]]], count=10) == ["b", "a"]  # 足りなければある分だけ


def test_pick_tiered_samples_takes_the_same_number_from_each_group_of_a_tier():
    # 1つの段に組がいくつかあれば、どの組からも同じ数ずつ（どれかが尽きるか、残りの枠を組の数で割れなくなるまで）。余りは次の段へ
    words = [(f"w{i}", f"w{i}") for i in range(10)]
    many = [(f"m{i}", f"m{i}") for i in range(3)]
    picked = pick_tiered_samples([[words, many], [words], [many]], count=9)
    assert len(set(picked)) == 9
    assert sum(p.startswith("m") for p in picked[-6:]) == 3  # 組の段: 複数が尽きるまで 3 ずつ（頼む文の近く）
    assert all(p.startswith("w") for p in picked[:3])  # 残りの 3 は次の段（単語）から
    many = [(f"m{i}", f"m{i}") for i in range(10)]
    picked = pick_tiered_samples([[words, many], [words], [many]], count=7)
    assert sum(p.startswith("m") for p in picked) == 3  # 7 は 2 で割れないので 3 ずつ、余りの 1 は単語の段から


# ---- 答えの分け方と、空の欄への入れ方 ----

def test_parse_caption_splits_sections_and_lines():
    text = ("```\npicture:\n  - place: hilltop, dusk\n  - characters: 1 girl\n\naction:\n  - girl waves.\n\n"
            "girl A:\n  - looks: standing\n  clothes: red dress\n```")
    assert parse_caption(text) == [("picture", ["place: hilltop, dusk", "characters: 1 girl"]),
                                   ("action", ["girl waves."]),
                                   ("girl A", ["looks: standing", "clothes: red dress"])]


@pytest.mark.parametrize("name, sections, present, expected", [
    ("girl", ["picture", "girl", "guy"], [], "girl"),
    ("girl A", ["picture", "girl", "guy"], [], "girl"),  # A, B を除いた名前で1つに決まる
    # 1つの行の人は A, B を除いた名前でも書き出す（girl A だけ → girl）ので、girl は「その行で入力のある girl が1つならそれ」
    ("girl", ["picture", "girl A", "girl B"], ["girl B"], "girl B"),
    ("girl", ["picture", "girl A", "girl B"], [], "girl A"),  # 無ければ（2つあっても）表で先のもの
    ("girl", ["picture", "girl A", "girl B"], ["girl A", "girl B"], "girl A"),
    ("stick figure", ["picture", "girl"], [], None),
])
def test_match_section(name, sections, present, expected):
    assert match_section(name, sections, present) == expected


def test_fill_text_fills_keys_without_values_and_keeps_the_rest():
    lines = ["place: hilltop, dusk", "characters: 1 girl", "view: from front", "extra: lens flare"]
    # characters は自動で作るので入れない。値のある view は変えない。確定タグの並びの位置に入れる
    assert fill_text("view: from side", lines, PICTURE) == "place: hilltop, dusk\nview: from side\nextra: lens flare"


def test_fill_text_adds_sentences_only_when_there_are_none():
    assert fill_text("", ["girl waves.", "guy smiles."], []) == "girl waves.\nguy smiles."
    assert fill_text("girl sits.", ["girl waves."], []) == "girl sits."


def test_fill_text_treats_none_and_nan_as_no_tag():
    # Qwen がたまに返す「none」「nan」（ごくまれに「non presented」）は、タグが無いものとして入れない
    # （大文字・小文字、前後の括弧、文末の . は問わない。ほかの語句は入れる）
    assert fill_text("", ["looks: nan", "clothes: None, red dress", "body: NaN"], SUBJECT) == "clothes: red dress"
    assert fill_text("", ["looks: NONE", "clothes: NAN", "body: (none)"], SUBJECT) == ""
    assert fill_text("", ["none"], []) == ""
    assert fill_text("", ["(none)", "(None)."], []) == ""
    assert fill_text("", ["none.", "girl waves."], []) == "girl waves."
    assert fill_text("", ["looks: Non presented", "body: (non presented)."], SUBJECT) == ""


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


def test_fill_section_overwrite_replaces_answered_keys_and_sentences():
    # 🔄: 答えにあるキーは値があっても置き換え、答えに文があれば前の文を置き換える。答えに無いキー（body）は残す
    text, added = fill_section("looks: sitting\nbody: long hair\ngirl sits.",
                               ["looks: standing", "clothes: red dress", "girl waves."], SUBJECT, overwrite=True)
    assert text == "looks: standing\nclothes: red dress\nbody: long hair\ngirl waves."
    assert added == {"keys": {"looks": "standing", "clothes": "red dress"}, "sentences": ["girl waves."]}


def test_fill_section_overwrite_keeps_what_the_answer_does_not_have():
    # 答えに文が無ければ前の文は残す。none・nan と自動のキー（characters）では消さない
    text, added = fill_section("looks: sitting\ngirl sits.", ["looks: none", "characters: 1 girl"], SUBJECT, overwrite=True)
    assert text == "looks: sitting\ngirl sits." and added == {"keys": {}, "sentences": []}


WORD_MARKS = [{"section": "action", "key": "", "phrase": "*spread arms*"}, None,
              {"section": "girl", "key": "looks", "phrase": "ponytail"}]
KEYS = {"picture": PICTURE, "action": [], "girl A": SUBJECT}


def test_keep_word_marks_adds_back_the_words_the_overwrite_dropped():
    # 🔄 で外れた単語のマーク（①など）は、押す前の入力で当たっていた語句を足し直す
    # （キーのある語句はそのキーの値の末尾に、キーなしの語句は文の行として末尾に。当たらなかった語句（smile）は足さない）
    before = {"picture": "", "action": "girl spread arms", "girl A": "looks: ponytail, smile"}
    after = {"picture": "place: beach", "action": "girl waves.", "girl A": "looks: long hair\nclothes: red dress"}
    assert keep_word_marks(before, after, WORD_MARKS, KEYS) == {
        "picture": "place: beach", "action": "girl waves.\ngirl spread arms",
        "girl A": "looks: long hair, ponytail\nclothes: red dress"}


def test_keep_word_marks_adds_nothing_when_the_answer_keeps_the_mark():
    # 答えにも同じマークに当たる語句があれば、外れないので足さない（重ならない）
    before = {"picture": "", "action": "girl spread arms", "girl A": "looks: ponytail"}
    after = {"picture": "", "action": "girl spread arms wide.", "girl A": "looks: ponytail, smile"}
    assert keep_word_marks(before, after, WORD_MARKS, KEYS) == after


# ---- API（偽の ComfyUI で） ----

ANSWER = ("picture:\n  - place: hilltop\n  - characters: 1 girl\n  - view: from side\n\naction:\n  - girl waves.\n\n"
          "girl A:\n  - looks: standing\n  - clothes: red dress\n\nstick figure:\n  - looks: none")


@pytest.fixture
def comfy():
    fake = FakeComfy(ANSWER)
    yield fake
    fake.close()


ASK = f"r{SAMPLE_COUNT:02}.png"  # 頼む行（上に見本の数だけ、キャプションのある行がある）
SPARE = f"r{SAMPLE_COUNT + 1:02}.png"  # 空の行（見本を足すときに書く）


@pytest.fixture
def qwen_api(api, comfy, tmp_path, monkeypatch):
    """qwen 版で開いたプロジェクト proj: r00〜r17 の 18 枚（見本の数 + 2）。r00〜r15 の girl が見本（looks: pose0〜15）"""
    monkeypatch.setitem(pictag.app.config, "QWEN_URL", comfy.url)
    api.load(make_images(tmp_path / "imgs" / "proj", {f"r{i:02}.png": (100, 100) for i in range(SAMPLE_COUNT + 2)}))
    for i in range(SAMPLE_COUNT):
        api.write(api.row_index(f"r{i:02}.png"), f"looks: pose{i}")
    return api


def sample_captions(comfy, call=0):
    """call 回目に送った見本（並びのまま）。最後の --- の後ろ（その行に書いてあるものと頼む文）は見ない"""
    prompt = comfy.prompts[call]["prompt"]["tg"]["inputs"]["prompt"]
    head = "Example captions of other images in the same set:\n\n"
    return prompt.rsplit("\n\n---\n\n", 1)[0].removeprefix(head).split("\n\n---\n\n")


def sample_numbers(comfy, call=0):
    """送った見本の looks: poseN の N（並びのまま。公開の例には無い）"""
    return [int(i) for caption in sample_captions(comfy, call) for i in re.findall(r"looks: pose(\d+)", caption)]


def test_qwen_fill_sends_format_samples_and_image_then_fills_empty_keys(qwen_api, comfy, tool):
    assert qwen_api.table()["qwen"] is True
    row = qwen_api.row_index(ASK)
    qwen_api.write(row, "looks: sitting")
    res = qwen_api.qwen_fill(row)
    assert res["success"], res
    assert res["public"] == 0  # 上に 16 行あれば、公開の例は使わない
    texts = res["row"]["texts"]
    assert texts["picture"] == "place: hilltop\nview: from side"  # characters は自動なので入れない
    assert texts["action"] == "girl waves."
    assert texts["girl"] == "looks: sitting\nclothes: red dress"  # girl A → girl。値のあった looks は変えない
    assert res["filled"] == ["picture", "action", "girl"]
    assert res["row"]["edited_at"]  # Qwen の下書きも、その行の書き換えとして数える（📍）
    assert res["row"]["qwen_hint"] == ANSWER  # 表に無い段落（stick figure）も、答えにはそのまま残る

    inputs = comfy.prompts[0]["prompt"]["tg"]["inputs"]
    assert "girl:\n  - looks:\n  - clothes:\n  - body:" in inputs["system_prompt"]
    assert sample_numbers(comfy) == list(range(16))  # 上の 16 行のキャプションが見本（表の並びのまま）
    assert inputs["max_length"] > 507  # キャプションの上限より長く書ける
    stem = ASK.removesuffix(".png")
    assert f'filename="proj_{stem}.jpg"'.encode() in comfy.uploads[0] and b"\xff\xd8\xff" in comfy.uploads[0]  # JPEG で送る
    assert (tool.data_work_target / "qwen" / f"{stem}.txt").read_text(encoding="utf-8") == ANSWER


ANSWER2 = ("picture:\n  - place: beach\n\naction:\n  - girl runs.\n\n"
           "girl:\n  - looks: sitting\n  - clothes: blue coat")


def test_pressing_again_replaces_only_the_previous_draft(qwen_api, comfy):
    # 押し直したら、前に Qwen が入れてそのあと直していない欄だけを、新しい答えで置き換える（開き直しても覚えている）
    row = qwen_api.row_index(ASK)
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


def test_qwen_fill_sends_what_is_written_but_not_the_previous_draft(qwen_api, comfy):
    # 何も書いていなければ今までの文面。書いてあれば、それを入れたひな形も送る（前に Qwen が入れて直していないものは送らない）
    row = qwen_api.row_index(ASK)
    qwen_api.qwen_fill(row)
    assert "already written" not in comfy.prompts[0]["prompt"]["tg"]["inputs"]["prompt"]
    qwen_api.write(row, "looks: standing\nclothes: red dress, hat")  # Qwen の looks はそのまま、clothes だけ直す
    qwen_api.write(row, "view: guy POV", section="picture")  # Qwen の place・view を消して書く
    qwen_api.qwen_fill(row)
    assert ("already written. Keep what is written as it is, and fill in the empty parts by looking at the image:\n\n"
            "picture:\n  - place:\n  - characters:\n  - vibes:\n  - view: guy POV\n  - extra:\n\n"
            "action:\n\n"  # 直していない Qwen の文も送らない
            "girl:\n  - looks:\n  - clothes: red dress, hat\n  - body:\n\n"
            "guy:\n  - looks:\n  - clothes:\n  - body:\n\n"
            "Write the caption for this image.") in comfy.prompts[1]["prompt"]["tg"]["inputs"]["prompt"]


@pytest.mark.parametrize("mode", pictag.QWEN_MODES)
def test_every_qwen_button_sends_what_is_written(qwen_api, comfy, mode):
    # 🤖・🔖・🔄・🎲 のどれでも送る（🔄 は、書いた値も答えで置き換わる）
    row = qwen_api.row_index(ASK)
    qwen_api.write(row, "view: from side, guy POV", section="picture")
    assert qwen_api.qwen_fill(row, mode=mode)["success"]
    assert "  - view: from side, guy POV\n" in comfy.prompts[0]["prompt"]["tg"]["inputs"]["prompt"]


def test_qwen_sentence_example_follows_the_majority_verb_form(qwen_api, comfy):
    # ひな形の文の例は、action の文で多い方の動詞の形（文が無い・同じ数なら boy is sitting.）
    def system(call):
        return comfy.prompts[call]["prompt"]["tg"]["inputs"]["system_prompt"]

    qwen_api.qwen_fill(qwen_api.row_index(ASK))  # 文はまだ無い。答えで action に「girl waves.」（does の形）が入る
    assert "action:\n  - (e.g. boy is sitting.)" in system(0)
    qwen_api.qwen_fill(qwen_api.row_index(SPARE))
    assert "action:\n  - (e.g. boy sits.)" in system(1)


def test_overwrite_replaces_filled_fields_and_keeps_word_mark_words(qwen_api):
    # 🔄: 答えにあるキーと文は、入力があっても置き換える（答えに無い body は残す。ボタンで選んだ view も答えで置き換わる）。
    # 上書きで外れる単語のマーク（①）の語句は足し直す
    row = qwen_api.row_index(ASK)
    qwen_api.write(row, "view: from behind", section="picture")
    qwen_api.write(row, "girl spread arms", section="action")
    qwen_api.write(row, "looks: sitting\nbody: long hair")
    qwen_api.post("/set_auto_mark", {"index": 0, "mark": {"section": "action", "key": "", "phrase": "*spread arms*"}})
    res = qwen_api.qwen_fill(row, mode="overwrite")
    assert res["success"], res
    texts = res["row"]["texts"]
    assert texts["picture"] == "place: hilltop\nview: from side"
    assert texts["action"] == "girl waves.\ngirl spread arms"
    assert texts["girl"] == "looks: standing\nclothes: red dress\nbody: long hair"
    assert res["filled"] == ["picture", "action", "girl"]


def test_qwen_answer_stays_for_hint_by_qwen_after_reopening(qwen_api):
    qwen_api.qwen_fill(qwen_api.row_index(ASK))
    qwen_api.save()
    qwen_api.open_project("proj")
    asked = next(r for r in qwen_api.rows() if r["サムネイル"] == ASK)
    assert asked["qwen_hint"] == ANSWER


def test_qwen_fill_fills_up_with_public_samples_when_short(qwen_api, comfy):
    # 見本が 16 に満たなければ、ある分（上の 5 行）と、足りない分を公開の例（映画の場面。10 個まで）から。
    # 公開の例は頼む文から遠い前の方
    res = qwen_api.qwen_fill(qwen_api.row_index("r05.png"))
    assert res["success"] and res["public"] == 10, res
    samples = sample_captions(comfy)
    assert len(samples) == 15 and all("third-person POV" in s for s in samples[:10])
    assert sample_numbers(comfy) == [0, 1, 2, 3, 4]


def test_qwen_fill_works_without_any_samples(api, comfy, tmp_path, monkeypatch):
    # キャプションのある行が1つも無くても、公開の例（10 個）を見本にして押せる（4つのボタンのどれでも）
    monkeypatch.setitem(pictag.app.config, "QWEN_URL", comfy.url)
    api.load(make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100)}))
    for call, mode in enumerate(pictag.QWEN_MODES):
        res = api.qwen_fill(api.row_index("a.png"), mode=mode)
        assert res["success"] and res["public"] == 10, res
        assert len(sample_captions(comfy, call)) == 10


def test_public_samples_follow_the_majority_verb_form(api, comfy, tmp_path, monkeypatch):
    # 公開の例の action の文（s を省いた現在形）は、プロジェクトで多い方の形に直して渡す（決まらなければ書いてあるまま）
    monkeypatch.setitem(pictag.app.config, "QWEN_URL", comfy.url)
    api.load(make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100)}))
    row = api.row_index("a.png")

    def prompt(call):
        return comfy.prompts[call]["prompt"]["tg"]["inputs"]["prompt"]

    api.qwen_fill(row)  # action の文がまだ無い
    assert "girl spread arms, guy hold girl's waist from behind" in prompt(0)
    api.write(row, "girl is sitting.\nguy is standing.", section="action")
    api.qwen_fill(row)
    assert "girl is spreading arms, guy is holding girl's waist from behind" in prompt(1)
    api.write(row, "girl sits.", section="action")
    api.qwen_fill(row)
    assert "girl spreads arms, guy holds girl's waist from behind" in prompt(2)


def test_qwen_fill_random_takes_samples_from_the_whole_project(qwen_api, comfy):
    # 🎲: その行と削除済みを除く、キャプションのある行からランダムに 16 個（下の行も）。足りなければ公開の例で補う
    row = qwen_api.row_index("r05.png")
    res = qwen_api.qwen_fill(row, mode="random")  # ほかの行は r00〜r04・r06〜r15 の 15 行だけ
    assert res["success"] and res["public"] == 1, res
    assert sorted(sample_numbers(comfy)) == [*range(5), *range(6, 16)]
    qwen_api.write(qwen_api.row_index(SPARE), "looks: pose17")
    res = qwen_api.qwen_fill(row, mode="random")
    assert res["success"] and res["public"] == 0, res
    assert sorted(sample_numbers(comfy, 1)) == [*range(5), *range(6, 16), 17]  # ほかに 16 行なので全部。その行（5）は入らない


def test_qwen_fill_mark_takes_rows_with_the_same_marks_first(qwen_api, comfy):
    # 🔖: 複数のマーク（★●▲■…）を共有する行 → 排他のマーク（A〜H）が同じ行 → ほかの行からランダム、の順に 16 個
    # （複数のマークを共有する行が頼む文の直前）。マークは番号（0 = A・★、1 = B）
    qwen_api.write(qwen_api.row_index(SPARE), "looks: pose17")  # その行のほかに 17 行
    index = {i: qwen_api.row_index(f"r{i:02}.png") for i in range(SAMPLE_COUNT)}
    ask = qwen_api.row_index(ASK)
    qwen_api.post("/set_mark", {"rows": [index[1], index[2], ask], "mark": 0})
    qwen_api.post("/set_mark", {"rows": [index[4]], "mark": 1})
    qwen_api.post("/set_marks", {"rows": [index[3], ask], "mark": 0, "on": True})
    res = qwen_api.qwen_fill(ask, mode="mark")
    assert res["success"], res
    used = sample_numbers(comfy)
    assert len(set(used)) == 16 and 16 not in used
    assert used[-1] == 3 and sorted(used[-3:-1]) == [1, 2]  # ★ の行が最後、その前に A の行


@pytest.mark.parametrize("mode", ["mark", "overwrite"])  # 🔄 も 🔖 と同じ見本
def test_qwen_fill_mark_orders_word_and_many_marks_before_the_one_mark(qwen_api, comfy, mode):
    # 🔖: 単語のマーク（①〜⑯。設定した語句が入力にある）と複数のマーク（★●▲■…）の両方を共有する行 → 単語だけ・複数だけを
    # 共有する行を同じ数ずつ → 単語の残り → 複数の残り → 排他のマーク（A〜H）が同じ行 → ほかの行（先の段ほど頼む文の近く）
    index = {i: qwen_api.row_index(f"r{i:02}.png") for i in range(SAMPLE_COUNT)}
    ask = qwen_api.row_index(ASK)
    qwen_api.write(ask, "looks: pose1x")
    # ① は pose1・pose10〜15 の行と頼む行に付く
    qwen_api.post("/set_auto_mark", {"index": 0, "mark": {"section": "girl", "key": "looks", "phrase": "pose1*"}})
    qwen_api.post("/set_marks", {"rows": [*(index[i] for i in (2, 3, 4, 10, 11)), ask], "mark": 0, "on": True})  # ★
    qwen_api.post("/set_mark", {"rows": [index[5], index[6], ask], "mark": 0})  # A
    res = qwen_api.qwen_fill(ask, mode=mode)
    assert res["success"], res
    used = sample_numbers(comfy)
    words_only = {1, 12, 13, 14, 15}
    assert sorted(used) == list(range(16))  # ほかの行は 16 行なので全部。並びで段が分かる
    assert set(used[-2:]) == {10, 11}  # 単語と複数の両方
    assert {2, 3, 4} <= set(used[-8:-2]) and len(set(used[-8:-2]) & words_only) == 3  # 複数だけ 3 行と、単語だけ 3 行
    assert set(used[-10:-8]) <= words_only  # 単語の残り（複数の残りは無い）
    assert set(used[-12:-10]) == {5, 6}  # 排他
    assert set(used[:4]) == {0, 7, 8, 9}  # ほかの行


def test_qwen_fill_rejects_an_unknown_mode(qwen_api, comfy):
    assert qwen_api.qwen_fill(qwen_api.row_index(ASK), mode="zzz")["success"] is False
    assert comfy.prompts == []


def test_qwen_fill_reports_when_comfyui_is_not_reachable(qwen_api, monkeypatch):
    monkeypatch.setitem(pictag.app.config, "QWEN_URL", "http://127.0.0.1:9")  # 誰も待っていないポート
    res = qwen_api.qwen_fill(qwen_api.row_index(ASK))
    assert res["success"] is False and "ComfyUI" in res["message"]


def test_qwen_fill_reports_a_failed_run(qwen_api, comfy):
    comfy.status = "error"
    res = qwen_api.qwen_fill(qwen_api.row_index(ASK))
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
