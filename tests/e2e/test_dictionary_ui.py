"""共用辞書の画面（Playwright）。入力は映画の有名なシーン（tests/scenes.py）"""
import re

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
    """共用辞書の画面で looks の standing と sitting に kind .posture（前後の決まりなし・排他制限）を付与して、画像の画面へ戻る"""
    show_dictionary(page)
    page.fill("#dictFilter", ".looks")
    dict_row(page, "looks", "standing").locator(".dict-phrase").click()
    dict_row(page, "looks", "sitting").locator(".dict-phrase").click(modifiers=["Control"])
    page.click("#dictGroupButton")
    page.fill("#groupName", "posture")
    page.check('#groupDialog input[name="groupAffix"][value=""]')
    page.click('#groupDialog button[value="ok"]')
    expect(dict_row(page, "looks", "standing").locator(".group-badge")).to_have_text(".posture")
    expect(dict_row(page, "looks", "sitting").locator(".group-badge")).to_have_text(".posture")
    show_images(page)


# ---- テスト ----

def test_tab_switches_between_images_and_dictionary(page, movies):
    open_movies(page)
    show_dictionary(page)
    expect(page.locator("#imagesView")).to_be_hidden()
    expect(page.locator("#tools")).to_be_hidden()

    standing = dict_row(page, "looks", "standing")  # 段落をまたいで1行
    expect(standing.locator(".dict-sections")).to_have_text("girl, guy")
    expect(standing.locator(".num")).to_have_text("4（0）")  # 開いているプロジェクトの回数（ほかのプロジェクトの回数）
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
    page.fill("#dictFilter", ".vibes")
    expect(page.locator("#dictBody .dict-phrase")).to_have_text(["carefree", "cheerful", "dreamy", "romantic", "windy"])
    page.select_option("#dictShared", "in")
    expect(page.locator("#dictBody tr")).to_have_count(0)
    expect(page.locator("#dictEmpty")).to_be_visible()


def test_search_button_and_enter_narrow_to_rows_with_the_words_as_typed(page, movies):
    # 打っている間は、あいまいに合う行（fzf のよう）。「対象を表示」の右の「検索」か Enter で、打った語がそのまま入っている行だけ
    # （大文字と小文字は区別しない。「以外を表示」なら入っていない行）。また打つと、あいまいに戻る
    open_movies(page)
    show_dictionary(page)
    rows = page.locator("#dictBody tr")
    expect(rows.first).to_be_visible()
    total = rows.count()
    xs = [page.locator(s).bounding_box()["x"]
          for s in ("#dictResetButton", "#dictFilter", "#dictFilterMode", "#dictSearchButton", "#dictShared")]
    assert xs == sorted(xs)  # 左から リセット・検索の欄・対象を表示・検索・共用辞書

    page.fill("#dictFilter", "SS")
    fuzzy = rows.count()
    assert fuzzy > 2  # standing（.looks の s）など
    page.click("#dictSearchButton")
    expect(page.locator("#dictBody .dict-phrase")).to_have_text(["long dress", "yellow dress"])
    page.select_option("#dictFilterMode", "out")
    expect(rows).to_have_count(total - 2)
    page.select_option("#dictFilterMode", "in")

    page.fill("#dictFilter", "ss")
    expect(rows).to_have_count(fuzzy)
    page.press("#dictFilter", "Enter")
    expect(page.locator("#dictBody .dict-phrase")).to_have_text(["long dress", "yellow dress"])


def test_a_word_that_starts_with_a_dot_looks_only_at_kind_names(page, movies):
    # 「.」で始まる語は、kind（キーを含む）の名前とだけ比べる（語句の中の「.」とは比べない）。「.」の無い語は、語句と kind の名前の両方
    movies.write(movies.row_index("titanic.png"), "girl waves. guy smiles.", section="action")
    movies.save()
    open_movies(page)
    show_dictionary(page)
    expect(dict_row(page, "", "girl waves. guy smiles.")).to_be_visible()  # 辞書を読むまで待つ
    page.fill("#dictFilter", ".smiles")
    expect(page.locator("#dictBody tr")).to_have_count(0)
    page.fill("#dictFilter", ".action smiles")
    expect(page.locator("#dictBody .dict-phrase")).to_have_text(["girl waves. guy smiles."])


