"""拡張子だけ違う画像（a.jpg と a.png）: 読み込むとき、名前順で先の1つのほかの名前に拡張子を足す
（キャプション・hint・Qwen の答えは拡張子を除いた名前なので、重ならないように）"""
from pathlib import Path

import pytest

import app as pictag
from helpers import caption_of, make_images


@pytest.fixture
def imgs(tmp_path):
    # a.png は長辺 600px より大きい（サムネイルを作る）
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (800, 800), "b.png": (100, 100)})


@pytest.mark.parametrize("alive, taken, renamed", [
    ({"a.jpg", "a.png", "b.png"}, set(), {"a.png": "a_png.png"}),
    ({"A.png", "a.jpg"}, set(), {"a.jpg": "a_jpg.jpg"}),  # 大文字小文字だけの違いも同じ名前（名前順で先の A.png を残す）
    ({"a.jpg", "a.png", "a.webp"}, set(), {"a.png": "a_png.png", "a.webp": "a_webp.webp"}),
    ({"a.jpg", "a.png", "a_png.gif"}, set(), {"a.png": "a_png_2.png"}),  # 足した名前も、ほかの画像と重ねない
    ({"a.jpg", "a.png"}, {"a_png.png"}, {"a.png": "a_png_2.png"}),  # 表やサムネイルにだけ残る名前も避ける
    ({"a.jpg", "b.png"}, set(), {}),
])
def test_separated_names(alive, taken, renamed):
    assert pictag.separated_names(alive, taken) == renamed


def test_loading_renames_images_that_differ_only_in_extension(api, tool, client, base_dir, imgs):
    # a.png に入力・サムネイル・hint・Qwen の答えがあるところへ a.jpg が増えた → 名前順で先の a.jpg を残し、a.png を a_png.png に
    api.load(imgs)
    api.write(api.row_index("a.png"), "t")
    api.save()
    client.get("/thumbnail/a.png")
    (imgs / "a.txt").write_text("hint of a", encoding="utf-8")
    qwen = base_dir / "data_work" / "proj" / "qwen"
    qwen.mkdir()
    (qwen / "a.txt").write_text("answer", encoding="utf-8")
    make_images(imgs, {"a.jpg": (100, 100)})

    res = api.load(imgs)
    assert res["renamed"] == [["a.png", "a_png.png"]] and res["rename_failed"] == []
    assert sorted(p.name for p in imgs.iterdir()) == ["a.jpg", "a.txt", "a_png.png", "a_png.txt", "b.png"]
    assert tool.hints == {"a.jpg": "hint of a", "a_png.png": "hint of a"}  # hint は新しい名前にも写す
    assert sorted(p.name for p in qwen.iterdir()) == ["a.txt"]  # Qwen の答えはどちらの画像のものか分からないので写さない
    assert "a_png.png" not in tool.qwen_hints
    work = base_dir / "data_work" / "proj"
    assert (work / "t_a_png.png").is_file() and not (work / "t_a.png").exists()
    captions = base_dir / "data_out" / "proj" / "captions"  # すぐ保存する
    assert (captions / "a_png.caption").read_text(encoding="utf-8") == caption_of("t")

    assert api.load(imgs)["renamed"] == []  # 読み直しても、元の名前の行は削除済みにならない（保存してある）
    rows = tool.df.set_index("サムネイル")
    assert rows.index.tolist() == ["a.jpg", "a_png.png", "b.png"]
    assert rows.loc["a_png.png", "girl"] == "t" and not rows.loc["a_png.png", "is_dead"]


def test_saving_also_renames_images_added_meanwhile(api, tool, imgs):
    # 保存は読み直すので、開いている間に増えた a.jpg もそこで分ける
    api.load(imgs)
    make_images(imgs, {"a.jpg": (100, 100)})
    res = api.save()
    assert res["renamed"] == [["a.png", "a_png.png"]] and res["rename_failed"] == []
    assert tool.df["サムネイル"].tolist() == ["a.jpg", "a_png.png", "b.png"]


@pytest.mark.parametrize("busy", ["a.png", "t_a.png"])  # 画像 / サムネイル（画像は元の名前に戻す）
def test_an_image_that_cannot_be_renamed_keeps_its_name(api, tool, client, base_dir, imgs, monkeypatch, busy):
    api.load(imgs)
    client.get("/thumbnail/a.png")
    make_images(imgs, {"a.jpg": (100, 100)})
    rename = Path.rename

    def refuse(self, target):
        if self.name == busy:
            raise PermissionError("使用中です")
        return rename(self, target)

    monkeypatch.setattr(Path, "rename", refuse)
    res = api.load(imgs)
    assert res["success"] is True and res["renamed"] == []
    assert len(res["rename_failed"]) == 1 and res["rename_failed"][0].startswith("a.png: ")
    assert "使用中です" in res["rename_failed"][0]
    assert sorted(p.name for p in imgs.iterdir()) == ["a.jpg", "a.png", "b.png"]
    assert (base_dir / "data_work" / "proj" / "t_a.png").is_file()
    assert tool.df["サムネイル"].tolist() == ["a.jpg", "a.png", "b.png"]
