"""マーキング（作業用の印。キャプションには書き出さない）

- 排他の列（mark）: 0〜7 のどれか1つ、または空
- 複数可の列（marks）: 0〜7 の組み合わせ
- 中では番号で持ち、画面に見せる記号はこの表で決める（記号を差し替えても、保存したデータは変わらない）
- 表の中の形（文字）: 排他は '' か '0'〜'7'、複数は番号を小さい順にカンマでつないだもの（'0,3,6'）。保存データは数と数の組
- 単語のマーク（0〜7。中の名前は auto）: 行には持たない。プロジェクトごとの設定（番号ごとに、A, B を除いた段落の名前・キー・語句）で、
  その語句に合う語句のある行に付く（画面とサーバーが入力から決める。合わせ方は matches_pattern）。キーなし（空）は文に合わせる。
  設定は table.json の auto_marks に書く
"""
import re

from caption_format import parse_line
from subjects import base_name

COUNT = 8  # 列ごとのマークの数（番号は 0〜7）
ONE = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']  # 排他のマークの記号（番号の順）
MANY = ['★', '●', '▲', '■', '◆', '♥', '♣', '♠']  # 複数のマークの記号（番号の順）
AUTO = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧']  # 単語のマークの記号（番号の順）
AUTO_FIELDS = ('section', 'key', 'phrase')
COLUMNS = ['mark', 'marks']
# 0.4.4 までの保存データは記号で持っていた。読むときにこの表で番号へ直す（今の記号の表を変えても読めるように、別に固定）
LEGACY_ONE = ['A', 'B', 'C', 'D']
LEGACY_MANY = ['★', '●', '▲', '■']


def is_number(mark):
    """マークの番号か（0〜7 の整数。真偽は番号ではない）"""
    return isinstance(mark, int) and not isinstance(mark, bool) and 0 <= mark < COUNT


def check_number(mark):
    if not is_number(mark):
        raise ValueError(f'マークの番号は 0〜{COUNT - 1} です')
    return mark


def check_one(mark):
    """排他のマーク（None は外す）"""
    return None if mark is None else check_number(mark)


def one_number(text):
    """表の中の排他のマーク → 番号（無ければ None）"""
    return int(text) if isinstance(text, str) and text.isdigit() and int(text) < COUNT else None


def one_text(mark):
    return '' if mark is None else str(mark)


def many_numbers(text):
    """表の中の複数のマーク → 番号の組（小さい順。知らないものは捨てる）"""
    parts = text.split(',') if isinstance(text, str) else []
    return sorted({int(p) for p in parts if p.isdigit() and int(p) < COUNT})


def many_text(numbers):
    return ','.join(str(n) for n in sorted(set(numbers)))


def toggle_many(text, mark, on):
    """複数のマークに番号を足す・消す"""
    return many_text(set(many_numbers(text)) - {mark} | ({mark} if on else set()))


def one_from_file(value):
    """保存データの排他のマーク（番号。0.4.4 までは記号）→ 表の中の形"""
    if isinstance(value, str) and value in LEGACY_ONE:
        return str(LEGACY_ONE.index(value))
    return one_text(value) if is_number(value) else ''


def many_from_file(value):
    """保存データの複数のマーク（番号の組。0.4.4 までは記号の並び）→ 表の中の形"""
    if isinstance(value, str):
        return many_text(LEGACY_MANY.index(ch) for ch in value if ch in LEGACY_MANY)
    return many_text(n for n in value if is_number(n)) if isinstance(value, list) else ''


def marks_to_file(mark, marks):
    """表の中の形 → 保存データ（無いものは書かない）"""
    one, many = one_number(mark), many_numbers(marks)
    return {**({'mark': one} if one is not None else {}), **({'marks': many} if many else {})}


def auto_mark_of(value):
    """保存データの単語のマークの設定 {section, key, phrase}（どれも文字。段落と語句は空でない。キーなしは空）。それ以外は None（設定なし）"""
    ok = (isinstance(value, dict) and all(isinstance(value.get(f), str) for f in AUTO_FIELDS)
          and value['section'].strip() and value['phrase'].strip())
    return {f: value[f] for f in AUTO_FIELDS} if ok else None


def auto_marks_from_file(value):
    """保存データの単語のマークの設定（8 個。無い・足りない番号は設定なし）"""
    items = value if isinstance(value, list) else []
    return [auto_mark_of(items[i]) if i < len(items) else None for i in range(COUNT)]


def matches_pattern(pattern, phrase):
    """単語のマークの語句 pattern が入力の語句 phrase に合うか（文末の . は外して比べる。* は何文字でも、ほかは文字のまま）

    画面の matchesPattern と同じ
    """
    p, t = (s.strip().removesuffix('.').strip() for s in (pattern, phrase))
    if '*' not in p:
        return p == t
    return re.fullmatch('.*'.join(map(re.escape, p.split('*'))), t) is not None


def auto_marks_of(texts, auto_marks):
    """行の入力 {段落: 入力} に付く単語のマーク（番号を小さい順に）: 設定した語句が、A, B を除いた名前が同じ段落の、
    そのキーの行（キーなしは文の行）の語句に合う。画面の autoMarksOf と同じ
    """
    def hit(m):
        return any(matches_pattern(m['phrase'], p)
                   for s, text in texts.items() if base_name(s) == m['section']
                   for key, phrases in map(parse_line, text.splitlines()) if key == m['key']
                   for p in phrases)

    return [i for i, m in enumerate(auto_marks) if m and hit(m)]
