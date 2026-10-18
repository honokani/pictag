"""SDXL 版（旧版）のプロジェクトは開かない（fixture は tests/fixtures/make_legacy_dumps.py で生成）"""
from helpers import copy_legacy_fixture, make_images


def snapshot(directory):
    return {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def test_sdxl_project_is_refused_and_left_untouched(api, tool, base_dir, tmp_path):
    copy_legacy_fixture("normal", base_dir)
    imgs = make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100)})
    (base_dir / "data_out" / "proj" / "tgt_path.txt").write_text(str(imgs), encoding="utf-8")
    before = snapshot(base_dir)

    res = api.open_project("proj")
    assert res["success"] is False and "SDXL" in res["message"]
    res = api.load(imgs)
    assert res["success"] is False and "SDXL" in res["message"]

    assert tool.image_dir is None
    assert snapshot(base_dir) == before
