"""共用辞書の画面（Playwright）。入力は映画の有名なシーン（tests/scenes.py）"""
import pytest

import app as pictag
from helpers import Api
from scenes import load_scenes

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e

COUPLES = ["titanic.png", "roman_holiday.png", "lalaland.png"]


@pytest.fixture
def movies(tool, tmp_path):
    """3つの場面を入力して保存したプロジェクト movies"""
    api = Api(pictag.app.test_client())
    load_scenes(api, tmp_path / "imgs" / "movies", COUPLES)
    api.save()
    return api


# ---- 画面操作のヘルパー ----

def open_movies(page):
    page.goto(page.base_url)
    page.select_option("#projectSelect", "movies")
    expect(page.locator("#gridBody tr")).to_have_count(3)


def show_dictionary(page):
    page.click('.tab[data-view="dictionary"]')
    expect(page.locator("#dictView")).to_be_visible()


def show_images(page):
    page.click('.tab[data-view="images"]')
    expect(page.locator("#imagesView")).to_be_visible()


def dict_row(page, key, text):
    return page.locator(f'#dictBody tr[data-key="{key}"][data-text="{text}"]')


def cell(page, name, section="girl"):
    return page.locator(f'#gridBody tr[data-name="{name}"] td.cell[data-section="{section}"]')


def looks_field(page, name, section="girl"):
    """開いた入力欄の looks の欄"""
    return cell(page, name, section).locator('textarea[data-key="looks"]')


def line_of(page, name, key, section="girl"):
    return cell(page, name, section).locator(".ln", has_text=f"{key}:")


def hold(page, button):
    button.hover()
    page.mouse.down()
    page.wait_for_timeout(1300)
    page.mouse.up()


def group_postures(page):
    """共用辞書の画面で looks の standing と sitting を1つだけのグループにして、画像の画面へ戻る"""
    show_dictionary(page)
    page.select_option("#dictKey", "looks")
    dict_row(page, "looks", "standing").locator(".dict-phrase").click()
    dict_row(page, "looks", "sitting").locator(".dict-phrase").click()
    page.click("#dictGroupButton")
    expect(dict_row(page, "looks", "standing").locator(".group-badge")).to_have_text("G1")
    expect(dict_row(page, "looks", "sitting").locator(".group-badge")).to_have_text("G1")
    show_images(page)


# ---- テスト ----

def test_tab_switches_between_images_and_dictionary(page, movies):
    open_movies(page)
    show_dictionary(page)
    expect(page.locator("#imagesView")).to_be_hidden()
    expect(page.locator("#tools")).to_be_hidden()

    standing = dict_row(page, "looks", "standing")  # 段落をまたいで1行
    expect(standing.locator(".dict-sections")).to_have_text("girl, guy")
    expect(standing.locator(".num")).to_have_text("4")
    expect(standing.locator(".dict-shared")).to_have_text("")
    expect(dict_row(page, "", "spread")).to_have_attribute("data-kind", "word")

    show_images(page)
    expect(page.locator("#dictView")).to_be_hidden()
    expect(page.locator("#tools")).to_be_visible()


def test_filter_by_text_key_and_shared(page, movies):
    open_movies(page)
    show_dictionary(page)
    page.fill("#dictFilter", "stand")
    expect(page.locator("#dictBody tr")).to_have_count(1)

    page.fill("#dictFilter", "")
    page.select_option("#dictKey", "vibes")
    expect(page.locator("#dictBody .dict-phrase")).to_have_text(["carefree", "cheerful", "dreamy", "romantic", "windy"])
    page.select_option("#dictShared", "in")
    expect(page.locator("#dictBody tr")).to_have_count(0)
    expect(page.locator("#dictEmpty")).to_be_visible()


