"""辞書（使用中の語句・共用辞書）と、入力への語句の足し引き

- 使用中の語句は全プロジェクトの入力から作る。新しい語句は使った時点で入り、どの画像からも消えたら消える
- 共用辞書（data_work/shared.json）は freeze や登録で語句を入れたもの。使われなくなっても残る。
  確定タグ（段落ごとのキーの並び）と「1つだけ」のグループ（groups.py）も持つ。削除・改名は「キー: 語句」単位（どの段落のものも）
- キーなしの文（action など）は、文のほかに単語（girl / spread / girl's ...）も辞書に入れる
"""
import re
from collections import Counter

from caption_format import parse_line, phrases_of, with_line
from groups import normalize_groups

RESERVED_SECTIONS = {'サムネイル', 'is_dead', 'mark', 'marks'}  # 表の固定列と同じ名前は使えない

# 確定タグ: 段落ごとのキーの並び（空の欄にも出す）。subject は人物などの段落（girl / guy / dog …）すべてに使う
DEFAULT_TEMPLATES = {'picture': ['place', 'characters', 'vibes', 'view', 'extra'], 'subject': ['looks', 'clothes', 'body']}
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
    return {'templates': {name: list(keys) for name, keys in DEFAULT_TEMPLATES.items()}, 'phrases': [], 'words': [],
            'groups': []}


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


def register_phrases(shared, entries):
    """(段落, キー, 語句) を共用辞書に足す（既にあるものは足さない）"""
    known = {phrase_id(p) for p in shared['phrases']}
    new = [t for t in dict.fromkeys(entries) if t not in known]
    return {**shared, 'phrases': [*shared['phrases'], *({'section': s, 'key': k, 'phrase': p} for s, k, p in new)]}


def register_words(shared, entries):
    """(段落, 単語) を共用辞書に足す（既にあるものは足さない）"""
    known = {word_id(w) for w in shared['words']}
    new = [t for t in dict.fromkeys(entries) if t not in known]
    return {**shared, 'words': [*shared['words'], *({'section': s, 'word': w} for s, w in new)]}


def freeze(shared, phrase_usage, word_usage):
    """使用中の語句・単語を共用辞書に足す（既にあるものは足さない）。(新しい共用辞書, 足した数) を返す"""
    frozen = register_words(register_phrases(shared, phrase_usage), word_usage)
    added = len(frozen['phrases']) - len(shared['phrases']) + len(frozen['words']) - len(shared['words'])
    return frozen, added


def ungroup_phrases(shared, pairs):
    """(キー, 語句) をグループから外す（語句が1つになったグループは消える）"""
    out = set(pairs)
    groups = [{**g, 'phrases': [p for p in g['phrases'] if (g['key'], p) not in out]} for g in shared['groups']]
    return {**shared, 'groups': normalize_groups(groups)}


def group_phrases(shared, key, phrases):
    """同じキーの語句を「1つだけ」のグループにする（入っているグループがあれば、それとまとめる）"""
    return {**shared, 'groups': normalize_groups([*shared['groups'], {'key': key, 'phrases': list(phrases)}])}


def unregister_phrases(shared, pairs):
    """(キー, 語句) を共用辞書から消す（どの段落のものも）。グループからも外す"""
    out = set(pairs)
    kept = [p for p in shared['phrases'] if (p['key'], p['phrase']) not in out]
    return ungroup_phrases({**shared, 'phrases': kept}, out)


def unregister_words(shared, words):
    """単語を共用辞書から消す（どの段落のものも）"""
    out = set(words)
    return {**shared, 'words': [w for w in shared['words'] if w['word'] not in out]}


def rename_registered(shared, key, old, new):
    """共用辞書の「key: old」を new にする（どの段落のものも。重なれば1つに）。グループの中の名前も変える"""
    def rename(phrase):
        return new if phrase == old else phrase

    phrases = [{**p, 'phrase': rename(p['phrase'])} if p['key'] == key else p for p in shared['phrases']]
    groups = [{**g, 'phrases': [rename(p) for p in g['phrases']]} if g['key'] == key else g for g in shared['groups']]
    return {**shared, 'phrases': list({phrase_id(p): p for p in phrases}.values()), 'groups': normalize_groups(groups)}


