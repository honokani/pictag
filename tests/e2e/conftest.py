import threading

import pytest
from werkzeug.serving import make_server

import app as pictag


@pytest.fixture
def live_server(tool):
    """テスト用の tool（一時ディレクトリ）で動くサーバー"""
    server = make_server("127.0.0.1", 0, pictag.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


@pytest.fixture(scope="session")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        launched, reasons = None, []
        # インストール済みの Chrome / Edge を優先（playwright install 不要）
        for options in ({"channel": "chrome"}, {"channel": "msedge"}, {}):
            try:
                launched = p.chromium.launch(**options)
                break
            except Exception as e:
                reasons.append(f"{options}: {e}")
        if launched is None:
            pytest.skip("ブラウザを起動できません: " + " / ".join(reasons))
        yield launched
        launched.close()


@pytest.fixture
def page(browser, live_server):
    context = browser.new_context()
    page = context.new_page()
    page.base_url = live_server
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    yield page
    context.close()
    assert not errors, f"JavaScript の例外: {errors}"
