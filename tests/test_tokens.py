"""キャプションのトークン数（Qwen3-VL のトークナイザー）"""
import os
from pathlib import Path

import pytest

from helpers import word_tokenizer
from tokens import TOKEN_LIMIT, TokenCounter, ensure_file

# 依頼者の例（原文ママ）。実物のトークナイザーで 132 トークン
# 行末の空白（girl: / guy : の後ろ）も原文どおり残すため、1行ずつ並べる
OWNER_EXAMPLE = "\n".join([
    'picture:',
    '  - place: class room',
    '  - object: 1 girl + 1 guy',
    '  - vibes: size difference emphasized',
    '  - view: from below, third POV',
    '',
    'action:',
    '  - girl spead arms',
    "  - guy grab girl's waist",
    '',
    'girl: ',
    '  - looks: full body shot, standing',
    '  - clothes: school uniform, long/white socks, sneaker',
    '  - body: black/long hair, bare hands',
    '',
    'guy : ',
    '  - looks: full body shot, standing',
    '  - clothes: school uniform, sneaker',
    '  - body: black/short hair, bare hands',
    '',
])


def test_limit_is_caption_part_of_512_tokens():
    # musubi-tuner と Krea 公式: 定型文込み 541 で切り、先頭の定型文 34 を捨てる
    assert TOKEN_LIMIT == 541 - 34 == 507


def test_counts_tokens():
    counter = TokenCounter(word_tokenizer())
    # girl / : / - / body / : / long / hair
    assert counter.count("girl:\n  - body: long hair") == 7
    assert counter.count("") == 0


def test_count_is_none_until_tokenizer_is_loaded():
    assert TokenCounter().count("girl") is None


def test_load_replaces_cached_none(tmp_path):
    path = tmp_path / "tokenizer.json"
    word_tokenizer().save(str(path))
    counter = TokenCounter()
    assert counter.count("long hair") is None
    counter.load(path)
    assert counter.count("long hair") == 2


def test_ensure_file_keeps_existing_file(tmp_path):
    path = tmp_path / "t.json"
    path.write_text("{}", encoding="utf-8")
    calls = []
    assert ensure_file(path, "http://example.invalid", fetch=lambda url, p: calls.append(url)) == path
    assert calls == []


def test_ensure_file_fetches_missing_file(tmp_path):
    path = tmp_path / "sub" / "t.json"
    assert ensure_file(path, "http://example.invalid", fetch=lambda url, p: p.write_text("{}")) == path
    assert path.read_text() == "{}"


def test_ensure_file_returns_none_when_fetch_fails(tmp_path):
    def offline(url, path):
        raise OSError("network is unreachable")

    assert ensure_file(tmp_path / "t.json", "http://example.invalid", fetch=offline) is None
    assert not (tmp_path / "t.json").exists()


def test_background_load_counts_after_fetch(tmp_path):
    source = tmp_path / "source.json"
    word_tokenizer().save(str(source))
    counter = TokenCounter()
    counter.load_in_background(tmp_path / "data_work" / "tokenizer.json", "http://example.invalid",
                               fetch=lambda url, p: p.write_bytes(source.read_bytes())).join(timeout=10)
    assert counter.count("long hair") == 2


def test_start_once_fetches_only_once(tmp_path):
    source = tmp_path / "source.json"
    word_tokenizer().save(str(source))
    calls = []

    def fetch(url, path):
        calls.append(url)
        path.write_bytes(source.read_bytes())

    counter = TokenCounter()
    counter.start_once(tmp_path / "tokenizer.json", "http://example.invalid", fetch=fetch).join(timeout=10)
    assert counter.start_once(tmp_path / "tokenizer.json", "http://example.invalid", fetch=fetch) is None
    assert calls == ["http://example.invalid"]
    assert counter.count("long hair") == 2


REAL_TOKENIZER = os.environ.get("PICTAG_TEST_TOKENIZER")


@pytest.mark.skipif(not REAL_TOKENIZER, reason="PICTAG_TEST_TOKENIZER（Qwen3-VL の tokenizer.json）が未指定")
def test_real_tokenizer_counts_owner_example():
    counter = TokenCounter()
    counter.load(Path(REAL_TOKENIZER))
    assert counter.count(OWNER_EXAMPLE) == 132