def move_registered(shared, belongs, src, dst, phrases):
    """共用辞書の、belongs(段落) が真の段落の「src: 語句」（phrases）を「dst: 語句」にする（重なれば1つに）。グループはそのまま"""
    moving = set(phrases)

    def move(p):
        return {**p, 'key': dst} if belongs(p['section']) and p['key'] == src and p['phrase'] in moving else p

    return {**shared, 'phrases': list({phrase_id(p): p for p in map(move, shared['phrases'])}.values())}


def check_phrase(key, phrase):
    """語句の前後の空白を除いて検証する（カンマ・改行は語句の区切り。キーなしの文の「:」はキーと読まれる）"""
    phrase = phrase.strip() if isinstance(phrase, str) else ''
    if not phrase:
        raise ValueError('語句を入力してください')
    if '\n' in phrase or '\r' in phrase:
        raise ValueError('語句に改行は使えません')
    if ',' in phrase:
        raise ValueError('語句にカンマは使えません（語句の区切りになります）')
    if not key and ':' in phrase:
        raise ValueError('キーのない文に「:」は使えません（キーと読まれます）')
    return phrase


def check_key(key):
    """キー（空はキーなしの文）を検証する"""
    if not isinstance(key, str) or key != key.strip() or any(ch in key for ch in ',:\n\r'):
        raise ValueError('キーの指定が正しくありません')
    return key


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


def is_choice(phrase, member, targeted=()):
    """語句がボタンの語句 member にあたるか（targeted の語句は、後ろに対象の付いたもの（close-up face）も）"""
    return phrase == member or (member in targeted and phrase.startswith(f'{member} '))


def set_choice(text, key, phrase, group, on, targeted=()):
    """key の行に group の語句を1つだけ置く（on なら phrase にし、off なら group の語句を消す）

    targeted の語句は、後ろに対象の付いたもの（close-up face）も group の語句として消す
    """
    cleared = remove_matching(text, key, lambda p: any(is_choice(p, member, targeted) for member in group))
    return add_phrase(cleared, key, phrase) if on else cleared


def remove_matching(text, key, match):
    """入力の key の行から、match に合う語句を消す（語句が無くなった行は消す）"""
    def edit(line):
        k, phrases = parse_line(line)
        if k != key or not any(map(match, phrases)):
            return line
        rest = [p for p in phrases if not match(p)]
        return render_input_line(k, rest) if rest else None

    return '\n'.join(line for line in map(edit, text.splitlines()) if line is not None)


def remove_phrase(text, key, phrase):
    """入力から語句を消す（語句が無くなった行は消す）"""
    return remove_matching(text, key, lambda p: p == phrase)


def rename_phrase(text, key, old, new):
    """入力の key の行の語句 old を new にする（同じ行に new があれば1つに）"""
    def edit(line):
        k, phrases = parse_line(line)
        if k != key or old not in phrases:
            return line
        return render_input_line(k, list(dict.fromkeys(new if p == old else p for p in phrases)))

    return '\n'.join(map(edit, text.splitlines()))


def move_phrases(text, src, dst, phrases, keys):
    """入力の src の行の語句 phrases を dst の行へ移す（dst にもうある語句は src から消すだけ。語句が無くなった src の行は消す）

    dst の行は1行にまとめ、確定タグのキー（keys）なら並びの位置に、ほかのキーなら今の行の位置（無ければ末尾）に置く。
    phrases が src の行に無ければ変えない
    """
    parsed = [(line, *parse_line(line)) for line in text.splitlines()]
    moving = [p for p in dict.fromkeys(phrases) if any(k == src and p in ps for _, k, ps in parsed)]
    if not moving:
        return text

    def without(line, key, ps):
        if key != src or not any(p in moving for p in ps):
            return [line]
        kept = [p for p in ps if p not in moving]
        return [render_input_line(src, kept)] if kept else []

    rest = [kept for line, k, ps in parsed for kept in without(line, k, ps)]
    value = ', '.join(dict.fromkeys([*(p for _, k, ps in parsed if k == dst for p in ps), *moving]))
    if dst in keys:
        return with_line('\n'.join(rest), dst, value, keys)
    at = next((i for i, line in enumerate(rest) if parse_line(line)[0] == dst), len(rest))
    others = [line for line in rest if parse_line(line)[0] != dst]
    return '\n'.join([*others[:at], f'{dst}: {value}', *others[at:]])


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