def test_reset_puts_the_search_the_mode_and_the_shared_filter_back(page, movies):
    # 検索の欄の左の「リセット」: 検索の文字を消し、「対象を表示」と「共用辞書: すべて」に戻す
    open_movies(page)
    show_dictionary(page)
    rows = page.locator("#dictBody tr")
    expect(rows.first).to_be_visible()
    total = rows.count()
    page.fill("#dictFilter", "stand")
    page.select_option("#dictFilterMode", "out")
    page.select_option("#dictShared", "in")
    expect(rows).to_have_count(0)
    page.click("#dictResetButton")
    expect(page.locator("#dictFilter")).to_have_value("")
    expect(page.locator("#dictFilterMode")).to_have_value("in")
    expect(page.locator("#dictShared")).to_have_value("")
    expect(rows).to_have_count(total)


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
    expect(dict_row(page, "looks", "standing").locator(".num")).to_have_text("4（0）")  # 使っているので一覧に残る


def test_add_a_new_phrase_by_hand(page, movies):
    open_movies(page)
    show_dictionary(page)
    page.select_option("#dictAddSection", "girl")
    page.select_option("#dictAddKey", "looks")
    page.fill("#dictAddText", "kneeling")
    page.click("#dictAddForm button[type=submit]")
    kneeling = dict_row(page, "looks", "kneeling")
    expect(kneeling.locator(".num")).to_have_text("0（0）")
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


def test_count_shows_this_project_and_the_other_projects(page, movies, tmp_path):
    # 回数: プロジェクトを開いているときは「開いているプロジェクトの回数（ほかのプロジェクトの回数）」（候補と同じ書き方）
    other = Api(pictag.app.test_client())
    load_scenes(other, tmp_path / "imgs" / "others", ["titanic.png"])
    other.save()
    open_movies(page)
    show_dictionary(page)
    expect(dict_row(page, "looks", "standing").locator(".num")).to_have_text("4（2）")
    expect(dict_row(page, "looks", "sitting").locator(".num")).to_have_text("2（0）")
    expect(dict_row(page, "", "spread").locator(".num")).to_have_text("1（1）")  # キーなしの文の単語も


def test_count_before_opening_a_project_is_the_total(page, movies):
    # プロジェクトを開く前は、今までどおり全部のプロジェクトの回数だけ
    page.goto(page.base_url)
    show_dictionary(page)
    expect(dict_row(page, "looks", "standing").locator(".num")).to_have_text("4")


def test_rename_replaces_the_inputs_of_the_open_project(page, movies):
    open_movies(page)
    show_dictionary(page)
    dict_row(page, "clothes", "cardigan").locator(".dict-rename").click()
    editor = page.locator("#dictBody .rename-input")
    editor.fill("shawl")
    editor.press("Enter")
    expect(dict_row(page, "clothes", "shawl").locator(".num")).to_have_text("1（0）")
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

    # 排他制限の kind の語句が2つある行には ⚠（kind の語句を title に出す）
    cell(page, "lalaland.png").click()
    lalaland = looks_field(page, "lalaland.png")
    lalaland.fill("standing, sitting, dancing")
    lalaland.evaluate("el => el.blur()")
    conflict = cell(page, "lalaland.png").locator(".ln.conflict")
    expect(conflict).to_have_text("looks: standing, sitting, dancing")
    expect(conflict).to_have_attribute("title", "kind .posture（排他制限）: sitting / standing")  # 一覧の並び（abc 順）
    expect(page.locator("#gridBody .ln.conflict")).to_have_count(1)


def test_face_rows_come_right_after_looks_rows(page, movies):
    # 確定タグのキーの並び（picture → 人物）。girl だけにある face は、girl の組の並びどおり looks の次
    movies.write(movies.row_index("titanic.png"), "looks: standing\nface: eyes closed, smile\nclothes: long dress, cardigan")
    movies.save()
    open_movies(page)
    show_dictionary(page)
    expect(dict_row(page, "face", "smile")).to_have_count(1)
    keys = page.locator("#dictBody tr").evaluate_all("rows => [...new Set(rows.map(r => r.dataset.key))]")
    assert keys.index("face") == keys.index("looks") + 1 and keys.index("clothes") == keys.index("face") + 1


