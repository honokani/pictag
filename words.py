"""辞書（使用中の語句・共用辞書）と、入力への語句の足し引き

- 使用中の語句は全プロジェクトの入力から作る。新しい語句は使った時点で入り、どの画像からも消えたら消える
- 共用辞書（data_work/shared.json）は freeze で使用中の語句を足したもの。使われなくなっても残る。確定タグ（段落ごとのキーの並び）も持つ
- キーなしの文（action など）は、文のほかに単語（girl / spread / girl's ...）も辞書に入れる
"""
import re
from collections import Counter
from functools import reduce

from caption_format import parse_line, phrases_of

RESERVED_SECTIONS = {'サムネイル', 'is_dead'}  # 表の固定列と同じ名前は使えない

# 確定タグ: 段落ごとのキーの並び（空の欄にも出す）。subject は人物などの段落（girl / guy / dog …）すべてに使う
DEFAULT_TEMPLATES = {'picture': ['place', 'characters', 'vibes', 'view'], 'subject': ['looks', 'clothes', 'body']}
AUTO_KEYS = ['characters']  # 自動で作るキー（入力欄には出さない）

WORD = re.compile(r'[^\s,.;:!?"()\[\]]+')  # 単語（girl's のアポストロフィは残す）


def count_words(section_texts):
    """[(段落, 入力)] から (段落, キー, 語句) の使用回数を数える"""
    return Counter((section, key, phrase) for section, text in section_texts for key, phrase in phrases_of(text))


def sentence_words(text):
    """キーなしの文の単語"""
    return [word for key, phrase in phrases_of(text) if not key for word in WORD.findall(phrase)]


def count_sentence_words(section_texts):
    """[(段落, 入力)] から (段落, 単語) の使用回数を数える（キーなしの文だけ）"""
    return Counter((section, word) for section, text in section_texts for word in sentence_words(text))


def empty_shared():
    return {'templates': {name: list(keys) for name, keys in DEFAULT_TEMPLATES.items()}, 'phrases': [], 'words': []}


def phrase_id(entry):
    return (entry['section'], entry['key'], entry['phrase'])


def word_id(entry):
    return (entry['section'], entry['word'])


def phrase_entries(usage, shared):
    """使用中の語句と共用辞書の語句（使用回数の多い順。共用辞書だけの語句は 0 回）"""
    in_shared = {phrase_id(p) for p in shared['phrases']}
    return [{'section': s, 'key': k, 'phrase': p, 'count': usage.get((s, k, p), 0), 'shared': (s, k, p) in in_shared}
            for s, k, p in sorted(set(usage) | in_shared, key=lambda t: (-usage.get(t, 0), t))]


def word_entries(usage, shared):
    """使用中の単語と共用辞書の単語（使用回数の多い順。共用辞書だけの単語は 0 回）"""
    in_shared = {word_id(w) for w in shared['words']}
    return [{'section': s, 'word': w, 'count': usage.get((s, w), 0), 'shared': (s, w) in in_shared}
            for s, w in sorted(set(usage) | in_shared, key=lambda t: (-usage.get(t, 0), t))]


def freeze(shared, phrase_usage, word_usage):
    """使用中の語句・単語を共用辞書に足す（既にあるものは足さない）。(新しい共用辞書, 足した数) を返す"""
    known_phrases = {phrase_id(p) for p in shared['phrases']}
    known_words = {word_id(w) for w in shared['words']}
    new_phrases = [t for t in phrase_usage if t not in known_phrases]
    new_words = [t for t in word_usage if t not in known_words]
    return ({**shared,
             'phrases': [*shared['phrases'], *({'section': s, 'key': k, 'phrase': p} for s, k, p in new_phrases)],
             'words': [*shared['words'], *({'section': s, 'word': w} for s, w in new_words)]},
            len(new_phrases) + len(new_words))


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


def set_choice(text, key, phrase, group, on):
    """key の行に group の語句を1つだけ置く（on なら phrase にし、off なら group の語句を消す）"""
    cleared = reduce(lambda t, p: remove_phrase(t, key, p), group, text)
    return add_phrase(cleared, key, phrase) if on else cleared


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
