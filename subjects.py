"""人物などの段落（girl / guy A / dog …）: 自動の命名、characters の自動計算、view の選択肢"""
import re

from caption_format import group_in_order

LETTERED = re.compile(r'^(.*\S) ([A-Z])$')  # guy A の「 A」
IRREGULAR_PLURALS = {'man': 'men', 'woman': 'women', 'person': 'people', 'child': 'children'}

# POV のボタンの絵文字（段落の名前の A, B を除いた部分で決める）
EMOJI = {'girl': '👧', 'woman': '👩', 'guy': '👨', 'man': '👨', 'boy': '👦', 'dog': '🐕', 'cat': '🐈'}
OTHER_EMOJI = '👤'
THIRD_PERSON = {'emoji': '👥', 'label': 'third-person', 'phrase': 'third-person POV'}

# view の 🎥 の選択肢。組の中は1つだけ（☓ で組の語句を消す）。view の行には自由記述も書ける
CAMERA_GROUPS = [['from front', 'from side', 'from behind'], ['from above', 'from below'], ['close-up']]


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


def pov_choices(subjects):
    """view の 👀 の選択肢: 人物ごとの POV と、第三者の POV"""
    return [*({'emoji': EMOJI.get(base_name(s), OTHER_EMOJI), 'label': s, 'phrase': f'{s} POV'} for s in subjects),
            THIRD_PERSON]