def test_naming_a_kind_with_a_suffix_takes_in_phrases_that_end_with_it(page, movies):
    # kind を付与すると窓が出る（やめると付与しない。名前は必ず要る）。suffix の「 face」なら印は「._ face」で、
    # 「 face」で終わる語句（crying face）もいつも仲間。印をダブルクリックすると名前などを変えられる（名前は外せない）
    for name, text in [("titanic.png", "face: smiling face, crying face"), ("roman_holiday.png", "face: surprised face")]:
        movies.write(movies.row_index(name), text)
    movies.save()
    open_movies(page)
    show_dictionary(page)
    page.fill("#dictFilter", ".face")
    dict_row(page, "face", "smiling face").locator(".dict-phrase").click()
    dict_row(page, "face", "surprised face").locator(".dict-phrase").click(modifiers=["Control"])
    page.click("#dictGroupButton")
    page.click('#groupDialog button[value="cancel"]')
    expect(page.locator("#dictBody .group-badge")).to_have_count(0)
    page.click("#dictGroupButton")
    page.click('#groupDialog button[value="ok"]')  # 名前が空
    expect(page.locator("#status")).to_have_text("kind の名前を入れてください")
    expect(page.locator("#dictBody .group-badge")).to_have_count(0)

    page.click("#dictGroupButton")
    expect(page.locator('#groupDialog input[value="suffix"]')).to_be_checked()  # 初めは suffix
    page.fill("#groupName", " face")
    page.click('#groupDialog button[value="ok"]')
    for text in ["smiling face", "surprised face", "crying face"]:
        expect(dict_row(page, "face", text).locator(".group-badge")).to_have_text("._ face")

    show_images(page)
    expect(cell(page, "titanic.png").locator(".ln.conflict")).to_have_attribute(
        "title", "kind ._ face（「 face」で終わる語句も。排他制限）: smiling face / surprised face")

    show_dictionary(page)
    dict_row(page, "face", "crying face").locator(".group-badge").dblclick()
    expect(page.locator("#groupName")).to_have_value(" face")
    page.fill("#groupName", "expression")
    page.check('#groupDialog input[name="groupAffix"][value=""]')
    page.click('#groupDialog button[value="ok"]')
    expect(dict_row(page, "face", "smiling face").locator(".group-badge")).to_have_text(".expression")
    expect(dict_row(page, "face", "crying face").locator(".group-badge")).to_have_count(0)  # 決まりが無くなれば仲間でない


def test_dictionary_table_takes_the_left_40_percent_and_the_right_shows_images_a_row_and_kinds(page, movies):
    # 表は左 40%（改名の列の右端が境目。語句の列が残りの幅、段落は 60px でキーの左、ほかの列は中身の幅）。
    # 右 60% の上に画像、真ん中に画像の画面の行（簡易表示）、下に kind。
    # 見出しは「段落」「回数▲▼（▲▼）」「辞書」、kind はキーと語句の間。action だけで使うキーなしの文は、キーの列に action と出す。
    # 回数（4（0）など）は折り返さない
    page.set_viewport_size({"width": 1800, "height": 800})
    open_movies(page)
    show_dictionary(page)
    expect(page.locator("#dictBody .dict-key", has_text="action").first).to_be_visible()  # 行を描くまで待つ
    expect(page.locator("#dictBody .dict-key", has_text="（キーなし）")).to_have_count(0)
    heads = page.locator("#dictGrid thead th")
    expect(heads).to_have_text(["", "段落", "キー▲▼", "kind▲▼", "語句▲▼", "回数▲▼（▲▼）", "辞書", ""])
    expect(page.locator("#dictBody tr").first.locator("td").nth(1)).to_have_class("dict-sections")  # 行の中も同じ並び
    widths = heads.evaluate_all("ths => ths.map(th => th.getBoundingClientRect().width)")
    assert widths[0] <= 30 and abs(widths[1] - 60) <= 1  # チェックが入る分だけ / 段落は 60px
    assert widths[2] <= 130 and widths[3] <= 110 and widths[4] == max(widths)  # キーと kind は中身の幅、語句の列が残りの幅
    assert widths[5] <= 130 and widths[6] <= 50 and widths[7] <= 64  # 回数（見出しの ▲▼（▲▼））、「辞書」と、改名のボタンが入る幅
    assert page.locator("#dictBody td.num").evaluate_all("""tds => tds.every(td => {
        const range = document.createRange(); range.selectNodeContents(td); return range.getClientRects().length === 1; })""")
    rename = heads.nth(7).bounding_box()
    assert abs(rename["x"] + rename["width"] - 720) <= 20  # 境目（左の縦のスクロールバーの分だけ手前）
    images, shown, kinds = (page.locator(s).bounding_box() for s in ("#dictImages", "#dictRowView", "#dictKinds"))
    assert all(abs(box["x"] - 720) <= 2 for box in (images, shown, kinds))
    assert images["y"] < shown["y"] < kinds["y"]  # 右の上・真ん中・下


