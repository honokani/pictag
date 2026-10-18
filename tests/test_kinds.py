"""kind（種別）ごとのキャプション一覧"""
import pytest

from helpers import make_images


@pytest.fixture
def loaded(api, tmp_path):
    api.load(make_images(tmp_path / "imgs" / "proj", {"a.png": (100, 100)}))
    api.add("A", kind="k")
    api.add("Y", kind="char/outfit")
    api.add("Q", kind="what?#%")
    return api


@pytest.mark.parametrize("route", ["/get_captions_by_kind", "/get_table_captions_by_kind"])
@pytest.mark.parametrize("kind, caption", [("k", "A"), ("char/outfit", "Y"), ("what?#%", "Q")])
def test_captions_by_kind_query(loaded, client, route, kind, caption):
    r = client.get(route, query_string={"kind": kind})
    assert r.status_code == 200
    assert r.get_json()["captions"] == ["new_column", caption]


def test_captions_by_kind_path_route_still_works(loaded, client):
    assert client.get("/get_captions_by_kind/k").get_json()["captions"] == ["new_column", "A"]
