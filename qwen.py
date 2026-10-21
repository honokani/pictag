"""Qwen（ComfyUI の TextGenerate。Krea2 のテキストエンコーダーと同じ Qwen3-VL-4B）で、空の欄を下書きする

- 送るもの: システムプロンプト（指示文と、段落・確定タグの空のひな形）、その行の画像、
  見本（キャプション 16 個。🤖 は上にある行から近い順、🔖・🔄 は同じマークの行を先にランダム、🎲 はほかの行からランダム。
  足りなければ、足りない分を公開の例（public_samples.SCENES）で補う）、
  その行に書いてあるもの（前に Qwen が入れて、そのあと直していない下書きは除く）を入れたひな形（何か書いてあるときだけ）
- 答えのキャプションを段落と行に分け、値の無いキーと、文の無い段落にだけ入れる（書いてあるものは変えない）。
  🔄 は答えにあるキーと文を、書いてあっても置き換える（外れる単語のマークの語句は残す）
- ComfyUI の呼び方は pj_loratrain（loratrain/backends.py）と同じ。ComfyUI の起動・停止はしない（起動しておいたものに乗るだけ）
"""
import io
import json
import random
import re
import time
import urllib.request
import uuid

from PIL import Image

from caption_format import parse_line, parse_lines, render_line, with_line
from marks import auto_marks_of, matches_pattern
from subjects import OTHERS, base_name
from verbs import PRESENT, PROGRESSIVE
from words import AUTO_KEYS

DEFAULT_URL = 'http://127.0.0.1:8189'
CLIP = 'qwen3vl_4b_fp8_scaled.safetensors'  # Krea2 のテキストエンコーダー
SAMPLE_COUNT = 16   # 見本の数（空でないキャプション。10 個で約 4,700 トークンだった）
MAX_LENGTH = 700    # 答えの長さの上限（トークン。キャプションの上限 507 に余裕を足す）
IMAGE_SIDE = 1024   # 送る画像の長辺（画像のトークン数を抑える）
UPLOAD_FOLDER = 'pictag'  # ComfyUI の input/ の下に置く（同じ画像は上書きする）
TIMEOUT = 300       # 答えを待つ時間（秒）

INSTRUCTIONS = ("You write training captions for an image generation model. Describe the image in exactly this structured "
                "format, with short comma-separated English phrases as values (lines without a key are one short sentence). "
                "Put only actions in action (what the characters are doing, including their posture, and how they interact). "
                "Expressions, gaze, appearance and clothing belong to each character's section, never to action. "
                "Match the vocabulary and level of detail of the example captions. Leave out sections and keys that do not "
                "apply. Output only the caption.")
# その行に書いてあるもの（written_skeleton）を送るときの頼み方
WRITTEN_INTRO = ("Part of the caption for this image is already written. Keep what is written as it is, and fill in the empty "
                 "parts by looking at the image:")
# キーの無い段落に添える書き方の例（else は物ごとにキーで書く。ほかは短い文）
KEYLESS_EXAMPLES = {OTHERS: '(e.g. dog: brown fur, sitting)'}
# 文の例は、プロジェクトの action の文で多い方の動詞の形に合わせる（形が分からない・同じ数なら進行形）
SENTENCE_EXAMPLES = {PROGRESSIVE: '(e.g. boy is sitting.)', PRESENT: '(e.g. boy sits.)'}
SENTENCE_EXAMPLE = SENTENCE_EXAMPLES[PROGRESSIVE]
# Qwen がたまに「値が無い」の意味で返す語（人のいない画像の looks: nan、action: none、ごくまれに non presented など）。
# タグが無いものとして入れない（大文字・小文字、前後の括弧と文末の . は is_tag がそろえてから比べる）
NO_TAGS = {'none', 'nan', 'non presented', 'nothing', 'n/a', 'not applicable', 'unknown'}
# 「無い」を言っているだけの答え（指示文で書くなと頼むと、かえって軒並み no で返すことがあったので、入れるときに捨てる）:
# no + あいまいな語 + 物（no extra elements・no other details）か、no + あいまいな語 + そのキーの名前（view: no specific view）。
# あいまいな語の付かない、見て分かる「無い」（no shoes・no glasses・no clothes）は残す
VAGUE = r'(?:specific|particular|other|additional|extra|notable|special|distinct)'
VAGUE_THINGS = re.compile(rf'no(?: {VAGUE})* (?:element|detail|feature|object|item|thing)s?')


