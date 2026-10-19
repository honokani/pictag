"""列幅とマークの並び（Playwright）"""
import pytest

from helpers import make_images

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100)})


def load_dir(page, imgs, width=1800):
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(page.base_url)
    page.fill("#imageDir", str(imgs))
    page.click("#loadButton")
    expect(page.locator("#gridBody tr")).to_have_count(2)


def td(page, selector, name="a.png"):
    return page.locator(f'#gridBody tr[data-name="{name}"] {selector}')


def width(locator):
    return locator.bounding_box()["width"]


def overflow(page):
    """表の横のはみ出し（px）"""
    return page.evaluate("() => $('imagesView').scrollWidth - $('imagesView').clientWidth")


def spare_after_close_up(page):
    """picture の欄の右端（枠線の内側）と、close-up の右端の間"""
    picture = td(page, 'td.cell[data-section="picture"]').bounding_box()
    close_up = td(page, '.choice[data-phrase="close-up"]').bounding_box()
    return picture["x"] + picture["width"] - 1 - (close_up["x"] + close_up["width"])


def test_marks_are_two_columns_of_four(page, imgs):
    load_dir(page, imgs)
    box = {m: td(page, f'.mark-btn[data-mark="{m}"]').bounding_box() for m in ["A", "B", "D", "★", "■"]}
    assert abs(box["A"]["y"] - box["★"]["y"]) < 0.5 and box["★"]["x"] > box["A"]["x"]  # 左の列が A〜D、右の列が ★●▲■
    assert box["A"]["y"] < box["B"]["y"] < box["D"]["y"]
    assert abs(box["D"]["y"] - box["■"]["y"]) < 0.5
    assert width(td(page, "td.marks")) <= 64  # ボタン2つ分


def test_picture_column_ends_10px_after_close_up_and_keeps_its_width_while_editing(page, imgs):
    load_dir(page, imgs)
    assert 9.5 <= spare_after_close_up(page) <= 11
    picture = td(page, 'td.cell[data-section="picture"]')
    before = width(picture)
    picture.locator(".text").click()
    expect(picture.locator("textarea")).to_be_visible()
    assert abs(width(picture) - before) < 0.5


def test_hint_takes_the_rest_of_the_width(page, imgs):
    (imgs / "a.txt").write_text("1girl, solo, smile", encoding="utf-8")
    load_dir(page, imgs)
    assert overflow(page) == 0
    assert round(width(td(page, 'td.cell[data-section="action"]'))) == 220  # 段落は今までどおり
    assert round(width(td(page, 'td.cell[data-section="girl"]'))) == 220
    assert round(width(td(page, "td.meta"))) == 150  # 画像名の欄も縮めない
    assert width(td(page, "td.hint")) > 600  # 残りは hint
    assert 9.5 <= spare_after_close_up(page) <= 11


def test_without_hint_the_rest_goes_to_sections_other_than_picture(page, imgs):
    load_dir(page, imgs)
    assert overflow(page) == 0
    action = width(td(page, 'td.cell[data-section="action"]'))
    girl = width(td(page, 'td.cell[data-section="girl"]'))
    assert action > 400 and abs(action - girl) < 1
    assert 9.5 <= spare_after_close_up(page) <= 11  # picture は広げない
