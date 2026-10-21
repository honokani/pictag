import argparse
import os
import json
import logging
import subprocess
import sys
import threading
from collections import Counter
from functools import reduce
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
from PIL import Image

from caption_format import parse_line, phrases_of, render_caption, with_line
from groups import blocked_by, clean_groups
from qwen import (DEFAULT_URL, SAMPLE_COUNT, clear_drafts, fill_section, generate, jpeg_of, match_section, parse_caption,
                  pick_random_samples, pick_samples, pick_tiered_samples, system_prompt, user_prompt)
from subjects import (CAMERA_EMOJI, CAMERA_GROUPS, CANDIDATE_GROUPS, OTHERS, TARGETED, base_name, characters_of,
                      insert_position, name_for_new, pov_choices, template_keys)
from marks import (AUTO, COUNT, MANY, ONE, auto_marks_from_file, check_number, check_one, many_from_file, many_numbers,
                   many_text, marks_to_file, one_from_file, one_number, one_text, toggle_many)
from tokens import TOKEN_LIMIT, TokenCounter
from words import (AUTO_KEYS, add_phrase, check_key, check_phrase, check_section_name, count_sentence_words, count_words,
                   empty_shared, freeze, group_phrases, move_phrases, move_registered, phrase_entries, register_phrases,
                   register_words, remove_phrase, rename_phrase, rename_registered, set_choice, ungroup_phrases,
                   unregister_phrases, unregister_words, word_entries)

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# data_out / data_work の既定の置き場所（起動ディレクトリに依存させない）
APP_DIR = Path(__file__).resolve().parent

# 表の固定列（mark / marks はマーキング。キャプションには書き出さない）。それ以外の列は段落（大kind）で、値は入力の文字列
FIXED_COLUMNS = ['サムネイル', 'is_dead', 'mark', 'marks']
TABLE_FILE = 'table.json'  # data_out/<フォルダ名>/ 直下。画像 × 段落の入力
SHARED_FILE = 'shared.json'  # data_work/ 直下。共用辞書（freeze した語句・単語と確定タグ）
SDXL_DUMP = 'df_isflaged.dump'  # SDXL 版の表。これだけがあるフォルダは SDXL 版のプロジェクト
CAPTION_EXT = '.caption'  # 書き出すキャプションの拡張子（captions/<画像名>.caption）
HINT_EXT = '.txt'  # 画像フォルダの、画像と同じ名前のこの拡張子のファイルは hint（読むだけ）
QWEN_DIR = 'qwen'  # data_work/<フォルダ名>/ の下の、Qwen の答えの置き場（<画像名>.txt。右端の列の hint_by_qwen で見る）
QWEN_MODES = ('near', 'mark', 'random')  # 見本の選び方: 🤖 は上の行から近い順、🔖 は同じマークの行を先に、🎲 はほかの行からランダム
FIXED_SECTIONS = ['picture', 'action']  # 固定の段落: どのプロジェクトにも必ずあり、外せない・改名できない
DEFAULT_SECTIONS = [*FIXED_SECTIONS, 'girl', 'guy']  # 新規プロジェクトの段落（dog などは必要なときに足す。空の段落は出力しない）
TOKENIZER_FILE = Path('tokenizer') / 'qwen3vl_tokenizer.json'  # data_work/ 配下
LOCAL_ADDRESSES = {'127.0.0.1', '::1'}  # フォルダを選ぶ窓は、このPCから開いたときだけ（窓はこのPCに出る）

# フォルダを選ぶ窓（別のプロセスで開く。引数は選び始めるフォルダ、出力は選んだフォルダ。やめたら空）
FOLDER_DIALOG = '\n'.join([
    'import sys, tkinter',
    'from tkinter import filedialog',
    'root = tkinter.Tk()',
    'root.withdraw()',
    "root.attributes('-topmost', True)",
    "path = filedialog.askdirectory(parent=root, title='画像フォルダを選ぶ', initialdir=sys.argv[1] or None, mustexist=True)",
    "print(path or '')",
])

# キャプションのトークン数（tokenizer.json は起動時に裏で取得する）
token_counter = TokenCounter()

def to_flag(value):
    """セル値を bool に揃える（欠損や bool 以外は False）"""
    return bool(value) if pd.api.types.is_bool(value) else False

def to_text(value):
    """セル値を文字列に揃える（欠損や文字列以外は空）"""
    return value if isinstance(value, str) else ''

def same_path(a, b):
    """同じディレクトリを指すか（Windows の大文字小文字・区切り文字の違いは無視）"""
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))

def write_json(path, data):
    """JSON を書く（書きかけで壊れないよう、一時ファイルに書いてから置き換える）"""
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')
    os.replace(tmp, path)

def section_names(df):
    return [c for c in df.columns if c not in FIXED_COLUMNS]

def with_fixed_sections(sections):
    """固定の段落を先頭に揃える（無ければ足す）"""
    return [*FIXED_SECTIONS, *(s for s in sections if s not in FIXED_SECTIONS)]

def section_texts(df):
    """表の全入力を (段落, 入力) で並べる"""
    sections = section_names(df)
    return [(s, to_text(r[s])) for r in df.to_dict('records') for s in sections]

def table_to_json(df, auto_marks):
    """表と自動のマークの設定を JSON にする（空の入力は書かない）"""
    sections = section_names(df)
    return {
        'sections': sections,
        'rows': [{'image': r['サムネイル'], 'is_dead': to_flag(r['is_dead']),
                  **marks_to_file(to_text(r['mark']), to_text(r['marks'])),
                  'texts': {s: r[s] for s in sections if to_text(r[s])}}
                 for r in df.to_dict('records')],
        'auto_marks': auto_marks,
    }

def table_from_json(data):
    sections = [check_section_name(s) for s in data['sections']]
    rows = [{'サムネイル': r['image'], 'is_dead': bool(r['is_dead']),
             'mark': one_from_file(r.get('mark')), 'marks': many_from_file(r.get('marks', '')),
             **{s: to_text(r['texts'].get(s, '')) for s in sections}}
            for r in data['rows']]
    return pd.DataFrame(rows, columns=FIXED_COLUMNS + sections)

def read_auto_marks(path):
    """保存済みの自動のマークの設定（表が無い・設定が無い（0.4.4 まで）なら、どれも設定なし）"""
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return auto_marks_from_file(data.get('auto_marks') if isinstance(data, dict) else None)

def read_table(path):
    """保存済みの表（無ければ空）。読めなければ例外にする（開いて保存すると上書きで消えるため）"""
    if not path.exists():
        return pd.DataFrame()
    try:
        return table_from_json(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise ValueError(f'表を読めません: {path} ({e})') from e

def normalize_newlines(text):
    return text.replace('\r\n', '\n').replace('\r', '\n')

def read_hints(image_dir, image_names):
    """画像と同じ名前の .txt（画像フォルダにあるもの）を hint として読む。{画像名: 中身}"""
    paths = {name: image_dir / f"{Path(name).stem}{HINT_EXT}" for name in image_names}
    return {name: path.read_text(encoding='utf-8', errors='replace') for name, path in paths.items() if path.is_file()}

def ask_directory(initial):
    """このPCでフォルダを選ぶ窓を開き、選んだフォルダのパスを返す（やめたら空）

    Tk は Flask のスレッドで動かさず、別のプロセスで開く。窓を開いている間、応答は待つ
    """
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', FOLDER_DIALOG, initial],
                            capture_output=True, text=True, encoding='utf-8', timeout=600)
    if result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f'終了コード {result.returncode}')
    return result.stdout.strip()

def pairs_of(items):
    """画面から来た [{key, phrase}] を [(キー, 語句)] にする"""
    if not isinstance(items, list) or not all(isinstance(i, dict) and isinstance(i.get('phrase'), str) for i in items):
        raise ValueError('語句の指定が正しくありません')
    return [(check_key(i.get('key')), i['phrase']) for i in items]

