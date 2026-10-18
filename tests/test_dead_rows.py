"""削除済み画像（元フォルダから消えた画像）の扱い"""
import pytest

from helpers import make_images


@pytest.fixture
def imgs(tmp_path):
    # 600px 超はサムネイルが作られる
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (800, 800), "b.png": (800, 800), "c.png": (100, 100)})


def names(tool):
    return tool.df["サムネイル"].tolist()


def test_deleted_image_becomes_dead_and_caption_moves(api, tool, imgs):
    api.load(imgs)
    api.add("t")
    api.set(api.row_index("a.png"), "t")
    api.save()
    (imgs / "a.png").rename(imgs.parent / "a.png.bak")

    api.load(imgs)
    assert tool.df.set_index("サムネイル").loc["a.png", "is_dead"]
    assert (tool.captions_dead_dir / "a.txt").read_text(encoding="utf-8") == "t"
    assert not (tool.captions_dir / "a.txt").exists()


def test_row_indexes_are_positions_after_remove_all_dead(api, tool, imgs):
    api.load(imgs)
    api.add("t")
    api.save()
    (imgs / "a.png").rename(imgs.parent / "a.png.bak")
    api.load(imgs)
    assert api.post("/remove_all_dead")["removed_count"] == 1

    rows = api.rows()
    assert [r["サムネイル"] for r in rows] == ["b.png", "c.png"]
    assert [r["index"] for r in rows] == [0, 1]

    # 画面の 2 行目（c.png）にチェック → c.png だけが変わる
    api.set(rows[1]["index"], "t")
    flags = tool.df.set_index("サムネイル")["t"].to_dict()
    assert flags == {"b.png": False, "c.png": True}


def test_remove_all_dead_does_not_resurrect_after_save(api, tool, imgs):
    api.load(imgs)
    api.add("t")
    api.set(api.row_index("b.png"), "t")
    api.save()
    (imgs / "a.png").rename(imgs.parent / "a.png.bak")
    api.load(imgs)
    api.post("/remove_all_dead")

    api.save()
    assert names(tool) == ["b.png", "c.png"]
    api.open_project("proj")
    assert names(tool) == ["b.png", "c.png"]
    assert tool.df.set_index("サムネイル").loc["b.png", "t"]


def test_restored_image_comes_back_alive(api, tool, imgs):
    api.load(imgs)
    api.add("t")
    api.set(api.row_index("a.png"), "t")
    api.save()
    (imgs / "a.png").rename(imgs.parent / "a.png.bak")
    api.load(imgs)
    (imgs.parent / "a.png.bak").rename(imgs / "a.png")

    api.load(imgs)
    row = tool.df.set_index("サムネイル").loc["a.png"]
    assert not row["is_dead"] and row["t"]
    assert (tool.captions_dir / "a.txt").read_text(encoding="utf-8") == "t"