def test_choosing_a_phrase_shows_its_images_and_a_click_shows_the_row_of_the_image(page, movies):
    # 語句の行を選ぶと、開いているプロジェクトでその語句を使っている画像を右上に出す（最後に選んだ行の画像）。
    # 画像をクリックすると、右上と右下の間に、画像の画面のその行のサムネイルと段落の欄をそのまま出す（token・🤖・マーク・hint の列は
    # 出さない。別の語句を選んでも残す）。
    # 画像のダブルクリックか、出した行のサムネイルのクリックで、画像の画面のその行へ
    open_movies(page)
    show_dictionary(page)
    page.fill("#dictFilter", ".looks")
    thumbs = page.locator("#dictImageList .dict-thumb")
    expect(thumbs).to_have_count(0)
    dict_row(page, "looks", "smile").locator(".dict-phrase").click()
    expect(thumbs).to_have_count(2)
    assert sorted(thumbs.evaluate_all("els => els.map(e => e.title)")) == ["roman_holiday.png", "titanic.png"]
    dict_row(page, "looks", "dancing").locator(".dict-phrase").click(modifiers=["Control"])
    expect(thumbs).to_have_count(1)  # 最後に選んだ行（dancing）の画像
    dict_row(page, "looks", "smile").locator(".dict-phrase").click()  # 選んである行: 選択はそのままで、画像はその行の
    expect(thumbs).to_have_count(2)
    expect(page.locator("#dictBody tr.selected")).to_have_count(2)

    view = page.locator("#dictRowView")
    page.locator('#dictImageList .dict-thumb[title="roman_holiday.png"]').click()
    expect(page.locator("#dictView")).to_be_visible()  # クリックでは画面を変えない
    shown = view.locator('tbody tr[data-name="roman_holiday.png"]')
    expect(shown.locator('td.cell[data-section="girl"]')).to_contain_text("looks: sitting, smile")
    expect(view.locator("thead th")).to_have_count(5)  # サムネイルと、段落4つ
    expect(view.locator("thead th")).to_contain_text(["サムネイル", "picture", "action", "girl", "guy"])
    expect(shown.locator("td")).to_have_count(5)
    expect(view.locator("td.meta, td.marks, td.hint, th.hint-head")).to_have_count(0)  # token・マーク・hint の列は出さない

    dict_row(page, "looks", "dancing").locator(".dict-phrase").click()  # 別の語句を選んでも残す
    expect(thumbs).to_have_count(1)
    expect(shown).to_be_visible()
    shown.locator("td.thumb img").click()  # 出した行のサムネイル → 画像の画面のその行へ
    expect(page.locator("#imagesView")).to_be_visible()
    expect(page.locator('#gridBody tr[data-name="roman_holiday.png"]')).to_be_in_viewport()
    widths = lambda scope: page.locator(f'{scope} tr[data-name="roman_holiday.png"] td').evaluate_all(
        "tds => tds.map(td => [td.className, Math.round(td.getBoundingClientRect().width)])")
    in_grid = [w for w in widths("#gridBody") if w[0].split()[0] in ("thumb", "cell")]

    show_dictionary(page)
    assert widths("#dictRowView tbody") == in_grid  # 列の幅も画像の画面と同じ
    page.locator('#dictImageList .dict-thumb[title="lalaland.png"]').dblclick()  # 一覧のダブルクリックでも
    expect(page.locator("#imagesView")).to_be_visible()
    expect(page.locator('#gridBody tr[data-name="lalaland.png"]')).to_be_in_viewport()


def test_the_kind_list_colors_the_phrases_that_follow_the_rule(page, movies):
    # 右下の kind の仲間の語句: suffix・prefix の決まりに合う語句（closed eyes）には色を付け、合わないが付与した語句（wink eye）は今のまま
    movies.write(movies.row_index("titanic.png"), "face: closed eyes, wink eye")
    movies.save()
    open_movies(page)
    show_dictionary(page)
    page.fill("#dictFilter", ".face")
    dict_row(page, "face", "closed eyes").locator(".dict-phrase").click()
    dict_row(page, "face", "wink eye").locator(".dict-phrase").click(modifiers=["Control"])
    page.click("#dictGroupButton")
    page.fill("#groupName", " eyes")  # suffix（初め）
    page.click('#groupDialog button[value="ok"]')
    members = page.locator("#dictKindList .dict-kind").first.locator(".kind-member")
    expect(members).to_have_text(["closed eyes", "wink eye"])
    expect(members.first).to_have_class(re.compile(r"\brule\b"))
    expect(members.nth(1)).not_to_have_class(re.compile(r"\brule\b"))
    colors = members.evaluate_all("els => els.map(e => getComputedStyle(e).backgroundColor)")
    assert colors[0] != colors[1]


