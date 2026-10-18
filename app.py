import os
import json
import logging
from functools import reduce
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
from PIL import Image

from caption_format import render_caption
from kinds import (LEVELS, check_name, column_key, dictionary_columns, empty_kinds, entries_of,
                   in_table_scope, mid_columns, order_columns, parse_key, register_columns)
from kinds import add_value as add_to_kinds, remove as remove_from_kinds, rename as rename_in_kinds

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# data_out / data_work の既定の置き場所（起動ディレクトリに依存させない）
APP_DIR = Path(__file__).resolve().parent

# 表の固定列。それ以外の列名は kinds.column_key の文字列（[大kind, 中kind, 小kind, 値] の JSON）
FIXED_COLUMNS = ['サムネイル', 'is_dead']
KINDS_FILE = 'kinds.json'  # data_work/ 直下。辞書（全プロジェクト共通）
TABLE_FILE = 'table.json'  # data_out/<フォルダ名>/ 直下。画像 × 列のチェック
SDXL_DUMP = 'df_isflaged.dump'  # SDXL 版の表。これだけがあるフォルダは SDXL 版のプロジェクト

def to_flag(value):
    """セル値を bool に揃える（欠損や bool 以外は False）"""
    return bool(value) if pd.api.types.is_bool(value) else False

def same_path(a, b):
    """同じディレクトリを指すか（Windows の大文字小文字・区切り文字の違いは無視）"""
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))

def write_json(path, data):
    """JSON を書く（書きかけで壊れないよう、一時ファイルに書いてから置き換える）"""
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8', newline='\n')
    os.replace(tmp, path)

def read_kinds(path):
    """辞書を読む（無い・壊れているときは空の辞書）"""
    if not path.exists():
        return empty_kinds()
    try:
        kinds = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(kinds.get('bigs'), list) and isinstance(kinds.get('mids'), list):
            return kinds
        raise ValueError('bigs / mids がありません')
    except (OSError, ValueError, AttributeError) as e:
        logger.warning(f"Failed to load kinds: {e}")
        return empty_kinds()

def tag_keys(df):
    return [c for c in df.columns if c not in FIXED_COLUMNS]

def table_to_json(df):
    """表を JSON にする（列は [大kind, 中kind, 小kind, 値]、チェックは列の番号）"""
    keys = tag_keys(df)
    return {
        'columns': [list(parse_key(k)) for k in keys],
        'rows': [{'image': r['サムネイル'], 'is_dead': to_flag(r['is_dead']),
                  'checked': [i for i, k in enumerate(keys) if to_flag(r[k])]}
                 for r in df.to_dict('records')],
    }

def table_from_json(data):
    keys = [column_key(tuple(c)) for c in data['columns']]

    def row(r):
        checked = set(r['checked'])
        return {'サムネイル': r['image'], 'is_dead': bool(r['is_dead']), **{k: i in checked for i, k in enumerate(keys)}}

    return pd.DataFrame([row(r) for r in data['rows']], columns=FIXED_COLUMNS + keys)

