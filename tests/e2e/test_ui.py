"""画面操作（Playwright）"""
import re
from datetime import datetime

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


def count(caption):
    """テスト用のトークナイザーでのトークン数"""
    return TokenCounter(word_tokenizer()).count(caption)


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


def filled(page, name, section="girl"):
    """欄の値のある行（確定タグの空のキーは除く）"""
    return cell(page, name, section).locator(".ln:not(.empty)")


def open_editor(page, name, section="girl"):
    """入力欄を開き、「その他」の欄（確定タグの無い段落は、ただ1つの欄）を返す"""
    cell(page, name, section).click()
    return field(page, name, "", section)


def field(page, name, key, section="girl"):
    """開いた入力欄の、キーの欄（key が空なら「その他」の欄）"""
    return cell(page, name, section).locator(f'textarea[data-key="{key}"]')


def write(page, name, text, section="girl"):
    """入力欄に書いて確定する（キーの欄は空にし、全部を「その他」の欄に書く。「その他」の無い段落（picture）は、
    キーの行をそのキーの欄に書く。フォーカスを外すと送信する）"""
    other = open_editor(page, name, section)
    cell(page, name, section).locator("textarea").first.wait_for()
    for key_field in cell(page, name, section).locator('textarea:not([data-key=""])').all():
        key_field.fill("")
    if other.count():
        other.fill(text)
    else:
        for line in text.split("\n"):
            key, _, value = line.partition(":")
            field(page, name, key.strip(), section).fill(value.strip())
    page.evaluate("document.activeElement.blur()")
    expect(filled(page, name, section)).to_have_text(text.split("\n"))


def tokens_of(page, name):
    return row(page, name).locator(".tokens")


def section_names(page):
    return page.locator("#gridHead .section-name").all_inner_texts()


def wait_for_phrase(page, phrase):
    page.wait_for_function("phrase => state.phrases.some(p => p.phrase === phrase)", arg=phrase)


def wait_for_word(page, word):
    page.wait_for_function("word => state.words.some(w => w.word === word)", arg=word)


# ---- テスト ----

def test_browse_button_loads_the_chosen_folder(page, imgs, monkeypatch):
    monkeypatch.setattr(pictag, "ask_directory", lambda initial: str(imgs))  # 窓は開かず、選んだことにする
    page.goto(page.base_url)
    page.click("#browseButton")
    expect(page.locator("#gridBody tr")).to_have_count(3)
    expect(page.locator("#imageDir")).to_have_value(str(imgs))


def test_browse_cancelled_leaves_things_as_they_are(page, monkeypatch):
    monkeypatch.setattr(pictag, "ask_directory", lambda initial: "")
    page.goto(page.base_url)
    page.click("#browseButton")
    expect(page.locator("#status")).to_have_text("フォルダの選択をやめました")
    expect(page.locator("#browseButton")).to_be_enabled()
    expect(page.locator("#emptyNote")).to_be_visible()


def test_load_shows_rows_sections_and_template_keys(page, imgs):
    load_dir(page, imgs)
    assert section_names(page) == ["picture", "action", "girl", "guy"]
    expect(page.locator("#gridBody tr")).to_have_count(3)
    expect(tokens_of(page, "a.png")).to_have_text("0 / 507")
    expect(page.locator('#projectSelect option[value="proj"]')).to_be_attached()

    # 確定タグのキーは空の欄にも薄く出る（action は確定タグなし）
    expect(cell(page, "a.png", "picture").locator(".ln.empty")).to_have_text(["place:", "characters:", "vibes:", "view:", "extra:"])
    expect(cell(page, "a.png").locator(".ln.empty")).to_have_text(["looks:", "clothes:", "body:"])
    expect(cell(page, "a.png", "action").locator(".ln")).to_have_count(0)


def test_fixed_sections_have_no_remove_button(page, imgs):
    load_dir(page, imgs)
    expect(page.locator('#gridHead th[data-section="picture"] .remove-section')).to_have_count(0)
    expect(page.locator('#gridHead th[data-section="action"] .remove-section')).to_have_count(0)
    expect(page.locator('#gridHead th[data-section="girl"] .remove-section')).to_have_count(1)


def test_editor_puts_each_template_key_in_its_own_field_under_its_name(page, imgs, tool):
    load_dir(page, imgs)
    write(page, "a.png", "body: long hair\ngirl is smiling")
    open_editor(page, "a.png")
    expect(cell(page, "a.png").locator(".field-key")).to_have_text(["looks:", "clothes:", "body:", "その他:"])
    expect(field(page, "a.png", "body")).to_have_value("long hair")  # キーの後ろの値だけ
    expect(field(page, "a.png", "")).to_have_value("girl is smiling")  # キーの無い文などは「その他」
    expect(field(page, "a.png", "looks")).to_be_focused()  # 最初の値の無いキー

    field(page, "a.png", "looks").press_sequentially("standing")
    field(page, "a.png", "looks").evaluate("el => el.blur()")
    text = "looks: standing\nbody: long hair\ngirl is smiling"
    expect(filled(page, "a.png")).to_have_text(text.split("\n"))
    expect(cell(page, "a.png").locator(".ln.empty")).to_have_text(["clothes:"])
    expect(tokens_of(page, "a.png")).to_have_text(f"{count(caption_of(text))} / 507")
    # 値の無いキーは保存しない
    assert tool.df.set_index("サムネイル").loc["a.png", "girl"] == text


def test_moving_between_fields_keeps_the_editor_open(page, imgs):
    load_dir(page, imgs)
    open_editor(page, "a.png")
    field(page, "a.png", "looks").fill("standing")
    body = field(page, "a.png", "body")
    body.click()  # 欄を移っても閉じない
    body.press_sequentially("long hair")
    body.press("Enter")  # キーの欄の改行は、語句の区切り
    body.press_sequentially("black hair")
    cell(page, "a.png").locator(".field-key", has_text="clothes").click()  # キーの名前を押すと、その欄へ（閉じない）
    expect(field(page, "a.png", "clothes")).to_be_focused()
    field(page, "a.png", "clothes").press("Escape")
    expect(filled(page, "a.png")).to_have_text(["looks: standing", "body: long hair, black hair"])


def test_key_lines_written_in_the_other_field_join_their_key(page, imgs):
    # 「その他」に書いた確定タグのキーの行は、そのキーにまとめる（確定タグに無いキーの行と文は、そのまま後ろに）
    load_dir(page, imgs)
    open_editor(page, "a.png")
    field(page, "a.png", "looks").fill("standing")
    other = field(page, "a.png", "")
    other.fill("girl is smiling\nlooks: smiling\neyes: blue eyes")
    other.evaluate("el => el.blur()")
    expect(filled(page, "a.png")).to_have_text(["looks: standing, smiling", "girl is smiling", "eyes: blue eyes"])

    open_editor(page, "a.png")
    expect(field(page, "a.png", "looks")).to_have_value("standing, smiling")
    expect(field(page, "a.png", "")).to_have_value("girl is smiling\neyes: blue eyes")


