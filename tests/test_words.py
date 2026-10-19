"""使用中の語句（全プロジェクトの入力から作る辞書）と、入力への語句の足し引き"""
import pytest

from words import (add_phrase, check_section_name, count_sentence_words, count_words, empty_shared, freeze,
                   phrase_entries, remove_phrase, set_choice)


def test_count_words_counts_each_section_key_and_phrase():
    counter = count_words([
        ("girl", "body: long hair, black hair"),
        ("girl", "body: long hair\ngirl walks a dog"),
        ("dog", "fur: brown"),
    ])
    assert counter == {
        ("girl", "body", "long hair"): 2,
        ("girl", "body", "black hair"): 1,
        ("girl", "", "girl walks a dog"): 1,
        ("dog", "fur", "brown"): 1,
    }


def test_phrase_entries_are_sorted_by_use():
    counter = count_words([("girl", "body: black hair"), ("girl", "body: long hair"), ("girl", "body: long hair")])
    assert phrase_entries(counter, empty_shared()) == [
        {"section": "girl", "key": "body", "phrase": "long hair", "count": 2, "shared": False},
        {"section": "girl", "key": "body", "phrase": "black hair", "count": 1, "shared": False},
    ]


@pytest.mark.parametrize("text, key, phrase, expected", [
    ("", "body", "long hair", "body: long hair"),
    ("looks: standing", "body", "long hair", "looks: standing\nbody: long hair"),
    ("body: long hair", "body", "black hair", "body: long hair, black hair"),
    ("body: long hair", "body", "long hair", "body: long hair"),
    ("looks: standing", "", "girl walks a dog", "looks: standing\ngirl walks a dog"),
    ("girl walks a dog", "", "girl walks a dog", "girl walks a dog"),
])
def test_add_phrase(text, key, phrase, expected):
    assert add_phrase(text, key, phrase) == expected


@pytest.mark.parametrize("text, key, phrase, expected", [
    ("body: long hair, black hair", "body", "long hair", "body: black hair"),
    ("looks: standing\nbody: long hair", "body", "long hair", "looks: standing"),
    ("looks: standing", "body", "long hair", "looks: standing"),
    ("girl walks a dog\nlooks: standing", "", "girl walks a dog", "looks: standing"),
    ("smile, blush", "", "smile", "blush"),
])
def test_remove_phrase(text, key, phrase, expected):
    assert remove_phrase(text, key, phrase) == expected


@pytest.mark.parametrize("name", ["", "  ", "two\nlines", "サムネイル", "is_dead", "girl:"])
def test_invalid_section_names_are_rejected(name):
    with pytest.raises(ValueError):
        check_section_name(name)


def test_section_name_is_stripped():
    assert check_section_name("  girl ") == "girl"


def test_count_sentence_words_splits_lines_without_key():
    counter = count_sentence_words([
        ("action", "girl spread arms\nguy grab girl's waist"),
        ("action", "looks: standing\ngirl smiles, waves"),
    ])
    assert counter == {("action", w): n for w, n in [
        ("girl", 2), ("spread", 1), ("arms", 1), ("guy", 1), ("grab", 1), ("girl's", 1), ("waist", 1),
        ("smiles", 1), ("waves", 1)]}


def test_freeze_adds_used_entries_once():
    shared = {"templates": {}, "phrases": [{"section": "girl", "key": "body", "phrase": "long hair"}], "words": []}
    phrases = count_words([("girl", "body: long hair, black hair")])
    words = count_sentence_words([("action", "girl smiles")])
    frozen, added = freeze(shared, phrases, words)
    assert added == 3
    assert frozen["phrases"] == [{"section": "girl", "key": "body", "phrase": "long hair"},
                                 {"section": "girl", "key": "body", "phrase": "black hair"}]
    assert frozen["words"] == [{"section": "action", "word": "girl"}, {"section": "action", "word": "smiles"}]


def test_phrase_entries_include_shared_phrases_with_zero_count():
    shared = {"templates": {}, "phrases": [{"section": "girl", "key": "body", "phrase": "short hair"}], "words": []}
    entries = phrase_entries(count_words([("girl", "body: long hair")]), shared)
    assert entries == [
        {"section": "girl", "key": "body", "phrase": "long hair", "count": 1, "shared": False},
        {"section": "girl", "key": "body", "phrase": "short hair", "count": 0, "shared": True},
    ]


CAMERA = ["from front", "from side", "from behind"]


@pytest.mark.parametrize("text, phrase, on, expected", [
    ("", "from behind", True, "view: from behind"),
    ("view: from above, from front", "from behind", True, "view: from above, from behind"),
    ("view: from above, from behind", "from behind", False, "view: from above"),
    ("view: from behind", "from behind", False, ""),
    ("place: classroom", "from side", True, "place: classroom\nview: from side"),
])
def test_set_choice_keeps_one_phrase_of_the_group(text, phrase, on, expected):
    assert set_choice(text, "view", phrase, CAMERA, on) == expected


SHOTS = ["close-up", "portrait", "medium shot", "long shot"]


@pytest.mark.parametrize("text, phrase, on, expected", [
    ("view: close-up face, from below", "portrait", True, "view: from below, portrait"),  # 対象の付いた close-up も置き換える
    ("view: close-up face, from below", "close-up", False, "view: from below"),
    ("view: close-up hands", "close-up", True, "view: close-up"),
    ("view: close-upper body", "portrait", True, "view: close-upper body, portrait"),  # 「close-up 」で始まるものだけ
    ("view: portrait orientation", "medium shot", True, "view: portrait orientation, medium shot"),  # close-up だけ
])
def test_set_choice_treats_close_up_with_a_target_as_close_up(text, phrase, on, expected):
    assert set_choice(text, "view", phrase, SHOTS, on, targeted=["close-up"]) == expected
