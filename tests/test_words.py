"""使用中の語句（全プロジェクトの入力から作る辞書）と、入力への語句の足し引き"""
import pytest

from words import add_phrase, check_section_name, count_words, dictionary_entries, remove_phrase


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


def test_dictionary_entries_are_sorted_by_use():
    counter = count_words([("girl", "body: black hair"), ("girl", "body: long hair"), ("girl", "body: long hair")])
    assert dictionary_entries(counter) == [
        {"section": "girl", "key": "body", "phrase": "long hair", "count": 2},
        {"section": "girl", "key": "body", "phrase": "black hair", "count": 1},
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
