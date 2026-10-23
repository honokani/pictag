"""action の文の動詞の形（進行形 is doing / 現在形 does）を動詞ごとに数え、それぞれ多い方にそろえる"""
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


@pytest.mark.parametrize("line, targets, expected", [
    ("girl is sitting and smiling.", {"sit": PRESENT}, "girl sits and is smiling."),  # 後ろの smiling は is doing のまま（is を足す）
    ("girl is sitting and smiling.", {"smile": PRESENT}, "girl is sitting and smiles."),
    ("girl sits and smiles.", {"sit": PROGRESSIVE}, "girl is sitting and smiles."),
    ("girl sits and smiles.", {"smile": PROGRESSIVE}, "girl sits and is smiling."),
    ("girl sits and smiles and waves.", {"smile": PROGRESSIVE, "wave": PROGRESSIVE},
     "girl sits and is smiling and waving."),  # 続く -ing は前の is を分け合う
    ("girl is sitting and also smiling.", {"sit": PRESENT}, "girl sits and is also smiling."),
    ("girl and guy are hugging and kissing.", {"hug": PRESENT}, "girl and guy hug and are kissing."),
])
def test_convert_changes_each_verb_to_its_own_form(line, targets, expected):
    # 形は動詞ごと（{原形: 形}。無い動詞は今の形のまま）
    assert convert(line, SUBJECTS, targets.get) == (expected, True)


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


def test_survey_unifies_each_verb_to_its_own_majority():
    # 動詞をまたいで合わせない: say は is doing 3・does 2 → is doing、stand は is doing 1・does 4 → does
    lines = [(0, "girl says hello."), (1, "she say hi."), (2, "girl is saying hello."), (3, "guy is saying hi."),
             (4, "she is saying bye."), (5, "girl stands."), (6, "guy stands."), (7, "she stands."), (8, "they stand."),
             (9, "girl is standing.")]
    counts, targets, changes = survey(lines, SUBJECTS)
    assert counts == {"say": {PROGRESSIVE: 3, PRESENT: 2}, "stand": {PROGRESSIVE: 1, PRESENT: 4}}
    assert targets == {"say": PROGRESSIVE, "stand": PRESENT}
    assert changes == [(0, "girl says hello.", "girl is saying hello.", True, ("say",)),
                       (1, "she say hi.", "she is saying hi.", True, ("say",)),
                       (9, "girl is standing.", "girl stands.", True, ("stand",))]


def test_survey_adds_the_missing_s_even_to_a_verb_with_one_form():
    assert survey([(0, "she sit."), (1, "girl sits.")], SUBJECTS)[2] == [(0, "she sit.", "she sits.", True, ("sit",))]


def test_survey_counts_each_verb_joined_by_and():
    # girl is sitting and smiling. は sit と smile の is doing が1つずつ。sit だけ does にする
    lines = [(0, "girl is sitting and smiling."), (1, "girl sits."), (2, "guy sits."), (3, "girl is smiling.")]
    counts, targets, changes = survey(lines, SUBJECTS)
    assert counts == {"sit": {PROGRESSIVE: 1, PRESENT: 2}, "smile": {PROGRESSIVE: 2, PRESENT: 0}}
    assert changes == [(0, "girl is sitting and smiling.", "girl sits and is smiling.", True, ("sit",))]


def test_survey_counts_a_passive_sentence_as_its_verb():
    # is being carried は carry の is doing（does にするなら is carried）
    lines = [(0, "girl is being carried by guy."), (1, "guy carries girl."), (2, "guy carries bag.")]
    counts, targets, changes = survey(lines, SUBJECTS)
    assert counts == {"carry": {PROGRESSIVE: 1, PRESENT: 2}}
    assert changes == [(0, "girl is being carried by guy.", "girl is carried by guy.", True, ("carry",))]


def test_survey_on_a_tie_suggests_nothing_until_a_form_is_chosen():
    # 同じ数の動詞（sit）があれば、画面でどちらにするか聞くまで案は無い。選んだ形は、同じ数の動詞だけに使う
    lines = [(0, "girl sits."), (1, "girl is sitting."), (2, "girl smiles."), (3, "she smiles."), (4, "guy is smiling.")]
    assert survey(lines, SUBJECTS)[1:] == ({"sit": None, "smile": PRESENT}, [])
    counts, targets, changes = survey(lines, SUBJECTS, PROGRESSIVE)
    assert targets == {"sit": PROGRESSIVE, "smile": PRESENT}
    assert changes == [(0, "girl sits.", "girl is sitting.", True, ("sit",)),
                       (4, "guy is smiling.", "guy smiles.", True, ("smile",))]