def test_cell_shows_values_under_their_key_like_the_editor(page, imgs):
    # クリックする前も入力欄と同じく、キーの名前の下に値（値の無いキーは名前だけ）。キーの無い文などは「その他:」の下
    load_dir(page, imgs)
    write(page, "a.png", "looks: standing\nbody: long hair\ngirl is smiling")
    looks = cell(page, "a.png").locator(".ln", has_text="looks:")
    expect(looks.locator(".key")).to_have_text("looks:")
    expect(looks.locator(".val")).to_have_text("standing")
    key, value = looks.locator(".key").bounding_box(), looks.locator(".val").bounding_box()
    assert value["y"] >= key["y"] + key["height"] - 0.5  # 値はキーの名前の次の行
    expect(cell(page, "a.png").locator(".ln.empty")).to_have_text(["clothes:"])
    expect(cell(page, "a.png").locator(".ln.empty .val")).to_have_count(0)
    expect(cell(page, "a.png").locator(".others")).to_have_text("その他:")

    write(page, "b.png", "looks: standing")
    expect(cell(page, "b.png").locator(".others")).to_have_count(0)  # ほかの行が無ければ出さない
    write(page, "a.png", "pose: standing", section="action")
    expect(cell(page, "a.png", "action").locator(".key")).to_have_count(0)  # 確定タグの無い段落は今のまま


def test_picture_editor_has_no_other_field_because_of_extra(page, imgs):
    # 確定タグに extra のある段落（picture）は「その他」の欄を出さない。前に書いたほかの行があるときだけ、消えないように出す
    load_dir(page, imgs)
    cell(page, "a.png", "picture").locator(".text").click()
    expect(cell(page, "a.png", "picture").locator(".field-key")).to_have_text(["place:", "vibes:", "view:", "extra:"])
    expect(field(page, "a.png", "", "picture")).to_have_count(0)
    expect(field(page, "a.png", "place", "picture")).to_be_focused()
    page.keyboard.press("Escape")

    page.select_option("#bulkSection", "picture")  # 入力欄を開いた行は選択状態
    page.select_option("#bulkKey", "")
    page.locator("#bulkText").fill("an old photo")
    page.click('#bulkForm button[value="add"]')
    expect(cell(page, "a.png", "picture").locator(".others")).to_have_text("その他:")
    cell(page, "a.png", "picture").locator(".text").click()
    expect(field(page, "a.png", "", "picture")).to_have_value("an old photo")


def test_edit_updates_tokens_and_preview_then_saves(page, imgs, tool):
    load_dir(page, imgs)
    text = "looks: standing\nbody: long hair, black hair"
    write(page, "a.png", text)

    caption = caption_of(text)
    assert caption == "picture:\n  - characters: 1 girl\n\ngirl:\n  - looks: standing\n  - body: long black hair"
    expect(tokens_of(page, "a.png")).to_have_text(f"{count(caption)} / 507")
    expect(tokens_of(page, "a.png")).to_have_attribute("title", caption)
    expect(page.locator("#saveButton")).to_have_text("保存 *")

    page.click("#saveButton")
    expect(page.locator("#status")).to_have_text("保存しました")
    expect(page.locator("#saveButton")).to_have_text("保存")
    assert (tool.captions_dir / "a.caption").read_text(encoding="utf-8") == caption


def test_ctrl_s_saves(page, imgs, tool):
    load_dir(page, imgs)
    write(page, "b.png", "looks: standing")
    page.keyboard.press("Control+s")
    expect(page.locator("#status")).to_have_text("保存しました")
    assert (tool.captions_dir / "b.caption").read_text(encoding="utf-8") == caption_of("looks: standing")


def test_messages_show_the_time(page, imgs):
    page.clock.set_fixed_time(datetime(2026, 10, 19, 9, 5, 3))
    load_dir(page, imgs)
    expect(page.locator("#status")).to_have_text("「proj」を開きました（3 枚）")
    expect(page.locator("#statusTime")).to_have_text("09:05:03")

    page.clock.set_fixed_time(datetime(2026, 10, 19, 14, 32, 5))
    page.click("#saveButton")
    expect(page.locator("#status")).to_have_text("保存しました")
    expect(page.locator("#statusTime")).to_have_text("14:32:05")  # 出たままでも、いつのメッセージか分かる


