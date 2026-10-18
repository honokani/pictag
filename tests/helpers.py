import io
import os
import shutil
from pathlib import Path

from PIL import Image

from kinds import column_key

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXED_COLUMNS = ("サムネイル", "is_dead")

# 値だけ指定したときの大kind・中kind
BIG, MID = "g", "m"


def item(value, big=BIG, mid=MID, small=""):
    """列 (大kind, 中kind, 小kind, 値)"""
    return (big, mid, small, value)


def col(value, **names):
    """列の文字列キー（表の列名）"""
    return column_key(item(value, **names))


def to_key(column):
    """列のタプル・値の名前（既定の大kind・中kind）・固定列名を、表の列名にする"""
    if isinstance(column, tuple):
        return column_key(column)
    return column if column in FIXED_COLUMNS else col(column)


def target(it):
    """API に渡す対象 {big, mid, small, value}"""
    return dict(zip(("big", "mid", "small", "value"), it))


def caption_of(*values):
    """既定の大kind・中kind の値だけにチェックしたときのキャプション"""
    return f"{BIG}:\n  - {MID}: {', '.join(values)}"


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
    """旧版（SDXL 版）で作った dump（tests/fixtures/legacy_v0/<kind>）を base_dir へ配置する"""
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

    def add(self, value, big=BIG, mid=MID, small="", default=False):
        return self.post("/add_value", {"big": big, "mid": mid, "small": small, "value": value, "default_value": default})

    def set(self, row_index, column, value=True):
        return self.post("/update_cell", {"row_index": row_index, "column_name": to_key(column), "value": value})

    def save(self):
        return self.post("/save_data")

    def rows(self):
        r = self.c.get("/get_table_data")
        assert r.status_code == 200, r.data
        return r.get_json()["data"]

    def row_index(self, image_name):
        """画像名から行の index を引く（フロントが update_cell に送る値）"""
        return next(r["index"] for r in self.rows() if r["サムネイル"] == image_name)
