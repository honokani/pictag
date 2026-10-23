"""action の見出しの ⇄（Playwright）: 文の動詞の形（is doing / does）を、一覧で確かめてから動詞ごとに多い方にそろえる"""
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
    """r0〜r2 の 3 枚。sit・wave は does が多く、smile は is doing が多い。hand は s が無い（迷う）。保存して、画面で開けるようにする"""
    api = Api(pictag.app.test_client())
    api.load(make_images(tmp_path / "imgs" / "proj", {f"r{i}.png": (100, 100) for i in range(3)}))
    for i, text in enumerate(["girl sits.\nguy waves.\ngirl is smiling.", "she sit.\ngirl waves.\nguy is smiling.",
                              "guy is sitting and waving.\nguy hand on hip.\ngirl smiles."]):
        api.write(api.row_index(f"r{i}.png"), text, section="action")
    api.save()
    return api


def action_lines(page, name):
    return page.locator(f'#gridBody tr[data-name="{name}"] td.cell[data-section="action"] .ln')


def test_verb_button_lists_the_changes_under_each_verb(page, project):
    # 動詞ごとに、件数の行とその文。2つの動詞が変わる文は両方に出て、チェックは共通
    page.goto(page.base_url)
    page.select_option("#projectSelect", "proj")
    expect(page.locator("#gridBody tr")).to_have_count(3)
    expect(page.locator("#gridHead .verb-forms")).to_have_count(1)  # action の見出しだけ
    page.locator('#gridHead th[data-section="action"] .verb-forms').click()
    dialog = page.locator("#verbDialog")
    expect(dialog).to_be_visible()
    expect(page.locator("#verbSummary")).to_have_text("動詞ごとに、多い方の形にそろえます")
    groups = dialog.locator(".verb-group")
    expect(groups.locator(".verb-head")).to_have_text(["hand is doing 0・does 1 → does", "sit is doing 1・does 2 → does",
                                                       "smile is doing 2・does 1 → is doing", "wave is doing 1・does 2 → does"])
    expect(groups.nth(0).locator("li")).to_have_text(["迷う r2.png guy hand on hip. → guy hands on hip."])
    expect(groups.nth(0).locator("input")).not_to_be_checked()  # 迷う文は入れない
    expect(groups.nth(1).locator("li")).to_have_text(["r1.png she sit. → she sits.",
                                                      "r2.png guy is sitting and waving. → guy sits and waves."])
    expect(groups.nth(2).locator("li")).to_have_text(["r2.png girl smiles. → girl is smiling."])
    expect(groups.nth(3).locator("li")).to_have_text(["r2.png guy is sitting and waving. → guy sits and waves."])
    expect(groups.nth(1).locator("input").nth(0)).to_be_checked()
    groups.nth(1).locator("input").nth(1).uncheck()  # guy is sitting and waving. は外す → wave の下も外れる
    expect(groups.nth(3).locator("input")).not_to_be_checked()
    page.locator("#verbApply").click()
    expect(dialog).to_be_hidden()
    expect(action_lines(page, "r0.png")).to_have_text(["girl sits.", "guy waves.", "girl is smiling."])
    expect(action_lines(page, "r1.png")).to_have_text(["she sits.", "girl waves.", "guy is smiling."])
    expect(action_lines(page, "r2.png")).to_have_text(["guy is sitting and waving.", "guy hand on hip.", "girl is smiling."])
    expect(page.locator("#status")).to_have_class("ok")


def test_verb_button_asks_which_form_for_verbs_with_a_tie(page, project):
    # 同じ数の動詞があれば、どちらにそろえるかを聞く（選ぶまで入れられない）。選ぶと、同じ数の動詞をその形にした一覧
    project.write(project.row_index("r0.png"), "girl sits.", section="action")
    project.write(project.row_index("r1.png"), "girl is sitting.", section="action")
    project.write(project.row_index("r2.png"), "", section="action")
    project.save()
    page.goto(page.base_url)
    page.select_option("#projectSelect", "proj")
    expect(page.locator("#gridBody tr")).to_have_count(3)
    page.locator('#gridHead th[data-section="action"] .verb-forms').click()
    expect(page.locator("#verbSummary")).to_have_text("同じ数の動詞があります。どちらにそろえますか？")
    expect(page.locator("#verbLists .verb-head")).to_have_text(["sit is doing 1・does 1"])
    choices = page.locator("#verbLists .verb-choice button")
    expect(choices).to_have_text(["is doing の形（girl is sitting.）", "does の形（girl sits.）"])
    expect(page.locator("#verbApply")).to_be_disabled()
    choices.nth(1).click()
    expect(page.locator("#verbSummary")).to_have_text("動詞ごとに、多い方の形にそろえます")
    expect(page.locator("#verbLists .verb-head")).to_have_text(["sit is doing 1・does 1 → does（同じ数）"])
    page.locator("#verbApply").click()
    expect(action_lines(page, "r0.png")).to_have_text(["girl sits."])
    expect(action_lines(page, "r1.png")).to_have_text(["girl sits."])
