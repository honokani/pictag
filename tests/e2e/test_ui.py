"""画面操作（Playwright）"""
import pytest

import app as pictag
from helpers import caption_of, make_images, word_tokenizer
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
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100), "c.png": (800, 800)})


# ---- 画面操作のヘルパー ----

def load_dir(page, imgs):
    page.goto(page.base_url)
    page.fill("#imageDir", str(imgs))
    page.click("#loadButton")
    expect(page.locator("#gridBody tr").first).to_be_attached()


def row(page, name):
    return page.locator(f'#gridBody tr[data-name="{name}"]')


def cell(page, name, section="girl"):
    return row(page, name).locator(f'td.cell[data-section="{section}"]')


def open_editor(page, name, section="girl"):
    cell(page, name, section).click()
    return cell(page, name, section).locator("textarea")


def write(page, name, text, section="girl"):
    """入力欄に書いて確定する（フォーカスを外すと送信する）"""
    editor = open_editor(page, name, section)
    editor.fill(text)
    editor.evaluate("el => el.blur()")
    expect(cell(page, name, section).locator(".text")).to_have_text(text)


def tokens_of(page, name):
    return row(page, name).locator(".tokens")


def section_names(page):
    return page.locator("#gridHead .section-name").all_inner_texts()


def wait_for_word(page, phrase):
    page.wait_for_function("phrase => state.words.some(w => w.phrase === phrase)", arg=phrase)


# ---- テスト ----

def test_load_shows_rows_and_default_sections(page, imgs):
    load_dir(page, imgs)
    assert section_names(page) == ["picture", "action", "girl"]
    expect(page.locator("#gridBody tr")).to_have_count(3)
    expect(tokens_of(page, "a.png")).to_have_text("0 / 507")
    expect(page.locator('#projectSelect option[value="proj"]')).to_be_attached()


def test_edit_updates_tokens_and_preview_then_saves(page, imgs, tool):
    load_dir(page, imgs)
    text = "looks: standing\nbody: long hair, black hair"
    write(page, "a.png", text)

    caption = caption_of(text)
    assert caption == "girl:\n  - looks: standing\n  - body: long black hair"
    expect(tokens_of(page, "a.png")).to_have_text("12 / 507")
    expect(tokens_of(page, "a.png")).to_have_attribute("title", caption)
    expect(page.locator("#saveButton")).to_have_text("保存 *")

    page.click("#saveButton")
    expect(page.locator("#status")).to_have_text("保存しました")
    expect(page.locator("#saveButton")).to_have_text("保存")
    assert (tool.captions_dir / "a.txt").read_text(encoding="utf-8") == caption


def test_ctrl_s_saves(page, imgs, tool):
    load_dir(page, imgs)
    write(page, "b.png", "looks: standing")
    page.keyboard.press("Control+s")
    expect(page.locator("#status")).to_have_text("保存しました")
    assert (tool.captions_dir / "b.txt").read_text(encoding="utf-8") == caption_of("looks: standing")


