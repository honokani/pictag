"""画像の読み込み・サムネイル・画像配信"""
from urllib.parse import quote

import pytest
from PIL import Image

from helpers import image_of, make_images, touch_later

RED, BLUE = (255, 0, 0), (0, 0, 255)


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "big.png": ((900, 900), RED)})


def test_table_data_returns_image_names(api, imgs):
    api.load(imgs)
    assert [r["サムネイル"] for r in api.rows()] == ["a.png", "big.png"]


def test_thumbnail_of_big_image_is_resized(api, client, imgs):
    api.load(imgs)
    assert max(image_of(client.get("/thumbnail/big.png")).size) <= 600


def test_thumbnail_of_small_image_is_original(api, client, imgs):
    api.load(imgs)
    assert image_of(client.get("/thumbnail/a.png")).size == (100, 100)


def test_small_image_named_with_thumbnail_prefix(api, client, tmp_path):
    imgs = make_images(tmp_path / "imgs" / "proj", {"t_small.png": (64, 64), "small.png": (32, 32)})
    api.load(imgs)
    assert image_of(client.get("/thumbnail/t_small.png")).size == (64, 64)
    assert image_of(client.get("/image/t_small.png")).size == (64, 64)


def test_image_route_serves_original(api, client, imgs):
    api.load(imgs)
    assert image_of(client.get("/image/big.png")).size == (900, 900)


def test_image_route_falls_back_to_thumbnail_for_dead_image(api, client, imgs):
    api.load(imgs)
    (imgs / "big.png").rename(imgs.parent / "big.png.bak")
    api.load(imgs)
    assert max(image_of(client.get("/image/big.png")).size) <= 600


def test_image_names_with_url_special_characters(api, client, tmp_path):
    imgs = make_images(tmp_path / "imgs" / "proj", {"a#1%.png": (50, 50)})
    api.load(imgs)
    assert image_of(client.get("/thumbnail/" + quote("a#1%.png"))).size == (50, 50)


@pytest.mark.parametrize("route", ["/thumbnail/", "/image/"])
def test_path_traversal_is_blocked(api, client, imgs, tmp_path, route):
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    api.load(imgs)
    r = client.get(route + "..%5C..%5Csecret.txt")
    assert r.status_code == 404
    assert b"TOP SECRET" not in r.data


@pytest.mark.parametrize("route", ["/thumbnail/", "/image/"])
def test_only_listed_images_are_served(api, client, imgs, route):
    (imgs / "notes.txt").write_text("not an image")
    api.load(imgs)
    assert client.get(route + "notes.txt").status_code == 404


def test_image_routes_before_loading_project(client):
    assert client.get("/thumbnail/a.png").status_code == 404
    assert client.get("/image/a.png").status_code == 404


def test_thumbnail_regenerated_when_source_changes(api, client, tool, imgs):
    api.load(imgs)
    assert image_of(client.get("/thumbnail/big.png")).getpixel((0, 0)) == RED

    make_images(imgs, {"big.png": ((900, 900), BLUE)})
    touch_later(imgs / "big.png")
    api.load(imgs)
    assert image_of(client.get("/thumbnail/big.png")).getpixel((0, 0)) == BLUE
    with Image.open(tool.data_work_target / "t_big.png") as thumb:
        assert thumb.getpixel((0, 0)) == BLUE


def test_stale_thumbnail_removed_when_source_becomes_small(api, client, tool, imgs):
    api.load(imgs)
    make_images(imgs, {"big.png": ((100, 100), BLUE)})
    touch_later(imgs / "big.png")
    api.load(imgs)
    assert image_of(client.get("/thumbnail/big.png")).size == (100, 100)
    assert not (tool.data_work_target / "t_big.png").exists()


def test_directory_named_like_image_is_ignored(api, imgs):
    (imgs / "folder.png").mkdir()
    api.load(imgs)
    assert [r["サムネイル"] for r in api.rows()] == ["a.png", "big.png"]
