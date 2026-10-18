"""画面操作（Playwright）"""
import re
import time
from urllib.parse import quote

import pytest

import app as pictag
from helpers import make_images

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e


# ---- 画面操作のヘルパー ----

def open_app(page):
    page.goto(page.base_url)
    expect(page.locator("#kindSelect option").first).to_be_attached()


def load_dir(page, imgs):
    page.fill("#imageDir", str(imgs))
    page.click("button:has-text('読み込み')")
    expect(page.locator("#tableBody tr").first).to_be_visible()


def row_of(page, image_name):
    return page.locator("#tableBody tr", has=page.locator(f'img[src="/thumbnail/{quote(image_name)}"]'))


def checkbox(page, image_name, column):
    header = page.locator("#tableHeader th").all_inner_texts()
    return row_of(page, image_name).locator("td").nth(header.index(column)).locator("input[type=checkbox]")


def click_row(page, image_name, modifiers=None):
    row_of(page, image_name).locator("td").first.click(modifiers=modifiers or [])


def hide_dead(page, visible_rows):
    page.uncheck("#isDeadVisibleToggle")
    expect(page.locator("#tableBody tr")).to_have_count(visible_rows)


def option_values(page, selector):
    return page.locator(f"{selector} option").evaluate_all("els => els.map(e => e.value)")


ADD_TASK = "column追加"


def choose_task(page, task, kind=None):
    """タスクを選び、種別の選択肢の作り直しと続くキャプション読み込みが終わってから種別を選ぶ"""
    page.select_option("#taskSelect", task)
    has_new_kind = task == ADD_TASK  # 追加以外のタスクは new_kind を出さない
    assert stable(lambda: ("new_kind" in option_values(page, "#kindSelect")) == has_new_kind)
    if kind is not None:
        page.select_option("#kindSelect", kind)


def stable(predicate, timeout=5.0, hold=0.4):
    """predicate が hold 秒続けて真になるまで待つ（非同期の更新が出揃うのを待つ）"""
    end = time.monotonic() + timeout
    since = None
    while time.monotonic() < end:
        if predicate():
            since = since or time.monotonic()
            if time.monotonic() - since >= hold:
                return True
        else:
            since = None
        time.sleep(0.05)
    return False


def flags(column):
    """サーバー側の今の表（画像名 → 値）"""
    return pictag.caption_tool.df.set_index("サムネイル")[column].to_dict()


# ---- データ ----

@pytest.fixture
def imgs(api, tmp_path):
    """a, b, c, d の4枚。タグ smile(expr), solo(people) を保存済み"""
    imgs = make_images(tmp_path / "imgs" / "proj", {n: (100, 100) for n in ["a.png", "b.png", "c.png", "d.png"]})
    api.load(imgs)
    api.add("smile", kind="expr")
    api.add("solo", kind="people")
    api.save()
    return imgs


@pytest.fixture
def imgs_b_dead(api, imgs):
    """b を元フォルダから消して削除済みにする"""
    (imgs / "b.png").rename(imgs.parent / "b.png.bak")
    api.load(imgs)
    return imgs


# ---- テスト ----

def test_kind_list_refreshes_after_opening_project(page, imgs, base_dir, monkeypatch):
    # サーバーを「プロジェクト未読み込み」に戻してから画面を開く
    monkeypatch.setattr(pictag, "caption_tool", pictag.CaptionTool(base_dir=base_dir))
    open_app(page)
    assert option_values(page, "#kindSelect") == ["new_kind", "undef"]

    page.select_option("#existingProjects", "proj")
    expect(page.locator("#tableBody tr")).to_have_count(4)
    expect(page.locator('#kindSelect option[value="expr"]')).to_be_attached()
    assert option_values(page, "#kindSelect") == ["new_kind", "expr", "people"]


def test_selection_highlight_with_dead_rows_hidden(page, imgs_b_dead):
    open_app(page)
    load_dir(page, imgs_b_dead)
    hide_dead(page, 3)

    click_row(page, "c.png")
    expect(row_of(page, "c.png")).to_have_class(re.compile(r"(^|\s)selected-row(\s|$)"))
    expect(page.locator("#tableBody tr.selected-row")).to_have_count(1)


