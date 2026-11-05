"""共用辞書の管理（登録・削除・改名）と「1つだけ」のグループ（関数単体）"""
import pytest

from groups import blocked_by, clean_groups, group_of, normalize_groups
from words import (check_phrase, empty_shared, group_phrases, move_phrases, move_registered, name_group, register_phrases,
                   register_words, rename_phrase, rename_registered, replace_phrases, replace_registered, ungroup_phrases,
                   unregister_phrases, unregister_words)

POSTURES = ["standing", "sitting", "lying"]
SUBJECT_KEYS = ["looks", "clothes", "body"]


def test_normalize_merges_groups_sharing_a_phrase_and_drops_empty_ones():
    groups = [{"key": "looks", "phrases": ["standing", "sitting"]},
              {"key": "clothes", "phrases": ["suit", "sitting"]},  # 別のキーとはまとめない
              {"key": "looks", "phrases": ["lying", "kneeling"]},
              {"key": "looks", "phrases": ["sitting", "lying"]},  # 1つ目と3つ目をつなぐ
              {"key": "body", "phrases": ["short hair"]},  # 語句が1つの kind も残す
              {"key": "body", "phrases": []}]  # 語句の無い kind は消える
    assert normalize_groups(groups) == [
        {"key": "looks", "phrases": ["standing", "sitting", "lying", "kneeling"]},
        {"key": "clothes", "phrases": ["suit", "sitting"]},
        {"key": "body", "phrases": ["short hair"]},
    ]


def test_group_of_and_blocked_by():
    groups = [{"key": "looks", "phrases": POSTURES}]
    assert group_of(groups, "looks", "sitting") == groups[0]
    assert group_of(groups, "body", "sitting") is None

    text = "looks: sitting, smile\nclothes: suit"
    assert blocked_by(groups, text, "looks", "standing") == "sitting"
    assert blocked_by(groups, text, "looks", "sitting") is None  # 自分自身とはぶつからない
    assert blocked_by(groups, text, "looks", "eyes closed") is None  # グループの外
    assert blocked_by(groups, "clothes: standing", "looks", "lying") is None  # 別のキーの行


FACES = {"key": "face", "phrases": ["smiling face", "surprised face"], "name": " face", "affix": "postfix"}
EYES = {"key": "eyes", "phrases": ["eyes closed", "eyes open"], "name": "eyes ", "affix": "prefix"}


def test_a_group_with_a_postfix_or_prefix_takes_in_every_phrase_that_has_it():
    # postfix は名前で終わる語句、prefix は名前で始まる語句（同じキー）をいつも仲間にする。名前の空白もそのまま比べる
    groups = [FACES, EYES]
    assert group_of(groups, "face", "crying face") == FACES
    assert group_of(groups, "face", "smileface") is None  # 「 face」で終わらない
    assert group_of(groups, "looks", "crying face") is None  # 別のキー
    assert group_of(groups, "eyes", "eyes half closed") == EYES
    assert blocked_by(groups, "face: crying face, blush", "face", "smiling face") == "crying face"
    assert blocked_by(groups, "face: smileface", "face", "smiling face") is None


def test_normalize_keeps_the_first_name_and_groups_with_a_rule():
    groups = [FACES,
              {"key": "face", "phrases": ["smiling face", "grin"], "name": "mouth"},  # 重なれば、先にあった方の名前
              {"key": "face", "phrases": ["crying face", "pout"]},  # 決まり（ face で終わる）で1つ目と重なる
              {"key": "eyes", "phrases": ["eyes closed"], "name": "eyes ", "affix": "prefix"}]  # 決まりがあれば語句が1つでも残す
    assert normalize_groups(groups) == [
        {"key": "face", "phrases": ["smiling face", "surprised face", "grin", "crying face", "pout"], "name": " face", "affix": "postfix"},
        {"key": "eyes", "phrases": ["eyes closed"], "name": "eyes ", "affix": "prefix"}]


def test_clean_groups_keeps_only_a_valid_name_and_rule():
    loaded = [FACES, {"key": "body", "phrases": ["x", "y"], "name": 3, "affix": "sideways"}]
    assert clean_groups(loaded) == [FACES, {"key": "body", "phrases": ["x", "y"]}]


def test_group_phrases_with_a_name_and_name_group():
    shared = group_phrases(empty_shared(), "face", ["smiling face", "surprised face"], " face", "postfix")
    assert shared["groups"] == [FACES]
    shared = group_phrases(shared, "face", ["crying face", "pout"])  # 今あるグループ（決まりで重なる）に足すと、名前はそのまま
    phrases = ["smiling face", "surprised face", "crying face", "pout"]
    assert shared["groups"] == [{**FACES, "phrases": phrases}]
    shared = name_group(shared, "face", "pout", "mouth", "")  # 仲間の語句でグループを選び、名前を変える（前後の決まりなし）
    assert shared["groups"] == [{"key": "face", "phrases": phrases, "name": "mouth"}]
    assert name_group(shared, "face", "pout", "  ", "postfix")["groups"] == [{"key": "face", "phrases": phrases}]  # 空白だけなら番号


