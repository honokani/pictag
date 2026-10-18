"""プロジェクト（画像ディレクトリ）の読み込みと紐付け"""
from pathlib import Path

import pytest

import app as pictag
from helpers import caption_of, make_images


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100)})


def saved_with_tag(api, imgs):
    api.load(imgs)
    api.write(api.row_index("a.png"), "t")
    api.save()


def tgt_path(base_dir, project="proj"):
    return (base_dir / "data_out" / project / "tgt_path.txt").read_text(encoding="utf-8")


def test_default_base_dir_is_app_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # 起動ディレクトリに依存しない
    assert pictag.CaptionTool().base_dir.resolve() == Path(pictag.__file__).resolve().parent


def test_project_list_shows_saved_projects(api, client, imgs):
    api.load(imgs)
    projects = client.get("/get_existing_projects").get_json()["projects"]
    assert projects == [{"name": "proj", "image_path": str(imgs.resolve())}]


def test_load_nonexistent_directory_fails_without_side_effects(api, tool, base_dir, tmp_path):
    res = api.load(tmp_path / "nope" / "typo_dir")
    assert res["success"] is False
    assert not (base_dir / "data_out" / "typo_dir").exists()
    assert tool.image_dir is None


def test_failed_load_keeps_current_project(api, tool, imgs, tmp_path):
    api.load(imgs)
    api.load(tmp_path / "nope" / "typo_dir")
    assert tool.image_dir == imgs.resolve()
    assert tool.df["サムネイル"].tolist() == ["a.png"]


def test_open_project_with_missing_image_dir_keeps_captions(api, tool, imgs, base_dir):
    saved_with_tag(api, imgs)
    imgs.rename(imgs.parent / "unplugged")

    res = api.open_project("proj")
    assert res["success"] is False
    assert (base_dir / "data_out" / "proj" / "captions" / "a.caption").read_text(encoding="utf-8") == caption_of("t")
    assert list((base_dir / "data_out" / "proj" / "captions_dead").iterdir()) == []


def test_load_directory_accepts_quoted_path(api, tool, imgs):
    assert api.load(f'"{imgs}"')["success"]
    assert tool.image_dir == imgs.resolve()
    assert tool.df["サムネイル"].tolist() == ["a.png"]


def test_registered_path_is_absolute(api, base_dir, imgs, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert api.load(Path("imgs") / "proj")["success"]
    assert tgt_path(base_dir) == str(imgs.resolve())


def test_same_name_other_dir_is_rejected_while_registered_dir_exists(api, tool, base_dir, imgs, tmp_path):
    saved_with_tag(api, imgs)
    other = make_images(tmp_path / "other" / "proj", {"z.png": (100, 100)})

    res = api.load(other)
    assert res["success"] is False
    assert str(imgs.resolve()) in res["message"]
    assert tgt_path(base_dir) == str(imgs.resolve())
    assert (base_dir / "data_out" / "proj" / "captions" / "a.caption").read_text(encoding="utf-8") == caption_of("t")


def test_moved_dir_updates_registration(api, tool, base_dir, imgs, tmp_path):
    saved_with_tag(api, imgs)
    moved = tmp_path / "moved"
    moved.mkdir()
    imgs.rename(moved / "proj")

    assert api.load(moved / "proj")["success"]
    assert tgt_path(base_dir) == str((moved / "proj").resolve())
    row = tool.df.set_index("サムネイル").loc["a.png"]
    assert not row["is_dead"] and row["girl"] == "t"


def test_open_project_rejects_path_traversal(api, base_dir, imgs):
    evil = base_dir / "evil"
    evil.mkdir()
    (evil / "tgt_path.txt").write_text(str(imgs), encoding="utf-8")
    assert api.open_project("../evil")["success"] is False
