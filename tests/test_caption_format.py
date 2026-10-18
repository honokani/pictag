"""段落の入力（文字列）→ Krea2 用キャプション"""
import pytest

from caption_format import merge_same_tail, parse_line, phrases_of, render_caption

# (段落, 入力)。1行は「キー: 語句, 語句」か、キーなしの文
OWNER_SECTIONS = [
    ("picture", "place: classroom\nobject: 1 girl + 1 guy\nvibes: size difference emphasized\n"
                "view: from below, third POV"),
    ("action", "girl spreads arms\nguy grabs girl's waist"),
    ("girl", "looks: full body shot, standing\nclothes: school uniform, long socks, white socks, sneakers\n"
             "body: long hair, black hair, bare hands"),
    ("guy", "looks: full body shot, standing\nclothes: school uniform, sneakers\n"
            "body: short hair, black hair, bare hands"),
]

EXAMPLE_TEXT = """picture:
  - place: classroom
  - object: 1 girl + 1 guy
  - vibes: size difference emphasized
  - view: from below, third POV

action:
  - girl spreads arms
  - guy grabs girl's waist

girl:
  - looks: full body shot, standing
  - clothes: school uniform, long white socks, sneakers
  - body: long black hair, bare hands

guy:
  - looks: full body shot, standing
  - clothes: school uniform, sneakers
  - body: short black hair, bare hands"""


def test_renders_owner_example():
    assert render_caption(OWNER_SECTIONS) == EXAMPLE_TEXT


def test_empty_sections_are_left_out():
    assert render_caption([("girl", ""), ("dog", "  \n ")]) == ""
    assert render_caption([("girl", "looks: standing"), ("dog", "")]) == "girl:\n  - looks: standing"


@pytest.mark.parametrize("line, expected", [
    ("body: long hair,  black hair ,", ("body", ["long hair", "black hair"])),
    ("body: long hair, long hair", ("body", ["long hair"])),
    ("- looks: standing", ("looks", ["standing"])),
    ("girl walks a dog", ("", ["girl walks a dog"])),
    ("girl raises arms, guy raises arms", ("", ["girl raises arms", "guy raises arms"])),
    ("red, blue: mixed", ("", ["red", "blue: mixed"])),
])
def test_parse_line(line, expected):
    assert parse_line(line) == expected


@pytest.mark.parametrize("phrases, expected", [
    (["long hair", "black hair", "bare hands"], ["long black hair", "bare hands"]),
    (["school uniform", "long socks", "sneakers", "white socks"], ["school uniform", "long white socks", "sneakers"]),
    (["black hair", "black long hair"], ["black long hair"]),
    (["standing", "hair", "long hair"], ["standing", "hair", "long hair"]),
])
def test_merge_same_tail(phrases, expected):
    assert merge_same_tail(phrases) == expected


def test_lines_without_key_are_not_merged():
    assert render_caption([("action", "girl raises arms, guy raises arms")]) == (
        "action:\n  - girl raises arms, guy raises arms")


def test_key_without_phrases_and_blank_lines_are_left_out():
    assert render_caption([("girl", "body:\n\nlooks: standing\n")]) == "girl:\n  - looks: standing"


def test_crlf_input():
    assert render_caption([("girl", "looks: standing\r\nbody: long hair")]) == (
        "girl:\n  - looks: standing\n  - body: long hair")


def test_phrases_of_lists_phrases_before_merging():
    assert phrases_of("body: long hair, black hair\ngirl walks a dog") == [
        ("body", "long hair"), ("body", "black hair"), ("", "girl walks a dog")]