def test_suggestion_completes_phrase_of_the_line_key(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_word(page, "long hair")

    editor = open_editor(page, "a.png")
    editor.press_sequentially("body: lh")
    expect(page.locator("#suggestions li.active")).to_contain_text("long hair")
    editor.press("Enter")
    assert editor.input_value() == "body: long hair, "
    editor.evaluate("el => el.blur()")
    expect(cell(page, "a.png").locator(".text")).to_have_text("body: long hair")


def test_suggestion_at_line_start_adds_key_and_phrase(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_word(page, "long hair")

    editor = open_editor(page, "a.png")
    editor.press_sequentially("lh")
    expect(page.locator("#suggestions li.active")).to_contain_text("body: long hair")
    editor.press("Tab")
    assert editor.input_value() == "body: long hair"


def test_enter_after_accepting_makes_a_new_line(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair, bare hands")
    wait_for_word(page, "bare hands")

    editor = open_editor(page, "a.png")
    editor.press_sequentially("body: lh")
    editor.press("Enter")  # 確定（", " が付き、残りの候補が出る）
    editor.press("Enter")  # 打ちかけが無いので改行
    editor.press_sequentially("looks: standing")
    assert editor.input_value() == "body: long hair, \nlooks: standing"


def test_bulk_add_and_remove_on_selected_rows(page, imgs):
    load_dir(page, imgs)
    row(page, "a.png").locator("td.meta").click()
    row(page, "c.png").locator("td.meta").click(modifiers=["Shift"])
    expect(page.locator("#selectionInfo")).to_have_text("選択 3 行")

    page.select_option("#bulkSection", "girl")
    page.fill("#bulkText", "looks: standing")
    page.click("text=選択行に追加")
    expect(page.locator("#status")).to_have_text("3 行に追加しました")
    for name in ["a.png", "b.png", "c.png"]:
        expect(cell(page, name).locator(".text")).to_have_text("looks: standing")

    row(page, "b.png").locator("td.meta").click(modifiers=["Control"])
    expect(page.locator("#selectionInfo")).to_have_text("選択 2 行")
    page.fill("#bulkText", "looks: standing")
    page.click("text=選択行から削除")
    expect(cell(page, "a.png").locator(".text")).to_have_text("")
    expect(cell(page, "b.png").locator(".text")).to_have_text("looks: standing")
    expect(cell(page, "c.png").locator(".text")).to_have_text("")


def test_bulk_section_choice_survives_save(page, imgs):
    load_dir(page, imgs)
    page.select_option("#bulkSection", "girl")
    page.click("#saveButton")
    expect(page.locator("#status")).to_have_text("保存しました")
    expect(page.locator("#bulkSection")).to_have_value("girl")


def test_sections_add_rename_remove(page, imgs):
    load_dir(page, imgs)
    page.fill("#sectionName", "dog")
    page.click("#sectionForm button")
    expect(page.locator("#gridHead .section-name")).to_have_count(4)
    assert section_names(page) == ["picture", "action", "girl", "dog"]

    page.once("dialog", lambda dialog: dialog.accept("dog A"))
    page.locator('#gridHead th[data-section="dog"] .section-name').dblclick()
    expect(page.locator('#gridHead th[data-section="dog A"]')).to_be_attached()

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator('#gridHead th[data-section="dog A"] .remove-section').click()
    expect(page.locator("#gridHead .section-name")).to_have_count(3)


def test_dead_rows_toggle_and_remove(page, imgs):
    load_dir(page, imgs)
    page.click("#saveButton")
    expect(page.locator("#status")).to_have_text("保存しました")
    (imgs / "a.png").rename(imgs.parent / "a.png.bak")
    page.click("#loadButton")
    expect(row(page, "a.png")).to_have_class("dead")

    page.uncheck("#showDead")
    expect(row(page, "a.png")).to_be_hidden()
    page.check("#showDead")
    expect(row(page, "a.png")).to_be_visible()

    page.once("dialog", lambda dialog: dialog.accept())
    page.click("#removeDeadButton")
    expect(page.locator("#gridBody tr")).to_have_count(2)
    expect(row(page, "a.png")).to_have_count(0)


def test_image_dialog_shows_original(page, imgs):
    load_dir(page, imgs)
    row(page, "c.png").locator("td.thumb img").click()
    expect(page.locator("#imageDialog")).to_be_visible()
    expect(page.locator("#imageFull")).to_have_attribute("src", "/image/c.png")
    page.wait_for_function("() => document.getElementById('imageFull').naturalWidth === 800")
    page.keyboard.press("Escape")
    expect(page.locator("#imageDialog")).to_be_hidden()


def test_text_is_shown_as_text_not_html(page, imgs):
    load_dir(page, imgs)
    write(page, "a.png", "<b>bold</b>")
    expect(cell(page, "a.png").locator("b")).to_have_count(0)


def test_tokens_over_the_limit_are_marked(page, imgs, monkeypatch):
    monkeypatch.setattr(pictag, "TOKEN_LIMIT", 5)
    load_dir(page, imgs)
    write(page, "a.png", "looks: standing")
    expect(tokens_of(page, "a.png")).to_have_text("6 / 5")
    expect(tokens_of(page, "a.png")).to_have_class("tokens over")


def test_project_select_opens_saved_project(page, tmp_path):
    a = make_images(tmp_path / "imgs" / "proj_a", {"a.png": (100, 100)})
    b = make_images(tmp_path / "imgs" / "proj_b", {"b.png": (100, 100)})
    load_dir(page, a)
    write(page, "a.png", "looks: standing")
    page.click("#saveButton")
    expect(page.locator("#status")).to_have_text("保存しました")
    page.fill("#imageDir", str(b))
    page.click("#loadButton")
    expect(row(page, "b.png")).to_be_attached()

    page.select_option("#projectSelect", "proj_a")
    expect(cell(page, "a.png").locator(".text")).to_have_text("looks: standing")
