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


def robot(page, name):
    """🤖: 上の 10 行を見本に"""
    return row(page, name).locator('.qwen-btn[data-mode="near"]')


def marker(page, name):
    """🔖: 同じマークの行（A〜D → ★●▲■）を先に、足りなければランダムに 10 行を見本に"""
    return row(page, name).locator('.qwen-btn[data-mode="mark"]')


def dice(page, name):
    """🎲: ほかの行からランダムに 10 行を見本に"""
    return row(page, name).locator('.qwen-btn[data-mode="random"]')


def test_qwen_column_sits_between_token_and_marks_at_half_the_token_width(page, project, qwen_mode):
    # 列は token の半分の幅のまま。🤖・🔖・🎲 は横に並べず、上から縦に積む
    open_project(page)
    head = page.locator("#gridHead th")
    expect(head.nth(1)).to_have_text("token")
    expect(head.nth(2)).to_have_text("🤖")
    expect(head.nth(3)).to_have_text("マーク")
    expect(robot(page, "r10.png")).to_have_text("🤖")
    expect(marker(page, "r10.png")).to_have_text("🔖")
    expect(dice(page, "r10.png")).to_have_text("🎲")
    width = "el => el.getBoundingClientRect().width"
    meta = row(page, "r10.png").locator("td.meta").evaluate(width)
    assert abs(row(page, "r10.png").locator("td.qwen").evaluate(width) - meta / 2) <= 1
    boxes = [button(page, "r10.png").bounding_box() for button in (robot, marker, dice)]
    for upper, lower in zip(boxes, boxes[1:]):
        assert lower["y"] >= upper["y"] + upper["height"] - 0.5  # 🤖 の下に 🔖、その下に 🎲
    expect(dice(page, "r09.png")).to_be_disabled()  # ほかの見本は r00〜r08 の 9 行


def test_robot_needs_ten_samples_above_and_dice_ten_elsewhere(page, project, qwen_mode):
    project.write(project.row_index("r11.png"), "looks: pose11")  # 見本は r00〜r09 と r11 の 11 行
    project.save()
    open_project(page)
    expect(robot(page, "r05.png")).to_be_disabled()  # 上は 5 行
    expect(robot(page, "r05.png")).to_have_attribute("title", re.compile("10"))
    expect(dice(page, "r05.png")).to_be_enabled()  # ほかに 10 行
    expect(marker(page, "r05.png")).to_be_enabled()  # 🔖 も足りない分はランダムなので、🎲 と同じ
    expect(robot(page, "r10.png")).to_be_enabled()


def test_dice_fills_with_samples_from_the_whole_project(page, project, qwen_mode, comfy):
    project.write(project.row_index("r11.png"), "looks: pose11")
    project.save()
    open_project(page)
    dice(page, "r05.png").click()
    expect(row(page, "r05.png").locator('td.cell[data-section="action"] .ln')).to_have_text(["girl waves."])
    assert "looks: pose11" in comfy.prompts[0]["prompt"]["tg"]["inputs"]["prompt"]  # 下の行も見本に入る


def test_robot_fills_empty_keys_and_hint_by_qwen_shows_the_answer(page, project, qwen_mode):
    open_project(page)
    robot(page, "r10.png").click()
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