def test_register_selected_rows_and_unregister_with_a_long_press(page, movies):
    open_movies(page)
    show_dictionary(page)
    page.fill("#dictFilter", "stand")
    dict_row(page, "looks", "standing").locator(".dict-phrase").click()
    expect(page.locator("#dictSelInfo")).to_have_text("選択 1 件")
    page.click("#dictRegisterButton")
    expect(dict_row(page, "looks", "standing").locator(".shared-mark")).to_be_visible()
    expect(page.locator("#status")).to_have_text("1 件を共用辞書に入れました")

    unregister = page.locator("#dictUnregisterButton")
    unregister.click()  # 短く押しただけでは消えない
    expect(page.locator("#status")).to_have_text("1秒長押しすると、選んだ語句を共用辞書から消します")
    expect(dict_row(page, "looks", "standing").locator(".shared-mark")).to_be_visible()
    hold(page, unregister)
    expect(page.locator("#status")).to_have_text("1 件を共用辞書から消しました（入力はそのまま）")
    expect(dict_row(page, "looks", "standing").locator(".shared-mark")).to_have_count(0)
    expect(dict_row(page, "looks", "standing").locator(".num")).to_have_text("4")  # 使っているので一覧に残る


def test_add_a_new_phrase_by_hand(page, movies):
    open_movies(page)
    show_dictionary(page)
    page.select_option("#dictAddSection", "girl")
    page.select_option("#dictAddKey", "looks")
    page.fill("#dictAddText", "kneeling")
    page.click("#dictAddForm button[type=submit]")
    kneeling = dict_row(page, "looks", "kneeling")
    expect(kneeling.locator(".num")).to_have_text("0")
    expect(kneeling.locator(".shared-mark")).to_be_visible()
    expect(page.locator("#dictAddText")).to_have_value("")


def test_dictionary_works_before_opening_a_project(page):
    page.goto(page.base_url)
    show_dictionary(page)
    expect(page.locator("#dictEmpty")).to_be_visible()
    page.select_option("#dictAddSection", "picture")
    page.select_option("#dictAddKey", "place")
    page.fill("#dictAddText", "ship bow")
    page.click("#dictAddForm button[type=submit]")
    expect(dict_row(page, "place", "ship bow").locator(".shared-mark")).to_be_visible()


def test_rename_replaces_the_inputs_of_the_open_project(page, movies):
    open_movies(page)
    show_dictionary(page)
    dict_row(page, "clothes", "cardigan").locator(".dict-rename").click()
    editor = page.locator("#dictBody .rename-input")
    editor.fill("shawl")
    editor.press("Enter")
    expect(dict_row(page, "clothes", "shawl").locator(".num")).to_have_text("1")
    expect(dict_row(page, "clothes", "cardigan")).to_have_count(0)
    expect(page.locator("#status")).to_have_text(
        "「cardigan」を「shawl」にしました（開いているプロジェクトの 1 行を置き換えました。保存はまだです）")

    show_images(page)
    expect(line_of(page, "titanic.png", "clothes")).to_have_text("clothes: long dress, shawl")
    expect(page.locator("#saveButton")).to_have_text("保存 *")


def test_rename_is_cancelled_by_escape(page, movies):
    open_movies(page)
    show_dictionary(page)
    dict_row(page, "clothes", "cardigan").locator(".dict-rename").click()
    editor = page.locator("#dictBody .rename-input")
    editor.fill("shawl")
    editor.press("Escape")
    expect(page.locator("#dictBody .rename-input")).to_have_count(0)
    expect(dict_row(page, "clothes", "cardigan")).to_have_count(1)
    expect(page.locator("#saveButton")).to_have_text("保存")


def test_dictionary_fields_take_english_only(page, movies):
    # 共用辞書に入る欄（足す語句・改名）も英字だけ（全角は半角に、日本語は消す）
    open_movies(page)
    show_dictionary(page)
    page.locator("#dictAddText").fill("ｓｈａｗｌ肩掛け")
    expect(page.locator("#dictAddText")).to_have_value("shawl")
    dict_row(page, "clothes", "cardigan").locator(".dict-rename").click()
    editor = page.locator("#dictBody .rename-input")
    editor.fill("ｓｈａｗｌ")
    expect(editor).to_have_value("shawl")


def test_selected_phrase_can_be_replaced_by_a_mate_of_its_group(page, movies):
    # 範囲を選んで候補を選ぶと置き換える。選んだ語句は無くなるものとして見るので、同じグループの語句も候補に出る
    open_movies(page)
    group_postures(page)
    cell(page, "roman_holiday.png").click()
    editor = looks_field(page, "roman_holiday.png")
    start = editor.input_value().index("sitting")
    editor.focus()
    editor.evaluate(f"el => el.setSelectionRange({start}, {start})")
    for _ in "sitting":
        editor.press("Shift+ArrowRight")  # sitting を選ぶ
    standing = page.locator("#suggestions:visible li", has_text="standing")
    expect(standing).to_be_visible()
    standing.click()
    assert editor.input_value() == "standing, smile"


