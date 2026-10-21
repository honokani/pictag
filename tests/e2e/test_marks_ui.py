"""マーキングの画面操作（Playwright）。排他の A〜H、複数可の ★●▲■◆♥♣♠、自動の ①〜⑧（ボタンの data-mark は番号）"""
import re

import pytest

from helpers import make_images

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e

ONE = "ABCDEFGH"
MANY = "★●▲■◆♥♣♠"
AUTO = "①②③④⑤⑥⑦⑧"
ON = re.compile(r"\bon\b")


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


def auto(page, name, number):
    """行の自動のマーク（表示だけ）"""
    return row(page, name).locator(f'.mark-auto[data-mark="{number}"]')


def write(page, name, text, section="girl"):
    """入力欄の「その他」に書いて確定する（確定タグのキーの行は、そのキーにまとまる）"""
    cell = row(page, name).locator(f'td.cell[data-section="{section}"]')
    cell.click()
    cell.locator('textarea[data-key=""]').fill(text)
    page.evaluate("document.activeElement.blur()")
    expect(cell.locator(".ln:not(.empty)").first).to_be_visible()


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
    page.click('#bulkForm button[value="add"]')
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


def test_auto_marks_follow_the_phrase_chosen_by_right_click(page, imgs):
    # 右の列（①〜⑧）は自動: 帯の ①〜⑧ を右クリックして段落・キー・語句を選ぶと、その語句のある行に付く（行のマークは押しても変わらない）
    load_dir(page, imgs)
    write(page, "a.png", "looks: smile")
    write(page, "c.png", "looks: standing")
    expect(row(page, "a.png").locator(".mark-auto")).to_have_text(list(AUTO))
    setting = page.locator('#autoMarks .auto-mark[data-mark="0"]')
    expect(setting).to_have_class(re.compile(r"\bunset\b"))  # 設定の無いものは薄く

    setting.click(button="right")
    form = page.locator("#autoMarkForm")
    expect(form).to_be_visible()
    page.select_option("#autoMarkSection", "girl")
    page.select_option("#autoMarkKey", "looks")
    phrase = page.locator("#autoMarkPhrase")
    phrase.fill("ｓｍｉｌｅ")  # 英字だけの欄
    expect(phrase).to_have_value("smile")
    phrase.fill("")
    page.wait_for_function("() => state.phrases.some(p => p.phrase === 'smile')")
    phrase.press_sequentially("smi")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("smile")  # その段落のそのキーの語句
    phrase.press("Enter")
    form.locator('button[type="submit"]').click()
    expect(form).to_be_hidden()
    expect(setting).to_have_attribute("title", "① girl / looks / smile（右クリックで変える）")
    expect(auto(page, "a.png", 0)).to_have_class(ON)
    expect(auto(page, "b.png", 0)).not_to_have_class(ON)
    expect(page.locator("#saveButton")).to_have_text("保存 *")

    write(page, "b.png", "looks: smile")  # 入力が変われば付き直す
    expect(auto(page, "b.png", 0)).to_have_class(ON)
    auto(page, "b.png", 0).click()  # 押しても変わらない
    expect(auto(page, "b.png", 0)).to_have_class(ON)

    page.select_option("#filterAuto", label="① smile")  # 絞り込み
    expect(row(page, "c.png")).to_be_hidden()
    expect(row(page, "a.png")).to_be_visible()
    page.select_option("#filterAuto", "")

    setting.click(button="right")
    page.locator("#autoMarkClear").click()  # 外す
    expect(form).to_be_hidden()
    expect(auto(page, "a.png", 0)).not_to_have_class(ON)
    expect(setting).to_have_class(re.compile(r"\bunset\b"))


def test_word_marks_match_sentences_of_action_without_keys(page, imgs):
    # 帯の名前は「単語」。action のように確定タグの無い段落は「（キーなし）」で文に合わせる（文末の . は外し、* は何文字でも）
    load_dir(page, imgs)
    expect(page.locator("#autoMarks")).to_contain_text("単語")
    write(page, "a.png", "girl spread arms wildly", section="action")
    write(page, "b.png", "girl spread legs.", section="action")  # 文末に . のある文
    page.wait_for_function("() => state.phrases.some(p => p.phrase === 'girl spread legs.')")
    setting = page.locator('#autoMarks .auto-mark[data-mark="0"]')
    setting.click(button="right")
    page.select_option("#autoMarkSection", "action")
    expect(page.locator("#autoMarkKey option")).to_have_text(["（キーなし）"])
    phrase = page.locator("#autoMarkPhrase")
    phrase.press_sequentially("legs")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("girl spread legs")  # 候補はその段落の文（. は外す）
    expect(page.locator("#suggestions:visible li.active")).not_to_contain_text("legs.")
    phrase.fill("*spread arms*")
    page.locator('#autoMarkForm button[type="submit"]').click()
    expect(page.locator("#autoMarkForm")).to_be_hidden()
    expect(setting).to_have_attribute("title", "① action / （キーなし） / *spread arms*（右クリックで変える）")
    expect(auto(page, "a.png", 0)).to_have_class(ON)
    expect(auto(page, "b.png", 0)).not_to_have_class(ON)
