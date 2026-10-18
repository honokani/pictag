"""表の列（大kind × 中kind × 小kind × 値）の操作"""
import pytest

from helpers import col, item, make_images, target
from kinds import column_key, dictionary_columns, parse_key

GIRL_LONG = ("girl", "body", "hair", "long")
GIRL_HANDS = ("girl", "body", "", "bare hands")
GUY_LONG = ("guy", "body", "hair", "long")
GUY_HANDS = ("guy", "body", "", "bare hands")
DOG_BROWN = ("dog", "fur", "", "brown")


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100)})


def table_items(tool):
    return [parse_key(c) for c in tool.df.columns if c not in ("サムネイル", "is_dead")]


def add(api, it, default=False):
    big, mid, small, value = it
    return api.add(value, big=big, mid=mid, small=small, default=default)


def test_new_project_starts_with_all_dictionary_columns(api, tool, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)}))
    add(api, GIRL_LONG)
    add(api, DOG_BROWN)
    api.save()

    api.load(make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)}))
    assert table_items(tool) == [GIRL_LONG, DOG_BROWN]
    assert not tool.df[[column_key(GIRL_LONG), column_key(DOG_BROWN)]].to_numpy().any()


def test_existing_project_does_not_gain_columns_added_elsewhere(api, tool, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)}))
    api.add("A")
    api.save()
    api.load(make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)}))
    api.add("Z")
    api.save()

    api.open_project("proj_a")
    assert table_items(tool) == [item("A")]


def test_new_value_of_a_shared_mid_is_added_for_every_big_using_it(api, tool, imgs):
    api.load(imgs)
    add(api, GIRL_LONG)
    add(api, GUY_LONG)  # 辞書にある値 → guy の列だけ増える
    add(api, GIRL_HANDS)  # 新しい値 → body を使う girl と guy の両方に増える
    assert table_items(tool) == [GIRL_LONG, GIRL_HANDS, GUY_LONG, GUY_HANDS]


def test_columns_are_kept_in_dictionary_order(api, tool, imgs):
    api.load(imgs)
    add(api, GIRL_LONG)
    add(api, DOG_BROWN)
    add(api, GIRL_HANDS)
    assert table_items(tool) == [GIRL_LONG, GIRL_HANDS, DOG_BROWN]


def test_adding_an_existing_mid_to_another_big_brings_all_its_values(api, tool, imgs):
    api.load(imgs)
    api.add("full body shot", big="girl", mid="looks")
    api.add("standing", big="girl", mid="looks")
    assert api.add("", big="dog", mid="looks")["success"]
    assert table_items(tool)[2:] == [("dog", "looks", "", "full body shot"), ("dog", "looks", "", "standing")]


def test_default_value_fills_new_columns(api, tool, imgs):
    api.load(imgs)
    api.add("A", default=True)
    assert tool.df[col("A")].tolist() == [True, True]


def test_value_already_in_table_is_rejected(api, tool, imgs):
    api.load(imgs)
    api.add("A")
    res = api.add("A")
    assert res["success"] is False and res["error"]
    assert table_items(tool) == [item("A")]


@pytest.mark.parametrize("payload", [
    {"big": "", "mid": "m", "value": "A"},
    {"big": "g", "mid": "m", "value": "two\nlines"},
    {"big": "g", "mid": "", "small": "hair", "value": "A"},
    {"big": "g", "mid": "new mid", "value": ""},
])
def test_invalid_add_is_rejected_with_reason(api, tool, imgs, payload):
    api.load(imgs)
    res = api.post("/add_value", payload)
    assert res["success"] is False and res["error"]
    assert table_items(tool) == []


def test_add_needs_loaded_project(api, tool):
    assert api.add("A")["success"] is False
    assert dictionary_columns(tool.kinds) == []


def test_add_on_project_without_images(api, tool, tmp_path):
    empty = tmp_path / "imgs" / "empty"
    empty.mkdir(parents=True)
    api.load(empty)
    api.add("A")
    api.add("B")
    assert table_items(tool) == [item("A"), item("B")]


def test_remove_from_table_persists_after_save_and_stays_in_dictionary(api, tool, imgs):
    api.load(imgs)
    api.add("A")
    api.add("B")
    assert api.post("/remove_from_table", {"level": "value", **target(item("B"))})["success"]

    api.save()
    api.open_project("proj")
    assert table_items(tool) == [item("A")]
    assert item("B") in dictionary_columns(tool.kinds)


def test_remove_a_whole_big_from_table(api, tool, imgs):
    api.load(imgs)
    add(api, GIRL_LONG)
    add(api, DOG_BROWN)
    assert api.post("/remove_from_table", {"level": "big", "big": "dog"})["success"]
    assert table_items(tool) == [GIRL_LONG]


def test_rename_value_keeps_checks_for_every_big(api, tool, imgs):
    api.load(imgs)
    api.add("lng", big="girl", mid="body", small="hair")
    api.add("lng", big="guy", mid="body", small="hair")
    api.set(api.row_index("a.png"), ("guy", "body", "hair", "lng"))

    res = api.post("/rename", {"level": "value", **target(("girl", "body", "hair", "lng")), "new_name": "long"})
    assert res["success"], res
    assert table_items(tool) == [GIRL_LONG, GUY_LONG]
    assert tool.df.set_index("サムネイル").loc["a.png", column_key(GUY_LONG)]


def test_rename_to_an_existing_name_is_rejected_with_reason(api, tool, imgs):
    api.load(imgs)
    api.add("A")
    api.add("C")
    res = api.post("/rename", {"level": "value", **target(item("C")), "new_name": "A"})
    assert res["success"] is False and res["message"]
    assert table_items(tool) == [item("A"), item("C")]


def test_remove_from_dictionary_drops_columns_of_every_big(api, tool, imgs):
    api.load(imgs)
    add(api, GIRL_LONG)
    add(api, GUY_LONG)
    assert api.post("/remove_from_dictionary", {"level": "value", **target(GIRL_LONG)})["success"]
    assert table_items(tool) == []
    assert dictionary_columns(tool.kinds) == []


def test_columns_survive_missing_dictionary(api, tool, imgs, base_dir):
    api.load(imgs)
    api.add("A")
    api.add("B")
    api.set(api.row_index("a.png"), "B")
    api.save()
    (base_dir / "data_work" / "kinds.json").rename(base_dir / "data_work" / "moved_away.json")

    api.open_project("proj")
    assert table_items(tool) == [item("A"), item("B")]
    assert tool.df.set_index("サムネイル").loc["a.png", col("B")]
    assert dictionary_columns(tool.kinds) == [item("A"), item("B")]


def test_table_data_describes_columns(api, client, imgs):
    api.load(imgs)
    add(api, GIRL_LONG)
    body = client.get("/get_table_data").get_json()
    key = column_key(GIRL_LONG)
    assert body["columns"] == [{"key": key, "big": "girl", "mid": "body", "small": "hair", "value": "long"}]
    assert [r[key] for r in body["data"]] == [False, False]