def words_of(items):
    """画面から来た [単語] を確かめる"""
    if not isinstance(items, list) or not all(isinstance(w, str) and w for w in items):
        raise ValueError('単語の指定が正しくありません')
    return items

def read_shared(path):
    """共用辞書を読む（無い・壊れているときは既定の確定タグだけ。形の正しくないグループは除く）"""
    shared = empty_shared()
    if not path.exists():
        return shared
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        loaded = {key: data.get(key, value) if isinstance(data.get(key), type(value)) else value
                  for key, value in shared.items()}
        return {**loaded, 'groups': clean_groups(loaded['groups'])}
    except (OSError, ValueError, AttributeError) as e:
        logger.warning(f"Failed to load shared dictionary: {e}")
        return shared

class CaptionTool:
    def __init__(self, base_dir=None):
        # data_out / data_work の置き場所
        self.base_dir = Path(base_dir) if base_dir is not None else APP_DIR
        self.data_out_dir = self.base_dir / "data_out"
        self.data_work_dir = self.base_dir / "data_work"
        self.image_dir = None
        self.dir_name = None
        self.df = pd.DataFrame()
        self.auto_marks = [None] * COUNT  # 自動のマークの設定（番号ごとに {section, key, phrase} か None。プロジェクトごと）
        self.saved_cache = {}  # 他プロジェクトの表: パス → (mtime, 段落, 語句の使用回数, 単語の使用回数)
        self.hints = {}  # 画像名 → hint（画像フォルダの同じ名前の .txt）
        self.qwen_hints = {}  # 画像名 → Qwen の答え（data_work/<フォルダ名>/qwen/ の同じ名前の .txt）
        self.shared = read_shared(self.data_work_dir / SHARED_FILE)
        self.last_error = ''  # 直近の失敗理由（API が画面へ返す）

    def fail(self, message):
        """失敗理由を残して False を返す"""
        self.last_error = message
        logger.warning(message)
        return False

    def resolve_image_dir(self, image_dir):
        """入力された画像ディレクトリを検証して絶対パスにする（前後の空白・引用符は除く）"""
        text = str(image_dir or '').strip().strip('"\'').strip()
        if not text:
            raise ValueError('画像ディレクトリのパスを入力してください')
        path = Path(text)
        if not path.is_dir():
            raise FileNotFoundError(f'画像ディレクトリが見つかりません: {path}')
        path = path.resolve()
        if not path.name:
            raise ValueError(f'ドライブ直下は読み込めません: {path}')
        return path

    def check_not_sdxl(self, target):
        """SDXL 版のプロジェクト（SDXL 版の表だけがあるフォルダ）は開かない。SDXL のキャプションを上書きしないため"""
        if (target / SDXL_DUMP).exists() and not (target / TABLE_FILE).exists():
            raise ValueError(f'「{target.name}」は SDXL 版のプロジェクトです。SDXL 版（sdxl ブランチ）で開いてください')

    def check_registered_path(self, tgt_path_file, image_dir):
        """同名プロジェクトが別ディレクトリに紐付いていないか確認する

        紐付け先が今もあれば別データとみなして拒否。無ければ（移動・改名した）紐付けを新しいパスへ更新する
        """
        if not tgt_path_file.exists():
            return
        registered = Path(tgt_path_file.read_text(encoding='utf-8').strip())
        if same_path(registered, image_dir):
            return
        if registered.is_dir():
            raise ValueError(f'プロジェクト「{image_dir.name}」は別のディレクトリに紐付いています: {registered}')
        tgt_path_file.write_text(str(image_dir), encoding='utf-8')
        logger.info(f"Updated tgt_path.txt: {registered} -> {image_dir}")

    def setup_directories(self, image_dir):
        """ディレクトリ構造をセットアップ（検証で例外になった場合は今のプロジェクトのまま）"""
        image_dir = self.resolve_image_dir(image_dir)
        target = self.data_out_dir / image_dir.name
        self.check_not_sdxl(target)
        read_table(target / TABLE_FILE)  # 読めない表は開かない
        self.check_registered_path(target / "tgt_path.txt", image_dir)

        self.image_dir = image_dir
        self.dir_name = self.image_dir.name

        # data_out構造作成
        self.data_out_target = target
        self.data_out_dir.mkdir(parents=True, exist_ok=True)
        self.data_out_target.mkdir(exist_ok=True)

        # data_work構造作成
        self.data_work_target = self.data_work_dir / self.dir_name
        self.data_work_dir.mkdir(parents=True, exist_ok=True)
        self.data_work_target.mkdir(exist_ok=True)

        # captions と captions_dead ディレクトリ作成
        self.captions_dir = self.data_out_target / "captions"
        self.captions_dead_dir = self.data_out_target / "captions_dead"
        self.captions_dir.mkdir(exist_ok=True)
        self.captions_dead_dir.mkdir(exist_ok=True)

        logger.info(f"Directories created: {self.data_out_target}, {self.data_work_target}")
        logger.info(f"Caption directories: {self.captions_dir}, {self.captions_dead_dir}")

    def load_data(self):
        """既存データを読み込み"""
        # tgt_path.txt作成
        tgt_path_file = self.data_out_target / "tgt_path.txt"
        if not tgt_path_file.exists():
            with open(tgt_path_file, 'w', encoding='utf-8') as f:
                f.write(str(self.image_dir))
            logger.info(f"Created tgt_path.txt: {self.image_dir}")

        # 保存済みの表と、自動のマークの設定
        self.df = read_table(self.data_out_target / TABLE_FILE)
        self.auto_marks = read_auto_marks(self.data_out_target / TABLE_FILE)

        # 画像ファイル存在チェックと dead/alive 状態管理
        self.manage_dead_alive_status()

        # hint（読むだけ。保存やキャプションには使わない）と、前に Qwen が書いた答え
        self.hints = read_hints(self.image_dir, self.df['サムネイル'].tolist())
        self.qwen_hints = read_hints(self.data_work_target / QWEN_DIR, self.df['サムネイル'].tolist())

        logger.info(f"DataFrame created: {len(self.df)} rows, {len(self.df.columns)} columns")

    def saved_tables(self):
        """保存済みの他プロジェクトの (段落, 語句の使用回数, 単語の使用回数)。ファイルが変わらなければ読み直さない"""
        if not self.data_out_dir.exists():
            return []
        results = []
        for path in sorted(self.data_out_dir.glob(f'*/{TABLE_FILE}')):
            if path.parent.name == self.dir_name:
                continue  # 今のプロジェクトは画面の表（未保存の入力を含む）を使う
            mtime = path.stat().st_mtime_ns
            cached = self.saved_cache.get(path)
            if cached is None or cached[0] != mtime:
                try:
                    df = read_table(path)
                except ValueError as e:
                    logger.warning(str(e))
                    continue
                texts = section_texts(df)
                cached = (mtime, section_names(df), count_words(texts), count_sentence_words(texts))
                self.saved_cache[path] = cached
            results.append(cached[1:])
        return results

    def usage(self):
        """使用中の (語句, 単語) の使用回数（他プロジェクトの保存済みの表 + 今の表）"""
        phrases, words = Counter(), Counter()
        for _, saved_phrases, saved_words in self.saved_tables():
            phrases.update(saved_phrases)
            words.update(saved_words)
        if 'サムネイル' in self.df.columns:
            texts = section_texts(self.df)
            phrases.update(count_words(texts))
            words.update(count_sentence_words(texts))
        return phrases, words

    def dictionary(self):
        """画面に渡す辞書（使用中 + 共用辞書の語句・単語、確定タグ、「1つだけ」のグループ）"""
        phrases, words = self.usage()
        return {'phrases': phrase_entries(phrases, self.shared), 'words': word_entries(words, self.shared),
                'templates': self.shared['templates'], 'groups': self.shared['groups'],
                'fixed_sections': FIXED_SECTIONS, 'default_sections': DEFAULT_SECTIONS, 'auto_keys': AUTO_KEYS}

    def save_shared(self):
        self.data_work_dir.mkdir(parents=True, exist_ok=True)
        write_json(self.data_work_dir / SHARED_FILE, self.shared)

    def update_shared(self, change):
        """共用辞書を change で作り直して保存する（検証の ValueError は失敗理由を残して False）"""
        self.last_error = ''
        try:
            shared = change(self.shared)
        except ValueError as e:
            return self.fail(str(e))
        self.shared = shared
        self.save_shared()
        return True

    def freeze_dictionary(self):
        """使用中の語句・単語を共用辞書に足して保存する。足した数を返す"""
        self.shared, added = freeze(self.shared, *self.usage())
        self.save_shared()
        logger.info(f"Froze dictionary: {added} entries added")
        return added

    def register_entries(self, pairs, words):
        """使っている「キー: 語句」・単語を、使っている段落すべてで共用辞書に入れる（入っているものはそのまま）"""
        def change(shared):
            wanted, wanted_words = set(pairs_of(pairs)), set(words_of(words))
            phrase_usage, word_usage = self.usage()
            known = {t[1:] for t in phrase_usage} | {(p['key'], p['phrase']) for p in shared['phrases']}
            known_words = {w for _, w in word_usage} | {w['word'] for w in shared['words']}
            unknown = [p for k, p in wanted if (k, p) not in known] + [w for w in wanted_words if w not in known_words]
            if unknown:
                raise ValueError(f'「{unknown[0]}」はどの画像でも使われていません')
            return register_words(register_phrases(shared, [t for t in phrase_usage if t[1:] in wanted]),
                                  [t for t in word_usage if t[1] in wanted_words])
        return self.update_shared(change)

    def add_entry(self, section, key, phrase):
        """新しい「キー: 語句」を、段落を決めて共用辞書に入れる（まだどこでも使っていない語句を手で足す）"""
        def change(shared):
            k = check_key(key)
            return register_phrases(shared, [(check_section_name(section), k, check_phrase(k, phrase))])
        return self.update_shared(change)

    def unregister_entries(self, pairs, words):
        """「キー: 語句」・単語を共用辞書から消す（どの段落のものも。入力はそのまま）"""
        return self.update_shared(lambda shared: unregister_words(unregister_phrases(shared, pairs_of(pairs)), words_of(words)))

    def rename_entry(self, key, old, new, in_project):
        """「key: old」を new にする（共用辞書と、in_project なら開いているプロジェクトの入力も）

        入力を置き換えた行の数を返す（失敗は None）。他のプロジェクトの表は変えない
        """
        self.last_error = ''
        try:
            key = check_key(key)
            new = check_phrase(key, new)
            if not isinstance(old, str) or not old:
                raise ValueError('改名する語句の指定が正しくありません')
            if new == old:
                raise ValueError('今と同じ名前です')
            if not isinstance(in_project, bool):
                raise ValueError('入力も置き換えるかの指定が正しくありません')
        except ValueError as e:
            self.fail(str(e))
            return None
        registered = any((p['key'], p['phrase']) == (key, old) for p in self.shared['phrases'])
        sections = section_names(self.df) if in_project and 'サムネイル' in self.df.columns else []
        before = self.df[sections].map(to_text)
        after = before.map(lambda text: rename_phrase(text, key, old, new))
        changed = int((before != after).any(axis=1).sum())
        if not registered and not changed:
            where = '共用辞書にも、開いているプロジェクトの入力にも' if in_project else '共用辞書に'
            self.fail(f'「{old}」は{where}ありません')
            return None
        if registered:
            self.shared = rename_registered(self.shared, key, old, new)
            self.save_shared()
        if changed:
            self.df[sections] = after
        logger.info(f"Renamed phrase: {key}: {old} -> {new} (rows: {changed})")
        return changed

    def move_phrases(self, section, src, dst, phrases):
        """段落 section（A, B を除いた名前が同じ段落すべて）のキー src の語句 phrases を、キー dst へ移す

        開いているプロジェクトの全行（削除済みも）と、共用辞書のその段落の語句を移す。入力を変えた行の数を返す（失敗は None）
        """
        self.last_error = ''
        try:
            base = check_section_name(section)
            src, dst = check_key(src), check_key(dst)
            if not src or not dst:
                raise ValueError('移す元と移す先のキーを選んでください')
            if src == dst:
                raise ValueError('移す先が同じキーです')
            if not isinstance(phrases, list) or not phrases:
                raise ValueError('移す語句を入力してください')
            phrases = [check_phrase(src, p) for p in phrases]
        except ValueError as e:
            self.fail(str(e))
            return None
        belongs = lambda s: base_name(s) == base
        registered = any(belongs(p['section']) and p['key'] == src and p['phrase'] in phrases for p in self.shared['phrases'])
        sections = [s for s in section_names(self.df) if belongs(s)] if 'サムネイル' in self.df.columns else []
        before = self.df[sections].map(to_text)

        def moved(s):
            keys = template_keys(s, self.shared['templates'], FIXED_SECTIONS)
            return before[s].map(lambda text: move_phrases(text, src, dst, phrases, keys))

        after = pd.DataFrame({s: moved(s) for s in sections}, index=before.index, columns=sections)
        changed = int((before != after).any(axis=1).sum())
        if not registered and not changed:
            self.fail(f'{base} の {src} に「{phrases[0]}」はありません（開いているプロジェクトにも共用辞書にも）')
            return None
        if registered:
            self.shared = move_registered(self.shared, belongs, src, dst, phrases)
            self.save_shared()
        if changed:
            self.df[sections] = after
        logger.info(f"Moved phrases: {base}: {src} -> {dst} {phrases} (rows: {changed})")
        return changed

    def group(self, key, phrases):
        """同じキーの語句を「1つだけ」のグループにする（共用辞書に無い語句は、使っている段落で入れる）"""
        def change(shared):
            k = check_key(key)
            if not k:
                raise ValueError('キーのない文はグループにできません')
            if not isinstance(phrases, list) or not all(isinstance(p, str) for p in phrases):
                raise ValueError('語句の指定が正しくありません')
            wanted = list(dict.fromkeys(phrases))
            if len(wanted) < 2:
                raise ValueError('グループにする語句を2つ以上選んでください')
            phrase_usage, _ = self.usage()
            used = [t for t in phrase_usage if t[1] == k and t[2] in wanted]
            known = {t[2] for t in used} | {p['phrase'] for p in shared['phrases'] if p['key'] == k}
            unknown = [p for p in wanted if p not in known]
            if unknown:
                raise ValueError(f'「{k}: {unknown[0]}」は辞書にありません')
            return group_phrases(register_phrases(shared, used), k, wanted)
        return self.update_shared(change)

    def ungroup(self, pairs):
        """語句をグループから外す（語句が1つになったグループは消える）"""
        return self.update_shared(lambda shared: ungroup_phrases(shared, pairs_of(pairs)))

    def manage_dead_alive_status(self):
        """画像の生存状態を管理し、dead/alive状態を更新"""
        # 画像ファイル拡張子
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}

        # 元画像ファイル一覧取得
        if self.image_dir.exists():
            alive_image_files = {f.name for f in self.image_dir.iterdir()
                                if f.is_file() and f.suffix.lower() in image_extensions}
        else:
            alive_image_files = set()

        # サムネイル一覧取得
        thumbnail_files = set()
        if hasattr(self, 'data_work_target') and self.data_work_target.exists():
            for f in self.data_work_target.iterdir():
                if f.name.startswith('t_') and f.suffix.lower() in image_extensions:
                    original_name = f.name[2:]
                    thumbnail_files.add(original_name)

        # 既存DataFrameから全ファイル取得（これが重要）
        # 画像名ごとの行を1回だけ引いておく。画像名が文字列でない行は捨てる
        has_table = 'サムネイル' in self.df.columns
        existing_rows = {}
        if has_table:
            for record in self.df.to_dict('records'):
                name = record['サムネイル']
                if isinstance(name, str) and name not in existing_rows:
                    existing_rows[name] = record
        existing_files = set(existing_rows)

        # 全ての画像ファイル（既存DataFrame + 新規alive + サムネイル）
        all_image_files = existing_files | alive_image_files | thumbnail_files

        # 段落: 保存済みの表があればその段落を保つ（外した人物などの段落を戻さない）。固定の段落は必ず先頭に置く
        # 新規プロジェクトは既定の段落（picture / action / girl）から始める
        sections = with_fixed_sections(section_names(self.df)) if has_table else list(DEFAULT_SECTIONS)

        # DataFrameを再構築
        columns = FIXED_COLUMNS + sections
        data = []

        for img_file in sorted(all_image_files):
            is_alive = img_file in alive_image_files
            is_dead = not is_alive

            # 既存の入力を引き継ぐ
            existing_row = existing_rows.get(img_file, {})
            data.append({
                'サムネイル': img_file,
                'is_dead': is_dead,
                'mark': one_text(one_number(to_text(existing_row.get('mark', '')))),
                'marks': many_text(many_numbers(to_text(existing_row.get('marks', '')))),
                **{s: to_text(existing_row.get(s, '')) for s in sections},
            })

            # キャプション移動処理（サムネイルは画面が表示するときに作る。読み込みを待たせないため）
            if is_alive:
                # deadからの復帰処理
                stem = Path(img_file).stem
                dead_caption_path = self.captions_dead_dir / f"{stem}{CAPTION_EXT}"
                if dead_caption_path.exists():
                    self.move_caption_from_dead_to_alive(img_file)

            else:
                # aliveからdeadへの移動処理
                stem = Path(img_file).stem
                alive_caption_path = self.captions_dir / f"{stem}{CAPTION_EXT}"
                if alive_caption_path.exists():
                    self.move_caption_from_alive_to_dead(img_file)

        # DataFrameを更新
        if data:
            self.df = pd.DataFrame(data, columns=columns)
        else:
            self.df = pd.DataFrame(columns=columns)

        # dead数を正しくカウント
        dead_count = len(self.df[self.df['is_dead'] == True]) if not self.df.empty else 0
        logger.info(f"Managed dead/alive status: {len(alive_image_files)} alive, {dead_count} dead, total: {len(all_image_files)}")

    def move_caption_from_dead_to_alive(self, image_name):
        """キャプションファイルをdeadからaliveに移動"""
        try:
            stem = Path(image_name).stem
            dead_caption_path = self.captions_dead_dir / f"{stem}{CAPTION_EXT}"
            alive_caption_path = self.captions_dir / f"{stem}{CAPTION_EXT}"

            if dead_caption_path.exists():
                # ファイル移動（上書き）
                if alive_caption_path.exists():
                    alive_caption_path.unlink()  # 既存ファイル削除
                dead_caption_path.rename(alive_caption_path)
                logger.info(f"Moved caption from dead to alive: {image_name}")
        except Exception as e:
            logger.error(f"Failed to move caption from dead to alive for {image_name}: {e}")

    def move_caption_from_alive_to_dead(self, image_name):
        """キャプションファイルをaliveからdeadに移動"""
        try:
            stem = Path(image_name).stem
            alive_caption_path = self.captions_dir / f"{stem}{CAPTION_EXT}"
            dead_caption_path = self.captions_dead_dir / f"{stem}{CAPTION_EXT}"

            if alive_caption_path.exists():
                # ファイル移動（上書き）
                if dead_caption_path.exists():
                    dead_caption_path.unlink()  # 既存ファイル削除
                alive_caption_path.rename(dead_caption_path)
                logger.info(f"Moved caption from alive to dead: {image_name}")
        except Exception as e:
            logger.error(f"Failed to move caption from alive to dead for {image_name}: {e}")

    def thumbnail_file(self, image_name):
        """サムネイルのパス（生成済みかは問わない）"""
        return self.data_work_target / f"t_{image_name}"

    def is_known_image(self, image_name):
        """表に載っている画像か（画像配信はこれに限る）"""
        if self.image_dir is None or 'サムネイル' not in self.df.columns:
            return False
        return bool((self.df['サムネイル'] == image_name).any())

    def create_thumbnail(self, image_path):
        """サムネイル作成。表示に使うパスを返す

        サムネイルの mtime は元画像の mtime に揃えておき、一致しなければ（元画像を差し替えたら）作り直す
        """
        thumb_path = self.thumbnail_file(image_path.name)

        if not image_path.exists():
            # 元画像が無い（削除済み）: 残っているサムネイルを使う
            return thumb_path if thumb_path.exists() else image_path

        source_stat = image_path.stat()
        if thumb_path.exists() and thumb_path.stat().st_mtime_ns == source_stat.st_mtime_ns:
            return thumb_path

        try:
            with Image.open(image_path) as img:
                # サイズチェック
                width, height = img.size
                if max(width, height) <= 600:
                    # リサイズ不要、元ファイルパス返す（小さく差し替えられた画像の古いサムネイルは消す）
                    if thumb_path.exists():
                        thumb_path.unlink()
                    return image_path

                # リサイズ実行（同時に要求されても壊れないよう、一時ファイルに書いてから置き換える）
                img.thumbnail((600, 600), Image.Resampling.LANCZOS)
                tmp_path = thumb_path.with_name(f".tmp{threading.get_ident()}_{thumb_path.name}")
                img.save(tmp_path, quality=85)
                os.utime(tmp_path, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
                os.replace(tmp_path, thumb_path)
                logger.info(f"Created thumbnail: {thumb_path}")
                return thumb_path

        except Exception as e:
            logger.error(f"Failed to create thumbnail for {image_path}: {e}")
            return image_path

    def subjects(self):
        """人物などの段落（固定の段落以外）を表の並びで"""
        return [s for s in section_names(self.df) if s not in FIXED_SECTIONS]

    def add_section(self, name):
        """人物などの段落を足す（入力は空）。同じ名前があれば A, B, … を付け（今ある無印は A に改名）、その隣に置く。無ければ末尾"""
        self.last_error = ''
        if self.image_dir is None:
            return self.fail('先にプロジェクトを読み込んでください')
        try:
            name = check_section_name(name)
            if name in FIXED_SECTIONS:
                raise ValueError(f'「{name}」は固定の段落です')
            renames, name = name_for_new(name, self.subjects())
        except ValueError as e:
            return self.fail(str(e))
        if name in self.df.columns:
            return self.fail(f'段落「{name}」は既にあります')
        self.df = self.df.rename(columns=renames)
        self.df.insert(insert_position(name, list(self.df.columns)), name, '')
        logger.info(f"Added section: {name} (renamed: {renames})")
        return True

    def rename_section(self, old, new):
        """段落の名前を変える（入力はそのまま）。固定の段落は改名できない"""
        self.last_error = ''
        if old in FIXED_SECTIONS:
            return self.fail(f'「{old}」は固定の段落なので改名できません')
        if old not in section_names(self.df):
            return self.fail(f'段落「{old}」がありません')
        try:
            new = check_section_name(new)
        except ValueError as e:
            return self.fail(str(e))
        if new != old and new in self.df.columns:
            return self.fail(f'段落「{new}」は既にあります')
        self.df = self.df.rename(columns={old: new})
        logger.info(f"Renamed section: {old} -> {new}")
        return True

    def remove_section(self, name):
        """段落を表から外す（その段落の入力も消える）。固定の段落は外せない"""
        self.last_error = ''
        if name in FIXED_SECTIONS:
            return self.fail(f'「{name}」は固定の段落なので外せません')
        if name not in section_names(self.df):
            return self.fail(f'段落「{name}」がありません')
        self.df = self.df.drop(columns=[name])
        logger.info(f"Removed section: {name}")
        return True

    def is_row(self, row_index):
        return type(row_index) is int and row_index in self.df.index

    def update_text(self, row_index, section, text):
        """入力を書き換える（表にある行・段落に、文字列だけ書く）"""
        if section not in section_names(self.df) or not self.is_row(row_index) or not isinstance(text, str):
            return False
        self.df.at[row_index, section] = normalize_newlines(text)
        return True

    def edit_rows(self, rows, section, text, edit):
        """複数行の段落に、入力1行分（キー: 語句, 語句）の語句をまとめて足す・消す"""
        self.last_error = ''
        if section not in section_names(self.df):
            return self.fail(f'段落「{section}」がありません')
        if not isinstance(rows, list) or not rows or not all(self.is_row(r) for r in rows):
            return self.fail('行の指定が正しくありません')
        key, phrases = parse_line(text if isinstance(text, str) else '')
        if not phrases:
            return self.fail('語句を入力してください')
        for r in dict.fromkeys(rows):
            self.df.at[r, section] = reduce(lambda t, p: edit(t, key, p), phrases, to_text(self.df.at[r, section]))
        return True

    def add_to_rows(self, rows, section, text):
        """一括入力で語句を足す。同じグループの別の語句がある行には、その語句を足さない

        足さなかった語句のある行の数を返す（失敗は None）
        """
        groups = self.shared['groups']

        def add(current, key, phrase):
            return current if blocked_by(groups, current, key, phrase) else add_phrase(current, key, phrase)

        if not self.edit_rows(rows, section, text, add):
            return None
        key, phrases = parse_line(text)

        def has_all(r):
            return set(phrases) <= {p for k, p in phrases_of(to_text(self.df.at[r, section])) if k == key}

        return sum(1 for r in dict.fromkeys(rows) if not has_all(r))

    def choose(self, rows, section, key, phrase, group, on):
        """ボタンでの選択: 複数行の段落の key の行に、group の語句を1つだけ置く（on でなければ group の語句を消す）"""
        self.last_error = ''
        if section not in section_names(self.df):
            return self.fail(f'段落「{section}」がありません')
        if not isinstance(rows, list) or not rows or not all(self.is_row(r) for r in rows):
            return self.fail('行の指定が正しくありません')
        valid_group = isinstance(group, list) and all(isinstance(p, str) and p for p in group)
        if not (isinstance(key, str) and key and valid_group and phrase in group and isinstance(on, bool)):
            return self.fail('選択の指定が正しくありません')
        for r in dict.fromkeys(rows):
            self.df.at[r, section] = set_choice(to_text(self.df.at[r, section]), key, phrase, group, on, TARGETED)
        return True

    def mark_rows(self, rows, column, change, check):
        """複数行のマークを書き換える（check でマークを検証してから）"""
        self.last_error = ''
        if not isinstance(rows, list) or not rows or not all(self.is_row(r) for r in rows):
            return self.fail('行の指定が正しくありません')
        try:
            check()
        except ValueError as e:
            return self.fail(str(e))
        for r in dict.fromkeys(rows):
            self.df.at[r, column] = change(to_text(self.df.at[r, column]))
        return True

    def set_mark(self, rows, mark):
        """排他のマーク（番号 0〜7。None なら外す）を複数行に付ける"""
        return self.mark_rows(rows, 'mark', lambda _: one_text(mark), lambda: check_one(mark))

    def set_marks(self, rows, mark, on):
        """複数のマーク（番号 0〜7）を複数行に付ける・外す"""
        def check():
            check_number(mark)
            if not isinstance(on, bool):
                raise ValueError('付けるか外すかの指定が正しくありません')
        return self.mark_rows(rows, 'marks', lambda marks: toggle_many(marks, mark, on), check)

    def clear_marks(self, column):
        """マークの列（mark / marks）を全行で消す"""
        self.last_error = ''
        if column not in ('mark', 'marks'):
            return self.fail(f'マークの列ではありません: {column}')
        if 'サムネイル' in self.df.columns:
            self.df[column] = ''
        return True

    def set_auto_mark(self, index, mark):
        """自動のマーク（番号 0〜7）の設定を {section（A, B を除いた段落の名前）, key, phrase} にする（None なら外す）

        行には持たない（画面が入力から付ける）。保存で table.json に書く。設定の一覧を返す（失敗は None）
        """
        self.last_error = ''
        try:
            check_number(index)
            if mark is not None:
                if not isinstance(mark, dict):
                    raise ValueError('自動のマークの設定が正しくありません')
                key = check_key(mark.get('key'))
                if not key:
                    raise ValueError('キーを選んでください')
                mark = {'section': check_section_name(mark.get('section')), 'key': key, 'phrase': check_phrase(key, mark.get('phrase'))}
        except ValueError as e:
            self.fail(str(e))
            return None
        self.auto_marks = [mark if i == index else m for i, m in enumerate(self.auto_marks)]
        return self.auto_marks

    def row_texts(self, record, sections):
        """キャプションに使う入力と characters。picture に characters（入力のある人物の段落から）を入れる"""
        texts = {s: to_text(record[s]) for s in sections}
        characters = characters_of([(s, texts[s]) for s in sections if s not in FIXED_SECTIONS and phrases_of(texts[s])])
        keys = self.shared['templates'].get('picture', [])
        if 'picture' in texts and 'characters' in keys:
            texts['picture'] = with_line(texts['picture'], 'characters', characters, keys)
        return texts, characters

    def caption_of(self, record, sections):
        """1行のキャプション（書き出す文面）"""
        texts, _ = self.row_texts(record, sections)
        return render_caption([(s, texts[s]) for s in sections])

    def row_view(self, index, record, sections):
        """画面に渡す1行（入力・characters・キャプション・トークン数・hint・Qwen の答え）"""
        texts, characters = self.row_texts(record, sections)
        caption = render_caption([(s, texts[s]) for s in sections])
        return {'index': int(index), 'サムネイル': record['サムネイル'], 'is_dead': to_flag(record['is_dead']),
                'texts': {s: to_text(record[s]) for s in sections}, 'characters': characters,
                'hint': self.hints.get(record['サムネイル'], ''), 'qwen_hint': self.qwen_hints.get(record['サムネイル'], ''),
                'mark': one_number(to_text(record['mark'])), 'marks': many_numbers(to_text(record['marks'])),
                'caption': caption, 'tokens': token_counter.count(caption)}

    def row_views(self, indexes):
        sections = section_names(self.df)
        return [self.row_view(i, self.df.loc[i].to_dict(), sections) for i in dict.fromkeys(indexes)]

    def save_qwen_hint(self, image_name, text):
        """Qwen の答えを data_work/<フォルダ名>/qwen/<画像名>.txt に残す（同じ画像は上書き）"""
        folder = self.data_work_target / QWEN_DIR
        folder.mkdir(exist_ok=True)
        (folder / f"{Path(image_name).stem}{HINT_EXT}").write_text(text, encoding='utf-8', newline='\n')
        self.qwen_hints[image_name] = text

    def qwen_fill(self, row_index, url, mode='near'):
        """Qwen に下書きさせ、その行の空の欄（値の無いキーと、文の無い段落）に入れる

        見本は空でないキャプション 10 個（削除済みの行は除く）。mode が near（🤖）なら上にある行から近い順に、
        mark（🔖）なら A〜D が同じ行 → ★●▲■ を共有する行 → ほかの行の順にランダムに、
        random（🎲）ならその行のほかの全部の行からランダムに。(画面に渡す1行, 入れた段落) を返す。
        行・見本・画像の問題は ValueError、ComfyUI の問題は OSError（繋がらない・時間切れ）か RuntimeError（実行の失敗）
        """
        if mode not in QWEN_MODES:
            raise ValueError(f'見本の選び方が正しくありません: {mode}')
        if not self.is_row(row_index):
            raise ValueError('行がありません')
        sections = section_names(self.df)
        records = self.df.to_dict('records')
        position = list(self.df.index).index(row_index)
        name = records[position]['サムネイル']
        if to_flag(records[position]['is_dead']) or not (self.image_dir / name).is_file():
            raise ValueError(f'{name} は元の画像がありません')
        if mode == 'near':
            samples = pick_samples([self.caption_of(r, sections) for r in records[:position] if not to_flag(r['is_dead'])])
            missing = f'上に見本（キャプションのある行）が {SAMPLE_COUNT} 行必要です'
        else:
            others = [(i, r) for i, r in enumerate(records) if i != position and not to_flag(r['is_dead'])]
            captions = [(i, self.caption_of(r, sections)) for i, r in others]
            if mode == 'random':
                samples = pick_random_samples([caption for _, caption in captions])
            else:  # mark: 排他のマークが同じ行 → 複数のマークを共有する行 → ほかの行
                one, many = to_text(records[position]['mark']), set(many_numbers(to_text(records[position]['marks'])))
                marks = {i: (to_text(r['mark']), set(many_numbers(to_text(r['marks'])))) for i, r in others}
                samples = pick_tiered_samples([[(i, c) for i, c in captions if one and marks[i][0] == one],
                                               [(i, c) for i, c in captions if many & marks[i][1]],
                                               captions])
            missing = f'見本（キャプションのある行）がほかに {SAMPLE_COUNT} 行必要です'
        if not samples:
            raise ValueError(missing)
        keys = {s: template_keys(s, self.shared['templates'], FIXED_SECTIONS) for s in sections}
        answer = generate(url, jpeg_of(self.image_dir / name), f"{self.dir_name}_{Path(name).stem}.jpg",
                          user_prompt(samples), system_prompt([(s, keys[s]) for s in sections]))
        self.save_qwen_hint(name, answer)
        # 押し直したときは、前に Qwen が入れて、そのあと直していないもの（前の下書き）を消してから入れる
        before = {s: to_text(self.df.at[row_index, s]) for s in sections}
        drafts = self.read_qwen_drafts(name)
        texts = {s: clear_drafts(before[s], drafts.get(s, {})) for s in sections}
        added = {}
        for block, lines in parse_caption(answer):
            section = match_section(block, sections)
            if section is None:
                continue
            texts[section], put = fill_section(texts[section], lines, keys[section])
            drafted = added.setdefault(section, {'keys': {}, 'sentences': []})
            drafted['keys'].update(put['keys'])
            drafted['sentences'] += put['sentences']
        for section in sections:
            if texts[section] != before[section]:
                self.update_text(row_index, section, texts[section])
        added = {s: d for s, d in added.items() if d['keys'] or d['sentences']}
        self.save_qwen_drafts(name, added)
        logger.info(f"Qwen filled {name}: {sorted(added)}")
        return self.row_views([row_index])[0], [s for s in sections if s in added]

    def qwen_drafts_file(self, image_name):
        """Qwen が欄に入れたもの（前の下書き）の置き場: data_work/<フォルダ名>/qwen/<画像名>.json"""
        return self.data_work_target / QWEN_DIR / f"{Path(image_name).stem}.json"

    def read_qwen_drafts(self, image_name):
        """前の下書き {段落: {'keys': {キー: 値}, 'sentences': [文]}}（無い・壊れているときは空）"""
        try:
            return json.loads(self.qwen_drafts_file(image_name).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def save_qwen_drafts(self, image_name, drafts):
        path = self.qwen_drafts_file(image_name)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(drafts, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')

    def save_data(self):
        """データ保存"""
        if self.image_dir is None:
            raise ValueError('先にプロジェクトを読み込んでください')

        # 保存前に重複チェック（行番号は画面の行位置と揃うよう振り直す）
        if not self.df.empty:
            original_len = len(self.df)
            self.df = self.df.drop_duplicates(subset=['サムネイル'], keep='first').reset_index(drop=True)
            if original_len != len(self.df):
                logger.warning(f"Removed {original_len - len(self.df)} duplicate rows before saving")

        # 表
        write_json(self.data_out_target / TABLE_FILE, table_to_json(self.df, self.auto_marks))

        # captionsディレクトリ作成
        self.captions_dir.mkdir(exist_ok=True)

        # txtファイル保存（改行は LF。削除済み画像は captions_dead へ）
        sections = section_names(self.df)
        for record in self.df.to_dict('records'):
            folder = self.captions_dead_dir if to_flag(record['is_dead']) else self.captions_dir
            caption_path = folder / f"{Path(record['サムネイル']).stem}{CAPTION_EXT}"
            texts, _ = self.row_texts(record, sections)
            caption_path.write_text(render_caption([(s, texts[s]) for s in sections]), encoding='utf-8', newline='\n')

        logger.info(f"Data saved: {len(self.df)} rows, {len(sections)} sections")

# グローバルインスタンス
caption_tool = CaptionTool()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_existing_projects')
def get_existing_projects():
    """既存プロジェクト一覧取得"""
    data_out_dir = caption_tool.data_out_dir

    if not data_out_dir.exists():
        return jsonify({'projects': []})

    projects = []
    for item in data_out_dir.iterdir():
        if item.is_dir():
            tgt_path_file = item / "tgt_path.txt"
            image_path = ""
            if tgt_path_file.exists():
                try:
                    with open(tgt_path_file, 'r', encoding='utf-8') as f:
                        image_path = f.read().strip()
                except Exception as e:
                    logger.warning(f"Failed to read tgt_path.txt: {e}")

            projects.append({
                'name': item.name,
                'image_path': image_path
            })

    logger.info(f"Found {len(projects)} projects")
    return jsonify({'projects': projects})

@app.route('/load_existing_project', methods=['POST'])
def load_existing_project():
    """既存プロジェクト読み込み"""
    data = request.get_json()
    project_name = data.get('project_name')

    if not project_name:
        return jsonify({'success': False, 'message': 'Project name required'})

    # プロジェクト名は data_out 直下のフォルダ名だけ（../ 等で外を読ませない）
    if Path(project_name).name != project_name or project_name in ('.', '..'):
        return jsonify({'success': False, 'message': 'Invalid project name'})

    data_out_dir = caption_tool.data_out_dir / project_name
    tgt_path_file = data_out_dir / "tgt_path.txt"

    if not tgt_path_file.exists():
        return jsonify({'success': False, 'message': 'tgt_path.txt not found'})

    try:
        with open(tgt_path_file, 'r', encoding='utf-8') as f:
            image_dir = f.read().strip()

        caption_tool.setup_directories(image_dir)
        caption_tool.load_data()
        return jsonify({
            'success': True,
            'message': 'Project loaded successfully',
            'image_dir': image_dir
        })
    except Exception as e:
        logger.error(f"Failed to load existing project: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/load_directory', methods=['POST'])
def load_directory():
    """ディレクトリ読み込み"""
    data = request.get_json()
    image_dir = data.get('image_dir')

    try:
        caption_tool.setup_directories(image_dir)
        caption_tool.load_data()
        return jsonify({'success': True, 'message': 'Directory loaded successfully'})
    except Exception as e:
        logger.error(f"Failed to load directory: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/choose_directory', methods=['POST'])
def choose_directory():
    """このPCでフォルダを選ぶ窓を開く（{initial}: 選び始めるフォルダ）。path: 選んだフォルダ（やめたら空）"""
    if request.remote_addr not in LOCAL_ADDRESSES:
        return jsonify({'success': False,
                        'message': 'フォルダを選ぶ窓は、このアプリを動かしている PC からだけ使えます。パスを入力してください'})
    data = request.get_json() or {}
    initial = data.get('initial').strip().strip('"\'') if isinstance(data.get('initial'), str) else ''
    try:
        path = ask_directory(initial if initial and Path(initial).is_dir() else '')
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        logger.error(f"Failed to open the folder dialog: {e}")
        return jsonify({'success': False, 'message': f'フォルダを選ぶ窓を開けません（{e}）。パスを入力してください'})
    return jsonify({'success': True, 'path': str(Path(path)) if path else ''})

@app.route('/get_table_data')
def get_table_data():
    """テーブルデータ取得

    sections: 段落の並び。data: 行ごとの {index, サムネイル, is_dead, texts, characters, caption, tokens}
    サムネイル列は画像ファイル名（URL はフロントで /thumbnail/<名前>, /image/<名前> を組み立てる）
    tokens はトークナイザーの準備ができるまで null。view_choices は view のボタン（🎥 の組と、人物ごとの 👀）
    others_section は確定タグを持たない段落（else）の名前。candidate_groups は語句の候補をまとめる名前の組（女性・男性）
    """
    df = caption_tool.df
    common = {'token_limit': TOKEN_LIMIT, 'templates': caption_tool.shared['templates'], 'fixed_sections': FIXED_SECTIONS,
              'auto_keys': AUTO_KEYS, 'others_section': OTHERS, 'candidate_groups': CANDIDATE_GROUPS,
              'view_choices': {'camera': CAMERA_GROUPS, 'camera_emoji': CAMERA_EMOJI, 'targeted': TARGETED,
                               'pov': pov_choices(caption_tool.subjects())},
              'mark_choices': {'one': ONE, 'many': MANY, 'auto': AUTO}, 'auto_marks': caption_tool.auto_marks,
              'qwen': bool(app.config.get('QWEN_URL'))}
    if 'サムネイル' not in df.columns:
        return jsonify({'sections': [], 'data': [], **common})

    sections = section_names(df)
    data = [caption_tool.row_view(index, record, sections) for index, record in zip(df.index, df.to_dict('records'))]
    return jsonify({'sections': sections, 'data': data, **common})

@app.route('/thumbnail/<filename>')
def serve_thumbnail(filename):
    """サムネイル画像配信（filename は元画像名）。初めて表示するときに作る（元画像が更新されていれば作り直す）

    長辺 600px 以下の画像は元画像。元画像が消えた削除済み画像は、残っているサムネイル
    """
    if not caption_tool.is_known_image(filename):
        return "Image not found", 404

    path = caption_tool.create_thumbnail(caption_tool.image_dir / filename)
    if path.exists():
        return send_file(path.resolve())

    return "Image not found", 404

@app.route('/image/<filename>')
def serve_image(filename):
    """元画像配信（元画像が無い削除済み画像はサムネイル）"""
    if not caption_tool.is_known_image(filename):
        return "Image not found", 404

    for path in [caption_tool.image_dir / filename, caption_tool.thumbnail_file(filename)]:
        if path.exists():
            return send_file(path.resolve())

    return "Image not found", 404

@app.route('/get_dictionary')
def get_dictionary():
    """辞書（phrases: 語句、words: キーなしの文の単語、templates: 確定タグ、groups: 「1つだけ」のグループ）

    使用回数の多い順で、共用辞書だけのものは 0 回
    """
    return jsonify(caption_tool.dictionary())

def dictionary_result(success, message):
    """共用辞書を書き換える API の応答（成功なら新しい辞書も返す）"""
    if not success:
        return jsonify({'success': False, 'message': caption_tool.last_error})
    return jsonify({'success': True, 'message': message, 'dictionary': caption_tool.dictionary()})

@app.route('/register_entries', methods=['POST'])
def register_entries():
    """使っている語句・単語を共用辞書に入れる（{phrases: [{key, phrase}], words: [単語]}）"""
    data = request.get_json() or {}
    success = caption_tool.register_entries(data.get('phrases', []), data.get('words', []))
    return dictionary_result(success, '共用辞書に入れました')

@app.route('/add_entry', methods=['POST'])
def add_entry():
    """新しい語句を共用辞書に足す（{section, key, phrase}）"""
    data = request.get_json() or {}
    success = caption_tool.add_entry(data.get('section'), data.get('key'), data.get('phrase'))
    return dictionary_result(success, '共用辞書に足しました')

@app.route('/unregister_entries', methods=['POST'])
def unregister_entries():
    """語句・単語を共用辞書から消す（{phrases: [{key, phrase}], words: [単語]}）。入力はそのまま"""
    data = request.get_json() or {}
    success = caption_tool.unregister_entries(data.get('phrases', []), data.get('words', []))
    return dictionary_result(success, '共用辞書から消しました')

@app.route('/rename_entry', methods=['POST'])
def rename_entry():
    """語句の改名（{key, old, new, in_project}）。changed: 開いているプロジェクトで入力を置き換えた行の数"""
    data = request.get_json() or {}
    changed = caption_tool.rename_entry(data.get('key'), data.get('old'), data.get('new'), data.get('in_project'))
    if changed is None:
        return jsonify({'success': False, 'message': caption_tool.last_error})
    return jsonify({'success': True, 'changed': changed, 'dictionary': caption_tool.dictionary()})


@app.route('/move_phrases', methods=['POST'])
def move_phrases_route():
    """キーを移す（{section, from_key, to_key, phrases}）。changed: 開いているプロジェクトで入力を変えた行の数"""
    data = request.get_json() or {}
    changed = caption_tool.move_phrases(data.get('section'), data.get('from_key'), data.get('to_key'), data.get('phrases'))
    if changed is None:
        return jsonify({'success': False, 'message': caption_tool.last_error})
    return jsonify({'success': True, 'changed': changed, 'dictionary': caption_tool.dictionary()})

@app.route('/group_phrases', methods=['POST'])
def group_phrases_api():
    """同じキーの語句を「1つだけ」のグループにする（{key, phrases}）"""
    data = request.get_json() or {}
    return dictionary_result(caption_tool.group(data.get('key'), data.get('phrases')), 'グループにしました')

@app.route('/ungroup_phrases', methods=['POST'])
def ungroup_phrases_api():
    """語句をグループから外す（{phrases: [{key, phrase}]}）"""
    data = request.get_json() or {}
    return dictionary_result(caption_tool.ungroup(data.get('phrases', [])), 'グループから外しました')

@app.route('/freeze', methods=['POST'])
def freeze_dictionary():
    """使用中の語句・単語を共用辞書に入れる"""
    try:
        added = caption_tool.freeze_dictionary()
        return jsonify({'success': True, 'added': added, 'message': f'共用辞書に {added} 件入れました'})
    except OSError as e:
        logger.error(f"Failed to freeze dictionary: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/qwen_fill', methods=['POST'])
def qwen_fill():
    """🤖 / 🔖 / 🎲: Qwen に下書きさせ、その行の空の欄に入れる（{row_index, mode: near（既定）/ mark / random}。qwen 版のときだけ）

    入れた段落と、行を返す
    """
    url = app.config.get('QWEN_URL')
    if not url:
        return jsonify({'success': False, 'message': 'qwen 版で起動していません（--qwen を付けて起動）'})
    data = request.get_json() or {}
    try:
        row, filled = caption_tool.qwen_fill(data.get('row_index'), url, data.get('mode', 'near'))
    except (ValueError, RuntimeError) as e:  # 行・見本・画像の問題と、ComfyUI での実行の失敗
        return jsonify({'success': False, 'message': str(e)})
    except TimeoutError as e:
        return jsonify({'success': False, 'message': f'ComfyUI（{url}）の答えを待ちきれませんでした（{e}）'})
    except OSError as e:  # 繋がらない（URLError も含む）
        logger.error(f"Failed to reach ComfyUI at {url}: {e}")
        return jsonify({'success': False, 'message': f'ComfyUI（{url}）に繋がりません。WSL で ComfyUI を起動してください（{e}）'})
    return jsonify({'success': True, 'row': row, 'filled': filled})

@app.route('/update_text', methods=['POST'])
def update_text():
    """入力の更新（{row_index, section, text}）。更新後の characters・キャプション・トークン数を返す"""
    data = request.get_json() or {}
    row_index = data.get('row_index')
    if not caption_tool.update_text(row_index, data.get('section'), data.get('text')):
        return jsonify({'success': False})
    row = caption_tool.row_views([row_index])[0]
    return jsonify({'success': True, 'characters': row['characters'], 'caption': row['caption'], 'tokens': row['tokens']})

@app.route('/set_choice', methods=['POST'])
def set_choice_on_rows():
    """ボタンでの選択（{rows, section, key, phrase, group, on}）。group の語句は1つだけ残る"""
    data = request.get_json() or {}
    rows = data.get('rows')
    if not caption_tool.choose(rows, data.get('section'), data.get('key'), data.get('phrase'), data.get('group'), data.get('on')):
        return jsonify({'success': False, 'message': caption_tool.last_error})
    return jsonify({'success': True, 'rows': caption_tool.row_views(rows)})

@app.route('/set_mark', methods=['POST'])
def set_mark():
    """排他のマーク（{rows, mark}。mark は番号 0〜7（記号は marks.py の ONE）、null なら外す）"""
    data = request.get_json() or {}
    rows = data.get('rows')
    if not caption_tool.set_mark(rows, data.get('mark')):
        return jsonify({'success': False, 'message': caption_tool.last_error})
    return jsonify({'success': True, 'rows': caption_tool.row_views(rows)})

@app.route('/set_marks', methods=['POST'])
def set_marks():
    """複数のマーク（{rows, mark, on}。mark は番号 0〜7（記号は marks.py の MANY））"""
    data = request.get_json() or {}
    rows = data.get('rows')
    if not caption_tool.set_marks(rows, data.get('mark'), data.get('on')):
        return jsonify({'success': False, 'message': caption_tool.last_error})
    return jsonify({'success': True, 'rows': caption_tool.row_views(rows)})

@app.route('/clear_marks', methods=['POST'])
def clear_marks():
    """マークの列を全行で消す（{column}。mark か marks）"""
    data = request.get_json() or {}
    success = caption_tool.clear_marks(data.get('column'))
    return jsonify({'success': success, 'message': caption_tool.last_error})

@app.route('/set_auto_mark', methods=['POST'])
def set_auto_mark():
    """自動のマークの設定（{index: 0〜7, mark: {section, key, phrase} か null}）。プロジェクトごと（保存で table.json に書く）"""
    data = request.get_json() or {}
    marks = caption_tool.set_auto_mark(data.get('index'), data.get('mark'))
    if marks is None:
        return jsonify({'success': False, 'message': caption_tool.last_error})
    return jsonify({'success': True, 'auto_marks': marks})

@app.route('/add_phrase', methods=['POST'])
def add_phrase_to_rows():
    """複数行への一括入力（{rows, section, text}。text は「キー: 語句, 語句」かキーなしの文）

    同じグループの別の語句がある行には足さない（skipped: 足さなかった語句のある行の数）
    """
    data = request.get_json() or {}
    rows = data.get('rows')
    skipped = caption_tool.add_to_rows(rows, data.get('section'), data.get('text'))
    if skipped is None:
        return jsonify({'success': False, 'message': caption_tool.last_error})
    return jsonify({'success': True, 'rows': caption_tool.row_views(rows), 'skipped': skipped})

@app.route('/remove_phrase', methods=['POST'])
def remove_phrase_from_rows():
    """複数行から語句をまとめて消す（{rows, section, text}）"""
    data = request.get_json() or {}
    rows = data.get('rows')
    if not caption_tool.edit_rows(rows, data.get('section'), data.get('text'), remove_phrase):
        return jsonify({'success': False, 'message': caption_tool.last_error})
    return jsonify({'success': True, 'rows': caption_tool.row_views(rows)})

@app.route('/add_section', methods=['POST'])
def add_section():
    """段落の追加API（{name}）"""
    data = request.get_json() or {}
    success = caption_tool.add_section(data.get('name'))
    return jsonify({'success': success, 'message': caption_tool.last_error})

@app.route('/rename_section', methods=['POST'])
def rename_section():
    """段落の改名API（{old, new}）"""
    data = request.get_json() or {}
    success = caption_tool.rename_section(data.get('old'), data.get('new'))
    return jsonify({'success': success, 'message': caption_tool.last_error})

@app.route('/remove_section', methods=['POST'])
def remove_section():
    """段落を表から外すAPI（{name}）"""
    data = request.get_json() or {}
    success = caption_tool.remove_section(data.get('name'))
    return jsonify({'success': success, 'message': caption_tool.last_error})

@app.route('/remove_all_dead', methods=['POST'])
def remove_all_dead():
    """削除済み画像に対応する表の行を完全に削除"""
    try:
        if caption_tool.df.empty:
            return jsonify({'success': False, 'message': 'データがありません'})

        # 削除前のカウント
        before_count = len(caption_tool.df)
        dead_count = len(caption_tool.df[caption_tool.df['is_dead'] == True]) if 'is_dead' in caption_tool.df.columns else 0

        if dead_count == 0:
            return jsonify({'success': False, 'message': '削除済み画像がありません'})

        # 削除する行のサムネイルも消す（残っていると次の読み込みで削除済み行として復活する）
        dead_names = caption_tool.df.loc[caption_tool.df['is_dead'] == True, 'サムネイル'].tolist()
        for name in dead_names:
            thumb_path = caption_tool.thumbnail_file(name)
            if thumb_path.exists():
                thumb_path.unlink()

        # is_dead == False の行のみ残す（行番号は画面の行位置と揃うよう振り直す）
        caption_tool.df = caption_tool.df[caption_tool.df['is_dead'] == False].reset_index(drop=True)

        after_count = len(caption_tool.df)

        logger.info(f"Removed {dead_count} dead rows. Total rows: {before_count} -> {after_count}")

        # 自動保存
        caption_tool.save_data()

        return jsonify({
            'success': True,
            'message': f'{dead_count}件の削除済み画像のデータを削除しました',
            'removed_count': dead_count
        })

    except Exception as e:
        logger.error(f"Failed to remove dead images: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/save_data', methods=['POST'])
def save_data():
    """データ保存API"""
    try:
        caption_tool.save_data()
        caption_tool.load_data()
        return jsonify({'success': True, 'message': 'Data saved successfully'})
    except Exception as e:
        logger.error(f"Failed to save data: {e}")
        return jsonify({'success': False, 'message': str(e)})

def server_options(env):
    """起動設定（既定は 127.0.0.1 のみ。LAN へ公開するときは PICTAG_HOST=0.0.0.0）"""
    return {'host': env.get('PICTAG_HOST', '127.0.0.1'), 'port': 5000, 'debug': True}

def qwen_url(argv):
    """起動の引数から、qwen 版の ComfyUI の宛先を読む（--qwen が無ければ None。宛先は --comfyui-url、既定は 127.0.0.1:8189）"""
    parser = argparse.ArgumentParser(description='pictag（Krea 2 の LoRA 学習用キャプション）')
    parser.add_argument('--qwen', action='store_true', help='Qwen（ComfyUI の TextGenerate）で空の欄を下書きする 🤖 を使う')
    parser.add_argument('--comfyui-url', default=DEFAULT_URL, help=f'ComfyUI の宛先（既定は {DEFAULT_URL}）')
    args = parser.parse_args(argv)
    return args.comfyui_url.rstrip('/') if args.qwen else None

if __name__ == '__main__':
    app.config['QWEN_URL'] = qwen_url(sys.argv[1:])
    options = server_options(os.environ)
    # トークナイザーは裏で取得する。debug のリローダーでは親プロセスで取得しない（子プロセスと二重になるため）
    if not options['debug'] or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        token_counter.start_once(caption_tool.data_work_dir / TOKENIZER_FILE)
    app.run(**options)
