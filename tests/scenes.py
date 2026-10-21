"""テスト用の入力: 映画の有名なシーン（pictag の入力の形。書き出すと Krea 2 のキャプションになる）

SCENES: {画像名: {段落: 入力}}（本体の public_samples.py。qwen 版で見本が足りないときにも使う）
"""
from collections import Counter

from helpers import make_images
from public_samples import SCENES
from subjects import base_name

FIXED = ("picture", "action")


def subject_counts(names):
    """場面の人物の段落の数（名前ごとに、場面の中で一番多い数）"""
    counts = Counter()
    for name in names:
        counts |= Counter(base_name(s) for s in SCENES[name] if s not in FIXED)
    return counts


def column_of(section, sections):
    """場面の段落名 → 表の段落名（表で A, B が付いていれば A の方）"""
    return section if section in sections else f"{section} A"


def load_scenes(api, image_dir, names):
    """names の場面の画像を作って読み込み、人物の段落を足して入力する。{画像名: 行の index} を返す"""
    make_images(image_dir, {name: (64, 64) for name in names})
    api.load(image_dir)
    for base, count in subject_counts(names).items():
        have = sum(1 for s in api.table()["sections"] if base_name(s) == base)
        for _ in range(count - have):
            api.add_section(base)
    sections = api.table()["sections"]
    rows = {name: api.row_index(name) for name in names}
    for name in names:
        for section, text in SCENES[name].items():
            api.write(rows[name], text, section=column_of(section, sections))
    return rows
