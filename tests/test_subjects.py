"""人物などの段落: 自動の命名、characters の自動計算、view の選択肢"""
import pytest

from subjects import CAMERA_GROUPS, base_name, characters_of, name_for_new, pov_choices


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
    assert pov_choices(["girl", "guy A", "dog"]) == [
        {"emoji": "👧", "label": "girl", "phrase": "girl POV"},
        {"emoji": "👨", "label": "guy A", "phrase": "guy A POV"},
        {"emoji": "🐕", "label": "dog", "phrase": "dog POV"},
        {"emoji": "👥", "label": "third-person", "phrase": "third-person POV"},
    ]


def test_camera_groups():
    assert CAMERA_GROUPS == [["from front", "from side", "from behind"], ["from above", "from below"], ["close-up"]]
