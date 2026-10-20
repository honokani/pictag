"""マーキングの画面操作（Playwright）。排他の A〜H と複数可の ★●▲■◆♥♣♠（ボタンの data-mark は番号）"""
import pytest

from helpers import make_images

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e

ONE = "ABCDEFGH"
MANY = "★●▲■◆♥♣♠"


@pytest.fixture
def imgs(tmp_path):
    return make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100), "b.png": (100, 100), "c.png": (100, 100)})


def load_dir(page, imgs):
    page.goto(page.base_url)
    page.fill("#imageDir", str(imgs))
    page.click("#loadButton")
    expect(page.locator("#gridBody tr")).to_have_count(3)


def row(page, name):
    return page.locator(f'#gridBody tr[data-name="{name}"]')


def mark(page, name, symbol):
    """行のマークのボタン（記号で指す。ボタンは種類と番号を持つ）"""
    kind, number = ("one", ONE.index(symbol)) if symbol in ONE else ("many", MANY.index(symbol))
    return row(page, name).locator(f'.mark-btn[data-kind="{kind}"][data-mark="{number}"]')


def select(page, name, modifiers=None):
    row(page, name).locator("td.meta").click(modifiers=modifiers or [])


def test_eight_exclusive_and_eight_multi_marks(page, imgs):
    load_dir(page, imgs)
    expect(row(page, "a.png").locator('.mark-btn[data-kind="one"]')).to_have_text(list(ONE))
    expect(row(page, "a.png").locator('.mark-btn[data-kind="many"]')).to_have_text(list(MANY))
    mark(page, "a.png", "H").click()
    mark(page, "a.png", "♠").click()
    expect(mark(page, "a.png", "H")).to_have_class("mark-btn on")
    expect(mark(page, "a.png", "♠")).to_have_class("mark-btn on")


def test_mark_buttons_toggle_on_one_row(page, imgs):
    load_dir(page, imgs)
    mark(page, "a.png", "A").click()
    expect(mark(page, "a.png", "A")).to_have_class("mark-btn on")
    mark(page, "a.png", "B").click()  # 排他: A が外れて B
    expect(mark(page, "a.png", "A")).to_have_class("mark-btn")
    expect(mark(page, "a.png", "B")).to_have_class("mark-btn on")
    mark(page, "a.png", "B").click()
    expect(mark(page, "a.png", "B")).to_have_class("mark-btn")

    mark(page, "a.png", "★").click()
    mark(page, "a.png", "●").click()  # 複数: 両方付く
    expect(mark(page, "a.png", "★")).to_have_class("mark-btn on")
    expect(mark(page, "a.png", "●")).to_have_class("mark-btn on")
    expect(page.locator("#saveButton")).to_have_text("保存 *")


def test_mark_button_inside_selection_marks_all_selected_rows(page, imgs):
    load_dir(page, imgs)
    select(page, "a.png")
    select(page, "b.png", ["Shift"])
    mark(page, "b.png", "C").click()
    expect(mark(page, "a.png", "C")).to_have_class("mark-btn on")
    expect(mark(page, "b.png", "C")).to_have_class("mark-btn on")
    expect(mark(page, "c.png", "C")).to_have_class("mark-btn")


def test_number_keys_no_longer_mark(page, imgs):
    # マークのショートカット（1〜4・0・5〜8）は外した（マークが増えて数字キーでは足りない）。案内も出さない
    load_dir(page, imgs)
    select(page, "a.png")
    page.keyboard.press("1")
    page.keyboard.press("5")
    expect(row(page, "a.png").locator(".mark-btn.on")).to_have_count(0)
    expect(page.locator("#keyHelp")).to_have_count(0)


def test_filter_then_select_visible_and_bulk_add(page, imgs):
    load_dir(page, imgs)
    mark(page, "a.png", "A").click()
    mark(page, "c.png", "A").click()

    page.select_option("#filterOne", label="A")
    expect(row(page, "b.png")).to_be_hidden()
    page.click("#selectVisibleButton")
    expect(page.locator("#selectionInfo")).to_have_text("選択 2 行")

    page.select_option("#bulkSection", "picture")
    page.select_option("#bulkKey", "view")
    page.fill("#bulkText", "from above")
    page.click("text=選択行に追加")
    page.select_option("#filterOne", "")
    for name, expected in [("a.png", 1), ("b.png", 0), ("c.png", 1)]:
        expect(row(page, name).locator('td.cell[data-section="picture"] .ln', has_text="view: from above")).to_have_count(expected)


def test_filter_none_and_ctrl_a(page, imgs):
    load_dir(page, imgs)
    mark(page, "a.png", "■").click()
    page.select_option("#filterMany", "none")
    expect(row(page, "a.png")).to_be_hidden()
    page.locator("#grid").click(position={"x": 5, "y": 5})  # 入力欄の外にフォーカス
    page.keyboard.press("Control+a")
    expect(page.locator("#selectionInfo")).to_have_text("選択 2 行")


def test_clear_needs_a_long_press(page, imgs):
    load_dir(page, imgs)
    mark(page, "a.png", "A").click()
    mark(page, "a.png", "★").click()
    clear_one = page.locator('.clear-marks .hold[data-column="mark"]')
    expect(clear_one).to_have_text("A〜H をクリア")

    clear_one.click()  # 短く押しただけでは消えない
    expect(page.locator("#status")).to_have_text("1秒長押しすると、全行のマークを消します")
    expect(mark(page, "a.png", "A")).to_have_class("mark-btn on")

    clear_one.hover()
    page.mouse.down()
    page.wait_for_timeout(1300)
    page.mouse.up()
    expect(page.locator("#status")).to_have_text("全行の A〜H を消しました")
    expect(mark(page, "a.png", "A")).to_have_class("mark-btn")
    expect(mark(page, "a.png", "★")).to_have_class("mark-btn on")  # 複数の列は残る


def test_marks_survive_save(page, imgs):
    load_dir(page, imgs)
    mark(page, "b.png", "D").click()
    mark(page, "b.png", "◆").click()
    page.click("#saveButton")
    expect(page.locator("#status")).to_have_text("保存しました")
    expect(mark(page, "b.png", "D")).to_have_class("mark-btn on")
    expect(mark(page, "b.png", "◆")).to_have_class("mark-btn on")