def test_the_kind_list_turns_the_exclusive_restriction_on_and_off(page, movies):
    # 右下の kind の一覧の「排他制限」のチェックで、その kind の排他制限を付け外しする（名前と前後の決まりはそのまま）
    open_movies(page)
    group_postures(page)
    show_dictionary(page)
    check = page.locator("#dictKindList .dict-kind").first.locator("input.kind-exclusive")
    badge = dict_row(page, "looks", "standing").locator(".group-badge")
    expect(check).to_be_checked()
    expect(badge).to_have_attribute("title", re.compile("（排他制限）"))
    check.uncheck()
    expect(page.locator("#status")).to_have_text("kind .posture の排他制限を外しました")
    expect(badge).not_to_have_attribute("title", re.compile("排他制限"))
    expect(badge).to_have_text(".posture")
    expect(check).not_to_be_checked()
    check.check()
    expect(page.locator("#status")).to_have_text("kind .posture に排他制限を付けました")
    expect(badge).to_have_attribute("title", re.compile("（排他制限）"))


def test_the_kind_list_deletes_a_kind_with_a_long_press(page, movies):
    # 右下の kind の「消す」: 短く押すと説明だけ、1秒長押しで kind を消す（語句は表と入力にそのまま）
    open_movies(page)
    group_postures(page)
    show_dictionary(page)
    delete = page.locator("#dictKindList .dict-kind").first.locator(".kind-delete")
    delete.click()
    expect(page.locator("#status")).to_have_text("1秒長押しすると、この kind を消します（語句はそのまま）")
    expect(page.locator("#dictKindList .dict-kind")).to_have_count(1)
    hold(page, delete)
    expect(page.locator("#status")).to_have_text("kind .posture を消しました（語句はそのまま）")
    expect(page.locator("#dictKindList .dict-kind")).to_have_count(0)
    expect(dict_row(page, "looks", "standing").locator(".group-badge")).to_have_count(0)
    show_images(page)
    expect(line_of(page, "titanic.png", "looks")).to_have_text("looks: standing, eyes closed, smile")


def test_the_kind_name_field_suggests_kind_names_and_tags(page, movies):
    # kind の窓の名前の欄: ダブルクリックで過去タグ（今ある kind の名前を先に、後ろに辞書の語句と単語）を出し、打つと fzf のように絞る。
    # 候補は欄の右に出す（欄の下の選択を覆わない）。Enter で入れるのは、ダブルクリックで出した一覧か ↑↓ で選んだとき（クリックでも入る）。
    # 打った名前のままの Enter は窓の「決める」。kind は印の形で見せ、名前だけを入れる。Esc は候補だけを閉じる（窓は閉じない）。
    # 今ある kind を選ぶと、その kind の前後の決まり（suffix など）と排他制限も窓に入る（辞書のタグを選んだときは、窓の設定はそのまま）
    open_movies(page)
    group_postures(page)
    show_dictionary(page)
    page.fill("#dictFilter", ".clothes")
    dict_row(page, "clothes", "long dress").locator(".dict-phrase").click()
    page.click("#dictGroupButton")
    name = page.locator("#groupName")
    items = page.locator("#groupDialog .suggestions li")
    expect(page.locator('#groupDialog input[name="groupAffix"][value="suffix"]')).to_be_checked()  # 初めは suffix
    page.uncheck("#groupExclusive")
    name.dblclick()
    expect(items.first).to_have_text(".posture")  # kind の名前が先
    assert items.count() > 1  # 後ろに辞書のタグ
    box, field = page.locator("#groupDialog .suggestions").bounding_box(), name.bounding_box()
    assert box["x"] >= field["x"] + field["width"] and abs(box["y"] - field["y"]) <= 1  # 欄の右
    page.keyboard.press("Enter")
    expect(name).to_have_value("posture")
    expect(page.locator('#groupDialog input[name="groupAffix"][value=""]')).to_be_checked()  # .posture は前後の決まりなし
    expect(page.locator("#groupExclusive")).to_be_checked()  # .posture は排他制限あり
    expect(page.locator("#groupDialog")).to_be_visible()

    name.fill("dres")
    expect(items).to_contain_text(["long dress", "yellow dress"])
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    expect(name).to_have_value("yellow dress")
    name.fill("dres")
    expect(items.first).to_be_visible()
    page.keyboard.press("Escape")
    expect(items.first).to_be_hidden()
    expect(page.locator("#groupDialog")).to_be_visible()  # Esc は候補だけを閉じる
    name.fill("yel")
    items.first.click()
    expect(name).to_have_value("yellow dress")
    expect(page.locator('#groupDialog input[name="groupAffix"][value=""]')).to_be_checked()  # 辞書のタグでは変えない

    name.fill("hair")  # 打った名前のままの Enter は、候補を入れずに「決める」
    expect(items.first).to_be_visible()
    page.keyboard.press("Enter")
    expect(page.locator("#groupDialog")).to_be_hidden()
    expect(dict_row(page, "clothes", "long dress").locator(".group-badge")).to_have_text(".hair")