def test_register_adds_only_new_entries():
    shared = register_phrases(empty_shared(), [("girl", "looks", "standing"), ("guy", "looks", "standing")])
    again = register_phrases(shared, [("girl", "looks", "standing"), ("girl", "looks", "sitting")])
    assert again["phrases"] == [{"section": "girl", "key": "looks", "phrase": "standing"},
                                {"section": "guy", "key": "looks", "phrase": "standing"},
                                {"section": "girl", "key": "looks", "phrase": "sitting"}]
    words = register_words(again, [("action", "spread"), ("action", "spread")])
    assert words["words"] == [{"section": "action", "word": "spread"}]


def test_unregister_removes_key_phrase_of_every_section_and_from_groups():
    shared = register_phrases(empty_shared(), [("girl", "looks", "standing"), ("guy", "looks", "standing"),
                                               ("girl", "looks", "sitting"), ("girl", "body", "standing")])
    shared = group_phrases(shared, "looks", ["standing", "sitting"])
    out = unregister_phrases(shared, [("looks", "standing")])
    assert out["phrases"] == [{"section": "girl", "key": "looks", "phrase": "sitting"},
                              {"section": "girl", "key": "body", "phrase": "standing"}]
    assert out["groups"] == [{"key": "looks", "phrases": ["sitting"]}]  # 語句が1つになった kind も残る


def test_unregister_words_of_every_section():
    shared = register_words(empty_shared(), [("action", "spread"), ("girl", "spread"), ("action", "arms")])
    assert unregister_words(shared, ["spread"])["words"] == [{"section": "action", "word": "arms"}]


def test_rename_registered_merges_duplicates_and_renames_in_groups():
    shared = register_phrases(empty_shared(), [("girl", "looks", "standnig"), ("girl", "looks", "standing"),
                                               ("guy", "looks", "standnig")])
    shared = group_phrases(shared, "looks", ["standnig", "sitting"])
    out = rename_registered(shared, "looks", "standnig", "standing")
    assert out["phrases"] == [{"section": "girl", "key": "looks", "phrase": "standing"},
                              {"section": "guy", "key": "looks", "phrase": "standing"}]
    assert out["groups"] == [{"key": "looks", "phrases": ["standing", "sitting"]}]


def test_move_phrases_to_the_line_of_another_key():
    text = "looks: black ponytail hair, smile\nbody: bare hands"
    assert move_phrases(text, "looks", "body", ["black ponytail hair"], SUBJECT_KEYS) == (
        "looks: smile\nbody: bare hands, black ponytail hair")
    assert move_phrases("looks: a, b, c", "looks", "body", ["a", "c", "a"], SUBJECT_KEYS) == "looks: b\nbody: a, c"


def test_move_phrases_puts_a_new_key_line_in_template_order_and_drops_an_emptied_line():
    text = "looks: black ponytail hair\nclothes: school uniform\ngirl is smiling"
    assert move_phrases(text, "looks", "body", ["black ponytail hair"], SUBJECT_KEYS) == (
        "clothes: school uniform\nbody: black ponytail hair\ngirl is smiling")


def test_move_phrases_already_in_the_destination_only_leave_the_source():
    text = "looks: smile, black ponytail hair\nbody: black ponytail hair"
    assert move_phrases(text, "looks", "body", ["black ponytail hair"], SUBJECT_KEYS) == "looks: smile\nbody: black ponytail hair"


def test_move_phrases_to_a_key_outside_the_template_keeps_its_line_or_goes_last():
    text = "looks: smile, ponytail\nhair: black\ngirl is smiling"
    assert move_phrases(text, "looks", "hair", ["ponytail"], SUBJECT_KEYS) == "looks: smile\nhair: black, ponytail\ngirl is smiling"
    assert move_phrases("looks: ponytail\nbody: bare hands", "looks", "hair", ["ponytail"], SUBJECT_KEYS) == (
        "body: bare hands\nhair: ponytail")


def test_move_phrases_leaves_text_without_them_alone():
    text = "looks: smile\nclothes: ponytail\nponytail"  # 別のキーとキーなしの文の語句は動かさない
    assert move_phrases(text, "looks", "body", ["ponytail"], SUBJECT_KEYS) == text


def test_move_registered_changes_the_key_in_the_chosen_sections_only():
    shared = register_phrases(empty_shared(), [("dog A", "looks", "lying"), ("dog B", "looks", "lying"),
                                               ("girl", "looks", "lying"), ("dog A", "body", "lying")])
    out = move_registered(shared, lambda section: section.startswith("dog"), "looks", "body", ["lying"])
    assert out["phrases"] == [{"section": "dog A", "key": "body", "phrase": "lying"},  # 重なれば1つに
                              {"section": "dog B", "key": "body", "phrase": "lying"},
                              {"section": "girl", "key": "looks", "phrase": "lying"}]


