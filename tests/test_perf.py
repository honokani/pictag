"""保存（save_data → load_data）の所要時間"""
import time

from helpers import make_images

N_IMAGES, N_PHRASES = 800, 60
LIMIT_SEC = 4.0  # SDXL 版の修正前は約 8.5 秒（画像数×タグ数ぶん DataFrame を絞り込んでいた）


def test_save_with_many_images_and_phrases(api, tool, tmp_path):
    imgs = make_images(tmp_path / "imgs" / "proj", {f"img{i:05d}.png": (8, 8) for i in range(N_IMAGES)})
    api.load(imgs)
    rows = list(range(N_IMAGES))
    for j in range(N_PHRASES):
        assert api.bulk_add(rows, f"k{j % 5}: phrase{j}", section=("picture", "girl")[j % 2])["success"]

    t = time.perf_counter()
    api.save()
    elapsed = time.perf_counter() - t
    assert len(tool.df) == N_IMAGES
    assert elapsed < LIMIT_SEC, f"{elapsed:.2f}s"
