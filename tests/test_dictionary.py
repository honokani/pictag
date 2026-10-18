"""使用中の語句（辞書）と保存（JSON・Krea2 形式のキャプション txt）"""
import json

import pytest

from helpers import make_images


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100)})


def test_dictionary_lists_phrases_in_use_including_unsaved_edits(api, imgs):
    api.load(imgs)
    api.write(api.row_index("a.png"), "body: long hair\ngirl walks a dog")
    api.write(api.row_index("b.png"), "body: long hair")
    assert api.words() == {("girl", "body", "long hair"): 2, ("girl", "", "girl walks a dog"): 1}


def test_dictionary_includes_saved_projects(api, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)}))
    api.add_section("dog")
    api.write(0, "fur: brown", section="dog")
    api.save()

    api.load(make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)}))
    api.write(0, "looks: standing")
    assert api.words() == {("dog", "fur", "brown"): 1, ("girl", "looks", "standing"): 1}


def test_phrase_disappears_when_no_image_uses_it(api, imgs):
    api.load(imgs)
    api.write(0, "body: long hair")
    api.save()
    api.write(0, "")
    assert api.words() == {}
    api.save()
    assert api.words() == {}


def test_save_writes_krea2_captions_with_lf(api, tool, imgs):
    api.load(imgs)
    row = api.row_index("a.png")
    api.write(row, "place: classroom", section="picture")
    api.write(row, "girl walks a dog", section="action")
    api.write(row, "body: long hair, black hair")
    api.save()

    assert (tool.captions_dir / "a.txt").read_bytes() == (
        b"picture:\n  - place: classroom\n\naction:\n  - girl walks a dog\n\ngirl:\n  - body: long black hair")
    assert (tool.captions_dir / "b.txt").read_bytes() == b""


def test_save_writes_readable_json(api, imgs, base_dir):
    api.load(imgs)
    api.write(api.row_index("a.png"), "looks: standing")
    api.save()

    table = json.loads((base_dir / "data_out" / "proj" / "table.json").read_text(encoding="utf-8"))
    assert table == {"sections": ["picture", "action", "girl"],
                     "rows": [{"image": "a.png", "is_dead": False, "texts": {"girl": "looks: standing"}},
                              {"image": "b.png", "is_dead": False, "texts": {}}]}


def test_unreadable_table_is_not_opened(api, tool, imgs, base_dir):
    api.load(imgs)
    api.save()
    (base_dir / "data_out" / "proj" / "table.json").write_text("{broken", encoding="utf-8")
    other = make_images(imgs.parent / "other", {"z.png": (100, 100)})
    api.load(other)

    res = api.open_project("proj")
    assert res["success"] is False and res["message"]
    assert tool.image_dir == other.resolve()
    assert (base_dir / "data_out" / "proj" / "table.json").read_text(encoding="utf-8") == "{broken"
