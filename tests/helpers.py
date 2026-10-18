import io
import os
import shutil
from pathlib import Path

from PIL import Image
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from caption_format import render_caption

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# 段落を指定しないときの段落（新規プロジェクトの既定の段落にある）
SECTION = "girl"


def caption_of(text, section=SECTION):
    """1つの段落だけに入力したときのキャプション"""
    return render_caption([(section, text)])


def word_tokenizer():
    """空白と記号で区切るだけの小さなトークナイザー（テスト用）"""
    tokenizer = Tokenizer(WordLevel({"[UNK]": 0}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    return tokenizer


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

    def write(self, row_index, text, section=SECTION):
        return self.post("/update_text", {"row_index": row_index, "section": section, "text": text})

    def add_section(self, name):
        return self.post("/add_section", {"name": name})

    def bulk_add(self, rows, text, section=SECTION):
        return self.post("/add_phrase", {"rows": rows, "section": section, "text": text})

    def bulk_remove(self, rows, text, section=SECTION):
        return self.post("/remove_phrase", {"rows": rows, "section": section, "text": text})

    def save(self):
        return self.post("/save_data")

    def table(self):
        r = self.c.get("/get_table_data")
        assert r.status_code == 200, r.data
        return r.get_json()

    def rows(self):
        return self.table()["data"]

    def row_index(self, image_name):
        """画像名から行の index を引く（フロントが update_text に送る値）"""
        return next(r["index"] for r in self.rows() if r["サムネイル"] == image_name)

    def dictionary(self):
        r = self.c.get("/get_dictionary")
        assert r.status_code == 200, r.data
        return r.get_json()

    def phrases(self):
        """辞書の語句 {(段落, キー, 語句): 使用回数}"""
        return {(w["section"], w["key"], w["phrase"]): w["count"] for w in self.dictionary()["phrases"]}

    def words(self):
        """辞書の単語（キーなしの文から） {(段落, 単語): 使用回数}"""
        return {(w["section"], w["word"]): w["count"] for w in self.dictionary()["words"]}