def test_the_kind_list_shows_every_kind_and_jumps_to_its_phrases(page, movies):
    # 右下に全部の kind を表で（キー・名称（印）・排他制限・改名と消す・タグ（仲間の語句））。kind の数の説明は出さない
    # （kind が無いときだけ説明を出す）。語句をクリックすると左の表のその行を選ぶ（検索で見えなければ検索を外す）。改名で窓が出る
    open_movies(page)
    show_dictionary(page)
    expect(page.locator("#dictKindsNote")).to_have_text("kind はまだありません（左の表で語句を選び、「kindを付与する」）")
    group_postures(page)
    show_dictionary(page)
    expect(page.locator("#dictKindsNote")).to_be_hidden()
    expect(page.locator("#dictKindList thead th")).to_have_text(["キー", "名称", "排他制限", "", "タグ"])
    kind = page.locator("#dictKindList .dict-kind").first
    expect(kind.locator("td")).to_have_count(5)
    expect(kind.locator("td").first).to_have_text("looks")
    expect(kind.locator(".group-badge")).to_have_text(".posture")
    expect(kind.locator(".kind-member")).to_have_text(["sitting", "standing"])
    page.fill("#dictFilter", ".body")
    kind.locator(".kind-member", has_text="standing").click()
    expect(page.locator("#dictFilter")).to_have_value("")
    expect(page.locator("#dictBody tr.selected")).to_have_attribute("data-text", "standing")
    kind.locator(".kind-edit").click()
    expect(page.locator("#groupName")).to_have_value("posture")
    page.fill("#groupName", "pose")
    page.click('#groupDialog button[value="ok"]')
    expect(kind.locator(".group-badge")).to_have_text(".pose")


def test_rename_and_delete_buttons_do_not_wrap_in_a_narrow_window(page, movies):
    # 窓が狭くても、左の表の「改名」と、右下の kind の表の「改名」「消す」は折り返さない
    page.set_viewport_size({"width": 1280, "height": 800})
    open_movies(page)
    group_postures(page)
    show_dictionary(page)
    expect(page.locator("#dictBody .dict-rename").first).to_be_visible()
    one_line = """els => els.length > 0 && els.every(el => {
        const range = document.createRange(); range.selectNodeContents(el); return range.getClientRects().length === 1; })"""
    assert page.locator("#dictBody .dict-rename").evaluate_all(one_line)
    assert page.locator("#dictKindList .kind-edit, #dictKindList .kind-delete").evaluate_all(one_line)


def test_click_selects_one_row_and_ctrl_or_shift_select_more(page, movies):
    # ふつうのクリックはその行だけを選ぶ。Ctrl（と左端のチェック）で足し引き、Shift で範囲を足す。
    # 選んである行をふつうにクリックしても選択はそのままで、最後に選んだ行（右に画像を出す行）がその行になる
    open_movies(page)
    show_dictionary(page)
    page.fill("#dictFilter", ".looks")
    rows = page.locator("#dictBody tr")
    expect(rows.nth(2)).to_be_visible()
    selected = page.locator("#dictBody tr.selected")
    rows.nth(0).locator(".dict-phrase").click()
    rows.nth(1).locator(".dict-phrase").click()
    expect(selected).to_have_count(1)
    rows.nth(0).locator(".dict-phrase").click(modifiers=["Control"])
    expect(selected).to_have_count(2)
    rows.nth(1).locator(".dict-phrase").click()
    expect(selected).to_have_count(2)
    assert page.evaluate("() => dict.focus") == rows.nth(1).get_attribute("data-id")
    rows.nth(2).locator(".dict-phrase").click()
    expect(selected).to_have_count(1)
    rows.nth(0).locator(".dict-phrase").click(modifiers=["Shift"])
    expect(selected).to_have_count(3)
    rows.nth(2).locator(".dict-check").click()
    expect(selected).to_have_count(2)


