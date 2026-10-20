"""Qwen（ComfyUI の TextGenerate。Krea2 のテキストエンコーダーと同じ Qwen3-VL-4B）で、空の欄を下書きする

- 送るもの: システムプロンプト（指示文と、段落・確定タグの空のひな形）、その行の画像、見本（上にある行のキャプション 10 個）
- 答えのキャプションを段落と行に分け、値の無いキーと、文の無い段落にだけ入れる（書いてあるものは変えない）
- ComfyUI の呼び方は pj_loratrain（loratrain/backends.py）と同じ。ComfyUI の起動・停止はしない（起動しておいたものに乗るだけ）
"""
import io
import json
import time
import urllib.request
import uuid

from PIL import Image

from caption_format import parse_line, with_line
from subjects import OTHERS, base_name
from words import AUTO_KEYS

DEFAULT_URL = 'http://127.0.0.1:8189'
CLIP = 'qwen3vl_4b_fp8_scaled.safetensors'  # Krea2 のテキストエンコーダー
SAMPLE_COUNT = 10   # 見本の数（上にある行の、空でないキャプション）
MAX_LENGTH = 700    # 答えの長さの上限（トークン。キャプションの上限 507 に余裕を足す）
IMAGE_SIDE = 1024   # 送る画像の長辺（画像のトークン数を抑える）
UPLOAD_FOLDER = 'pictag'  # ComfyUI の input/ の下に置く（同じ画像は上書きする）
TIMEOUT = 300       # 答えを待つ時間（秒）

INSTRUCTIONS = ("You write training captions for an image generation model. Describe the image in exactly this structured "
                "format, with short comma-separated English phrases as values (lines without a key are one short sentence). "
                "Match the vocabulary and level of detail of the example captions. Leave out sections and keys that do not "
                "apply. Output only the caption.")
# キーの無い段落に添える書き方の例（else は物ごとにキーで書く。ほかは短い文）
KEYLESS_EXAMPLES = {OTHERS: '(e.g. dog: brown fur, sitting)'}
SENTENCE_EXAMPLE = '(e.g. boy is sitting.)'


# ---- 送る文面 ----

def skeleton(sections):
    """[(段落, 確定タグのキー)] から、値を書かないひな形を作る。キーの無い段落には書き方の例を添える"""
    def block(name, keys):
        lines = [f'  - {key}:' for key in keys] or [f'  - {KEYLESS_EXAMPLES.get(base_name(name), SENTENCE_EXAMPLE)}']
        return '\n'.join([f'{name}:', *lines])

    return '\n\n'.join(block(name, keys) for name, keys in sections)


def system_prompt(sections):
    return f'{INSTRUCTIONS}\n\nFormat:\n{skeleton(sections)}'


def user_prompt(samples):
    return ('Example captions of other images in the same set:\n\n' + '\n\n---\n\n'.join(samples)
            + '\n\n---\n\nWrite the caption for this image.')


def pick_samples(captions_above, count=SAMPLE_COUNT):
    """上にある行のキャプション（表の並び）から、空でないものを近い順に count 個（並びは表のまま）。足りなければ []"""
    nearest = [caption for caption in reversed(captions_above) if caption][:count]
    return nearest[::-1] if len(nearest) == count else []


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


def match_section(name, sections):
    """答えの段落名を表の段落に当てる: 同じ名前。無ければ A, B を除いた名前で1つに決まる段落（決まらなければ None）"""
    if name in sections:
        return name
    same = [section for section in sections if base_name(section) == base_name(name)]
    return same[0] if len(same) == 1 else None


def with_key(text, key, value, keys):
    """key の行を「key: value」にする。確定タグのキーはその並びの位置に、ほかのキーは末尾に置く"""
    if key in keys:
        return with_line(text, key, value, keys)
    return '\n'.join([*(line for line in text.splitlines() if parse_line(line)[0] != key), f'{key}: {value}'])


def fill_text(text, lines, keys):
    """入力 text に、答えの行 lines を入れる。入れるのは値の無いキー（自動のキーは除く）と、文が1つも無いときの文だけ"""
    present = [parse_line(line) for line in text.splitlines()]
    filled = {key for key, phrases in present if key and phrases}
    has_sentence = any(not key and phrases for key, phrases in present)
    for line in lines:
        key, phrases = parse_line(line)
        if not phrases or key in AUTO_KEYS or (key and key in filled) or (not key and has_sentence):
            continue
        value = ', '.join(phrases)
        text = with_key(text, key, value, keys) if key else '\n'.join(filter(None, [text, value]))
        if key:
            filled.add(key)
    return text


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
