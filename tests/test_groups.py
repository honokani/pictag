"""共用辞書の管理（登録・削除・改名）と「1つだけ」のグループ（関数単体）"""
import pytest

from groups import blocked_by, group_of, normalize_groups
from words import (check_phrase, empty_shared, group_phrases, register_phrases, register_words, rename_phrase,
                   rename_registered, ungroup_phrases, unregister_phrases, unregister_words)

POSTURES = ["standing", "sitting", "lying"]


def test_normalize_merges_groups_sharing_a_phrase_and_drops_small_ones():
    groups = [{"key": "looks", "phrases": ["standing", "sitting"]},
              {"key": "clothes", "phrases": ["suit", "sitting"]},  # 別のキーとはまとめない
              {"key": "looks", "phrases": ["lying", "kneeling"]},
              {"key": "looks", "phrases": ["sitting", "lying"]},  # 1つ目と3つ目をつなぐ
              {"key": "body", "phrases": ["short hair"]}]  # 語句が1つのグループは消える
    assert normalize_groups(groups) == [
        {"key": "looks", "phrases": ["standing", "sitting", "lying", "kneeling"]},
        {"key": "clothes", "phrases": ["suit", "sitting"]},
    ]


def test_group_of_and_blocked_by():
    groups = [{"key": "looks", "phrases": POSTURES}]
    assert group_of(groups, "looks", "sitting") == POSTURES
    assert group_of(groups, "body", "sitting") == []

    text = "looks: sitting, smile\nclothes: suit"
    assert blocked_by(groups, text, "looks", "standing") == "sitting"
    assert blocked_by(groups, text, "looks", "sitting") is None  # 自分自身とはぶつからない
    assert blocked_by(groups, text, "looks", "eyes closed") is None  # グループの外
    assert blocked_by(groups, "clothes: standing", "looks", "lying") is None  # 別のキーの行


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
    assert out["groups"] == []  # 語句が1つになったグループは消える


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


def test_rename_phrase_in_input_lines_of_the_key_only():
    text = "looks: standnig, smile\nclothes: standnig\nlooks: standing, standnig"
    assert rename_phrase(text, "looks", "standnig", "standing") == (
        "looks: standing, smile\nclothes: standnig\nlooks: standing")


def test_group_phrases_extends_the_group_a_phrase_is_in():
    shared = group_phrases(empty_shared(), "looks", ["standing", "sitting"])
    shared = group_phrases(shared, "looks", ["lying", "sitting"])
    assert shared["groups"] == [{"key": "looks", "phrases": POSTURES}]


def test_ungroup_drops_a_group_left_with_one_phrase():
    shared = group_phrases(empty_shared(), "looks", POSTURES)
    shared = ungroup_phrases(shared, [("looks", "lying")])
    assert shared["groups"] == [{"key": "looks", "phrases": ["standing", "sitting"]}]
    assert ungroup_phrases(shared, [("looks", "sitting")])["groups"] == []


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