def test_dictionary_rows_sort_and_search_tags_and_kinds_together(page, movies):
    # キー・kind・語句の見出しの ▲▼ で並べ替える（同じものをもう一度押すと元の並び。kind の無い行は後ろ）。
    # 検索の欄は、空白で区切った語の全部が、語句・キー（.looks）・kind（.posture）のどれかにあいまいに合う行（以外を表示なら合わない行）
    open_movies(page)
    group_postures(page)
    show_dictionary(page)
    page.fill("#dictFilter", "")
    texts = lambda: page.locator("#dictBody tr").evaluate_all("rows => rows.map(r => r.dataset.text)")
    default = texts()
    page.click('#dictGrid button.sort[data-sort="text"][data-dir="-1"]')
    assert page.evaluate("""() => { const t = [...document.querySelectorAll('#dictBody tr')].map(r => r.dataset.text);
        return t.every((x, i) => i === 0 || t[i - 1].localeCompare(x, undefined, {sensitivity: 'base'}) >= 0); }""")
    page.click('#dictGrid button.sort[data-sort="text"][data-dir="-1"]')
    assert texts() == default
    page.click('#dictGrid button.sort[data-sort="kind"][data-dir="1"]')
    assert texts()[:2] == ["sitting", "standing"]  # kind のある行が先（その中は元の並び）
    page.click('#dictGrid button.sort[data-sort="kind"][data-dir="1"]')

    page.fill("#dictFilter", ".looks stan")
    expect(page.locator("#dictBody .dict-phrase")).to_have_text(["standing"])
    page.fill("#dictFilter", ".posture")
    expect(page.locator("#dictBody .dict-phrase")).to_have_text(["sitting", "standing"])
    page.select_option("#dictFilterMode", "out")
    expect(page.locator("#dictBody tr .group-badge")).to_have_count(0)
    expect(page.locator("#dictBody tr").first).to_be_visible()


def test_dictionary_rows_sort_by_the_count_of_this_project_and_of_the_others(page, movies, tmp_path):
    # 回数の見出しの ▲▼（▲▼）: 前の ▲▼ は開いているプロジェクトの回数、括弧の中はほかのプロジェクトの回数で並べる
    # （▲ は少ない順、▼ は多い順。同じ数は元の並び。同じものをもう一度押すと元の並び）
    other = Api(pictag.app.test_client())
    load_scenes(other, tmp_path / "imgs" / "others", ["titanic.png"])
    other.save()
    open_movies(page)
    show_dictionary(page)
    expect(dict_row(page, "looks", "standing").locator(".num")).to_have_text("4（2）")
    texts = lambda: page.locator("#dictBody tr").evaluate_all("rows => rows.map(r => r.dataset.text)")
    counts = lambda at: [int(re.findall(r"\d+", t)[at])
                         for t in page.locator("#dictBody td.num").evaluate_all("tds => tds.map(td => td.textContent)")]
    default = texts()
    page.click('#dictGrid button.sort[data-sort="here"][data-dir="-1"]')
    assert counts(0) == sorted(counts(0), reverse=True) and counts(0)[0] == 4
    page.click('#dictGrid button.sort[data-sort="others"][data-dir="-1"]')
    assert counts(1) == sorted(counts(1), reverse=True) and texts()[0] == "standing"  # ほかのプロジェクトで2回
    page.click('#dictGrid button.sort[data-sort="others"][data-dir="1"]')
    assert counts(1) == sorted(counts(1)) and texts()[-1] == "standing"
    page.click('#dictGrid button.sort[data-sort="others"][data-dir="1"]')
    assert texts() == default


def test_a_kind_from_one_phrase_that_is_not_exclusive_marks_no_conflict(page, movies):
    # 語句1つでも kind を付与できる。排他制限を外した kind は、同じ行に仲間が2つあっても ⚠ を付けない
    movies.write(movies.row_index("titanic.png"), "body: red/long hair, wavy hair")
    movies.save()
    open_movies(page)
    show_dictionary(page)
    page.fill("#dictFilter", ".body")
    dict_row(page, "body", "red/long hair").locator(".dict-phrase").click()
    page.click("#dictGroupButton")
    expect(page.locator("#groupExclusive")).to_be_checked()  # 初めは排他制限あり
    expect(page.locator("#groupDialog label:has(#groupExclusive)")).to_have_text("排他制限")
    page.fill("#groupName", "hair")
    page.uncheck("#groupExclusive")
    page.click('#groupDialog button[value="ok"]')
    expect(dict_row(page, "body", "wavy hair").locator(".group-badge")).to_have_text("._hair")
    show_images(page)
    expect(cell(page, "titanic.png").locator(".ln.conflict")).to_have_count(0)


