"""action の文の動詞の形をそろえる API（/verb_forms で案を出し、/apply_verb_forms で選んだものを入れる）"""
import pytest

from helpers import make_images


@pytest.fixture
def proj(api, tmp_path):
    """r0〜r3 の 4 枚。action に is doing の形 1 文と、does の形 3 文（r3 は削除済み）"""
    imgs = make_images(tmp_path / "imgs" / "proj", {f"r{i}.png": (100, 100) for i in range(4)})
    api.load(imgs)
    for i, text in enumerate(["she sit.\nguy waves.", "girl is smiling.", "guy hand on hip.", "girl is dancing."]):
        api.write(api.row_index(f"r{i}.png"), text, section="action")
    api.save()
    (imgs / "r3.png").rename(imgs.parent / "r3.png.bak")
    api.load(imgs)
    return imgs


def test_verb_forms_suggests_changes_to_the_majority_form(api, proj):
    res = api.post("/verb_forms")
    assert res["success"], res
    assert res["counts"] == {"progressive": 1, "present": 3} and res["target"] == "present"  # 削除済みの r3 は数えない
    rows = [api.row_index(f"r{i}.png") for i in range(3)]
    assert res["changes"] == [
        {"index": rows[0], "name": "r0.png", "before": "she sit.", "after": "she sits.", "sure": True},
        {"index": rows[1], "name": "r1.png", "before": "girl is smiling.", "after": "girl smiles.", "sure": True},
        {"index": rows[2], "name": "r2.png", "before": "guy hand on hip.", "after": "guy hands on hip.", "sure": False}]


def test_apply_verb_forms_writes_only_the_picked_sentences_that_are_still_there(api, proj):
    rows = [api.row_index(f"r{i}.png") for i in range(2)]
    edited = {r["index"]: r["edited_at"] for r in api.rows()}
    res = api.post("/apply_verb_forms", {"changes": [
        {"index": rows[0], "before": "she sit.", "after": "she sits."},
        {"index": rows[1], "before": "girl is laughing.", "after": "girl laughs."}]})  # もう無い文は入れない
    assert res == {"success": True, "changed": 1}
    texts = {r["index"]: r["texts"]["action"] for r in api.rows()}
    assert texts[rows[0]] == "she sits.\nguy waves." and texts[rows[1]] == "girl is smiling."
    assert {r["index"]: r["edited_at"] for r in api.rows()} == edited  # まとめて直すのは、書き換えた時刻（📍）に数えない


@pytest.mark.parametrize("changes", [None, "x", [{"index": 0, "before": "a"}], [{"index": 0, "before": "a", "after": "b\nc"}]])
def test_apply_verb_forms_rejects_a_bad_request(api, proj, changes):
    assert api.post("/apply_verb_forms", {"changes": changes})["success"] is False