def test_group_hides_mates_from_suggestions_and_marks_conflicts(page, movies):
    open_movies(page)
    group_postures(page)

    # roman_holiday の girl は sitting。同じグループの standing は looks の候補に出ない
    cell(page, "roman_holiday.png").click()
    editor = looks_field(page, "roman_holiday.png")
    editor.focus()
    editor.evaluate("el => el.setSelectionRange(el.value.length, el.value.length)")
    page.keyboard.type(", ")
    expect(page.locator("#suggestions li").first).to_be_visible()
    texts = page.locator("#suggestions li").all_inner_texts()
    assert not any(t.startswith("standing") for t in texts), texts
    assert any(t.startswith("dancing") for t in texts), texts
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")

    # 同じグループの語句が2つある行には ⚠（グループの語句を title に出す）
    cell(page, "lalaland.png").click()
    lalaland = looks_field(page, "lalaland.png")
    lalaland.fill("standing, sitting, dancing")
    lalaland.evaluate("el => el.blur()")
    conflict = cell(page, "lalaland.png").locator(".ln.conflict")
    expect(conflict).to_have_text("looks: standing, sitting, dancing")
    expect(conflict).to_have_attribute("title", "1つだけのグループ: sitting / standing")  # 一覧の並び（abc 順）
    expect(page.locator("#gridBody .ln.conflict")).to_have_count(1)


def test_bulk_add_reports_rows_skipped_by_a_group(page, movies):
    open_movies(page)
    group_postures(page)
    page.click("#selectVisibleButton")
    page.select_option("#bulkSection", "girl")
    page.select_option("#bulkKey", "looks")
    page.fill("#bulkText", "sitting")
    page.click('#bulkForm button[value="add"]')
    expect(page.locator("#status")).to_have_text("3 行に追加しました（2 行は、同じグループの語句があるので足していません）")
    expect(line_of(page, "titanic.png", "looks")).to_have_text("looks: standing, eyes closed, smile")
    expect(line_of(page, "roman_holiday.png", "looks")).to_have_text("looks: sitting, smile")


def test_mark_keys_do_nothing_on_the_dictionary(page, movies):
    open_movies(page)
    page.click("#selectVisibleButton")
    show_dictionary(page)
    page.locator("#dictCount").click()  # 入力欄の外にフォーカス
    page.keyboard.press("1")
    show_images(page)
    expect(page.locator('#gridBody .mark-btn.on')).to_have_count(0)


def test_move_phrases_of_a_section_to_another_key(page, movies):
    # 帯の「キーを移す」: 段落（A, B も）・キー・語句（候補はその段落のそのキーの語句）・移す先を選び、全行の入力を移す（保存はまだ）
    open_movies(page)
    page.wait_for_function("() => state.phrases.some(p => p.phrase === 'smile')")  # 辞書は表のあとに読む
    page.select_option("#moveSection", "girl")
    page.select_option("#moveFrom", "looks")
    phrase = page.locator("#movePhrase")
    phrase.press_sequentially("smi")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("smile")
    phrase.press("Enter")
    page.select_option("#moveTo", "body")
    page.click("#moveForm button")
    expect(page.locator("#status")).to_have_text("girl の looks の smile を body に移しました（開いているプロジェクトの 2 行。保存はまだです）")
    expect(line_of(page, "roman_holiday.png", "looks")).to_have_text("looks: sitting")
    expect(line_of(page, "roman_holiday.png", "body")).to_have_text("body: black/short hair, smile")
    expect(line_of(page, "titanic.png", "looks")).to_have_text("looks: standing, eyes closed")
    expect(line_of(page, "roman_holiday.png", "looks", "guy")).to_have_text("looks: sitting")  # ほかの段落は変えない
    expect(page.locator("#saveButton")).to_have_text("保存 *")
    expect(phrase).to_have_value("")