def test_suggestion_completes_phrase_of_the_line_key(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_phrase(page, "long hair")

    editor = open_editor(page, "a.png")
    editor.fill("")
    editor.press_sequentially("body: lh")
    expect(page.locator("#suggestions li.active")).to_contain_text("long hair")
    editor.press("Enter")
    assert editor.input_value() == "body: long hair, "
    editor.evaluate("el => el.blur()")
    expect(filled(page, "a.png")).to_have_text(["body: long hair"])


def test_phrase_chosen_inside_a_line_is_separated_by_commas(page, imgs):
    # キーのある行の途中で語句を選ぶと、カンマの直後なら前に空白、後ろに語が続けばカンマで区切る（行末は今どおり ", "）
    load_dir(page, imgs)
    write(page, "b.png", "looks: short hair")
    wait_for_phrase(page, "short hair")

    editor = open_editor(page, "a.png")
    for at in [len("looks: cool,"), len("looks: cool, ")]:  # カンマの直後 / カンマと空白の後
        editor.fill("looks: cool, 40 yo")
        editor.evaluate(f"el => el.setSelectionRange({at}, {at})")
        editor.press("ArrowRight")
        editor.press("ArrowLeft")  # カーソルを動かすと候補が出る
        expect(page.locator("#suggestions:visible li.active")).to_contain_text("short hair")
        editor.press("Tab")
        assert editor.input_value() == "looks: cool, short hair, 40 yo"


def test_choosing_a_candidate_replaces_the_selected_text(page, imgs):
    # 範囲を選んだ状態で候補を選ぶと、選んだ文字と置き換える（区切りは行の途中で選んだときと同じ）
    load_dir(page, imgs)
    write(page, "b.png", "looks: long hair")
    wait_for_phrase(page, "long hair")

    editor = open_editor(page, "a.png")
    editor.fill("looks: cool, short hair, 40 yo")
    start = len("looks: cool, ")
    editor.evaluate(f"el => el.setSelectionRange({start}, {start})")
    for _ in "short hair":
        editor.press("Shift+ArrowRight")  # short hair を選ぶ
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("long hair")
    editor.press("Tab")
    assert editor.input_value() == "looks: cool, long hair, 40 yo"


def test_line_start_does_not_suggest_phrases_already_in_the_cell(page, imgs):
    # 行頭の「キー: 語句」の候補に、その欄の同じキーにもう入っている語句は出さない
    load_dir(page, imgs)
    write(page, "b.png", "looks: cold eyes")
    write(page, "a.png", "looks: cool")
    wait_for_phrase(page, "cool")

    editor = open_editor(page, "a.png")
    editor.press("Control+End")
    editor.press("Enter")
    editor.press_sequentially("co")
    suggestions = page.locator("#suggestions:visible")
    expect(suggestions).to_contain_text("looks: cold eyes")
    expect(suggestions).not_to_contain_text("looks: cool")


def test_suggestion_at_line_start_adds_key_and_phrase(page, imgs):
    # 「その他」の欄の行頭で「キー: 語句」を選ぶと、確定タグのキーならその欄に足す（ほかのキーは今までどおりその行に）
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair\neyes: blue eyes")
    wait_for_phrase(page, "blue eyes")

    editor = open_editor(page, "a.png")
    editor.press_sequentially("lh")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("body: long hair")
    editor.press("Tab")
    expect(field(page, "a.png", "body")).to_have_value("long hair")
    assert editor.input_value() == ""  # 打ちかけは消す
    expect(editor).to_be_focused()

    editor.press_sequentially("blue")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("eyes: blue eyes")
    editor.press("Tab")
    assert editor.input_value() == "eyes: blue eyes"


def test_key_chosen_in_the_other_field_moves_to_its_field(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_phrase(page, "long hair")

    editor = open_editor(page, "a.png")
    editor.press_sequentially("bod")
    expect(page.locator("#suggestions:visible li.active")).to_have_text("body:")
    editor.press("Tab")
    expect(field(page, "a.png", "body")).to_be_focused()  # そのキーの欄へ移り、その語句の候補を出す
    assert editor.input_value() == ""  # 打ちかけは消す
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("long hair")


def test_key_field_suggests_phrases_of_its_key(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_phrase(page, "long hair")

    open_editor(page, "a.png")
    looks = field(page, "a.png", "looks")
    looks.press_sequentially("lh")  # looks の欄 → 候補は looks の語句だけ（無い）
    expect(page.locator("#suggestions")).to_be_hidden()
    body = field(page, "a.png", "body")
    body.press_sequentially("lh")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("long hair")
    body.press("Enter")
    assert body.input_value() == "long hair, "
    body.evaluate("el => el.blur()")
    expect(filled(page, "a.png")).to_have_text(["looks: lh", "body: long hair"])


def test_enter_after_accepting_makes_a_new_line(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair, bare hands")
    wait_for_phrase(page, "bare hands")

    editor = open_editor(page, "a.png")
    editor.fill("")
    editor.press_sequentially("body: lh")
    editor.press("Enter")  # 確定（", " が付き、残りの候補が出る）
    editor.press("Enter")  # 打ちかけが無いので改行
    editor.press_sequentially("looks: standing")
    assert editor.input_value() == "body: long hair, \nlooks: standing"


def test_down_on_the_last_suggestion_closes_them_and_moves_down(page, imgs):
    # 候補の一番下で ↓ を押すと、候補を閉じて、ふつうのテキストのように下の行へカーソルが動く
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair, bare hands")
    wait_for_phrase(page, "bare hands")

    editor = open_editor(page, "a.png")
    editor.fill("body: \nlooks: standing")
    editor.evaluate("el => el.setSelectionRange(6, 6)")  # body: の行末
    editor.press_sequentially("a")
    expect(page.locator("#suggestions:visible li")).to_have_count(2)
    editor.press("ArrowDown")  # 一番下の候補へ
    expect(page.locator("#suggestions li").last).to_have_class(re.compile(r"\bactive\b"))
    editor.press("ArrowDown")  # 一番下で ↓
    expect(page.locator("#suggestions")).to_be_hidden()
    assert editor.evaluate("el => el.value.slice(0, el.selectionStart).split('\\n').length") == 2  # 下の行
    assert editor.input_value() == "body: a\nlooks: standing"


def test_phrase_suggestions_are_split_by_kind(page, imgs):
    # 語句の候補は同じ種類の段落で使ったものだけ。女性（girl・woman）・男性（guy・man・boy）はそれぞれまとめ、ほかは種類ごと
    load_dir(page, imgs)
    for name in ["woman", "dog"]:
        page.fill("#sectionName", name)
        page.click("#sectionForm button")
    expect(page.locator("#gridHead .section-name")).to_have_count(6)
    write(page, "a.png", "looks: standing")
    write(page, "a.png", "looks: muscular", section="guy")
    wait_for_phrase(page, "muscular")
    suggestions = page.locator("#suggestions:visible")

    for section, shown, other in [("girl", "standing", "muscular"), ("woman", "standing", "muscular"),
                                  ("guy", "muscular", "standing")]:
        open_editor(page, "b.png", section).fill("looks: ")
        expect(suggestions).to_contain_text(shown)
        expect(suggestions).not_to_contain_text(other)
    open_editor(page, "b.png", "dog").fill("looks: ")  # dog ではまだ使っていない
    expect(page.locator("#suggestions")).to_be_hidden()

    editor = open_editor(page, "b.png")  # 行頭の「キー: 語句」も同じ
    editor.fill("")
    editor.press_sequentially("mus")
    expect(page.locator("#suggestions")).to_be_hidden()
    editor.fill("")
    editor.evaluate("el => el.blur()")

    row(page, "a.png").locator("td.meta").click()  # 一括入力も同じ
    page.select_option("#bulkSection", "guy")
    page.select_option("#bulkKey", "looks")
    page.locator("#bulkText").press_sequentially("s")
    expect(suggestions).to_contain_text("muscular")
    expect(suggestions).not_to_contain_text("standing")


def test_action_suggests_words_inside_a_sentence(page, imgs):
    load_dir(page, imgs)
    write(page, "a.png", "girl spread arms\nguy grab girl's waist", section="action")
    wait_for_word(page, "spread")

    editor = open_editor(page, "b.png", section="action")
    editor.press_sequentially("girl sp")
    expect(page.locator("#suggestions li.active")).to_contain_text("spread")
    editor.press("Enter")
    assert editor.input_value() == "girl spread, "  # 行末なら ", "（欄を離れると行末のカンマは消える）
    editor.press_sequentially("wa")
    expect(page.locator("#suggestions li.active")).to_contain_text("waist")


def write_spread(page):
    """action に spread（2回）と、ほかの単語（1回ずつ）を入れる"""
    write(page, "a.png", "girl spread arms", section="action")
    write(page, "c.png", "guy spread legs", section="action")
    wait_for_word(page, "legs")


def test_two_spaces_after_a_word_show_words_and_a_third_hides_them(page, imgs):
    load_dir(page, imgs)
    write_spread(page)

    editor = open_editor(page, "b.png", section="action")
    suggestions = page.locator("#suggestions")
    shown = page.locator("#suggestions:visible li.active")  # しまった一覧の項目は残るので、見えているものだけ
    editor.press_sequentially("girl ")
    expect(suggestions).to_be_hidden()  # スペース1つでは出さない
    editor.press_sequentially(" ")
    expect(shown).to_contain_text("spread")  # 打たなくても、よく使う順
    editor.press_sequentially(" ")
    expect(suggestions).to_be_hidden()  # 3つ目でしまう
    editor.press("Backspace")
    expect(shown).to_contain_text("spread")
    editor.press("Tab")
    assert editor.input_value() == "girl spread, "  # 2つのスペースは1つにまとめる


def test_two_spaces_inside_a_sentence_insert_a_word_between(page, imgs):
    load_dir(page, imgs)
    write_spread(page)

    editor = open_editor(page, "b.png", section="action")
    editor.fill("girl arms")
    editor.evaluate("el => el.setSelectionRange(5, 5)")  # girl␣|arms
    editor.press_sequentially(" ")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("spread")
    editor.press("Tab")
    assert editor.input_value() == "girl spread arms"  # 後ろの語とは空白1つで分ける


def test_word_chosen_before_a_comma_keeps_that_comma(page, imgs):
    load_dir(page, imgs)
    write_spread(page)

    editor = open_editor(page, "b.png", section="action")
    editor.fill("girl spread, ")
    editor.evaluate("el => el.setSelectionRange(11, 11)")  # girl spread|,
    editor.press_sequentially(" ar")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("arms")
    editor.press("Tab")
    assert editor.input_value() == "girl spread arms, "  # 後ろにカンマがあれば足さない（重ねない）


def test_spaces_do_not_hide_phrase_suggestions_of_a_key(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_phrase(page, "long hair")

    editor = open_editor(page, "a.png")
    editor.fill("")
    editor.press_sequentially("body:   ")  # キーのある行は、スペース3つでも今のまま出す
    expect(page.locator("#suggestions li.active")).to_contain_text("long hair")


def test_bulk_keyless_text_shows_words_after_two_spaces(page, imgs):
    load_dir(page, imgs)
    write_spread(page)
    row(page, "b.png").locator("td.meta").click()
    page.select_option("#bulkSection", "action")
    bulk = page.locator("#bulkText")
    bulk.press_sequentially("girl  ")
    expect(page.locator("#suggestions:visible li.active")).to_contain_text("spread")
    bulk.press("Tab")
    assert bulk.input_value() == "girl spread, "


def test_leaving_the_editor_tidies_commas_and_spaces(page, imgs):
    load_dir(page, imgs)
    editor = open_editor(page, "a.png", section="action")
    editor.fill("\n".join([
        "a,, b", "c, , d", "e,  ,f",  # カンマの連なりは1つに
        "g,h", "i,  j", "k , l",      # カンマの後ろは空白1つ
        ", m  n,",                    # 頭のカンマは消す。語の間の空白は1つ（行末のカンマは、action の文では「.」）
    ]))
    editor.evaluate("el => el.blur()")
    expect(filled(page, "a.png", "action")).to_have_text(["a, b", "c, d", "e, f", "g, h", "i, j", "k, l", "m n."])

    editor = open_editor(page, "a.png")
    editor.fill("looks:  , standing,,smiling\nbody: long  hair ,  bare hands,")
    editor.evaluate("el => el.blur()")
    expect(filled(page, "a.png")).to_have_text(["looks: standing, smiling", "body: long hair, bare hands"])


def test_leaving_the_editor_merges_a_repeated_key(page, imgs):
    # 行頭で重なった同じキーは1つにまとめる（looks: looks : → looks:。値の無いキーは保存しない）
    load_dir(page, imgs)
    editor = open_editor(page, "a.png")
    editor.fill("looks: looks :\nclothes:clothes: clothes : skirt\nbody: body: long hair")
    editor.evaluate("el => el.blur()")
    expect(filled(page, "a.png")).to_have_text(["clothes: skirt", "body: long hair"])
    expect(cell(page, "a.png").locator(".ln.empty")).to_have_text(["looks:"])


def test_leaving_action_ends_sentences_with_periods(page, imgs):
    # action のキーの無い文だけ: 「, .」と行末のカンマは「.」（最後の行も）。キーのある行とほかの段落は行末のカンマを消す
    load_dir(page, imgs)
    editor = open_editor(page, "a.png", section="action")
    editor.fill("girl spread arms, \nguy dancing, .\ngirl smiles,. guy waves\npose: standing, \nboy jumps,")
    editor.evaluate("el => el.blur()")
    expect(filled(page, "a.png", "action")).to_have_text(
        ["girl spread arms.", "guy dancing.", "girl smiles. guy waves", "pose: standing", "boy jumps."])

    editor = open_editor(page, "a.png")
    editor.fill("smiling, ")
    editor.evaluate("el => el.blur()")
    expect(filled(page, "a.png")).to_have_text(["smiling"])


def test_text_is_tidied_to_english(page, imgs):
    # 英字にそろえる: 全角の英数字・記号・空白は半角、アクセントは外す、「、」「。」と曲がった引用符・ダッシュは英字の記号、タブは空白。
    # そろえても英字（半角の英数字・記号・空白。入力欄は改行も）にならないかな・漢字などは消す
    load_dir(page, imgs)
    assert page.evaluate("englishOnly('ｌｏｎｇ　ｈａｉｒ，ｃａｆé、girl’s “wave” — ok。\\t黒髪\\nnext 😀')") == (
        "long hair,cafe,girl's \"wave\" - ok. \nnext ")
    assert page.evaluate("englishOnly('a\\nb', false)") == "ab"  # 1行の欄は改行も消す


def test_fields_for_captions_take_english_only(page, imgs):
    # キャプションや辞書に入る欄は、打ったそばから英字にそろえ、英字以外を消したときだけ知らせる。IME の変換中は待つ
    load_dir(page, imgs)
    editor = open_editor(page, "a.png", section="action")
    editor.fill("girl ｓｍｉｌｅｓ")
    expect(editor).to_have_value("girl smiles")
    expect(page.locator("#status")).not_to_have_text(re.compile("英字以外"))  # 半角に直しただけなら知らせない
    editor.fill("girl smiles 笑顔")
    expect(editor).to_have_value("girl smiles ")
    expect(page.locator("#status")).to_have_text("英字以外は入れられません（笑顔 を外しました）")

    editor.fill("")
    editor.evaluate("el => { el.value = 'あ'; el.dispatchEvent(new InputEvent('input', {isComposing: true})); }")
    expect(editor).to_have_value("あ")  # 変換中は触らない
    editor.evaluate("el => el.dispatchEvent(new CompositionEvent('compositionend'))")
    expect(editor).to_have_value("")  # 確定したら直す
    page.keyboard.press("Escape")

    open_editor(page, "a.png")
    field(page, "a.png", "looks").fill("ｓｔａｎｄｉｎｇ")
    expect(field(page, "a.png", "looks")).to_have_value("standing")
    page.keyboard.press("Escape")

    for selector in ["#bulkText", "#movePhrase", "#sectionName"]:  # 一括入力（入力欄を開いた行は選択中）・キーを移す・段落を追加
        page.locator(selector).fill("ｄｏｇ犬")
        expect(page.locator(selector)).to_have_value("dog")
    page.once("dialog", lambda dialog: dialog.accept("ｂｏｙ"))  # 段落の改名
    page.locator('#gridHead th[data-section="guy"] .section-name').dblclick()
    expect(page.locator('#gridHead th[data-section="boy"]')).to_be_attached()


def test_editor_shows_space_and_newline_marks_that_are_not_text(page, imgs):
    load_dir(page, imgs)
    write(page, "a.png", "body: long hair")
    editor = open_editor(page, "a.png")
    marks = cell(page, "a.png").locator(".ws-marks")
    expect(marks).to_have_count(4)  # 欄ごとに重ねる
    expect(marks.locator(".sp")).to_have_count(1)  # 開いたときから出す
    editor.fill("girl  is\nsmiling")
    expect(marks.locator(".sp")).to_have_count(3)
    expect(marks.locator(".nl")).to_have_count(1)
    assert editor.input_value() == "girl  is\nsmiling"  # 印は文字に入らない
    editor.evaluate("el => el.blur()")
    expect(marks).to_have_count(0)  # 表示中の欄には出さない


def test_marks_wrap_where_the_editor_wraps(page, imgs):
    load_dir(page, imgs)
    editor = open_editor(page, "a.png", section="action")
    editor.fill(", ".join(["girl spread arms wide"] * 8))  # 何行にも折り返す長さ
    # 印の層を中身の高さにすると、入力欄と同じ高さになる（同じ所で折り返している）
    heights = editor.evaluate("""el => {
        const layer = el.nextElementSibling;
        layer.style.bottom = 'auto';
        return [el.offsetHeight, layer.offsetHeight];
    }""")
    assert heights[0] > 100 and heights[0] == heights[1]


def test_bulk_text_shows_space_marks_and_clears_them(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_phrase(page, "long hair")
    row(page, "a.png").locator("td.meta").click()
    page.select_option("#bulkSection", "girl")
    page.select_option("#bulkKey", "body")
    page.locator("#bulkText").press_sequentially("long hair")
    marks = page.locator("#bulkForm .ws-marks .sp")
    expect(marks).to_have_count(1)
    page.click('#bulkForm button[value="add"]')
    expect(filled(page, "a.png")).to_have_text(["body: long hair"])
    expect(marks).to_have_count(0)  # 欄を空にしたら印も消す


def test_freeze_puts_words_into_shared_dictionary(page, imgs, tool):
    load_dir(page, imgs)
    write(page, "a.png", "body: long hair")
    page.once("dialog", lambda dialog: dialog.accept())
    page.click("#freezeButton")
    expect(page.locator("#status")).to_have_text("共用辞書に 1 件入れました")
    assert {"section": "girl", "key": "body", "phrase": "long hair"} in tool.shared["phrases"]


def test_bulk_add_and_remove_on_selected_rows(page, imgs):
    load_dir(page, imgs)
    row(page, "a.png").locator("td.meta").click()
    row(page, "c.png").locator("td.meta").click(modifiers=["Shift"])
    expect(page.locator("#selectionInfo")).to_have_text("選択 3 行")

    page.select_option("#bulkSection", "girl")
    page.select_option("#bulkKey", "looks")
    page.fill("#bulkText", "standing")
    page.click('#bulkForm button[value="add"]')
    expect(page.locator("#status")).to_have_text("3 行に追加しました")
    for name in ["a.png", "b.png", "c.png"]:
        expect(filled(page, name)).to_have_text(["looks: standing"])

    row(page, "b.png").locator("td.meta").click(modifiers=["Control"])
    expect(page.locator("#selectionInfo")).to_have_text("選択 2 行")
    page.fill("#bulkText", "standing")
    page.click('#bulkForm button[value="remove"]')
    expect(filled(page, "a.png")).to_have_count(0)
    expect(filled(page, "b.png")).to_have_text(["looks: standing"])
    expect(filled(page, "c.png")).to_have_count(0)


def test_bulk_section_choice_survives_save(page, imgs):
    load_dir(page, imgs)
    row(page, "a.png").locator("td.meta").click()
    page.select_option("#bulkSection", "girl")
    page.click("#saveButton")
    expect(page.locator("#status")).to_have_text("保存しました")
    expect(page.locator("#bulkSection")).to_have_value("girl")


def test_sections_add_rename_remove(page, imgs):
    load_dir(page, imgs)
    page.fill("#sectionName", "dog")
    page.click("#sectionForm button")
    expect(page.locator("#gridHead .section-name")).to_have_count(5)
    assert section_names(page) == ["picture", "action", "girl", "guy", "dog"]
    # 足した段落も人物用の確定タグを使う
    expect(cell(page, "a.png", "dog").locator(".ln.empty")).to_have_text(["looks:", "clothes:", "body:"])

    page.once("dialog", lambda dialog: dialog.accept("dog A"))
    page.locator('#gridHead th[data-section="dog"] .section-name').dblclick()
    expect(page.locator('#gridHead th[data-section="dog A"]')).to_be_attached()

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator('#gridHead th[data-section="dog A"] .remove-section').click()
    expect(page.locator("#gridHead .section-name")).to_have_count(4)


def fold_button(page, section):
    return page.locator(f'#gridHead th[data-section="{section}"] .fold-section')


def test_section_column_folds_narrow_and_opens_again(page, imgs):
    # 見出しの右端の ◀ で列を細く畳み（入力のある行に ●）、▶ で元の幅に戻す
    load_dir(page, imgs)
    write(page, "a.png", "looks: standing")
    width = "el => el.getBoundingClientRect().width"
    expect(fold_button(page, "girl")).to_have_text("◀")
    fold_button(page, "girl").click()
    expect(fold_button(page, "girl")).to_have_text("▶")
    expect(cell(page, "a.png")).to_have_text("●")
    expect(cell(page, "b.png")).to_have_text("")
    assert cell(page, "a.png").evaluate(width) < 40

    fold_button(page, "girl").click()
    expect(filled(page, "a.png")).to_have_text(["looks: standing"])
    assert cell(page, "a.png").evaluate(width) >= 220


def test_clicking_a_folded_cell_opens_the_column_and_starts_editing(page, imgs):
    load_dir(page, imgs)
    fold_button(page, "guy").click()
    expect(fold_button(page, "guy")).to_have_text("▶")
    cell(page, "b.png", "guy").click()
    expect(field(page, "b.png", "looks", "guy")).to_be_focused()
    expect(fold_button(page, "guy")).to_have_text("◀")


def test_folded_columns_are_remembered_per_project(page, imgs, tmp_path):
    load_dir(page, imgs)
    fold_button(page, "guy").click()
    expect(fold_button(page, "guy")).to_have_text("▶")
    load_dir(page, imgs)  # 読み込み直しても畳んだまま
    expect(fold_button(page, "guy")).to_have_text("▶")
    load_dir(page, make_images(tmp_path / "imgs" / "other", {"x.png": (100, 100)}))  # ほかのプロジェクトは開いたまま
    expect(fold_button(page, "guy")).to_have_text("◀")


def test_folding_picture_keeps_the_thumbnail_size(page, imgs):
    # サムネイルは picture の欄の高さに合わせるが、畳んだ picture には合わせない（畳む前の大きさのまま）
    load_dir(page, imgs)
    thumb = row(page, "a.png").locator("td.thumb img")
    size = thumb.evaluate("el => el.getBoundingClientRect().width")
    fold_button(page, "picture").click()
    expect(fold_button(page, "picture")).to_have_text("▶")
    assert thumb.evaluate("el => el.getBoundingClientRect().width") == size


def test_zoomed_thumbnails_are_remembered_per_project(page, imgs):
    load_dir(page, imgs)
    zoom = page.locator("#gridHead .thumb-zoom")
    expect(zoom).to_have_text("▶")
    thumb = row(page, "a.png").locator("td.thumb img")
    size = thumb.evaluate("el => el.getBoundingClientRect().width")
    zoom.click()
    expect(zoom).to_have_text("◀")
    load_dir(page, imgs)  # 読み込み直しても広げたまま
    expect(zoom).to_have_text("◀")
    assert abs(thumb.evaluate("el => el.getBoundingClientRect().width") - size * 1.5) <= 1


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
    expect(tokens_of(page, "a.png")).to_have_text(f"{count(caption_of('looks: standing'))} / 5")
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
    expect(filled(page, "a.png")).to_have_text(["looks: standing"])


def picture_view(page, name):
    return cell(page, name, "picture").locator(".ln", has_text="view:")


def choice(page, name, phrase):
    """view のボタン（語句で指す。ボタンの表示は絵文字）"""
    return cell(page, name, "picture").locator(f'.choice[data-phrase="{phrase}"]')


def test_picture_shows_characters_automatically(page, imgs):
    load_dir(page, imgs)
    write(page, "a.png", "looks: standing")
    characters = cell(page, "a.png", "picture").locator(".ln.auto")
    expect(characters).to_have_text("characters: 1 girl")

    page.fill("#sectionName", "dog")
    page.click("#sectionForm button")
    write(page, "a.png", "looks: sitting", section="dog")
    expect(characters).to_have_text("characters: 1 girl + 1 dog")
    expect(cell(page, "b.png", "picture").locator(".ln.auto")).to_have_text("characters:")


def test_else_has_no_template_keys_and_its_keys_join_characters(page, imgs):
    # else は人物でない物（dog: / cat:）の段落: 確定タグも POV のボタンも無く、characters にはキーを数なしで足す
    load_dir(page, imgs)
    page.fill("#sectionName", "else")
    page.click("#sectionForm button")
    expect(page.locator("#gridHead .section-name")).to_have_count(5)
    expect(cell(page, "a.png", "else").locator(".ln")).to_have_count(0)
    expect(open_editor(page, "a.png", "else")).to_have_value("")
    page.keyboard.press("Escape")

    write(page, "a.png", "looks: standing")
    write(page, "a.png", "dog: brown fur, sitting\ncat: black", section="else")
    expect(cell(page, "a.png", "picture").locator(".ln.auto")).to_have_text("characters: 1 girl + dog + cat")
    expect(cell(page, "a.png", "picture").locator(".choice-row.pov .choice")).to_have_text(["☓", "👥", "👧", "👨"])
    wait_for_phrase(page, "black")
    page.select_option("#bulkSection", "else")
    assert set(option_values(page, "#bulkKey")) == {"", "cat", "dog"}  # 確定タグは無く、使ったキーだけ


def test_adding_girl_twice_names_them_a_and_b(page, imgs):
    load_dir(page, imgs)
    page.fill("#sectionName", "girl")
    page.click("#sectionForm button")
    expect(page.locator("#gridHead .section-name")).to_have_count(5)
    assert section_names(page) == ["picture", "action", "girl A", "girl B", "guy"]  # 同じ種類は隣に並べる
    expect(choice(page, "a.png", "girl B POV")).to_have_text("👧 B")
    pov = cell(page, "a.png", "picture").locator(".choice-row.pov .choice")
    expect(pov).to_have_text(["☓", "👥", "👧 A", "👧 B", "👨"])  # third-person が先頭


def test_view_buttons_toggle_and_clear(page, imgs):
    load_dir(page, imgs)
    choice(page, "a.png", "from behind").click()
    expect(picture_view(page, "a.png")).to_have_text("view: from behind")
    expect(choice(page, "a.png", "from behind")).to_have_class(re.compile(r"\bon\b"))
    choice(page, "a.png", "from front").click()
    expect(picture_view(page, "a.png")).to_have_text("view: from front")
    choice(page, "a.png", "from above").click()
    choice(page, "a.png", "girl POV").click()
    expect(picture_view(page, "a.png")).to_have_text("view: from front, from above, girl POV")

    cell(page, "a.png", "picture").locator('.choice.clear[data-group="camera0"]').click()
    expect(picture_view(page, "a.png")).to_have_text("view: from above, girl POV")
    choice(page, "a.png", "girl POV").click()
    expect(picture_view(page, "a.png")).to_have_text("view: from above")


def test_view_buttons_show_emoji_and_shot_sizes_are_one_group(page, imgs):
    load_dir(page, imgs)
    expect(choice(page, "a.png", "from front")).to_have_text("🧍")
    expect(choice(page, "a.png", "medium shot")).to_have_attribute("title", "medium shot")  # 語句はマウスを載せると見える
    choice(page, "a.png", "medium shot").click()
    choice(page, "a.png", "third-person POV").click()
    expect(picture_view(page, "a.png")).to_have_text("view: medium shot, third-person POV")
    choice(page, "a.png", "long shot").click()  # ショットの大きさは1つだけ。POV とは同時に選べる
    expect(picture_view(page, "a.png")).to_have_text("view: third-person POV, long shot")


def test_eye_level_sits_between_above_and_below(page, imgs):
    load_dir(page, imgs)
    vertical = cell(page, "a.png", "picture").locator('.choice:not(.clear)[data-group="camera1"]')
    expect(vertical).to_have_text(["🦅", "👁️", "🐛"])
    choice(page, "a.png", "eye level").click()
    expect(picture_view(page, "a.png")).to_have_text("view: eye level")
    choice(page, "a.png", "from below").click()  # 上下の組は1つだけ
    expect(picture_view(page, "a.png")).to_have_text("view: from below")


def test_close_up_with_a_target_lights_the_button_and_is_replaced(page, imgs):
    load_dir(page, imgs)
    write(page, "a.png", "view: close-up face, from below", section="picture")
    close_up = choice(page, "a.png", "close-up")
    expect(close_up).to_have_class(re.compile(r"\bon\b"))
    expect(close_up).to_have_attribute("title", "close-up face")  # 入っている語句が見える
    choice(page, "a.png", "portrait").click()
    expect(picture_view(page, "a.png")).to_have_text("view: from below, portrait")
    choice(page, "a.png", "close-up").click()  # 戻すと close-up だけ（対象は手で書き足す）
    expect(picture_view(page, "a.png")).to_have_text("view: from below, close-up")


def test_pov_buttons_show_letters_and_are_colored_by_gender(page, imgs):
    load_dir(page, imgs)
    expect(choice(page, "a.png", "guy POV")).to_have_text("👨")  # guy は最初からある
    page.fill("#sectionName", "guy")
    page.click("#sectionForm button")
    expect(choice(page, "a.png", "guy B POV")).to_have_text("👨 B")
    expect(choice(page, "a.png", "third-person POV")).to_have_text("👥")

    girl, guy = choice(page, "a.png", "girl POV"), choice(page, "a.png", "guy A POV")
    expect(girl).to_have_class(re.compile(r"\bfemale\b"))
    expect(guy).to_have_class(re.compile(r"\bmale\b"))
    background = "el => getComputedStyle(el).backgroundColor"
    assert girl.evaluate(background) != guy.evaluate(background)


def test_emoji_buttons_are_as_wide_as_the_clear_button(page, imgs):
    load_dir(page, imgs)
    picture = cell(page, "a.png", "picture")
    clear = picture.locator(".choice.clear").first.bounding_box()["width"]
    for phrase in ["from front", "from above", "long shot", "third-person POV", "girl POV"]:
        assert abs(choice(page, "a.png", phrase).bounding_box()["width"] - clear) < 0.5, phrase


def test_view_button_applies_to_selected_rows(page, imgs):
    load_dir(page, imgs)
    row(page, "a.png").locator("td.meta").click()
    row(page, "b.png").locator("td.meta").click(modifiers=["Shift"])
    choice(page, "a.png", "close-up").click()  # 語句で指すので、表示が絵文字でもそのまま
    for name in ["a.png", "b.png"]:
        expect(picture_view(page, name)).to_have_text("view: close-up")
    expect(picture_view(page, "c.png")).to_have_class("ln empty")


def test_view_keeps_free_text(page, imgs):
    load_dir(page, imgs)
    write(page, "a.png", "view: focus on hands", section="picture")
    choice(page, "a.png", "close-up").click()
    expect(picture_view(page, "a.png")).to_have_text("view: focus on hands, close-up")


def test_adding_sections_quickly_keeps_the_next_name(page, imgs):
    load_dir(page, imgs)
    page.fill("#sectionName", "dog")
    page.click("#sectionForm button")
    page.fill("#sectionName", "cat")  # 1つ目の応答を待たずに次を打つ
    page.click("#sectionForm button")
    expect(page.locator("#gridHead .section-name")).to_have_count(6)
    assert section_names(page) == ["picture", "action", "girl", "guy", "dog", "cat"]


def test_clicking_beside_view_buttons_does_not_open_editor(page, imgs):
    load_dir(page, imgs)
    pov_row = cell(page, "a.png", "picture").locator(".choice-row").last
    box = pov_row.bounding_box()
    pov_row.click(position={"x": box["width"] - 4, "y": box["height"] / 2})  # 最後のボタンの右の余白
    expect(cell(page, "a.png", "picture").locator("textarea")).to_have_count(0)

    cell(page, "a.png", "picture").locator(".text").click()
    expect(field(page, "a.png", "place", "picture")).to_have_count(1)


def test_hint_column_shows_same_name_txt_read_only(page, imgs, tool):
    (imgs / "a.txt").write_text("1girl, solo, smile", encoding="utf-8")
    load_dir(page, imgs)
    expect(page.locator("#gridHead .side-view.on")).to_have_text("hint")  # hint があれば、最初は hint を出す
    hint = row(page, "a.png").locator("td.hint textarea")
    expect(hint).to_have_value("1girl, solo, smile")
    expect(hint).to_have_attribute("readonly", "")
    hint.click()
    assert hint.evaluate("el => [el.selectionStart, el.selectionEnd]") == [0, len("1girl, solo, smile")]
    expect(row(page, "a.png").locator("td.cell textarea")).to_have_count(0)  # 入力欄は開かない
    expect(row(page, "b.png").locator("td.hint textarea")).to_have_count(0)  # hint の無い画像は空の欄を出さない


def test_hint_shows_the_whole_text_and_can_be_folded(page, imgs):
    long_hint = ", ".join(f"tag{i}" for i in range(150))
    (imgs / "a.txt").write_text(long_hint, encoding="utf-8")
    load_dir(page, imgs)
    hint = row(page, "a.png").locator("td.hint textarea")
    expect(hint).to_have_value(long_hint)
    assert hint.evaluate("el => el.scrollHeight <= el.clientHeight + 1")  # 全文が見える（中でスクロールしない）

    row(page, "a.png").locator(".hint-toggle").click()  # 畳む
    expect(row(page, "a.png").locator("td.hint textarea")).to_have_count(0)
    expect(row(page, "a.png").locator(".hint-toggle")).to_have_text("＋ hint")

    load_dir(page, imgs)  # 読み込み直しても畳んだまま
    expect(row(page, "a.png").locator("td.hint textarea")).to_have_count(0)
    row(page, "a.png").locator(".hint-toggle").click()  # 開く
    expect(row(page, "a.png").locator("td.hint textarea")).to_have_value(long_hint)


CAPTION_A = "picture:\n  - characters: 1 girl\n\ngirl:\n  - looks: standing"


def test_without_hint_files_the_column_shows_the_caption_preview(page, imgs):
    # hint が無ければ、同じ列に preview（書き出すキャプション）を出す。欄を書き換えると、その行の preview もすぐ変わる
    load_dir(page, imgs)
    expect(page.locator("#gridHead th.hint-head")).to_have_text("preview")
    expect(page.locator("#gridHead .side-view")).to_have_count(0)  # 切り替えるものが無いのでボタンにしない
    preview = row(page, "a.png").locator("td.hint textarea")
    expect(preview).to_have_count(0)  # 入力の無い行の preview は空
    write(page, "a.png", "looks: standing")
    expect(preview).to_have_value(CAPTION_A)
    expect(preview).to_have_attribute("readonly", "")


def test_hint_and_preview_buttons_switch_the_column(page, imgs):
    # hint があれば、見出しの hint / preview のボタンで列の中身を切り替える（どちらを出すかはプロジェクトごとに覚える）
    (imgs / "a.txt").write_text("1girl, solo, smile", encoding="utf-8")
    load_dir(page, imgs)
    side = row(page, "a.png").locator("td.hint textarea")
    hint_button, preview_button = (page.locator(f'#gridHead .side-view[data-view="{view}"]') for view in ["hint", "preview"])
    expect(hint_button).to_have_class(re.compile(r"\bon\b"))
    expect(side).to_have_value("1girl, solo, smile")

    preview_button.click()
    expect(preview_button).to_have_class(re.compile(r"\bon\b"))
    expect(side).to_have_count(0)  # 入力の無い行の preview は空
    expect(row(page, "a.png").locator(".hint-toggle")).to_have_count(0)  # 畳むのは hint だけ
    load_dir(page, imgs)  # 読み込み直しても preview のまま
    expect(preview_button).to_have_class(re.compile(r"\bon\b"))
    write(page, "a.png", "looks: standing")
    expect(side).to_have_value(CAPTION_A)

    hint_button.click()
    expect(side).to_have_value("1girl, solo, smile")


def test_switching_hint_and_preview_keeps_the_first_whole_row_where_it_was(page, tmp_path):
    # hint と preview は行ごとに高さが違う。切り替えても、見えていた最初の行（上が切れていない行）を押す前と同じ位置に見せる
    tall = make_images(tmp_path / "imgs" / "tall", {f"r{i}.png": (100, 100) for i in range(8)})
    for i in range(8):  # hint は長く（行が高い）、preview は入力が無いので空（行が低い）
        (tall / f"r{i}.txt").write_text(", ".join(f"tag{j}" for j in range(200)), encoding="utf-8")
    load_dir(page, tall)
    head_bottom = "() => $('gridHead').querySelector('th').getBoundingClientRect().bottom"

    def below_head(name):
        return row(page, name).evaluate("tr => tr.getBoundingClientRect().top") - page.evaluate(head_bottom)

    page.evaluate("y => { $('imagesView').scrollTop += y; }", below_head("r3.png") - 30)  # r3 を見出しの 30px 下に
    assert abs(below_head("r3.png") - 30) <= 1
    for view in ["preview", "hint"]:  # 行き来しても同じ
        page.locator(f'#gridHead .side-view[data-view="{view}"]').click()
        expect(page.locator(f'#gridHead .side-view[data-view="{view}"]')).to_have_class(re.compile(r"\bon\b"))
        assert abs(below_head("r3.png") - 30) <= 2, view  # 押す前と同じ、見出しの 30px 下


def option_values(page, selector):
    return page.locator(f"{selector} option").evaluate_all("els => els.map(e => e.value)")


def test_editing_selects_the_row(page, imgs):
    load_dir(page, imgs)
    cell(page, "b.png").click()
    expect(row(page, "b.png")).to_have_class("selected")
    expect(page.locator("#selectionInfo")).to_have_text("選択 1 行")


def test_bulk_form_shows_only_while_selected(page, imgs):
    load_dir(page, imgs)
    expect(page.locator("#bulkForm")).to_be_hidden()
    row(page, "a.png").locator("td.meta").click()
    expect(page.locator("#bulkForm")).to_be_visible()


def test_bulk_keys_follow_the_section(page, imgs):
    load_dir(page, imgs)
    row(page, "a.png").locator("td.meta").click()
    expect(page.locator("#bulkKey")).to_have_value("place")  # 最初は先頭のキー
    page.select_option("#bulkSection", "picture")
    assert option_values(page, "#bulkKey") == ["place", "vibes", "view", "extra", ""]
    page.select_option("#bulkSection", "girl")
    assert option_values(page, "#bulkKey") == ["looks", "clothes", "body", ""]
    page.select_option("#bulkSection", "action")
    assert option_values(page, "#bulkKey") == [""]


def test_bulk_phrase_suggestions_follow_the_key(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_phrase(page, "long hair")
    row(page, "a.png").locator("td.meta").click()
    page.select_option("#bulkSection", "girl")
    page.select_option("#bulkKey", "body")
    page.locator("#bulkText").press_sequentially("lh")
    expect(page.locator("#suggestions li.active")).to_contain_text("long hair")
    page.locator("#bulkText").press("Enter")
    assert page.locator("#bulkText").input_value() == "long hair, "
    page.click('#bulkForm button[value="add"]')
    expect(filled(page, "a.png")).to_have_text(["body: long hair"])


def test_deselect_needs_a_long_press(page, imgs):
    load_dir(page, imgs)
    row(page, "a.png").locator("td.meta").click()
    row(page, "c.png").locator("td.meta").click(modifiers=["Shift"])
    page.click("#deselectButton")
    expect(page.locator("#status")).to_have_text("1秒長押しすると、選択を解除します")
    expect(page.locator("#selectionInfo")).to_have_text("選択 3 行")

    page.locator("#deselectButton").hover()
    page.mouse.down()
    page.wait_for_timeout(1300)
    page.mouse.up()
    expect(page.locator("#status")).to_have_text("選択を解除しました")
    expect(page.locator("#bulkForm")).to_be_hidden()
    expect(page.locator("#gridBody tr.selected")).to_have_count(0)


def test_selecting_rows_does_not_shift_the_table(page, imgs):
    # 行を選ぶと2段目の帯に一括入力が並ぶが、帯は1段のまま（窓の幅 1440px 以上。自動のマーク ①〜⑧ と絞り込みの「自動」を足してから）
    page.set_viewport_size({"width": 1440, "height": 800})
    load_dir(page, imgs)
    before = page.locator("#grid").bounding_box()["y"]
    row(page, "a.png").locator("td.meta").click()
    expect(page.locator("#bulkForm")).to_be_visible()
    assert page.locator("#grid").bounding_box()["y"] == before


def test_hold_button_fills_while_pressed_and_resets_when_released_early(page, imgs):
    load_dir(page, imgs)
    row(page, "a.png").locator("td.meta").click()
    button = page.locator("#deselectButton")
    button.hover()
    page.mouse.down()
    expect(button).to_have_class("hold holding")
    page.wait_for_timeout(500)
    width = button.evaluate("el => parseFloat(getComputedStyle(el, '::before').width)")
    assert 0 < width < button.evaluate("el => el.getBoundingClientRect().width")  # 途中まで伸びている
    page.mouse.up()
    expect(button).to_have_class("hold")
    expect(page.locator("#selectionInfo")).to_have_text("選択 1 行")  # 1秒未満で離したので解除しない