def test_rename_phrase_in_input_lines_of_the_key_only():
    text = "looks: standnig, smile\nclothes: standnig\nlooks: standing, standnig"
    assert rename_phrase(text, "looks", "standnig", "standing") == (
        "looks: standing, smile\nclothes: standnig\nlooks: standing")


def test_replace_phrases_in_input_lines_of_the_key_only():
    text = "looks: dark hair, smile\nbody: dark hair\ndark hair"  # 別のキーとキーなしの文の語句は変えない
    assert replace_phrases(text, "looks", ["dark hair"], "black hair") == "looks: black hair, smile\nbody: dark hair\ndark hair"
    assert replace_phrases("looks: a, b, c", "looks", ["c", "a"], "x") == "looks: x, b"  # 1つにまとめる（前の方の位置に）
    assert replace_phrases("looks: grin, smile", "looks", ["grin"], "smile") == "looks: smile"  # 今ある語句にもまとめられる


def test_replace_registered_in_the_chosen_sections_only_and_keeps_groups():
    shared = register_phrases(empty_shared(), [("girl", "looks", "grin"), ("girl", "looks", "smile"),
                                               ("guy", "looks", "grin")])
    shared = group_phrases(shared, "looks", ["grin", "frown"])
    out = replace_registered(shared, lambda section: section == "girl", "looks", ["grin"], "smile")
    assert out["phrases"] == [{"section": "girl", "key": "looks", "phrase": "smile"},  # 重なれば1つに
                              {"section": "guy", "key": "looks", "phrase": "grin"}]
    assert out["groups"] == [{"key": "looks", "phrases": ["grin", "frown"]}]  # グループは段落をまたぐので変えない


def test_group_phrases_extends_the_group_a_phrase_is_in():
    shared = group_phrases(empty_shared(), "looks", ["standing", "sitting"])
    shared = group_phrases(shared, "looks", ["lying", "sitting"])
    assert shared["groups"] == [{"key": "looks", "phrases": POSTURES}]


def test_ungroup_keeps_a_kind_with_one_phrase_and_drops_an_empty_one():
    shared = group_phrases(empty_shared(), "looks", POSTURES)
    shared = ungroup_phrases(shared, [("looks", "lying"), ("looks", "sitting")])
    assert shared["groups"] == [{"key": "looks", "phrases": ["standing"]}]
    assert ungroup_phrases(shared, [("looks", "standing")])["groups"] == []


def test_a_kind_that_is_not_exclusive_blocks_nothing():
    # 「1つだけ」でない kind（分類だけ）は、同じ行に仲間があってもぶつからない。「1つだけ」は kind ごと（書いていなければ 1つだけ）
    hair = {"key": "body", "phrases": ["long hair", "black hair"], "exclusive": False}
    assert blocked_by([hair], "body: long hair", "body", "black hair") is None
    assert blocked_by([{"key": "body", "phrases": ["long hair", "black hair"]}], "body: long hair", "body", "black hair") == "long hair"
    assert clean_groups([hair, {"key": "looks", "phrases": ["a", "b"], "exclusive": "no"}]) == [
        hair, {"key": "looks", "phrases": ["a", "b"]}]  # 形の正しくない値は 1つだけ のまま


def test_group_phrases_and_name_group_set_whether_a_kind_is_exclusive():
    shared = group_phrases(empty_shared(), "body", ["long hair"], "hair", "postfix", False)  # 語句1つでも kind にできる
    assert shared["groups"] == [{"key": "body", "phrases": ["long hair"], "name": "hair", "affix": "postfix", "exclusive": False}]
    shared = name_group(shared, "body", "black hair", "hair", "postfix", True)  # 決まりの仲間で選び、1つだけにする
    assert shared["groups"] == [{"key": "body", "phrases": ["long hair"], "name": "hair", "affix": "postfix"}]


@pytest.mark.parametrize("key, phrase, message", [
    ("looks", "  ", "語句を入力してください"),
    ("looks", "standing, sitting", "カンマ"),
    ("looks", "standing\nsitting", "改行"),
    ("", "girl: smile", "「:」"),
])
def test_check_phrase_rejects(key, phrase, message):
    with pytest.raises(ValueError, match=message):
        check_phrase(key, phrase)


def test_check_phrase_trims_and_allows_colon_after_a_key():
    assert check_phrase("looks", "  standing ") == "standing"
    assert check_phrase("extra", "3:4 ratio") == "3:4 ratio"


def test_empty_shared_has_no_groups():
    assert empty_shared()["groups"] == []
