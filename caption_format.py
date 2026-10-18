"""段落の入力（文字列）→ Krea2 用キャプション

段落（大kind）ごとの入力は複数行の文字列。各行は「キー: 語句, 語句」か、キーなしの文（カンマで区切ってもよい）。

    girl:
      - looks: full body shot, standing
      - body: long black hair, bare hands

- 空の段落・語句の無い行は出さない。行頭の「-」と前後の空白は無視する
- キー付きの行は、末尾の語が同じ語句をまとめる（long hair, black hair → long black hair）。キーなしの文はまとめない
"""


def group_in_order(pairs):
    """(キー, 値) を、キーが最初に出た順にまとめる"""
    groups = {}
    for key, value in pairs:
        groups.setdefault(key, []).append(value)
    return groups.items()


def split_phrases(text):
    """カンマで区切り、空と重複を除く（順序は保つ）"""
    return list(dict.fromkeys(p.strip() for p in text.split(',') if p.strip()))


def parse_line(line):
    """1行を (キー, [語句]) にする。キーなしの行はキーが空"""
    line = line.strip().lstrip('-').strip()
    key, sep, rest = line.partition(':')
    if sep and key.strip() and ',' not in key:
        return key.strip(), split_phrases(rest)
    return '', split_phrases(line)


def parse_lines(text):
    """入力を (キー, [語句]) の列にする（語句の無い行は除く）"""
    return [(key, phrases) for key, phrases in map(parse_line, text.splitlines()) if phrases]


def tail_group(phrase):
    """末尾の語でまとめるためのキー（1語の語句はまとめない）"""
    words = phrase.split()
    return ('tail', words[-1].lower()) if len(words) >= 2 else ('single', phrase)


def merge_group(phrases):
    if len(phrases) == 1:
        return phrases[0]
    modifiers = dict.fromkeys(word for phrase in phrases for word in phrase.split()[:-1])
    return ' '.join([*modifiers, phrases[0].split()[-1]])


def merge_same_tail(phrases):
    """末尾の語が同じ語句（2語以上）を、最初に出た位置へまとめる"""
    return [merge_group(group) for _, group in group_in_order((tail_group(p), p) for p in phrases)]


def render_line(key, phrases):
    return f"{key}: {', '.join(merge_same_tail(phrases))}" if key else ', '.join(phrases)


def render_section(name, text):
    lines = [render_line(key, phrases) for key, phrases in parse_lines(text)]
    return '\n'.join([f'{name}:', *(f'  - {line}' for line in lines)]) if lines else ''


def render_caption(sections):
    """[(段落, 入力)] をキャプションにする"""
    return '\n\n'.join(filter(None, (render_section(name, text) for name, text in sections)))


def phrases_of(text):
    """入力の語句を (キー, 語句) で並べる（まとめる前の1つずつ）"""
    return [(key, phrase) for key, phrases in parse_lines(text) for phrase in phrases]
