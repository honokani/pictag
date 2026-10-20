"""qwen 版の画面（Playwright）: 🤖 の列と、右端の列の hint_by_qwen（ComfyUI は偽物）"""
import re

import pytest

import app as pictag
from helpers import Api, FakeComfy, make_images, word_tokenizer
from tokens import TokenCounter

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e

ANSWER = ("picture:\n  - place: hilltop\n  - characters: 1 girl\n\naction:\n  - girl waves.\n\n"
          "girl:\n  - looks: standing\n  - clothes: red dress")


@pytest.fixture(autouse=True)
def tokens(monkeypatch):
    # 実物のトークナイザーは取りに行かず、空白と記号で区切る小さなもので数える
    monkeypatch.setattr(pictag, "token_counter", TokenCounter(word_tokenizer()))


@pytest.fixture
def comfy():
    fake = FakeComfy(ANSWER)
    yield fake
    fake.close()


@pytest.fixture
def project(tool, tmp_path):
    """r00〜r11 の 12 枚。r00〜r09 の girl が見本（looks: pose0〜9）。保存して、画面で開けるようにする"""
    api = Api(pictag.app.test_client())
    api.load(make_images(tmp_path / "imgs" / "proj", {f"r{i:02}.png": (100, 100) for i in range(12)}))
    for i in range(10):
        api.write(api.row_index(f"r{i:02}.png"), f"looks: pose{i}")
    api.save()
    return api


@pytest.fixture
def qwen_mode(comfy, monkeypatch):
    """--qwen で起動したことにする（宛先は偽の ComfyUI）"""
    monkeypatch.setitem(pictag.app.config, "QWEN_URL", comfy.url)


def open_project(page):
    page.goto(page.base_url)
    page.select_option("#projectSelect", "proj")
    expect(page.locator("#gridBody tr")).to_have_count(12)


def row(page, name):
    return page.locator(f'#gridBody tr[data-name="{name}"]')


def test_robot_column_sits_between_token_and_marks_at_half_the_token_width(page, project, qwen_mode):
    open_project(page)
    head = page.locator("#gridHead th")
    expect(head.nth(1)).to_have_text("token")
    expect(head.nth(2)).to_have_text("🤖")
    expect(head.nth(3)).to_have_text("マーク")
    width = "el => el.getBoundingClientRect().width"
    meta = row(page, "r10.png").locator("td.meta").evaluate(width)
    assert abs(row(page, "r10.png").locator("td.qwen").evaluate(width) - meta / 2) <= 1


def test_robot_needs_ten_samples_above(page, project, qwen_mode):
    open_project(page)
    button = row(page, "r09.png").locator(".qwen-btn")  # 上の見本は 9 行
    expect(button).to_be_disabled()
    expect(button).to_have_attribute("title", re.compile("10"))
    expect(row(page, "r10.png").locator(".qwen-btn")).to_be_enabled()


def test_robot_fills_empty_keys_and_hint_by_qwen_shows_the_answer(page, project, qwen_mode):
    open_project(page)
    row(page, "r10.png").locator(".qwen-btn").click()
    girl = row(page, "r10.png").locator('td.cell[data-section="girl"] .ln:not(.empty)')
    expect(girl).to_have_text(["looks: standing", "clothes: red dress"])
    expect(row(page, "r10.png").locator('td.cell[data-section="action"] .ln')).to_have_text(["girl waves."])
    expect(page.locator("#status")).to_have_class("ok")

    page.locator('#gridHead .side-view[data-view="hint_by_qwen"]').click()  # hint が無いので preview / hint_by_qwen
    expect(row(page, "r10.png").locator("td.hint textarea")).to_have_value(ANSWER)
    expect(row(page, "r09.png").locator("td.hint textarea")).to_have_count(0)  # 答えの無い行は空


def test_without_the_qwen_option_there_is_no_robot(page, project):
    open_project(page)
    expect(page.locator("#gridHead th", has_text="🤖")).to_have_count(0)
    expect(page.locator("td.qwen")).to_have_count(0)
    expect(page.locator("#gridHead .side-view")).to_have_count(0)  # 右端の列は preview の文字だけ（今と同じ）
