"""人物などの段落（girl / guy A / dog …）: 自動の命名、characters の自動計算、view の選択肢"""
import re

from caption_format import group_in_order

LETTERED = re.compile(r'^(.*\S) ([A-Z])$')  # guy A の「 A」
IRREGULAR_PLURALS = {'man': 'men', 'woman': 'women', 'person': 'people', 'child': 'children'}

# POV のボタンの絵文字（段落の名前の A, B を除いた部分で決める）と色（女性・男性）
EMOJI = {'girl': '👧', 'woman': '👩', 'guy': '👨', 'man': '👨', 'boy': '👦', 'dog': '🐕', 'cat': '🐈'}
OTHER_EMOJI = '👤'
FEMALE = {'girl', 'woman'}
MALE = {'guy', 'man', 'boy'}
THIRD_PERSON = {'emoji': '👥', 'label': '', 'tone': '', 'phrase': 'third-person POV'}

# view の 🎥 の選択肢。組の中は1つだけ（☓ で組の語句を消す）。view の行には自由記述も書ける
# 3つ目の組はショットの大きさ（寄り → 引き）
CAMERA_GROUPS = [['from front', 'from side', 'from behind'], ['from above', 'from below'],
                 ['close-up', 'portrait', 'medium shot', 'long shot']]
# 🎥 のボタンの絵文字（語句はボタンにマウスを載せると見える）。above / below は鳥の目・虫の目
CAMERA_EMOJI = {'from front': '🧍', 'from side': '🚶', 'from behind': '🔙', 'from above': '🦅', 'from below': '🐛',
                'close-up': '🔍', 'portrait': '🖼️', 'medium shot': '👕', 'long shot': '🏞️'}


def base_name(section):
    """guy A → guy（A〜Z の付かない名前はそのまま）"""
    match = LETTERED.match(section)
    return match.group(1) if match else section


def plural(word, count):
    if count == 1:
        return word
    return IRREGULAR_PLURALS.get(word, f'{word}s')


def characters_of(present):
    """入力のある人物の段落（表の並び順）から characters の値を作る: 1 girl + 2 guys (guy A, guy B)"""
    def part(base, names):
        lettered = [name for name in names if name != base]
        return f'{len(names)} {plural(base, len(names))}' + (f" ({', '.join(lettered)})" if lettered else '')

    return ' + '.join(part(base, names) for base, names in group_in_order((base_name(s), s) for s in present))


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
    """view の 👀 の選択肢: 第三者の POV（先頭）と、人物ごとの POV

    ボタンは絵文字と A, B の文字（girl A → 👧 A）。絵文字の決まっていない名前は、見分けられるよう名前を残す（👤 alien）
    """
    def choice(section):
        base = base_name(section)
        lettered = LETTERED.match(section)
        label = (lettered.group(2) if lettered else '') if base in EMOJI else section
        return {'emoji': EMOJI.get(base, OTHER_EMOJI), 'label': label, 'tone': tone_of(base), 'phrase': f'{section} POV'}

    return [THIRD_PERSON, *map(choice, subjects)]
