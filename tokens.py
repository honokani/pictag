"""Krea 2 のキャプションのトークン数（Qwen3-VL のトークナイザー）

musubi-tuner と Krea 公式の実装は、キャプションの前後に定型文を付けて 541 トークンで切り、先頭の定型文（34 トークン）を捨てる。
キャプションに使えるのは 541 - 34 = 507 トークンで、超えた分は末尾から黙って消える。
"""
import logging
import os
import threading
import urllib.request
from functools import lru_cache

from tokenizers import Tokenizer

logger = logging.getLogger(__name__)

TOKEN_LIMIT = 507
TOKENIZER_URL = 'https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct/resolve/main/tokenizer.json'


def download(url, path, timeout=60):
    """url を path に保存する（書きかけで残らないよう、一時ファイルに書いてから置き換える）"""
    tmp = path.with_name(path.name + '.part')
    with urllib.request.urlopen(url, timeout=timeout) as res:
        tmp.write_bytes(res.read())
    os.replace(tmp, path)


def ensure_file(path, url, fetch=download):
    """path が無ければ url から取ってくる。取れなければ None（ネットワーク不通など）"""
    if path.exists():
        return path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fetch(url, path)
        return path
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


class TokenCounter:
    """トークン数を数える（同じ文面は数え直さない）。トークナイザーが無い間は None"""

    def __init__(self, tokenizer=None):
        self.tokenizer = tokenizer
        self.count = lru_cache(maxsize=8192)(self._count)
        self.started = False
        self.lock = threading.Lock()

    def _count(self, text):
        if self.tokenizer is None:
            return None
        return len(self.tokenizer.encode(text, add_special_tokens=False).ids)

    def load(self, path):
        self.tokenizer = Tokenizer.from_file(str(path))
        self.count.cache_clear()  # 読み込み前の None を捨てる
        logger.info(f"Loaded tokenizer: {path}")

    def load_in_background(self, path, url=TOKENIZER_URL, fetch=download):
        """起動を待たせないよう、取得と読み込みを裏で行う"""
        def run():
            found = ensure_file(path, url, fetch)
            if found:
                self.load(found)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    def start_once(self, path, url=TOKENIZER_URL, fetch=download):
        """取得と読み込みを、最初の1回だけ裏で始める（2回目以降は None）"""
        with self.lock:
            if self.started:
                return None
            self.started = True
        return self.load_in_background(path, url, fetch)
