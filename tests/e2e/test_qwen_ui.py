"""qwen 版の画面（Playwright）: 🤖 の列と、右端の列の hint_by_qwen（ComfyUI は偽物）"""
import re
from itertools import pairwise

import pytest

import app as pictag
from helpers import Api, FakeComfy, make_images, word_tokenizer
from qwen import SAMPLE_COUNT
from tokens import TokenCounter

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e

ANSWER = ("picture:\n  - place: hilltop\n  - characters: 1 girl\n\naction:\n  - girl waves.\n\n"
          "girl:\n  - looks: standing\n  - clothes: red dress")
ASK = f"r{SAMPLE_COUNT:02}.png"  # 頼む行（上に見本の数だけ、キャプションのある行がある）
SPARE = f"r{SAMPLE_COUNT + 1:02}.png"  # 空の行（見本を足すときに書く）
LAST = f"r{SAMPLE_COUNT - 1:02}.png"  # 最後の見本の行


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
    """r00〜r17 の 18 枚（見本の数 + 2）。r00〜r15 の girl が見本（looks: pose0〜15）。保存して、画面で開けるようにする"""
    api = Api(pictag.app.test_client())
    api.load(make_images(tmp_path / "imgs" / "proj", {f"r{i:02}.png": (100, 100) for i in range(SAMPLE_COUNT + 2)}))
    for i in range(SAMPLE_COUNT):
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
    expect(page.locator("#gridBody tr")).to_have_count(SAMPLE_COUNT + 2)


def row(page, name):
    return page.locator(f'#gridBody tr[data-name="{name}"]')


def robot(page, name):
    """🤖: 上の 16 行を見本に"""
    return row(page, name).locator('.qwen-btn[data-mode="near"]')


def marker(page, name):
    """🔖: 同じマークの行（単語①と複数★の両方 → 単語①だけ・複数★だけを同じ数ずつ → 単語① → 複数★ → 排他A）を先に、
    足りなければランダムに 16 行を見本に"""
    return row(page, name).locator('.qwen-btn[data-mode="mark"]')


def rewriter(page, name):
    """🔄: 🔖 と同じ見本で、入力のある欄も上書き"""
    return row(page, name).locator('.qwen-btn[data-mode="overwrite"]')


def dice(page, name):
    """🎲: ほかの行からランダムに 16 行を見本に"""
    return row(page, name).locator('.qwen-btn[data-mode="random"]')


def test_qwen_column_sits_between_token_and_marks_at_half_the_token_width(page, project, qwen_mode):
    # 列は token の半分の幅のまま。🤖・🔖・🔄・🎲 は横に並べず、上から縦に積む
    open_project(page)
    head = page.locator("#gridHead th")
    expect(head.nth(1)).to_have_text("token")
    expect(head.nth(2)).to_have_text("🤖")
    expect(head.nth(3)).to_have_text("マーク")
    expect(robot(page, ASK)).to_have_text("🤖")
    expect(marker(page, ASK)).to_have_text("🔖")
    expect(rewriter(page, ASK)).to_have_text("🔄")
    expect(dice(page, ASK)).to_have_text("🎲")
    width = "el => el.getBoundingClientRect().width"
    meta = row(page, ASK).locator("td.meta").evaluate(width)
    assert abs(row(page, ASK).locator("td.qwen").evaluate(width) - meta / 2) <= 1
    boxes = [button(page, ASK).bounding_box() for button in (robot, marker, rewriter, dice)]
    for upper, lower in pairwise(boxes):
        assert lower["y"] >= upper["y"] + upper["height"] - 0.5  # 🤖 の下に 🔖、その下に 🔄、その下に 🎲
    expect(dice(page, LAST)).to_be_disabled()  # ほかの見本は r00〜r14 の 15 行


def test_robot_needs_sixteen_samples_above_and_dice_sixteen_elsewhere(page, project, qwen_mode):
    project.write(project.row_index(SPARE), "looks: pose17")  # 見本は r00〜r15 と r17 の 17 行
    project.save()
    open_project(page)
    expect(robot(page, "r05.png")).to_be_disabled()  # 上は 5 行
    expect(robot(page, "r05.png")).to_have_attribute("title", re.compile("16"))
    expect(dice(page, "r05.png")).to_be_enabled()  # ほかに 16 行
    expect(marker(page, "r05.png")).to_be_enabled()  # 🔖 も足りない分はランダムなので、🎲 と同じ
    expect(robot(page, ASK)).to_be_enabled()


def test_dice_fills_with_samples_from_the_whole_project(page, project, qwen_mode, comfy):
    project.write(project.row_index(SPARE), "looks: pose17")
    project.save()
    open_project(page)
    dice(page, "r05.png").click()
    expect(row(page, "r05.png").locator('td.cell[data-section="action"] .ln')).to_have_text(["girl waves."])
    assert "looks: pose17" in comfy.prompts[0]["prompt"]["tg"]["inputs"]["prompt"]  # 下の行も見本に入る


def test_robot_fills_empty_keys_and_hint_by_qwen_shows_the_answer(page, project, qwen_mode):
    open_project(page)
    robot(page, ASK).click()
    girl = row(page, ASK).locator('td.cell[data-section="girl"] .ln:not(.empty)')
    expect(girl).to_have_text(["looks: standing", "clothes: red dress"])
    expect(row(page, ASK).locator('td.cell[data-section="action"] .ln')).to_have_text(["girl waves."])
    expect(page.locator("#status")).to_have_class("ok")

    page.locator('#gridHead .side-view[data-view="hint_by_qwen"]').click()  # hint が無いので preview / hint_by_qwen
    expect(row(page, ASK).locator("td.hint textarea")).to_have_value(ANSWER)
    expect(row(page, LAST).locator("td.hint textarea")).to_have_count(0)  # 答えの無い行は空


def test_rewriter_overwrites_fields_that_have_input(page, project, qwen_mode):
    # 🔄 は入力のある欄も Qwen の答えで置き換える（🤖・🔖・🎲 は空の欄だけ）
    project.write(project.row_index(ASK), "looks: sitting")
    project.write(project.row_index(ASK), "girl sits.", section="action")
    project.save()
    open_project(page)
    expect(rewriter(page, ASK)).to_have_attribute("title", re.compile("上書き"))
    rewriter(page, ASK).click()
    girl = row(page, ASK).locator('td.cell[data-section="girl"] .ln:not(.empty)')
    expect(girl).to_have_text(["looks: standing", "clothes: red dress"])
    expect(row(page, ASK).locator('td.cell[data-section="action"] .ln')).to_have_text(["girl waves."])
    expect(page.locator("#status")).to_have_class("ok")
    expect(page.locator("#status")).to_contain_text("上書き")


def test_without_the_qwen_option_there_is_no_robot(page, project):
    open_project(page)
    expect(page.locator("#gridHead th", has_text="🤖")).to_have_count(0)
    expect(page.locator("td.qwen")).to_have_count(0)
    expect(page.locator("#gridHead .side-view")).to_have_count(0)  # 右端の列は preview の文字だけ（今と同じ）
