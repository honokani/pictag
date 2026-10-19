"""画面操作（Playwright）"""
import re

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
    cell(page, name, section).click()
    return cell(page, name, section).locator("textarea")


def write(page, name, text, section="girl"):
    """入力欄に書いて確定する（フォーカスを外すと送信する）"""
    editor = open_editor(page, name, section)
    editor.fill(text)
    editor.evaluate("el => el.blur()")
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


def test_editor_starts_with_template_keys_and_caret_on_first_empty_key(page, imgs, tool):
    load_dir(page, imgs)
    editor = open_editor(page, "a.png")
    assert editor.input_value() == "looks: \nclothes: \nbody: "
    assert editor.evaluate("el => el.selectionStart") == len("looks: ")

    editor.press_sequentially("standing")
    editor.evaluate("el => el.blur()")
    expect(filled(page, "a.png")).to_have_text(["looks: standing"])
    expect(cell(page, "a.png").locator(".ln.empty")).to_have_text(["clothes:", "body:"])
    expect(tokens_of(page, "a.png")).to_have_text(f"{count(caption_of('looks: standing'))} / 507")
    # 値の無いキーは保存しない
    assert tool.df.set_index("サムネイル").loc["a.png", "girl"] == "looks: standing"


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


def test_suggestion_at_line_start_adds_key_and_phrase(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_phrase(page, "long hair")

    editor = open_editor(page, "a.png")
    editor.fill("")
    editor.press_sequentially("lh")
    expect(page.locator("#suggestions li.active")).to_contain_text("body: long hair")
    editor.press("Tab")
    assert editor.input_value() == "body: long hair"


def test_suggestion_fills_template_key_line(page, imgs):
    load_dir(page, imgs)
    write(page, "b.png", "body: long hair")
    wait_for_phrase(page, "long hair")

    editor = open_editor(page, "a.png")  # looks: / clothes: / body: が並んだ状態
    editor.press_sequentially("lh")  # looks の行に打つ → 候補は looks の語句だけ（無い）
    expect(page.locator("#suggestions")).to_be_hidden()
    editor.fill("looks: \nclothes: \nbody: ")
    editor.evaluate("el => el.setSelectionRange(el.value.length, el.value.length)")
    editor.press_sequentially("lh")
    editor.press("Enter")
    assert editor.input_value() == "looks: \nclothes: \nbody: long hair, "


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


def test_action_suggests_words_inside_a_sentence(page, imgs):
    load_dir(page, imgs)
    write(page, "a.png", "girl spread arms\nguy grab girl's waist", section="action")
    wait_for_word(page, "spread")

    editor = open_editor(page, "b.png", section="action")
    editor.press_sequentially("girl sp")
    expect(page.locator("#suggestions li.active")).to_contain_text("spread")
    editor.press("Enter")
    assert editor.input_value() == "girl spread "
    editor.press_sequentially("wa")
    expect(page.locator("#suggestions li.active")).to_contain_text("waist")


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
    page.click("text=選択行に追加")
    expect(page.locator("#status")).to_have_text("3 行に追加しました")
    for name in ["a.png", "b.png", "c.png"]:
        expect(filled(page, name)).to_have_text(["looks: standing"])

    row(page, "b.png").locator("td.meta").click(modifiers=["Control"])
    expect(page.locator("#selectionInfo")).to_have_text("選択 2 行")
    page.fill("#bulkText", "standing")
    page.click("text=選択行から削除")
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
    expect(cell(page, "a.png", "picture").locator("textarea")).to_have_count(1)


def test_hint_column_shows_same_name_txt_read_only(page, imgs, tool):
    (imgs / "a.txt").write_text("1girl, solo, smile", encoding="utf-8")
    load_dir(page, imgs)
    expect(page.locator("#gridHead th.hint-head")).to_have_text("hint")
    hint = row(page, "a.png").locator("td.hint textarea")
    expect(hint).to_have_value("1girl, solo, smile")
    expect(hint).to_have_attribute("readonly", "")
    hint.click()
    assert hint.evaluate("el => [el.selectionStart, el.selectionEnd]") == [0, len("1girl, solo, smile")]
    expect(row(page, "a.png").locator("td.cell textarea")).to_have_count(0)  # 入力欄は開かない
    expect(row(page, "b.png").locator("td.hint textarea")).to_have_value("")


def test_no_hint_column_without_txt_files(page, imgs):
    load_dir(page, imgs)
    expect(page.locator("#gridHead th.hint-head")).to_have_count(0)
    expect(page.locator("td.hint")).to_have_count(0)


def option_values(page, selector):
    return page.locator(f"{selector} option").evaluate_all("els => els.map(e => e.value)")


def test_editing_selects_the_row(page, imgs):
    load_dir(page, imgs)
    cell(page, "b.png").click()
    expect(row(page, "b.png")).to_have_class("selected")
    expect(page.locator("#selectionInfo")).to_have_text("選択 1 行")


def test_bulk_form_replaces_key_help_only_while_selected(page, imgs):
    load_dir(page, imgs)
    expect(page.locator("#keyHelp")).to_be_visible()
    expect(page.locator("#bulkForm")).to_be_hidden()
    row(page, "a.png").locator("td.meta").click()
    expect(page.locator("#bulkForm")).to_be_visible()
    expect(page.locator("#keyHelp")).to_be_hidden()


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
    page.click("text=選択行に追加")
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
    expect(page.locator("#keyHelp")).to_be_visible()
    expect(page.locator("#gridBody tr.selected")).to_have_count(0)


def test_selecting_rows_does_not_shift_the_table(page, imgs):
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
