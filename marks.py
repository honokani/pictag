"""マーキング（作業用の印。キャプションには書き出さない）

- 排他の列（mark）: A〜D のどれか1つ、または空
- 複数可の列（marks）: ★●▲■ の組み合わせ。記号の並びは常に ★●▲■ の順
"""
ONE = ['A', 'B', 'C', 'D']
MANY = ['★', '●', '▲', '■']
COLUMNS = ['mark', 'marks']


def check_one(mark):
    """排他のマーク（空は外す）"""
    if mark not in ['', *ONE]:
        raise ValueError(f'排他のマークは {"・".join(ONE)} のどれかです')
    return mark


def check_many(mark):
    if mark not in MANY:
        raise ValueError(f'複数のマークは {"".join(MANY)} のどれかです')
    return mark


def clean_many(marks):
    """複数のマークを ★●▲■ の順に揃える（知らない記号は捨てる）"""
    present = set(marks) if isinstance(marks, str) else set()
    return ''.join(m for m in MANY if m in present)


def toggle_many(marks, mark, on):
    """複数のマークに記号を足す・消す"""
    present = set(clean_many(marks)) - {mark} | ({mark} if on else set())
    return ''.join(m for m in MANY if m in present)