def test_multiselect_check_with_dead_rows_hidden(page, imgs_b_dead):
    open_app(page)
    load_dir(page, imgs_b_dead)
    hide_dead(page, 3)

    click_row(page, "d.png", ["Control"])
    click_row(page, "a.png", ["Control"])
    checkbox(page, "a.png", "smile").check()

    assert stable(lambda: flags("smile") == {"a.png": True, "b.png": False, "c.png": False, "d.png": True})
    expect(checkbox(page, "d.png", "smile")).to_be_checked()
    expect(checkbox(page, "c.png", "smile")).not_to_be_checked()


def test_shift_range_skips_hidden_dead_rows(page, imgs_b_dead):
    open_app(page)
    load_dir(page, imgs_b_dead)
    hide_dead(page, 3)

    click_row(page, "a.png")
    click_row(page, "c.png", ["Shift"])
    expect(page.locator("#tableBody tr.selected-row")).to_have_count(2)
    checkbox(page, "c.png", "smile").check()

    assert stable(lambda: flags("smile") == {"a.png": True, "b.png": False, "c.png": True, "d.png": False})


def test_check_after_remove_all_dead_updates_clicked_row(page, imgs_b_dead):
    open_app(page)
    load_dir(page, imgs_b_dead)
    page.once("dialog", lambda d: d.accept())
    page.click("button:has-text('削除済みを完全削除')")
    expect(page.locator("#tableBody tr")).to_have_count(3)

    checkbox(page, "c.png", "smile").check()
    assert stable(lambda: flags("smile") == {"a.png": False, "c.png": True, "d.png": False})


def test_rename_both_lists_only_table_columns(page, api, imgs):
    api.add("grin", kind="expr")
    api.post("/remove_column_from_table", {"column_name": "grin"})
    api.save()
    open_app(page)
    load_dir(page, imgs)

    choose_task(page, "kind・column両方改名", kind="expr")
    assert stable(lambda: option_values(page, "#captionSelect") == ["smile"])


def test_kind_with_special_characters_lists_captions(page, api, imgs):
    api.add("Q", kind="what?#%")
    api.save()
    open_app(page)
    load_dir(page, imgs)

    choose_task(page, "column改名", kind="what?#%")
    assert stable(lambda: option_values(page, "#captionSelect") == ["Q"])


def test_kind_list_after_save_during_rename_task(page, imgs):
    open_app(page)
    load_dir(page, imgs)
    choose_task(page, "column改名")
    expect(page.locator('#kindSelect option[value="new_kind"]')).to_have_count(0)

    # 保存後に種別一覧を読み直す（/get_kinds）のを待ってから確かめる
    with page.expect_response(lambda r: "/get_kinds" in r.url):
        page.click("button:has-text('保存')")
    assert stable(lambda: "new_kind" not in option_values(page, "#kindSelect"))


def test_rename_failure_shows_reason(page, imgs):
    open_app(page)
    load_dir(page, imgs)
    choose_task(page, "column改名", kind="people")
    assert stable(lambda: option_values(page, "#captionSelect") == ["solo"])
    page.select_option("#captionSelect", "solo")
    page.fill("#captionText", "smile")
    page.click("button:has-text('実行')")
    expect(page.locator("#statusMessage")).to_contain_text("既にあります")


def test_modal_shows_original_image_and_name(page, tmp_path):
    big = make_images(tmp_path / "imgs" / "big", {"big.png": (900, 900), "small.png": (100, 100)})
    open_app(page)
    load_dir(page, big)

    row_of(page, "big.png").locator("img").click()
    expect(page.locator("#imageModal")).to_be_visible()
    expect(page.locator("#imageModalTitle")).to_have_text("big.png")
    page.wait_for_function("() => document.getElementById('modalImage').naturalWidth > 0")
    assert page.evaluate("document.getElementById('modalImage').naturalWidth") == 900


def test_modal_reopen_and_close_leaves_no_backdrop(page, tmp_path):
    big = make_images(tmp_path / "imgs" / "big", {"big.png": (900, 900), "small.png": (100, 100)})
    open_app(page)
    load_dir(page, big)

    for name in ["big.png", "small.png", "big.png"]:
        row_of(page, name).locator("img").click()
        expect(page.locator("#imageModal")).to_be_visible()
        page.click("#imageModal .btn-close")
        expect(page.locator("#imageModal")).to_be_hidden()
    expect(page.locator(".modal-backdrop")).to_have_count(0)
    assert "modal-open" not in (page.get_attribute("body", "class") or "")
