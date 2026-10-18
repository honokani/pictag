"""使用中の語句（全プロジェクトの入力から作る辞書）と、入力への語句の足し引き

辞書は入力から作るので、新しい語句は使った時点で入り、どの画像からも消えたら消える。
"""
from collections import Counter

from caption_format import parse_line, phrases_of

RESERVED_SECTIONS = {'サムネイル', 'is_dead'}  # 表の固定列と同じ名前は使えない


def count_words(section_texts):
    """[(段落, 入力)] から (段落, キー, 語句) の使用回数を数える"""
    return Counter((section, key, phrase) for section, text in section_texts for key, phrase in phrases_of(text))


def dictionary_entries(counter):
    """使用回数の多い順に並べた辞書（同数なら段落・キー・語句の順）"""
    return [{'section': s, 'key': k, 'phrase': p, 'count': n}
            for (s, k, p), n in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]


def render_input_line(key, phrases):
    """入力の1行に戻す（キーなしは語句をカンマでつなぐ）"""
    return f"{key}: {', '.join(phrases)}" if key else ', '.join(phrases)


def add_phrase(text, key, phrase):
    """入力に語句を足す。同じキーの行があればその末尾に、無ければ行を足す（既にあれば変えない）"""
    lines = text.rstrip().splitlines()
    parsed = [parse_line(line) for line in lines]
    if any(k == key and phrase in phrases for k, phrases in parsed):
        return text
    at = next((i for i, (k, _) in enumerate(parsed) if key and k == key), None)
    if at is None:
        return '\n'.join([*lines, render_input_line(key, [phrase])])
    return '\n'.join([*lines[:at], render_input_line(key, [*parsed[at][1], phrase]), *lines[at + 1:]])


def remove_phrase(text, key, phrase):
    """入力から語句を消す（語句が無くなった行は消す）"""
    def edit(line):
        k, phrases = parse_line(line)
        if k != key or phrase not in phrases:
            return line
        rest = [p for p in phrases if p != phrase]
        return render_input_line(k, rest) if rest else None

    return '\n'.join(line for line in map(edit, text.splitlines()) if line is not None)


def check_section_name(name):
    """段落の名前の前後の空白を除いて検証する"""
    name = name.strip() if isinstance(name, str) else ''
    if not name:
        raise ValueError('段落の名前を入力してください')
    if '\n' in name or '\r' in name:
        raise ValueError('段落の名前に改行は使えません')
    if ':' in name:
        raise ValueError('段落の名前に「:」は使えません')
    if name in RESERVED_SECTIONS:
        raise ValueError(f'「{name}」は段落の名前に使えません')
    return name
