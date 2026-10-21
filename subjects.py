"""人物などの段落（girl / guy A / dog …）: 自動の命名、characters の自動計算、view の選択肢"""
import re
from collections import Counter

from caption_format import group_in_order, phrases_of

LETTERED = re.compile(r'^(.*\S) ([A-Z])$')  # guy A の「 A」
IRREGULAR_PLURALS = {'man': 'men', 'woman': 'women', 'person': 'people', 'child': 'children'}
# 人物でない物（dog: / cat: …）をキーで書き分ける段落。確定タグと POV のボタンを持たず、characters にはキーを数なしで並べる
OTHERS = 'else'

# POV のボタンの絵文字（段落の名前の A, B を除いた部分で決める）と色（女性・男性）
EMOJI = {'girl': '👧', 'woman': '👩', 'guy': '👨', 'man': '👨', 'boy': '👦', 'dog': '🐕', 'cat': '🐈'}
OTHER_EMOJI = '👤'
FEMALE = {'girl', 'woman'}
MALE = {'guy', 'man', 'boy'}
# 語句の候補をまとめる名前の組（女性・男性）。ほかの段落の候補は種類ごと（A, B を除いた名前）
CANDIDATE_GROUPS = [sorted(FEMALE), sorted(MALE)]
THIRD_PERSON = {'emoji': '👥', 'label': '', 'tone': '', 'phrase': 'third-person POV'}

# view の 🎥 の選択肢。組の中は1つだけ（☓ で組の語句を消す）。view の行には自由記述も書ける
# 2つ目の組は高さ（上 → 目の高さ → 下）、3つ目の組はショットの大きさ（寄り → 引き）
CAMERA_GROUPS = [['from front', 'from side', 'from behind'], ['from above', 'eye level', 'from below'],
                 ['close-up', 'portrait', 'medium shot', 'long shot']]
# 後ろに対象を書ける語句（close-up face）。ボタンでは、対象の付いたものも同じ語句として扱う
TARGETED = ['close-up']
# 🎥 のボタンの絵文字（語句はボタンにマウスを載せると見える）。above / below は鳥の目・虫の目、eye level は人の目
CAMERA_EMOJI = {'from front': '🧍', 'from side': '🚶', 'from behind': '🔙',
                'from above': '🦅', 'eye level': '👁️', 'from below': '🐛',
                'close-up': '🔍', 'portrait': '🖼️', 'medium shot': '👕', 'long shot': '🏞️'}


def base_name(section):
    """guy A → guy（A〜Z の付かない名前はそのまま）"""
    match = LETTERED.match(section)
    return match.group(1) if match else section


def display_names(present):
    """その行で入力のある人物などの段落の、書き出す名前 {段落: 名前}（キャプションの段落名と characters）

    同じ名前（A, B を除く）の段落が1つだけなら、A, B を除いた名前（guy A だけ → guy、girl B だけ → girl）。2つ以上ならそのまま
    """
    counts = Counter(base_name(s) for s in present)
    return {s: base_name(s) if counts[base_name(s)] == 1 else s for s in present}


def plural(word, count):
    if count == 1:
        return word
    return IRREGULAR_PLURALS.get(word, f'{word}s')


def template_keys(section, templates, fixed_sections):
    """段落の確定タグのキー（画面の templateKeys と同じ）: 自分の名前の確定タグ。無ければ、固定の段落と else は無し、ほかは subject"""
    if section in templates:
        return templates[section]
    return [] if section in fixed_sections or base_name(section) == OTHERS else templates.get('subject', [])


def characters_of(present):
    """入力のある人物などの段落 [(段落, 入力)]（表の並び順）から characters の値を作る: 1 girl + 2 guys (guy A, guy B) + dog

    else は人物に数えず、行のキー（dog: / cat: …）を数なしで並べる（同じキーは1回。キーの無い文は入れない）
    """
    def part(base, sections):
        if base == OTHERS:
            return ' + '.join(dict.fromkeys(key for _, text in sections for key, _ in phrases_of(text) if key))
        names = [name for name, _ in sections]
        lettered = [name for name in names if name != base]
        return f'{len(names)} {plural(base, len(names))}' + (f" ({', '.join(lettered)})" if lettered else '')

    parts = (part(base, sections) for base, sections in group_in_order((base_name(s), (s, text)) for s, text in present))
    return ' + '.join(filter(None, parts))


def name_for_new(name, sections):
    """足す人物の段落の名前。同じ名前があれば A, B, … を付ける（今ある無印の段落は A に改名する）

    (改名 {旧: 新}, 足す名前) を返す
    """
    base = base_name(name)
    same = [s for s in sections if base_name(s) == base]
    if not same:
        return {}, name
    renames = {base: f'{base} A'} if base in same else {}
    letters = [LETTERED.match(s).group(2) for s in same if s != base] + (['A'] if renames else [])
    following = chr(ord(max(letters)) + 1)
    if following > 'Z':
        raise ValueError(f'「{base}」はこれ以上足せません（Z まで）')
    return renames, f'{base} {following}'


def tone_of(base):
    """POV のボタンの色: female / male / ''（それ以外）"""
    return 'female' if base in FEMALE else 'male' if base in MALE else ''


def insert_position(name, columns):
    """足す人物の段落を入れる位置: 同じ名前（A, B を除く）の最後の段落のすぐ後ろ。無ければ末尾"""
    base = base_name(name)
    same = [i for i, column in enumerate(columns) if base_name(column) == base]
    return same[-1] + 1 if same else len(columns)


def pov_choices(subjects):
    """view の 👀 の選択肢: 第三者の POV（先頭）と、人物ごとの POV（else は人物でないので出さない）

    ボタンは絵文字と A, B の文字（girl A → 👧 A）。絵文字の決まっていない名前は、見分けられるよう名前を残す（👤 alien）
    """
    def choice(section):
        base = base_name(section)
        lettered = LETTERED.match(section)
        label = (lettered.group(2) if lettered else '') if base in EMOJI else section
        return {'emoji': EMOJI.get(base, OTHER_EMOJI), 'label': label, 'tone': tone_of(base), 'phrase': f'{section} POV'}

    return [THIRD_PERSON, *(choice(s) for s in subjects if base_name(s) != OTHERS)]


def pov_names(subjects):
    """👀 の選択肢にする名前（表の並び）: 段落ごとに、A, B を除いた名前と段落の名前（guy A, guy B → guy, guy A, guy B）

    入力のある段落が1つの種類は、その行では A, B を除いた名前で書くため。行ごとにどれを出すかは画面が決める
    """
    return list(dict.fromkeys(name for s in subjects for name in (base_name(s), s)))
