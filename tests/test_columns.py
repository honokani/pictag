"""カラム（タグ）とタグ辞書の操作"""
import pytest

from helpers import make_images


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100)})


def tag_columns(tool):
    return [c for c in tool.df.columns if c not in ("サムネイル", "is_dead")]


def captions(tool):
    return tool.caption_info_df["caption"].tolist()


def test_remove_from_table_persists_after_save(api, tool, imgs):
    api.load(imgs)
    api.add("A")
    api.add("B")
    assert api.post("/remove_column_from_table", {"column_name": "B"})["success"]

    api.save()
    assert tag_columns(tool) == ["A"]
    api.open_project("proj")
    assert tag_columns(tool) == ["A"]
    # 辞書には残る（column追加 の候補になる）
    assert "B" in captions(tool)


def test_new_project_starts_with_all_dictionary_captions(api, tool, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)}))
    api.add("A", kind="k1")
    api.add("B", kind="k2")
    api.save()

    api.load(make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)}))
    assert tag_columns(tool) == ["A", "B"]
    assert not tool.df[["A", "B"]].to_numpy().any()


def test_existing_project_does_not_gain_columns_added_elsewhere(api, tool, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)}))
    api.add("A")
    api.save()
    api.load(make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)}))
    api.add("Z")
    api.save()

    api.open_project("proj_a")
    assert tag_columns(tool) == ["A"]


def test_columns_in_dump_survive_missing_dictionary(api, tool, imgs, base_dir):
    api.load(imgs)
    api.add("A")
    api.add("B")
    api.set(api.row_index("a.png"), "B")
    api.save()
    (base_dir / "data_work" / "df_captioninfo.dump").rename(base_dir / "data_work" / "moved_away.dump")

    api.open_project("proj")
    assert tag_columns(tool) == ["A", "B"]
    assert tool.df.set_index("サムネイル").loc["a.png", "B"]
    info = tool.caption_info_df.set_index("caption")["kind"].to_dict()
    assert info == {"A": "undef", "B": "undef"}


def test_rename_column_keeps_values(api, tool, imgs):
    api.load(imgs)
    api.add("A")
    api.set(api.row_index("a.png"), "A")
    assert api.post("/rename_column", {"old_column": "A", "new_column": "A2", "kind": "k"})["success"]
    api.save()
    assert tag_columns(tool) == ["A2"]
    assert tool.df.set_index("サムネイル").loc["a.png", "A2"]


def test_rename_column_to_existing_column_is_rejected(api, tool, client, imgs):
    api.load(imgs)
    api.add("A")
    api.add("C")
    res = api.post("/rename_column", {"old_column": "C", "new_column": "A", "kind": "k"})
    assert res["success"] is False
    assert res.get("message")
    assert tag_columns(tool) == ["A", "C"]
    assert client.get("/get_table_data").status_code == 200


def test_rename_column_to_dictionary_caption_is_rejected(api, tool, imgs):
    api.load(imgs)
    api.add("X")
    api.post("/remove_column_from_table", {"column_name": "X"})
    api.add("C")
    res = api.post("/rename_column", {"old_column": "C", "new_column": "X", "kind": "k"})
    assert res["success"] is False
    assert captions(tool).count("X") == 1


def test_rename_both_to_existing_column_is_rejected(api, tool, imgs):
    api.load(imgs)
    api.add("A", kind="k1")
    api.add("C", kind="k1")
    res = api.post("/rename_both", {"old_kind": "k1", "new_kind": "k2", "old_column": "C", "new_column": "A"})
    assert res["success"] is False
    assert tag_columns(tool) == ["A", "C"]


def test_readd_dictionary_caption_with_same_kind(api, tool, imgs):
    api.load(imgs)
    api.add("X", kind="kA")
    api.post("/remove_column_from_table", {"column_name": "X"})
    assert api.add("X", kind="kA")["success"]
    assert tag_columns(tool) == ["X"]
    assert captions(tool).count("X") == 1


def test_add_existing_caption_with_other_kind_is_rejected(api, tool, imgs):
    api.load(imgs)
    api.add("X", kind="kA")
    api.post("/remove_column_from_table", {"column_name": "X"})
    res = api.add("X", kind="kB")
    assert res["success"] is False
    assert "kA" in res["error"]
    assert tag_columns(tool) == []
    assert tool.caption_info_df.to_dict("records") == [{"caption": "X", "kind": "kA"}]


@pytest.mark.parametrize("column", ["new_column", "index", "サムネイル", "is_dead"])
def test_reserved_column_names_are_rejected(api, tool, imgs, column):
    api.load(imgs)
    assert api.add(column)["success"] is False
    assert column not in captions(tool)


def test_reserved_kind_name_is_rejected(api, tool, imgs):
    api.load(imgs)
    assert api.add("A", kind="new_kind")["success"] is False
    api.add("A", kind="k")
    assert api.post("/rename_kind", {"old_kind": "k", "new_kind": "new_kind"})["success"] is False
    assert api.post("/rename_column", {"old_column": "A", "new_column": "new_column", "kind": "k"})["success"] is False
    assert api.post("/rename_both", {"old_kind": "k", "new_kind": "new_kind", "old_column": "A", "new_column": "A"})["success"] is False
    assert tool.caption_info_df.to_dict("records") == [{"caption": "A", "kind": "k"}]


def test_add_column_needs_loaded_project(api, tool):
    assert api.add("A")["success"] is False
    assert captions(tool) == []


def test_add_columns_on_project_without_images(api, tool, tmp_path):
    empty = tmp_path / "imgs" / "empty"
    empty.mkdir(parents=True)
    api.load(empty)
    api.add("A")
    api.add("B")
    assert list(tool.df.columns) == ["サムネイル", "is_dead", "A", "B"]
