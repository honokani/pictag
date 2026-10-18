"""旧版（pandas 2.0.3 / numpy 1.24.3）で保存した dump との互換（fixture は tests/fixtures/make_legacy_dumps.py で生成）"""
import pytest

from helpers import copy_legacy_fixture, make_images


def setup_legacy(kind, base_dir, tmp_path, images):
    copy_legacy_fixture(kind, base_dir)
    imgs = make_images(tmp_path / "imgs" / "proj", images)
    (base_dir / "data_out" / "proj" / "tgt_path.txt").write_text(str(imgs), encoding="utf-8")
    return imgs


def caption(tool, name, dead=False):
    return ((tool.captions_dead_dir if dead else tool.captions_dir) / name).read_text(encoding="utf-8")


def test_legacy_dump_loads_and_writes_same_captions(api, tool, base_dir, tmp_path):
    # 旧版保存時点: a, b, big が生存、c は削除済み
    setup_legacy("normal", base_dir, tmp_path, {"a.png": (100, 100), "b.png": (100, 100), "big.png": (800, 800)})
    assert api.open_project("proj")["success"]

    df = tool.df.set_index("サムネイル")
    assert df["is_dead"].to_dict() == {"a.png": False, "b.png": False, "big.png": False, "c.png": True}
    assert df.loc["a.png", ["1girl", "solo", "smile", "outdoors"]].tolist() == [True, True, False, False]
    assert tool.caption_info_df.set_index("caption")["kind"].to_dict() == {
        "1girl": "people", "solo": "people", "smile": "expression", "outdoors": "background"}

    api.save()
    assert caption(tool, "a.txt") == "1girl,solo"
    assert caption(tool, "b.txt") == "smile"
    assert caption(tool, "big.txt") == "1girl,outdoors"
    assert caption(tool, "c.txt", dead=True) == ""


def test_corrupted_legacy_dump_opens(api, tool, base_dir, tmp_path):
    # 旧版のバグで サムネイル=NaN の幽霊行が入った dump
    setup_legacy("corrupted", base_dir, tmp_path, {"b.png": (100, 100), "big.png": (800, 800)})
    res = api.open_project("proj")
    assert res["success"], res

    assert tool.df["サムネイル"].tolist() == ["b.png", "big.png"]
    assert tool.df.set_index("サムネイル").loc["b.png", "smile"]
    assert api.save()["success"]
    assert api.open_project("proj")["success"]
