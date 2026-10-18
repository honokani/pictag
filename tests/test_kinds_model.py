"""タグ辞書（大kind → 中kind → 小kind → 値）の操作"""
from functools import reduce

import pytest

from kinds import (add_value, column_key, dictionary_columns, empty_kinds, in_table_scope,
                   mid_columns, order_columns, parse_key, register_columns, remove, rename)

GIRL_LONG = ("girl", "body", "hair", "long")
GIRL_BLACK = ("girl", "body", "hair", "black")
GIRL_HANDS = ("girl", "body", "", "bare hands")
GUY_LONG = ("guy", "body", "hair", "long")
GUY_HANDS = ("guy", "body", "", "bare hands")
DOG_BROWN = ("dog", "fur", "", "brown")
WALK = ("action", "", "", "girl walks a dog")


def build(*items):
    return reduce(add_value, items, empty_kinds())


def test_add_value_creates_big_mid_and_entry():
    assert build(GIRL_LONG) == {
        "bigs": [{"name": "girl", "mids": ["body"], "lines": []}],
        "mids": [{"name": "body", "entries": [{"small": "hair", "value": "long"}]}],
    }


def test_values_without_mid_are_lines_of_the_big():
    assert build(WALK) == {"bigs": [{"name": "action", "mids": [], "lines": ["girl walks a dog"]}], "mids": []}


def test_adding_the_same_value_twice_changes_nothing():
    assert build(GIRL_LONG, GIRL_LONG, WALK, WALK) == build(GIRL_LONG, WALK)


def test_values_of_the_same_small_kind_stay_together():
    assert dictionary_columns(build(GIRL_LONG, GIRL_HANDS, GIRL_BLACK)) == [GIRL_LONG, GIRL_BLACK, GIRL_HANDS]


def test_mid_vocabulary_is_shared_between_bigs_that_use_it():
    kinds = build(GIRL_LONG, DOG_BROWN, GUY_HANDS)
    assert dictionary_columns(kinds) == [
        GIRL_LONG, ("girl", "body", "", "bare hands"),
        DOG_BROWN,
        GUY_LONG, GUY_HANDS,
    ]


def test_lines_come_after_mids_within_a_big():
    pose = ("action", "pose", "", "standing")
    assert dictionary_columns(build(WALK, pose)) == [pose, WALK]


def test_mid_columns_lists_all_values_for_one_big():
    kinds = build(GIRL_LONG, GIRL_HANDS)
    assert mid_columns(kinds, "guy", "body") == [GUY_LONG, GUY_HANDS]


def test_order_columns_follows_dictionary_and_keeps_unknown_last():
    kinds = build(GIRL_LONG, GIRL_HANDS, DOG_BROWN)
    unknown = ("cat", "fur", "", "white")
    assert order_columns(kinds, [DOG_BROWN, unknown, GIRL_HANDS, GIRL_LONG]) == [GIRL_LONG, GIRL_HANDS, DOG_BROWN, unknown]


def test_register_columns_adds_columns_missing_from_dictionary():
    kinds = register_columns(build(GIRL_LONG), [GIRL_LONG, DOG_BROWN, WALK])
    assert dictionary_columns(kinds) == [GIRL_LONG, DOG_BROWN, WALK]


@pytest.mark.parametrize("item", [GIRL_LONG, ("女の子", "体", "髪", 'long "wavy", soft'), WALK])
def test_column_key_round_trip(item):
    assert parse_key(column_key(item)) == item


# 改名: (階層, 対象, 新しい名前, 改名後の辞書の列)
RENAMES = [
    ("big", GIRL_LONG, "girl A", [("girl A", "body", "hair", "long"), ("girl A", "body", "", "bare hands"),
                                  GUY_LONG, GUY_HANDS]),
    ("mid", GIRL_LONG, "physique", [("girl", "physique", "hair", "long"), ("girl", "physique", "", "bare hands"),
                                    ("guy", "physique", "hair", "long"), ("guy", "physique", "", "bare hands")]),
    ("small", GIRL_LONG, "hairstyle", [("girl", "body", "hairstyle", "long"), GIRL_HANDS,
                                       ("guy", "body", "hairstyle", "long"), GUY_HANDS]),
    ("value", GIRL_LONG, "very long", [("girl", "body", "hair", "very long"), GIRL_HANDS,
                                       ("guy", "body", "hair", "very long"), GUY_HANDS]),
]


