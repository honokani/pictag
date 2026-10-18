import io
import os
import shutil
from pathlib import Path

from PIL import Image

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def make_images(directory, specs):
    """specs: {ファイル名: (幅, 高さ)} または {ファイル名: ((幅, 高さ), (R, G, B))}"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, spec in specs.items():
        size, color = spec if isinstance(spec[0], tuple) else (spec, (200, 100, 50))
        Image.new("RGB", size, color).save(directory / name)
    return directory


def touch_later(path, seconds=10):
    """mtime を未来へずらす（同一秒内の書き換えでも更新を検出させる）"""
    st = os.stat(path)
    os.utime(path, (st.st_atime + seconds, st.st_mtime + seconds))


def image_of(response):
    """画像レスポンスを PIL.Image にする"""
    assert response.status_code == 200, response.status_code
    return Image.open(io.BytesIO(response.data))


def copy_legacy_fixture(kind, base_dir):
    """旧版で作った dump（tests/fixtures/legacy_v0/<kind>）を base_dir へ配置する"""
    shutil.copytree(FIXTURES_DIR / "legacy_v0" / kind, base_dir, dirs_exist_ok=True)


class Api:
    """テスト用の薄い API ラッパー（レスポンスの JSON を返す）"""

    def __init__(self, client):
        self.c = client

    def post(self, url, payload=None):
        r = self.c.post(url, json=payload or {})
        assert r.status_code == 200, r.data
        return r.get_json()

    def load(self, image_dir):
        return self.post("/load_directory", {"image_dir": str(image_dir)})

    def open_project(self, name):
        return self.post("/load_existing_project", {"project_name": name})

    def add(self, column, kind="k", default=False):
        return self.post("/add_column", {"column_name": column, "kind": kind, "default_value": default})

    def set(self, row_index, column, value=True):
        return self.post("/update_cell", {"row_index": row_index, "column_name": column, "value": value})

    def save(self):
        return self.post("/save_data")

    def rows(self):
        r = self.c.get("/get_table_data")
        assert r.status_code == 200, r.data
        return r.get_json()["data"]

    def row_index(self, image_name):
        """画像名から行の index を引く（フロントが update_cell に送る値）"""
        return next(r["index"] for r in self.rows() if r["サムネイル"] == image_name)
