"""action の文の動詞の形（進行形 is doing / 現在形 does）を数え、多い方にそろえる"""
from collections import Counter

import pytest

from verbs import PRESENT, PROGRESSIVE, convert, count_forms, majority, survey

SUBJECTS = ("girl", "girl A", "guy")


@pytest.mark.parametrize("line, expected", [
    ("girl is sitting.", "girl sits."),
    ("she is sitting.", "she sits."),
    ("girl and guy are hugging.", "girl and guy hug."),
    ("girl is lying on bed.", "girl lies on bed."),
    ("guy is gently stroking dog.", "guy gently strokes dog."),
    ("girl is sitting and smiling.", "girl sits and smiles."),
    ("girl is sitting, guy is standing.", "girl sits, guy stands."),
    ("girl is being carried by guy.", "girl is carried by guy."),
    ("girl's hair is blowing in wind.", "girl's hair blows in wind."),  # 主語が分からなくても is / are で数が分かる
    ("she sit.", "she sits."),  # s の無い現在形にも s を付ける
    ("girl and guy hugs.", "girl and guy hug."),
])
def test_convert_to_present(line, expected):
    assert convert(line, SUBJECTS, PRESENT) == (expected, True)


@pytest.mark.parametrize("line, expected", [
    ("girl sits.", "girl is sitting."),
    ("she sit.", "she is sitting."),  # s の無い現在形も
    ("girl and guy hug.", "girl and guy are hugging."),
    ("girl lies on bed.", "girl is lying on bed."),
    ("guy gently strokes dog.", "guy is gently stroking dog."),
    ("girl sits and smiles.", "girl is sitting and smiling."),
    ("girl A waves at guy.", "girl A is waving at guy."),
    ("girls dance.", "girls are dancing."),
    ("girl sits, guy stands.", "girl is sitting, guy is standing."),
    ("they kiss.", "they are kissing."),
])
def test_convert_to_progressive(line, expected):
    assert convert(line, SUBJECTS, PROGRESSIVE) == (expected, True)


@pytest.mark.parametrize("line, target, expected", [
    ("girl is sitting on bench and reading book.", PRESENT, "girl sits on bench and reads book."),  # and の後ろが離れている
    ("girl holds bag and walks away.", PROGRESSIVE, "girl is holding bag and walking away."),
    ("girl is going to kiss guy.", PRESENT, "girl goes to kiss guy."),  # これからすること
    ("guy hand on hip.", PRESENT, "guy hands on hip."),  # 体の部分は名詞のことが多い
    ("girl is photobombing guy.", PRESENT, "girl photobombs guy."),  # 辞書に無い動詞
])
def test_convert_marks_sentences_it_is_unsure_of(line, target, expected):
    assert convert(line, SUBJECTS, target) == (expected, False)


@pytest.mark.parametrize("line, target", [("girl sits.", PRESENT), ("girl is sitting.", PROGRESSIVE),
                                          ("girl has long hair.", PROGRESSIVE), ("holding hands.", PRESENT),
                                          ("girl in red dress.", PROGRESSIVE)])
def test_convert_leaves_sentences_already_in_the_form_or_without_a_form(line, target):
    # 状態の動詞（has など）は is having にしない。主語の後ろに動詞の無い文は数えない
    assert convert(line, SUBJECTS, target) is None


def test_count_forms_counts_each_sentence():
    lines = ["girl is sitting, guy waves.", "she sit.", "girl has long hair.", "holding hands."]
    assert count_forms(lines, SUBJECTS) == Counter({PROGRESSIVE: 1, PRESENT: 2})


def test_majority_is_the_form_with_more_sentences():
    assert majority(Counter({PROGRESSIVE: 2, PRESENT: 1})) == PROGRESSIVE
    assert majority(Counter({PROGRESSIVE: 1, PRESENT: 3})) == PRESENT
    assert majority(Counter({PROGRESSIVE: 2, PRESENT: 2})) is None  # 同じ数ならそろえない
    assert majority(Counter()) is None


def test_survey_suggests_changes_to_the_majority():
    lines = [(0, "she sit."), (1, "girl is smiling."), (2, "guy waves."), (3, "guy hand on hip."), (4, "girl sits.")]
    counts, target, changes = survey(lines, SUBJECTS)
    assert counts == {PROGRESSIVE: 1, PRESENT: 4} and target == PRESENT
    assert changes == [(0, "she sit.", "she sits.", True), (1, "girl is smiling.", "girl smiles.", True),
                       (3, "guy hand on hip.", "guy hands on hip.", False)]
    assert survey([(0, "girl sits."), (1, "girl is smiling.")], SUBJECTS)[1:] == (None, [])  # 同じ数なら案は無い


def test_survey_takes_the_form_to_unify_to_when_given():
    # 同じ数のときは、画面でどちらにするか聞いて、選んだ形を渡す
    lines = [(0, "girl sits."), (1, "girl is smiling.")]
    assert survey(lines, SUBJECTS, PRESENT) == ({PROGRESSIVE: 1, PRESENT: 1}, PRESENT,
                                                [(1, "girl is smiling.", "girl smiles.", True)])
    assert survey(lines, SUBJECTS, PROGRESSIVE)[2] == [(0, "girl sits.", "girl is sitting.", True)]