# ---- 送る文面 ----

def skeleton(sections, sentence_example=SENTENCE_EXAMPLE):
    """[(段落, 確定タグのキー)] から、値を書かないひな形を作る。キーの無い段落には書き方の例を添える"""
    def block(name, keys):
        lines = [f'  - {key}:' for key in keys] or [f'  - {KEYLESS_EXAMPLES.get(base_name(name), sentence_example)}']
        return '\n'.join([f'{name}:', *lines])

    return '\n\n'.join(block(name, keys) for name, keys in sections)


def written_skeleton(sections):
    """[(段落, 確定タグのキー, 入力)] から、書いてある語句を入れたひな形を作る（何も書いていなければ ''）

    確定タグのキーはその並びで（同じキーの行はまとめる。値の無いキーは空のまま）、ほかのキーと文は書いた順に後ろへ
    """
    def block(name, keys, text):
        lines = parse_lines(text)
        values = {key: [phrase for k, phrases in lines if k == key for phrase in phrases] for key in keys}
        rows = [render_line(key, values[key]) if values[key] else f'{key}:' for key in keys]
        rest = [render_line(key, phrases) for key, phrases in lines if key not in keys]
        return '\n'.join([f'{name}:', *(f'  - {row}' for row in [*rows, *rest])])

    return '\n\n'.join(block(*section) for section in sections) if any(parse_lines(text) for _, _, text in sections) else ''


def system_prompt(sections, sentence_example=SENTENCE_EXAMPLE):
    return f'{INSTRUCTIONS}\n\nFormat:\n{skeleton(sections, sentence_example)}'


def user_prompt(samples, written=''):
    """見本と頼む文。書いてあるもの（written_skeleton）があれば、頼む文の前に置く"""
    written_part = f'{WRITTEN_INTRO}\n\n{written}\n\n' if written else ''
    return ('Example captions of other images in the same set:\n\n' + '\n\n---\n\n'.join(samples)
            + f'\n\n---\n\n{written_part}Write the caption for this image.')


def pick_samples(captions_above, count=SAMPLE_COUNT):
    """上にある行のキャプション（表の並び）から、空でないものを近い順に count 個（並びは表のまま。足りなければある分だけ）"""
    return [caption for caption in reversed(captions_above) if caption][:count][::-1]


def pick_random_samples(captions, count=SAMPLE_COUNT):
    """キャプションの中から、空でないものをランダムに count 個（押すたびに選び直す。足りなければある分だけ）"""
    present = [caption for caption in captions if caption]
    return random.sample(present, min(count, len(present)))