def test_bulk_add_reports_rows_skipped_by_a_group(page, movies):
    open_movies(page)
    group_postures(page)
    page.click("#selectVisibleButton")
    page.select_option("#bulkSection", "girl")
    page.select_option("#bulkKey", "looks")
    page.fill("#bulkText", "sitting")
    page.click('#bulkForm button[value="add"]')
    expect(page.locator("#status")).to_have_text("3 行に追加しました（2 行は、排他制限の kind の別の語句があるので足していません）")
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


def test_move_phrases_also_rewrites_other_projects_and_says_so(page, movies, tmp_path):
    # ほかの保存済みのプロジェクトの全行もすぐ書き直し、メッセージで伝える（開いているプロジェクトは保存まで書かない）
    other = Api(pictag.app.test_client())
    load_scenes(other, tmp_path / "imgs" / "others", ["titanic.png"])
    other.save()
    open_movies(page)
    page.wait_for_function("() => state.phrases.some(p => p.phrase === 'eyes closed')")  # 辞書は表のあとに読む
    page.select_option("#moveSection", "girl")
    page.select_option("#moveFrom", "looks")
    page.locator("#movePhrase").fill("eyes closed")
    page.select_option("#moveTo", "face")
    page.click("#moveForm button")
    expect(page.locator("#status")).to_have_text("girl の looks の eyes closed を face に移しました"
                                                 "（開いているプロジェクトの 1 行。保存はまだです。ほかの 1 プロジェクトの 1 行は書き換えて保存しました）")
    expect(line_of(page, "titanic.png", "face")).to_have_text("face: eyes closed")


def test_replace_phrases_of_a_section_when_moving_to_the_same_key(page, movies):
    # 「キーを移す」で移す先に同じキーを選ぶと、置換後の語句の欄が出てボタンが「置換」になる。置換後の語句は今ある語句でもよい
    open_movies(page)
    page.wait_for_function("() => state.phrases.some(p => p.phrase === 'smile')")  # 辞書は表のあとに読む
    page.select_option("#moveSection", "girl")
    page.select_option("#moveFrom", "looks")
    to_phrase, button = page.locator("#moveNew"), page.locator("#moveForm button")
    expect(page.locator("#moveTo")).not_to_have_value("looks")  # 同じキーは、選ぶまでは選ばない
    expect(to_phrase).to_be_hidden()
    expect(button).to_have_text("移す")
    page.locator("#movePhrase").fill("eyes closed")
    page.select_option("#moveTo", "looks")
    expect(to_phrase).to_be_visible()
    expect(button).to_have_text("置換")
    to_phrase.fill("ｓｍｉ")  # 英字だけの欄。候補はその段落のそのキーの語句
    expect(to_phrase).to_have_value("smi")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("smile")
    to_phrase.press("Enter")  # 候補を選ぶ（行末に付く「, 」は送るときに外す）
    to_phrase.press("Enter")  # 置換
    expect(page.locator("#status")).to_have_text(
        "girl の looks の eyes closed を smile に置き換えました（開いているプロジェクトの 1 行。保存はまだです）")
    expect(line_of(page, "titanic.png", "looks")).to_have_text("looks: standing, smile")  # 今ある smile にまとめる
    expect(line_of(page, "roman_holiday.png", "looks")).to_have_text("looks: sitting, smile")
    expect(page.locator("#saveButton")).to_have_text("保存 *")
    expect(page.locator("#movePhrase")).to_have_value("")
    expect(to_phrase).to_have_value("")
    expect(page.locator("#moveTo")).to_have_value("looks")  # 続けて置換できる
    page.select_option("#moveTo", "body")
    expect(to_phrase).to_be_hidden()
    expect(button).to_have_text("移す")
    page.select_option("#moveFrom", "body")  # 移す元を選び直して同じキーになるときは、別のキーにする
    expect(page.locator("#moveTo")).not_to_have_value("body")
    expect(to_phrase).to_be_hidden()
