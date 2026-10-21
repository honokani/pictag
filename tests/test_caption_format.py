"""段落の入力（文字列）→ Krea2 用キャプション"""
import pytest

from caption_format import merge_same_tail, parse_line, phrases_of, render_caption, with_line

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


@pytest.mark.parametrize("text", [
    "mirror: face reflects on mirror., ball reflects on mirror.",  # 文をカンマで区切っても、末尾の語でまとめない
    "mirror: face reflects on mirror.ball reflects on mirror.",    # . のすぐ後ろに続けても、空白を入れる
    "mirror: face reflects on mirror. ball reflects on mirror.",
])
def test_sentences_under_a_key_are_joined_with_spaces(text):
    # キーの値に書いた文（. ! ? で終わる語句）は、まとめずに空白でつなぐ（else の物ごとの文など）
    assert render_caption([("else", text)]) == "else:\n  - mirror: face reflects on mirror. ball reflects on mirror."


def test_space_after_a_period_keeps_abbreviations_and_numbers():
    # . の後ろに空白を入れるのは、2文字以上の語の後ろで、小文字が続くときだけ（e.g. や 1.5 は変えない）
    assert render_caption([("action", "girl sits.she smiles, e.g.dog, 1.5m")]) == (
        "action:\n  - girl sits. she smiles, e.g.dog, 1.5m")


def test_key_without_phrases_and_blank_lines_are_left_out():
    assert render_caption([("girl", "body:\n\nlooks: standing\n")]) == "girl:\n  - looks: standing"


def test_crlf_input():
    assert render_caption([("girl", "looks: standing\r\nbody: long hair")]) == (
        "girl:\n  - looks: standing\n  - body: long hair")


def test_phrases_of_lists_phrases_before_merging():
    assert phrases_of("body: long hair, black hair\ngirl walks a dog") == [
        ("body", "long hair"), ("body", "black hair"), ("", "girl walks a dog")]


PICTURE_KEYS = ["place", "characters", "vibes", "view"]


@pytest.mark.parametrize("text, value, expected", [
    ("place: classroom\nvibes: cozy", "1 girl", "place: classroom\ncharacters: 1 girl\nvibes: cozy"),
    ("", "1 girl", "characters: 1 girl"),
    ("vibes: cozy", "1 girl", "characters: 1 girl\nvibes: cozy"),
    ("characters: typed by hand\nplace: classroom", "1 dog", "place: classroom\ncharacters: 1 dog"),
    ("place: classroom\ncharacters: old", "", "place: classroom"),
])
def test_with_line_places_the_line_in_template_order(text, value, expected):
    assert with_line(text, "characters", value, PICTURE_KEYS) == expected
