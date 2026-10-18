"""旧版 pictag（commit 3b1c91d、pandas 2.0.3 / numpy 1.24.3）で dump を作り、互換テスト用 fixture にする。

旧版の環境（Python 3.11 + 旧 requirements: Flask==2.3.3, pandas==2.0.3, Pillow==10.0.1, numpy==1.24.3）で実行する:
    git show 3b1c91d:app.py > <tmp>/app.py
    <旧環境の python> tests/fixtures/make_legacy_dumps.py <tmp>/app.py

出力: tests/fixtures/legacy_v0/{normal,corrupted}/data_out/proj/df_isflaged.dump, data_work/df_captioninfo.dump
- normal: 画像 a, b, big（生存）と c（削除済み）、タグ4つ
- corrupted: normal の後に a も消し、旧版のバグ（完全削除→先頭行チェック→保存）で幽霊行（サムネイル=NaN）が入った dump
"""
import os
import sys
import shutil
import tempfile
import importlib.util
from pathlib import Path

from PIL import Image

OUT_ROOT = Path(__file__).resolve().parent / "legacy_v0"
IMAGES = {"a.png": (100, 100), "b.png": (100, 100), "c.png": (100, 100), "big.png": (800, 800)}
COLUMNS = [("1girl", "people"), ("solo", "people"), ("smile", "expression"), ("outdoors", "background")]
CHECKS = {"a.png": ["1girl", "solo"], "b.png": ["smile"], "big.png": ["1girl", "outdoors"]}


def load_legacy_app(app_path):
    spec = importlib.util.spec_from_file_location("legacy_app", app_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_dumps(work, dest):
    (dest / "data_out" / "proj").mkdir(parents=True, exist_ok=True)
    (dest / "data_work").mkdir(parents=True, exist_ok=True)
    shutil.copy2(work / "data_out" / "proj" / "df_isflaged.dump", dest / "data_out" / "proj" / "df_isflaged.dump")
    shutil.copy2(work / "data_work" / "df_captioninfo.dump", dest / "data_work" / "df_captioninfo.dump")


def main(app_path):
    work = Path(tempfile.mkdtemp(prefix="pictag_legacy_"))
    os.chdir(work)  # 旧版は data_out / data_work をカレントディレクトリに作る
    legacy = load_legacy_app(app_path)

    imgs = work / "imgs" / "proj"
    imgs.mkdir(parents=True)
    for name, size in IMAGES.items():
        Image.new("RGB", size, (120, 80, 40)).save(imgs / name)

    c = legacy.app.test_client()
    c.post("/load_directory", json={"image_dir": str(imgs)})
    for col, kind in COLUMNS:
        c.post("/add_column", json={"column_name": col, "kind": kind, "default_value": False})
    rows = {r["サムネイル"].split("/")[-1].removeprefix("t_"): r["index"] for r in c.get("/get_table_data").get_json()["data"]}
    for name, tags in CHECKS.items():
        for tag in tags:
            c.post("/update_cell", json={"row_index": rows[name], "column_name": tag, "value": True})
    c.post("/save_data")

    (imgs / "c.png").unlink()
    c.post("/load_directory", json={"image_dir": str(imgs)})
    c.post("/save_data")
    copy_dumps(work, OUT_ROOT / "normal")

    # 旧版のバグの連鎖: 先頭の a も消して完全削除 → index の先頭に穴 → 画面の先頭行(配列位置0)をチェック
    # → 幽霊行（サムネイル=NaN）→ 保存は txt 書き出しで失敗するが dump は先に書かれる
    (imgs / "a.png").unlink()
    c.post("/load_directory", json={"image_dir": str(imgs)})
    c.post("/remove_all_dead")
    c.post("/update_cell", json={"row_index": 0, "column_name": "smile", "value": True})
    c.post("/save_data")
    copy_dumps(work, OUT_ROOT / "corrupted")

    print(f"written: {OUT_ROOT}")
    for kind in ["normal", "corrupted"]:
        print(f"--- {kind} ---")
        print(legacy.pd.read_pickle(OUT_ROOT / kind / "data_out" / "proj" / "df_isflaged.dump"))


if __name__ == "__main__":
    main(sys.argv[1])
