"""辞書の取得と保存（JSON・Krea2 形式のキャプション txt）"""
import json

import pytest

from helpers import make_images


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100)})


def test_get_dictionary(api, client, imgs):
    api.load(imgs)
    api.add("long", big="girl", mid="body", small="hair")
    api.add("girl walks a dog", big="action", mid="")
    assert client.get("/get_dictionary").get_json()["kinds"] == {
        "bigs": [{"name": "girl", "mids": ["body"], "lines": []},
                 {"name": "action", "mids": [], "lines": ["girl walks a dog"]}],
        "mids": [{"name": "body", "entries": [{"small": "hair", "value": "long"}]}],
    }


def test_save_writes_krea2_captions(api, tool, imgs):
    api.load(imgs)
    items = [("picture", "place", "", "classroom"), ("action", "", "", "girl walks a dog"),
             ("girl", "body", "hair", "long"), ("girl", "body", "hair", "black")]
    for big, mid, small, value in items:
        api.add(value, big=big, mid=mid, small=small)
    row = api.row_index("a.png")
    for it in items:
        api.set(row, it)
    api.save()

    # 改行は LF（Windows でも CRLF にしない）
    assert (tool.captions_dir / "a.txt").read_bytes() == (
        b"picture:\n  - place: classroom\n\naction:\n  - girl walks a dog\n\ngirl:\n  - body: long black hair")
    assert (tool.captions_dir / "b.txt").read_bytes() == b""


def test_save_writes_readable_json(api, tool, imgs, base_dir):
    api.load(imgs)
    api.add("A")
    api.set(api.row_index("a.png"), "A")
    api.save()

    table = json.loads((base_dir / "data_out" / "proj" / "table.json").read_text(encoding="utf-8"))
    assert table == {"columns": [["g", "m", "", "A"]],
                     "rows": [{"image": "a.png", "is_dead": False, "checked": [0]},
                              {"image": "b.png", "is_dead": False, "checked": []}]}
    kinds = json.loads((base_dir / "data_work" / "kinds.json").read_text(encoding="utf-8"))
    assert kinds == tool.kinds
