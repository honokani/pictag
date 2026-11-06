"""削除済み画像（元フォルダから消えた画像）の扱い"""
import pytest

import app as pictag
from helpers import caption_of, make_images


@pytest.fixture
def imgs(tmp_path):
    # 600px 超はサムネイルが作られる
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (800, 800), "b.png": (800, 800), "c.png": (100, 100)})


def names(tool):
    return tool.df["サムネイル"].tolist()


def girl(tool):
    return tool.df.set_index("サムネイル")["girl"].to_dict()


def test_deleted_image_becomes_dead_and_caption_moves(api, tool, imgs):
    api.load(imgs)
    api.write(api.row_index("a.png"), "t")
    api.save()
    (imgs / "a.png").rename(imgs.parent / "a.png.bak")

    api.load(imgs)
    assert tool.df.set_index("サムネイル").loc["a.png", "is_dead"]
    assert (tool.captions_dead_dir / "a.caption").read_text(encoding="utf-8") == caption_of("t")
    assert not (tool.captions_dir / "a.caption").exists()


def test_row_indexes_are_positions_after_remove_all_dead(api, tool, imgs):
    api.load(imgs)
    api.save()
    (imgs / "a.png").rename(imgs.parent / "a.png.bak")
    api.load(imgs)
    assert api.post("/remove_all_dead")["removed_count"] == 1

    rows = api.rows()
    assert [r["サムネイル"] for r in rows] == ["b.png", "c.png"]
    assert [r["index"] for r in rows] == [0, 1]

    # 画面の 2 行目（c.png）に入力 → c.png だけが変わる
    api.write(rows[1]["index"], "t")
    assert girl(tool) == {"b.png": "", "c.png": "t"}


def test_remove_all_dead_does_not_resurrect_after_save(api, tool, imgs):
    api.load(imgs)
    api.write(api.row_index("b.png"), "t")
    api.save()
    (imgs / "a.png").rename(imgs.parent / "a.png.bak")
    api.load(imgs)
    api.post("/remove_all_dead")

    api.save()
    assert names(tool) == ["b.png", "c.png"]
    api.open_project("proj")
    assert names(tool) == ["b.png", "c.png"]
    assert girl(tool)["b.png"] == "t"


def test_restored_image_comes_back_alive(api, tool, imgs):
    api.load(imgs)
    api.write(api.row_index("a.png"), "t")
    api.save()
    (imgs / "a.png").rename(imgs.parent / "a.png.bak")
    api.load(imgs)
    (imgs.parent / "a.png.bak").rename(imgs / "a.png")

    api.load(imgs)
    row = tool.df.set_index("サムネイル").loc["a.png"]
    assert not row["is_dead"] and row["girl"] == "t"
    assert (tool.captions_dir / "a.caption").read_text(encoding="utf-8") == caption_of("t")


def dead(tool):
    return tool.df.set_index("サムネイル")["is_dead"].map(bool).to_dict()


def test_delete_images_sends_them_and_their_hints_to_the_trash_and_makes_the_rows_dead(api, tool, imgs, trash):
    # 画像削除: 選んだ行の画像（と同じ名前の hint の txt）をごみ箱へ移し、その行を削除済みにする（入力は残し、キャプションは
    # captions_dead へ）。サムネイルは data_work に残す（長辺 600px 以下の画像は元画像の写し）ので、削除済みの行にも画像が出て、
    # 読み込み直しても削除済みの行のまま
    (imgs / "a.txt").write_text("hint", encoding="utf-8")
    api.load(imgs)
    api.write(api.row_index("a.png"), "t")
    api.save()
    res = api.post("/delete_images", {"names": ["a.png", "c.png"]})
    assert res["success"] and res["deleted"] == ["a.png", "c.png"]
    assert res["message"] == "2 枚の画像をごみ箱へ移しました（行は削除済み。入力は残ります）"
    assert sorted(p.name for p in trash.iterdir()) == ["a.png", "a.txt", "c.png"]
    assert sorted(p.name for p in imgs.iterdir()) == ["b.png"]
    assert dead(tool) == {"a.png": True, "b.png": False, "c.png": True}
    assert girl(tool)["a.png"] == "t"
    assert (tool.captions_dead_dir / "a.caption").read_text(encoding="utf-8") == caption_of("t")
    assert not (tool.captions_dir / "a.caption").exists()
    assert tool.thumbnail_file("a.png").exists() and tool.thumbnail_file("c.png").exists()

    api.load(imgs)
    assert dead(tool) == {"a.png": True, "b.png": False, "c.png": True}
    assert girl(tool)["a.png"] == "t"


def test_delete_images_skips_dead_rows_and_refuses_what_is_not_a_row(api, tool, imgs):
    # もう削除済みの行は飛ばす（選んだ行がどれも削除済みなら、何もしない）。表に無い画像・空の指定は断る
    api.load(imgs)
    assert api.post("/delete_images", {"names": ["a.png"]})["success"]
    res = api.post("/delete_images", {"names": ["a.png", "b.png"]})
    assert res["success"] and res["deleted"] == ["b.png"] and res["skipped"] == ["a.png"]
    assert res["message"] == "1 枚の画像をごみ箱へ移しました（行は削除済み。入力は残ります）。削除済みの 1 行は飛ばしました"
    res = api.post("/delete_images", {"names": ["a.png"]})
    assert not res["success"] and res["message"] == "選んだ行は、どれも削除済みです"
    for names_ in ([], ["x.png"], "c.png", [1]):
        assert not api.post("/delete_images", {"names": names_})["success"], names_
    assert sorted(p.name for p in imgs.iterdir()) == ["c.png"]


def test_an_image_that_cannot_go_to_the_trash_stays_alive(api, tool, imgs, monkeypatch):
    # ごみ箱へ移せなかった画像の行は、生きたまま（理由を知らせる）
    api.load(imgs)

    def refuse(path):
        raise OSError("使用中です")

    monkeypatch.setattr(pictag, "trash", refuse)
    res = api.post("/delete_images", {"names": ["a.png"]})
    assert not res["success"] and res["message"] == "ごみ箱へ移せませんでした: a.png（使用中です）"
    assert dead(tool) == {"a.png": False, "b.png": False, "c.png": False}
    assert (imgs / "a.png").exists()
