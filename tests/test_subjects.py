"""人物などの段落: 自動の命名、characters の自動計算、view の選択肢"""
import pytest

from subjects import CAMERA_EMOJI, CAMERA_GROUPS, base_name, characters_of, insert_position, name_for_new, pov_choices


@pytest.mark.parametrize("section, expected", [("guy A", "guy"), ("girl", "girl"), ("big dog B", "big dog"), ("A", "A")])
def test_base_name(section, expected):
    assert base_name(section) == expected


@pytest.mark.parametrize("present, expected", [
    (["girl"], "1 girl"),
    (["girl", "guy A", "guy B"], "1 girl + 2 guys (guy A, guy B)"),
    (["girl A", "dog"], "1 girl (girl A) + 1 dog"),
    (["woman A", "woman B"], "2 women (woman A, woman B)"),
    ([], ""),
])
def test_characters_of(present, expected):
    assert characters_of([(section, "looks: standing") for section in present]) == expected


@pytest.mark.parametrize("present, expected", [
    ([("girl", "looks: standing"), ("else", "dog: brown fur, sitting\ncat: black")], "1 girl + dog + cat"),
    ([("girl", "looks: standing"), ("else", "dog: brown fur\na bird flying\ndog: small")], "1 girl + dog"),  # 同じキーは1回。キーの無い文は入れない
    ([("girl", "looks: standing"), ("else", "dog:\ncat: black")], "1 girl + cat"),  # 値の無いキーは入れない
    ([("else", "a bird flying")], ""),
    ([("girl", "looks: standing"), ("else", "dog: brown fur"), ("guy", "looks: sitting")], "1 girl + dog + 1 guy"),  # 表の並び
    ([("girl", "looks: standing"), ("else A", "dog: brown fur"), ("else B", "cat: black\ndog: small")], "1 girl + dog + cat"),
])
def test_characters_of_lists_keys_of_else_without_numbers(present, expected):
    # else（人物でない物の段落）は人物に数えず、行のキー（dog: / cat:）を数なしで並べる
    assert characters_of(present) == expected


@pytest.mark.parametrize("name, sections, expected", [
    ("guy", ["girl"], ({}, "guy")),
    ("guy", ["girl", "guy"], ({"guy": "guy A"}, "guy B")),
    ("guy", ["girl", "guy A", "guy B"], ({}, "guy C")),
    ("girl", ["girl"], ({"girl": "girl A"}, "girl B")),
    ("guy B", ["guy"], ({"guy": "guy A"}, "guy B")),
])
def test_name_for_new(name, sections, expected):
    assert name_for_new(name, sections) == expected


def test_name_for_new_runs_out_after_z():
    with pytest.raises(ValueError):
        name_for_new("guy", [f"guy {chr(c)}" for c in range(ord("A"), ord("Z") + 1)])


def test_pov_choices_follow_subject_sections():
    # ボタンは絵文字と A, B の文字（絵文字の決まっていない名前は名前を残す）。女性・男性で色を変える
    assert pov_choices(["girl", "guy A", "guy B", "dog", "alien"]) == [
        {"emoji": "👥", "label": "", "tone": "", "phrase": "third-person POV"},  # 先頭
        {"emoji": "👧", "label": "", "tone": "female", "phrase": "girl POV"},
        {"emoji": "👨", "label": "A", "tone": "male", "phrase": "guy A POV"},
        {"emoji": "👨", "label": "B", "tone": "male", "phrase": "guy B POV"},
        {"emoji": "🐕", "label": "", "tone": "", "phrase": "dog POV"},
        {"emoji": "👤", "label": "alien", "tone": "", "phrase": "alien POV"},
    ]


def test_pov_choices_leave_out_else():
    # else は人物でないので POV のボタンを出さない（else A, else B も）
    assert [c["phrase"] for c in pov_choices(["girl", "else A", "else B", "guy"])] == ["third-person POV", "girl POV", "guy POV"]


@pytest.mark.parametrize("name, columns, expected", [
    ("girl B", ["picture", "action", "girl A", "guy"], 3),  # 同じ名前の最後の段落のすぐ後ろ
    ("guy B", ["picture", "action", "girl A", "girl B", "guy A"], 5),
    ("girl C", ["picture", "girl A", "guy", "girl B"], 4),
    ("dog", ["picture", "action", "girl", "guy"], 4),  # 新しい名前は末尾
])
def test_insert_position_keeps_the_same_kind_together(name, columns, expected):
    assert insert_position(name, columns) == expected


def test_pov_tone_by_gender():
    tones = {c["phrase"]: c["tone"] for c in pov_choices(["woman", "boy", "man", "cat"])}
    assert tones == {"woman POV": "female", "boy POV": "male", "man POV": "male", "cat POV": "",
                     "third-person POV": ""}


def test_camera_groups_and_emoji():
    assert CAMERA_GROUPS == [["from front", "from side", "from behind"], ["from above", "eye level", "from below"],
                             ["close-up", "portrait", "medium shot", "long shot"]]
    assert sorted(CAMERA_EMOJI) == sorted(p for group in CAMERA_GROUPS for p in group)  # どのボタンにも絵文字
