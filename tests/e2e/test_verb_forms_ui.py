"""action の見出しの ⇄（Playwright）: 文の動詞の形（is doing / does）を、一覧で確かめてから多い方にそろえる"""
import pytest

import app as pictag
from helpers import Api, make_images, word_tokenizer
from tokens import TokenCounter

sync_api = pytest.importorskip("playwright.sync_api")
expect = sync_api.expect

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def tokens(monkeypatch):
    # 実物のトークナイザーは取りに行かず、空白と記号で区切る小さなもので数える
    monkeypatch.setattr(pictag, "token_counter", TokenCounter(word_tokenizer()))


@pytest.fixture
def project(tool, tmp_path):
    """r0〜r2 の 3 枚。action に is doing の形 1 文と、does の形 3 文。保存して、画面で開けるようにする"""
    api = Api(pictag.app.test_client())
    api.load(make_images(tmp_path / "imgs" / "proj", {f"r{i}.png": (100, 100) for i in range(3)}))
    for i, text in enumerate(["she sit.\nguy waves.", "girl is smiling.", "guy hand on hip."]):
        api.write(api.row_index(f"r{i}.png"), text, section="action")
    api.save()
    return api


def action_lines(page, name):
    return page.locator(f'#gridBody tr[data-name="{name}"] td.cell[data-section="action"] .ln')


def test_verb_button_puts_only_the_checked_changes(page, project):
    page.goto(page.base_url)
    page.select_option("#projectSelect", "proj")
    expect(page.locator("#gridBody tr")).to_have_count(3)
    expect(page.locator("#gridHead .verb-forms")).to_have_count(1)  # action の見出しだけ
    page.locator('#gridHead th[data-section="action"] .verb-forms').click()
    dialog = page.locator("#verbDialog")
    expect(dialog).to_be_visible()
    expect(page.locator("#verbSummary")).to_have_text("is doing の形 1 文・does の形 3 文 → does の形（girl sits.）にそろえます")
    sure = dialog.locator(".verb-sure input")
    expect(sure).to_have_count(2)
    expect(sure.nth(0)).to_be_checked()
    expect(dialog.locator(".verb-unsure input")).not_to_be_checked()  # 迷う文（guy hand on hip.）は入れない
    sure.nth(1).uncheck()  # girl is smiling. は外す
    page.locator("#verbApply").click()
    expect(dialog).to_be_hidden()
    expect(action_lines(page, "r0.png")).to_have_text(["she sits.", "guy waves."])
    expect(action_lines(page, "r1.png")).to_have_text(["girl is smiling."])
    expect(action_lines(page, "r2.png")).to_have_text(["guy hand on hip."])
    expect(page.locator("#status")).to_have_class("ok")