def read_table(path):
    """保存済みの表（無ければ空）。読めなければ例外にする（開いて保存すると上書きで消えるため）"""
    if not path.exists():
        return pd.DataFrame()
    try:
        return table_from_json(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise ValueError(f'表を読めません: {path} ({e})') from e

class CaptionTool:
    def __init__(self, base_dir=None):
        # data_out / data_work の置き場所
        self.base_dir = Path(base_dir) if base_dir is not None else APP_DIR
        self.data_out_dir = self.base_dir / "data_out"
        self.data_work_dir = self.base_dir / "data_work"
        self.image_dir = None
        self.dir_name = None
        self.df = pd.DataFrame()
        self.kinds = empty_kinds()
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
        # 辞書（プロジェクト共通）
        self.kinds = read_kinds(self.data_work_dir / KINDS_FILE)

        # tgt_path.txt作成
        tgt_path_file = self.data_out_target / "tgt_path.txt"
        if not tgt_path_file.exists():
            with open(tgt_path_file, 'w', encoding='utf-8') as f:
                f.write(str(self.image_dir))
            logger.info(f"Created tgt_path.txt: {self.image_dir}")

        # 保存済みの表
        self.df = read_table(self.data_out_target / TABLE_FILE)

        # 画像ファイル存在チェックと dead/alive 状態管理
        self.manage_dead_alive_status()

        # 表にあって辞書に無い列は辞書へ足し、列を辞書の順に並べる
        self.kinds = register_columns(self.kinds, self.tag_items())
        self.set_columns(self.tag_items())

        logger.info(f"DataFrame created: {len(self.df)} rows, {len(self.df.columns)} columns")

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

        # タグ列: 保存済みの表があればその列を保つ（「表から外す」した列を戻さない）
        # 新規プロジェクトは辞書の全列から始める
        if has_table:
            additional_columns = tag_keys(self.df)
        else:
            additional_columns = [column_key(item) for item in dictionary_columns(self.kinds)]
        additional_columns = list(dict.fromkeys(additional_columns))  # 重複除去（順序は保つ）

        # DataFrameを再構築
        columns = FIXED_COLUMNS + additional_columns
        data = []

        for img_file in sorted(all_image_files):
            is_alive = img_file in alive_image_files
            is_dead = not is_alive

            row = {
                'サムネイル': img_file,
                'is_dead': is_dead
            }

            # 既存のタグ列の値を設定
            existing_row = existing_rows.get(img_file, {})
            for col in additional_columns:
                row[col] = to_flag(existing_row.get(col, False))

            data.append(row)

            # サムネイル生成とキャプション移動処理
            if is_alive:
                # 生成済みでも元画像が更新されていれば作り直す
                self.create_thumbnail(self.image_dir / img_file)

                # deadからの復帰処理
                stem = Path(img_file).stem
                dead_caption_path = self.captions_dead_dir / f"{stem}.txt"
                if dead_caption_path.exists():
                    self.move_caption_from_dead_to_alive(img_file)

            else:
                # aliveからdeadへの移動処理
                stem = Path(img_file).stem
                alive_caption_path = self.captions_dir / f"{stem}.txt"
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
            dead_caption_path = self.captions_dead_dir / f"{stem}.txt"
            alive_caption_path = self.captions_dir / f"{stem}.txt"

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
            alive_caption_path = self.captions_dir / f"{stem}.txt"
            dead_caption_path = self.captions_dead_dir / f"{stem}.txt"

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

                # リサイズ実行
                img.thumbnail((600, 600), Image.Resampling.LANCZOS)
                img.save(thumb_path, quality=85, optimize=True)
                os.utime(thumb_path, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
                logger.info(f"Created thumbnail: {thumb_path}")
                return thumb_path

        except Exception as e:
            logger.error(f"Failed to create thumbnail for {image_path}: {e}")
            return image_path

    def tag_items(self):
        """表の列 (大kind, 中kind, 小kind, 値) を表の順に"""
        return [parse_key(k) for k in tag_keys(self.df)]

    def set_columns(self, items, default=False):
        """表の列を items にする（辞書の順に並べ直す）。新しい列は default で埋める"""
        if 'サムネイル' not in self.df.columns:
            self.df = pd.DataFrame(columns=FIXED_COLUMNS)
        keys = [column_key(item) for item in order_columns(self.kinds, list(dict.fromkeys(items)))]
        missing = [k for k in keys if k not in self.df.columns]
        if missing:
            filler = pd.DataFrame(to_flag(default), index=self.df.index, columns=missing)
            self.df = pd.concat([self.df, filler], axis=1)
        self.df = self.df[FIXED_COLUMNS + keys]

    def new_columns_for(self, big, mid, small, value):
        """値の追加で表に足す列（表に既にある列は除く）

        - 辞書に無い値（中kind の新しい語彙）は、表でその中kind を使っている大kind すべてに足す
        - 値が空なら、中kind の値を全部その大kind に足す（既存の中kind を別の大kind に付ける）
        """
        table = self.tag_items()
        if not value:
            if not mid or not entries_of(self.kinds, mid):
                raise ValueError('値を入力してください')
            items = [it for it in mid_columns(self.kinds, big, mid) if not small or it[2] == small]
        else:
            item = (big, mid, small, value)
            if item in table:
                raise ValueError(f'「{value}」は表に既にあります')
            is_new_word = mid and {'small': small, 'value': value} not in entries_of(self.kinds, mid)
            sharing = dict.fromkeys(it[0] for it in table if it[1] == mid) if is_new_word else {}
            items = [item, *((b, mid, small, value) for b in sharing if b != big)]
        items = [it for it in items if it not in table]
        if not items:
            raise ValueError('追加する列がありません')
        return items

    def add_value(self, big, mid, small, value, default_value=False):
        """値を辞書に足し、表に列を作る"""
        self.last_error = ''
        if self.image_dir is None:
            return self.fail('先にプロジェクトを読み込んでください')
        try:
            big = check_name(big)
            mid, small, value = (check_name(name) if (name or '').strip() else '' for name in (mid, small, value))
            if small and not mid:
                raise ValueError('キーなしの行に小kind は付けられません')
            items = self.new_columns_for(big, mid, small, value)
        except ValueError as e:
            return self.fail(str(e))

        self.kinds = reduce(add_to_kinds, items, self.kinds)
        self.set_columns([*self.tag_items(), *items], default_value)
        logger.info(f"Added columns: {items}")
        return True

    def rename(self, level, target, new_name):
        """辞書と表の名前を変える（共有の語彙なら、それを使う大kind すべての列が変わる）"""
        self.last_error = ''
        try:
            kinds, relabel = rename_in_kinds(self.kinds, level, target, new_name)
        except ValueError as e:
            return self.fail(str(e))

        items = self.tag_items()
        renamed = [relabel(it) for it in items]
        if len(set(renamed)) != len(renamed):
            return self.fail('改名すると表の列が重複します')
        self.df = self.df.rename(columns={column_key(a): column_key(b) for a, b in zip(items, renamed) if a != b})
        self.kinds = kinds
        if 'サムネイル' in self.df.columns:
            self.set_columns(self.tag_items())
        logger.info(f"Renamed {level} of {target} -> '{new_name}'")
        return True

    def remove_from_table(self, level, target):
        """表から外す（選んだ大kind の中だけ。辞書には残る）"""
        self.last_error = ''
        if level not in LEVELS:
            return self.fail(f'不明な階層です: {level}')
        items = self.tag_items()
        keep = [it for it in items if not in_table_scope(level, target, it)]
        if len(keep) == len(items):
            return self.fail('外す列がありません')
        self.set_columns(keep)
        logger.info(f"Removed from table: {level} {target}")
        return True

    def remove_from_dictionary(self, level, target):
        """辞書から消し、表からも外す"""
        self.last_error = ''
        try:
            kinds, removed = remove_from_kinds(self.kinds, level, target)
        except ValueError as e:
            return self.fail(str(e))
        self.kinds = kinds
        if 'サムネイル' in self.df.columns:
            self.set_columns([it for it in self.tag_items() if not removed(it)])
        logger.info(f"Removed from dictionary: {level} {target}")
        return True

    def update_cell(self, row_index, column_name, value):
        """セル更新（表にある行・タグ列に bool だけ書く。それ以外を .at に渡すと行や列が勝手に増える）"""
        if column_name in FIXED_COLUMNS or column_name not in self.df.columns:
            return False

        if type(row_index) is not int or row_index not in self.df.index or not isinstance(value, bool):
            return False

        self.df.at[row_index, column_name] = value
        return True

    def caption_of(self, record, keys, items):
        """表の1行の Krea2 用キャプション"""
        return render_caption([item for key, item in zip(keys, items) if to_flag(record[key])])

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

        # 表と辞書（プロジェクト共通）
        write_json(self.data_out_target / TABLE_FILE, table_to_json(self.df))
        write_json(self.data_work_dir / KINDS_FILE, self.kinds)

        # captionsディレクトリ作成
        self.captions_dir.mkdir(exist_ok=True)

        # txtファイル保存（改行は LF。削除済み画像は captions_dead へ）
        keys = tag_keys(self.df)
        items = [parse_key(k) for k in keys]
        for record in self.df.to_dict('records'):
            folder = self.captions_dead_dir if to_flag(record['is_dead']) else self.captions_dir
            txt_path = folder / f"{Path(record['サムネイル']).stem}.txt"
            txt_path.write_text(self.caption_of(record, keys, items), encoding='utf-8', newline='\n')

        logger.info(f"Data saved: {len(self.df)} rows, {len(keys)} columns")

# グローバルインスタンス
caption_tool = CaptionTool()

def target_of(data):
    """API の {big, mid, small, value} を対象のタプルにする"""
    return tuple((data.get(name) or '').strip() for name in LEVELS)

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

@app.route('/get_table_data')
def get_table_data():
    """テーブルデータ取得

    columns: 列ごとの {key, big, mid, small, value}。data: 行ごとの {index, サムネイル, is_dead, <key>: bool}
    サムネイル列は画像ファイル名（URL はフロントで /thumbnail/<名前>, /image/<名前> を組み立てる）
    """
    df = caption_tool.df
    if 'サムネイル' not in df.columns:
        return jsonify({'columns': [], 'data': []})

    keys = tag_keys(df)
    columns = [{'key': k, **dict(zip(LEVELS, parse_key(k)))} for k in keys]
    data = [{'index': int(index), 'サムネイル': r['サムネイル'], 'is_dead': to_flag(r['is_dead']),
             **{k: to_flag(r[k]) for k in keys}}
            for index, r in zip(df.index, df.to_dict('records'))]
    return jsonify({'columns': columns, 'data': data})

@app.route('/thumbnail/<filename>')
def serve_thumbnail(filename):
    """サムネイル画像配信（filename は元画像名。サムネイルが無い小さい画像は元画像）"""
    if not caption_tool.is_known_image(filename):
        return "Image not found", 404

    for path in [caption_tool.thumbnail_file(filename), caption_tool.image_dir / filename]:
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
    """辞書（大kind → 中kind → 小kind → 値）取得"""
    return jsonify({'kinds': caption_tool.kinds})

@app.route('/add_value', methods=['POST'])
def add_value():
    """値の追加API（{big, mid, small, value, default_value}。value が空なら中kind の値を全部付ける）"""
    data = request.get_json() or {}
    success = caption_tool.add_value(data.get('big'), data.get('mid'), data.get('small'), data.get('value'),
                                     data.get('default_value', False))
    return jsonify({'success': success, 'error': caption_tool.last_error})

@app.route('/update_cell', methods=['POST'])
def update_cell():
    """セル更新"""
    data = request.get_json()
    row_index = data.get('row_index')
    column_name = data.get('column_name')
    value = data.get('value')

    success = caption_tool.update_cell(row_index, column_name, value)
    return jsonify({'success': success})

@app.route('/rename', methods=['POST'])
def rename():
    """改名API（{level, big, mid, small, value, new_name}）"""
    data = request.get_json() or {}
    success = caption_tool.rename(data.get('level'), target_of(data), data.get('new_name'))
    return jsonify({'success': success, 'message': caption_tool.last_error})

@app.route('/remove_from_table', methods=['POST'])
def remove_from_table():
    """表から外すAPI（{level, big, mid, small, value}）"""
    data = request.get_json() or {}
    success = caption_tool.remove_from_table(data.get('level'), target_of(data))
    return jsonify({'success': success, 'message': caption_tool.last_error})

@app.route('/remove_from_dictionary', methods=['POST'])
def remove_from_dictionary():
    """辞書から削除API（{level, big, mid, small, value}）"""
    data = request.get_json() or {}
    success = caption_tool.remove_from_dictionary(data.get('level'), target_of(data))
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

if __name__ == '__main__':
    app.run(**server_options(os.environ))