@pytest.mark.parametrize("level, target, new_name, expected", RENAMES)
def test_rename_updates_dictionary_and_columns(level, target, new_name, expected):
    kinds, relabel = rename(build(GIRL_LONG, GIRL_HANDS, GUY_LONG), level, target, new_name)
    assert dictionary_columns(kinds) == expected
    assert [relabel(item) for item in [GIRL_LONG, GIRL_HANDS, GUY_LONG, GUY_HANDS]] == expected


def test_rename_line_of_a_big():
    kinds, relabel = rename(build(WALK), "value", WALK, "girl walks two dogs")
    assert dictionary_columns(kinds) == [("action", "", "", "girl walks two dogs")]
    assert relabel(WALK) == ("action", "", "", "girl walks two dogs")


def test_rename_to_the_same_name_changes_nothing():
    kinds = build(GIRL_LONG)
    renamed, relabel = rename(kinds, "value", GIRL_LONG, "long")
    assert renamed == kinds
    assert relabel(GIRL_LONG) == GIRL_LONG


@pytest.mark.parametrize("level, new_name", [("big", "dog"), ("mid", "fur"), ("small", "eyes"), ("value", "black")])
def test_rename_to_an_existing_name_is_rejected(level, new_name):
    kinds = build(GIRL_LONG, GIRL_BLACK, ("girl", "body", "eyes", "blue"), DOG_BROWN)
    with pytest.raises(ValueError):
        rename(kinds, level, GIRL_LONG, new_name)


@pytest.mark.parametrize("level", ["big", "mid", "small", "value"])
def test_rename_missing_target_is_rejected(level):
    with pytest.raises(ValueError):
        rename(build(DOG_BROWN), level, GIRL_LONG, "x")


@pytest.mark.parametrize("new_name", ["", "  ", "two\nlines"])
def test_rename_rejects_empty_or_multiline_names(new_name):
    with pytest.raises(ValueError):
        rename(build(GIRL_LONG), "value", GIRL_LONG, new_name)


def test_remove_value_removes_it_from_every_big_sharing_the_mid():
    kinds, removed = remove(build(GIRL_LONG, GIRL_HANDS, GUY_LONG), "value", GIRL_LONG)
    assert dictionary_columns(kinds) == [GIRL_HANDS, GUY_HANDS]
    assert [removed(item) for item in [GIRL_LONG, GUY_LONG, GIRL_HANDS]] == [True, True, False]


def test_remove_small_removes_all_its_values():
    kinds, removed = remove(build(GIRL_LONG, GIRL_BLACK, GIRL_HANDS), "small", GIRL_LONG)
    assert dictionary_columns(kinds) == [GIRL_HANDS]
    assert [removed(item) for item in [GIRL_LONG, GIRL_BLACK, GIRL_HANDS]] == [True, True, False]


def test_remove_mid_detaches_it_only_from_that_big():
    kinds, removed = remove(build(GIRL_LONG, GUY_LONG), "mid", GUY_LONG)
    assert dictionary_columns(kinds) == [GIRL_LONG]
    assert [removed(item) for item in [GUY_LONG, GIRL_LONG]] == [True, False]
    # 語彙は残る（guy にもう一度付けられる）
    assert mid_columns(kinds, "guy", "body") == [GUY_LONG]


def test_remove_big():
    kinds, removed = remove(build(GIRL_LONG, DOG_BROWN), "big", DOG_BROWN)
    assert dictionary_columns(kinds) == [GIRL_LONG]
    assert [removed(item) for item in [DOG_BROWN, GIRL_LONG]] == [True, False]


def test_remove_line():
    other = ("action", "", "", "girl rides on guy's shoulders")
    kinds, removed = remove(build(WALK, other), "value", WALK)
    assert dictionary_columns(kinds) == [other]
    assert [removed(item) for item in [WALK, other]] == [True, False]


@pytest.mark.parametrize("level, expected", [
    ("big", [True, True, True, False]),
    ("mid", [True, True, True, False]),
    ("small", [True, True, False, False]),
    ("value", [True, False, False, False]),
])
def test_table_scope_stays_within_the_chosen_big(level, expected):
    items = [GIRL_LONG, GIRL_BLACK, GIRL_HANDS, GUY_LONG]
    assert [in_table_scope(level, GIRL_LONG, item) for item in items] == expected
