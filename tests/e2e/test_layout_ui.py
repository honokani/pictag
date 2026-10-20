"""列幅とマークの並び（Playwright）"""
import pytest

import app as pictag
from helpers import make_images, word_tokenizer
from tokens import TokenCounter

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def tokens(monkeypatch):
    # 実物のトークナイザーは取りに行かず、空白と記号で区切る小さなもので数える
    monkeypatch.setattr(pictag, "token_counter", TokenCounter(word_tokenizer()))


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
    """picture の欄の右端（枠線の内側）と、🎥 の行の最後のボタン（ショットの大きさの組の右端）の間"""
    picture = td(page, 'td.cell[data-section="picture"]').bounding_box()
    last = td(page, ".choice-row.camera .choice").last.bounding_box()
    return picture["x"] + picture["width"] - 1 - (last["x"] + last["width"])


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
    expect(picture.locator("textarea").first).to_be_visible()
    assert abs(width(picture) - before) < 0.5


def test_hint_takes_the_rest_of_the_width(page, imgs):
    (imgs / "a.txt").write_text("1girl, solo, smile", encoding="utf-8")
    load_dir(page, imgs)
    assert overflow(page) == 0
    for section in ["action", "girl", "guy"]:
        assert round(width(td(page, f'td.cell[data-section="{section}"]'))) == 220, section  # 段落は今までどおり
    assert round(width(td(page, "td.meta"))) == 56  # token の欄は縮めない
    assert width(td(page, "td.hint")) > 400  # 残りは hint（最小は 220）
    assert 9.5 <= spare_after_close_up(page) <= 11


def test_token_column_shows_the_count_over_the_limit_without_the_file_name(page, imgs):
    load_dir(page, imgs)
    expect(page.locator("#gridHead th").nth(1)).to_have_text("token")
    tokens = td(page, "td.meta .tokens")
    assert tokens.inner_text() == "0\n/ 507"  # 2行で、数字は右揃え
    expect(td(page, "td.meta")).not_to_contain_text("a.png")
    expect(td(page, "td.thumb img")).to_have_attribute("title", "a.png")  # ファイル名はサムネイルに載せると見える


def test_thumbnail_is_a_square_as_tall_as_the_picture_cell(page, imgs):
    load_dir(page, imgs)
    img = td(page, "td.thumb img").bounding_box()
    row = page.locator('#gridBody tr[data-name="a.png"]').bounding_box()
    assert abs(img["width"] - img["height"]) < 0.5
    assert abs(img["height"] + 9 - row["height"]) <= 1.5  # 上下の余白 8px と下の枠線 1px


def test_thumbnail_keeps_its_size_when_picture_values_are_written(page, imgs):
    # 表示中の欄はキーの名前の下に値を出すが、サムネイルは値の行の分では大きくしない（列を広げない）
    load_dir(page, imgs)
    size = td(page, "td.thumb img").bounding_box()["height"]
    text = td(page, 'td.cell[data-section="picture"] .text').bounding_box()["height"]
    for name in ["a.png", "b.png"]:  # サムネイルは見えている行でいちばん低い picture に合わせるので、全行に書く
        td(page, 'td.cell[data-section="picture"] .text', name).click()
        td(page, 'textarea[data-key="place"]', name).fill("ship bow")
        td(page, 'textarea[data-key="vibes"]', name).fill("romantic")
        page.evaluate("document.activeElement.blur()")
    page.locator('#gridHead th[data-section="guy"] .fold-section').click()  # 表を描き直す（サムネイルを測り直す）
    assert td(page, 'td.cell[data-section="picture"] .text').bounding_box()["height"] > text + 30  # 値の行が増えた
    assert abs(td(page, "td.thumb img").bounding_box()["height"] - size) < 0.5


def test_without_hint_the_preview_takes_the_rest_of_the_width(page, imgs):
    load_dir(page, imgs)  # hint が無くても、同じ列に preview を出す
    assert overflow(page) == 0
    for section in ["action", "girl", "guy"]:
        assert round(width(td(page, f'td.cell[data-section="{section}"]'))) == 220, section  # hint があるときと同じ
    assert width(td(page, "td.hint")) > 400  # 残りは preview
    assert 9.5 <= spare_after_close_up(page) <= 11  # picture は広げない


def test_thumbnail_zooms_in_with_width_from_unfolded_columns_right_of_picture(page, imgs):
    # サムネイルの見出しの ▶ で 1.5 倍に広げる。増えた幅は、picture より右の畳んでいない列（右端の列も）から同じだけずつ借りる。◀ で戻す
    load_dir(page, imgs)
    page.locator('#gridHead th[data-section="guy"] .fold-section').click()  # 畳んだ列からは借りない
    expect(page.locator('#gridHead th[data-section="guy"]')).to_have_class("folded")
    img = td(page, "td.thumb img")
    columns = {"picture": td(page, 'td.cell[data-section="picture"]'), "action": td(page, 'td.cell[data-section="action"]'),
               "girl": td(page, 'td.cell[data-section="girl"]'), "guy": td(page, 'td.cell[data-section="guy"]'),
               "side": td(page, "td.hint")}
    size = width(img)
    before = {name: width(column) for name, column in columns.items()}

    page.locator("#gridHead .thumb-zoom").click()
    expect(page.locator("#gridHead .thumb-zoom")).to_have_text("◀")
    assert abs(width(img) - size * 1.5) <= 1
    lent = {name: before[name] - width(column) for name, column in columns.items()}
    for name in ["action", "girl", "side"]:  # 増えた幅（0.5 倍）を3つの列で分ける
        assert abs(lent[name] - size * 0.5 / 3) <= 1.5, name
    assert abs(lent["picture"]) < 0.5 and abs(lent["guy"]) < 0.5  # picture と畳んだ列は変えない
    assert overflow(page) == 0

    page.locator("#gridHead .thumb-zoom").click()
    expect(page.locator("#gridHead .thumb-zoom")).to_have_text("▶")
    assert abs(width(img) - size) <= 0.5


def test_save_button_stays_at_the_top_right(page, imgs):
    # 保存はいつも上の帯の右上の端。メッセージはその左に出し、長くても保存は動かない
    load_dir(page, imgs, width=1200)
    header = page.locator("header.bar")
    padding = header.evaluate("el => parseFloat(getComputedStyle(el).paddingRight)")
    for message in ["保存しました", "とても長いメッセージ " * 12]:
        page.evaluate("text => setStatus(text, 'ok')", message)
        head = header.bounding_box()
        save = page.locator("#saveButton").bounding_box()
        status = page.locator("#status").bounding_box()
        assert abs(head["x"] + head["width"] - padding - (save["x"] + save["width"])) <= 1, message  # 右の端
        assert save["y"] - head["y"] <= 10, message  # 上の端
        assert status["x"] + status["width"] <= save["x"], message  # メッセージは保存の左
