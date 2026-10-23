"""action の文の動詞の形をそろえる API（/verb_forms で案を出し、/apply_verb_forms で選んだものを入れる）"""
import pytest

from helpers import make_images


@pytest.fixture
def proj(api, tmp_path):
    """r0〜r3 の 4 枚（r3 は削除済み）。sit は is doing 1・does 2、smile は is doing 2・does 1、hand は does 1（s が無い）"""
    imgs = make_images(tmp_path / "imgs" / "proj", {f"r{i}.png": (100, 100) for i in range(4)})
    api.load(imgs)
    for i, text in enumerate(["girl sits.\nguy smiles.", "she sit.\ngirl is smiling.",
                              "guy is sitting.\nguy hand on hip.\ngirl is smiling.", "girl is sitting.\nguy is sitting."]):
        api.write(api.row_index(f"r{i}.png"), text, section="action")
    api.save()
    (imgs / "r3.png").rename(imgs.parent / "r3.png.bak")
    api.load(imgs)
    return imgs


def test_verb_forms_suggests_changes_to_the_majority_form_of_each_verb(api, proj):
    res = api.post("/verb_forms")
    assert res["success"], res
    assert res["counts"] == {"progressive": 3, "present": 4}  # 削除済みの r3 は数えない
    assert res["verbs"] == [{"verb": "hand", "progressive": 0, "present": 1, "target": "present"},
                            {"verb": "sit", "progressive": 1, "present": 2, "target": "present"},
                            {"verb": "smile", "progressive": 2, "present": 1, "target": "progressive"}]
    rows = [api.row_index(f"r{i}.png") for i in range(3)]
    assert res["changes"] == [
        {"index": rows[0], "name": "r0.png", "before": "guy smiles.", "after": "guy is smiling.", "sure": True,
         "verbs": ["smile"]},
        {"index": rows[1], "name": "r1.png", "before": "she sit.", "after": "she sits.", "sure": True, "verbs": ["sit"]},
        {"index": rows[2], "name": "r2.png", "before": "guy is sitting.", "after": "guy sits.", "sure": True,
         "verbs": ["sit"]},
        {"index": rows[2], "name": "r2.png", "before": "guy hand on hip.", "after": "guy hands on hip.", "sure": False,
         "verbs": ["hand"]}]


def test_verb_forms_on_a_tie_suggests_nothing_until_a_form_is_chosen(api, proj):
    # 同じ数の動詞があれば案は出さない（画面がどちらにするか聞く）。形を渡せば、同じ数の動詞をその形に
    api.write(api.row_index("r0.png"), "girl sits.", section="action")
    api.write(api.row_index("r1.png"), "girl is sitting.\ngirl smiles.\nguy smiles.", section="action")
    api.write(api.row_index("r2.png"), "", section="action")
    res = api.post("/verb_forms")
    assert res["verbs"] == [{"verb": "sit", "progressive": 1, "present": 1, "target": None}] and res["changes"] == []
    res = api.post("/verb_forms", {"target": "present"})
    assert res["success"] and res["verbs"] == [{"verb": "sit", "progressive": 1, "present": 1, "target": "present"}]
    assert [(c["before"], c["after"]) for c in res["changes"]] == [("girl is sitting.", "girl sits.")]


def test_verb_forms_rejects_an_unknown_form(api, proj):
    assert api.post("/verb_forms", {"target": "past"})["success"] is False


def test_apply_verb_forms_writes_only_the_picked_sentences_that_are_still_there(api, proj):
    rows = [api.row_index(f"r{i}.png") for i in range(2)]
    edited = {r["index"]: r["edited_at"] for r in api.rows()}
    res = api.post("/apply_verb_forms", {"changes": [
        {"index": rows[1], "before": "she sit.", "after": "she sits."},
        {"index": rows[0], "before": "girl is laughing.", "after": "girl laughs."}]})  # もう無い文は入れない
    assert res == {"success": True, "changed": 1}
    texts = {r["index"]: r["texts"]["action"] for r in api.rows()}
    assert texts[rows[1]] == "she sits.\ngirl is smiling." and texts[rows[0]] == "girl sits.\nguy smiles."
    assert {r["index"]: r["edited_at"] for r in api.rows()} == edited  # まとめて直すのは、書き換えた時刻（📍）に数えない


@pytest.mark.parametrize("changes", [None, "x", [{"index": 0, "before": "a"}], [{"index": 0, "before": "a", "after": "b\nc"}]])
def test_apply_verb_forms_rejects_a_bad_request(api, proj, changes):
    assert api.post("/apply_verb_forms", {"changes": changes})["success"] is False