def pick_tiered_samples(tiers, count=SAMPLE_COUNT):
    """先の段から順に、空でないキャプションをランダムに選んで count 個にする（その段で足りない分は次の段から）

    tiers: [[[(行, キャプション)]]]（段ごとの、行の組）。組が2つ以上ある段は、どの組からも同じ数ずつ選ぶ（どれかの組が尽きるか、
    残りの枠を組の数で割れなくなるまで。余りは次の段へ）。同じ行が後の段や後の組にあっても選ぶのは1回。
    並びは後の段が先で、最初の段が最後（いちばん似た見本を、頼む文の直前に置く。段の中は混ぜる）。足りなければある分だけ
    """
    chosen, picked = set(), []
    for groups in tiers:
        pools, seen = [], set(chosen)
        for group in groups:
            pool = [(row, caption) for row, caption in group if caption and row not in seen]
            seen.update(row for row, _ in pool)
            pools.append(pool)
        each = min(min(map(len, pools)), (count - len(chosen)) // len(pools))
        taken = [pair for pool in pools for pair in random.sample(pool, each)]
        chosen.update(row for row, _ in taken)
        picked.append(random.sample([caption for _, caption in taken], len(taken)))
    return [caption for captions in reversed(picked) for caption in captions]


# ---- 答えの分け方と、空の欄への入れ方 ----

def parse_caption(text):
    """答えのキャプションを [(段落, [行])] に分ける。段落は行頭の「名前:」、行はその下の字下げした行（先頭の「- 」は除く）"""
    blocks = []
    for raw in text.replace('\r\n', '\n').split('\n'):
        line = raw.strip()
        if not line or line.startswith('```'):
            continue
        if not raw[0].isspace() and line.endswith(':') and not line.startswith('-'):
            blocks.append((line[:-1].strip(), []))
        elif blocks:
            blocks[-1][1].append(line.lstrip('-').strip())
    return blocks


def match_section(name, sections, present=()):
    """答えの段落名を表の段落に当てる: 同じ名前。無ければ A, B を除いた名前が同じ段落（いくつもあれば、その行で入力のある段落
    （present）が1つならそれ、ほかは表で先のもの。1人の行は A, B を除いた名前で書き出すので、見本も答えも guy: になる）。無ければ None
    """
    if name in sections:
        return name
    same = [section for section in sections if base_name(section) == base_name(name)]
    written = [section for section in same if section in present]
    return written[0] if len(written) == 1 else same[0] if same else None


def with_key(text, key, value, keys):
    """key の行を「key: value」にする。確定タグのキーはその並びの位置に、ほかのキーは末尾に置く"""
    if key in keys:
        return with_line(text, key, value, keys)
    return '\n'.join([*(line for line in text.splitlines() if parse_line(line)[0] != key), f'{key}: {value}'])


def is_tag(phrase, key=''):
    """答えの語句がタグか。none・nan などと、「無い」を言っているだけの語句（extra: no extra elements・view: no specific view）は
    タグではない（大文字・小文字、前後の括弧（(none)）、文末の . は問わない）"""
    p = phrase.strip(' .()').lower()
    vague_key = bool(key) and re.fullmatch(rf'no(?: {VAGUE})+ {re.escape(key.lower())}s?', p)
    return not (p in NO_TAGS or VAGUE_THINGS.fullmatch(p) or vague_key)


def is_sentence(line):
    """キーの無い、語句のある行（文）か"""
    key, phrases = parse_line(line)
    return not key and bool(phrases)


def fill_section(text, lines, keys, overwrite=False):
    """入力 text に、答えの行 lines を入れる。入れるのは値の無いキー（自動のキーは除く）と、文が1つも無いときの文だけ
    （overwrite（🔄）なら、答えにあるキーは値があっても置き換え、答えに文があれば前の文を置き換える）

    答えの none・nan は捨て、語句が残らなかったキー・文は入れない（overwrite でも、それで消すことはない）。
    (入れたあとの入力, 入れたもの {'keys': {キー: 値}, 'sentences': [文]}) を返す（押し直したときに置き換える下書き）
    """
    answer = [(key, [phrase for phrase in phrases if is_tag(phrase, key)]) for key, phrases in map(parse_line, lines)]
    if overwrite and any(not key and phrases for key, phrases in answer):
        text = '\n'.join(line for line in text.splitlines() if not is_sentence(line))
    present = [parse_line(line) for line in text.splitlines()]
    filled = set() if overwrite else {key for key, phrases in present if key and phrases}
    has_sentence = any(not key and phrases for key, phrases in present)
    added = {'keys': {}, 'sentences': []}
    for key, phrases in answer:
        if not phrases or key in AUTO_KEYS or (key and key in filled) or (not key and has_sentence):
            continue
        value = ', '.join(phrases)
        if key:
            text = with_key(text, key, value, keys)
            filled.add(key)
            added['keys'][key] = value
        else:
            text = '\n'.join(filter(None, [text, value]))
            added['sentences'].append(value)
    return text, added


def clear_drafts(text, drafted):
    """前に Qwen が入れて、そのあと直していないもの（drafted と同じ値のキーと、同じ並びの文）を消す（押し直す前に）

    drafted は fill_section が返した「入れたもの」。直したキー・足した文は、自分で書いたものとして残す
    """
    keys, sentences = drafted.get('keys', {}), drafted.get('sentences', [])
    parsed = [(line, *parse_line(line)) for line in text.splitlines()]
    present = [', '.join(phrases) for _, key, phrases in parsed if not key and phrases]
    drop_sentences = bool(sentences) and present == sentences

    def is_draft(key, phrases):
        return bool(phrases) and (keys.get(key) == ', '.join(phrases) if key else drop_sentences)

    return '\n'.join(line for line, key, phrases in parsed if not is_draft(key, phrases))


def keep_word_marks(before, after, auto_marks, keys):
    """🔄 の上書きで外れた単語のマーク（①など）の語句を、押す前の入力 before から after に足し直す（{段落: 入力} を返す）

    足すのは外れたマークに当たっていた語句だけ（答えにも当たる語句があれば、外れないので足さない）。
    キーのある語句はそのキーの値の末尾に、キーなしの語句は文の行として末尾に。keys は {段落: 確定タグのキー}
    """
    lost = [auto_marks[i] for i in set(auto_marks_of(before, auto_marks)) - set(auto_marks_of(after, auto_marks))]

    def hits(section, key, phrases):
        return [phrase for phrase in phrases
                if any(base_name(section) == m['section'] and key == m['key'] and matches_pattern(m['phrase'], phrase) for m in lost)]

    def restored(section):
        text = after[section]
        for key, phrases in map(parse_line, before.get(section, '').splitlines()):
            words = hits(section, key, phrases)
            if not words:
                continue
            if key:
                current = [phrase for k, ps in map(parse_line, text.splitlines()) if k == key for phrase in ps]
                text = with_key(text, key, ', '.join(dict.fromkeys([*current, *words])), keys[section])
            else:
                text = '\n'.join(filter(None, [text, ', '.join(words)]))
        return text

    return {section: restored(section) for section in after}


# ---- ComfyUI（pj_loratrain の loratrain/backends.py と同じ呼び方） ----

def jpeg_of(path):
    """画像を長辺 IMAGE_SIDE に縮めた JPEG のバイト列にする"""
    with Image.open(path) as image:
        image = image.convert('RGB')
        image.thumbnail((IMAGE_SIDE, IMAGE_SIDE))
        buffer = io.BytesIO()
        image.save(buffer, 'JPEG', quality=90)
        return buffer.getvalue()


def http_json(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def upload(url, image, name):
    """画像を ComfyUI の input/pictag/ に上書きで置き、LoadImage に渡す名前を返す"""
    boundary = uuid.uuid4().hex

    def field(key, value):
        return f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()

    body = b''.join([
        f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
        f'Content-Type: image/jpeg\r\n\r\n'.encode(), image, b'\r\n',
        field('subfolder', UPLOAD_FOLDER), field('overwrite', 'true'), f'--{boundary}--\r\n'.encode()])
    request = urllib.request.Request(f'{url}/upload/image', data=body,
                                     headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(request, timeout=60) as response:
        saved = json.load(response)
    return f"{saved['subfolder']}/{saved['name']}" if saved.get('subfolder') else saved['name']


def comfy_graph(image_name, prompt, system):
    """ComfyUI に送るノードのつながり: Qwen を読む → 画像を読む → 文章を作る → 受け取る"""
    def node(class_type, **inputs):
        return {'class_type': class_type, 'inputs': inputs}

    return {'clip': node('CLIPLoader', clip_name=CLIP, type='krea2', device='default'),
            'img': node('LoadImage', image=image_name),
            'tg': node('TextGenerate', clip=['clip', 0], prompt=prompt, max_length=MAX_LENGTH, sampling_mode='off',
                       image=['img', 0], thinking=False, use_default_template=True, system_prompt=system),
            'show': node('PreviewAny', source=['tg', 0])}


def generate(url, image, name, prompt, system, timeout=TIMEOUT):
    """画像を送って Qwen に書かせ、答えの文面を返す（失敗は RuntimeError、時間切れは TimeoutError）"""
    image_name = upload(url, image, name)
    prompt_id = http_json(f'{url}/prompt', {'prompt': comfy_graph(image_name, prompt, system)})['prompt_id']
    deadline = time.time() + timeout
    while time.time() < deadline:
        entry = http_json(f'{url}/history/{prompt_id}').get(prompt_id)
        status = (entry or {}).get('status', {})
        if status.get('completed') is not None:
            if status.get('status_str') != 'success':
                messages = status.get('messages', [])
                detail = messages[-1][1].get('exception_message', '') if messages else ''
                raise RuntimeError(f'ComfyUI での実行に失敗しました: {detail}'.rstrip(': '))
            return ''.join(entry['outputs']['show']['text'])
        time.sleep(0.25)
    raise TimeoutError(f'ComfyUI の答えが {timeout} 秒で返りませんでした')
