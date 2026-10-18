"""Krea2 用キャプションの整形（表の1行 → 構造化テキスト）"""
from caption_format import merge_values, render_caption

# (大kind, 中kind, 小kind, 値)。辞書の順に並んだ、1行のうち True の項目
EXAMPLE_ITEMS = [
    ("picture", "place", "", "classroom"),
    ("picture", "object", "", "1 girl + 1 guy"),
    ("picture", "vibes", "", "size difference emphasized"),
    ("picture", "view", "", "from below"),
    ("picture", "view", "", "third POV"),
    ("action", "", "", "girl spreads arms"),
    ("action", "", "", "guy grabs girl's waist"),
    ("girl", "looks", "", "full body shot"),
    ("girl", "looks", "", "standing"),
    ("girl", "clothes", "", "school uniform"),
    ("girl", "clothes", "socks", "long"),
    ("girl", "clothes", "socks", "white"),
    ("girl", "clothes", "", "sneakers"),
    ("girl", "body", "hair", "long"),
    ("girl", "body", "hair", "black"),
    ("girl", "body", "", "bare hands"),
    ("guy", "looks", "", "full body shot"),
    ("guy", "looks", "", "standing"),
    ("guy", "clothes", "", "school uniform"),
    ("guy", "clothes", "", "sneakers"),
    ("guy", "body", "hair", "short"),
    ("guy", "body", "hair", "black"),
    ("guy", "body", "", "bare hands"),
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
    assert render_caption(EXAMPLE_ITEMS) == EXAMPLE_TEXT


def test_empty_row_renders_empty_caption():
    assert render_caption([]) == ""


def test_small_kind_values_are_joined_before_its_name():
    assert merge_values("hair", ["long", "black"]) == "long black hair"


def test_single_value_under_small_kind():
    assert render_caption([("girl", "body", "hair", "long")]) == "girl:\n  - body: long hair"


def test_values_without_mid_kind_are_lines_without_key():
    items = [("action", "", "", "girl spreads arms"), ("action", "", "", "guy grabs girl's waist")]
    assert render_caption(items) == "action:\n  - girl spreads arms\n  - guy grabs girl's waist"


def test_groups_keep_first_appearance_order():
    items = [
        ("girl", "body", "hair", "long"),
        ("girl", "clothes", "", "school uniform"),
        ("girl", "body", "", "bare hands"),
        ("girl", "body", "hair", "black"),
    ]
    assert render_caption(items) == "girl:\n  - body: long black hair, bare hands\n  - clothes: school uniform"
