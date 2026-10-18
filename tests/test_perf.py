"""保存（save_data → load_data）の所要時間"""
import time

from helpers import make_images

N_IMAGES, N_TAGS = 800, 60
LIMIT_SEC = 4.0  # 修正前は約 8.5 秒（画像数×タグ数ぶん DataFrame を絞り込んでいた）


def test_save_with_many_images_and_tags(api, tool, tmp_path):
    imgs = make_images(tmp_path / "imgs" / "proj", {f"img{i:05d}.png": (8, 8) for i in range(N_IMAGES)})
    api.load(imgs)
    for j in range(N_TAGS):
        api.add(f"tag{j}", mid=f"m{j % 5}")

    t = time.perf_counter()
    api.save()
    elapsed = time.perf_counter() - t
    assert len(tool.df) == N_IMAGES
    assert elapsed < LIMIT_SEC, f"{elapsed:.2f}s"
