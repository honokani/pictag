import os
import pickle
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
from PIL import Image

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# data_out / data_work の既定の置き場所（起動ディレクトリに依存させない）
APP_DIR = Path(__file__).resolve().parent

# 画面・API が特別扱いする名前（タグ名・種別名には使えない）
RESERVED_CAPTIONS = {'サムネイル', 'is_dead', 'index', 'new_column'}
RESERVED_KINDS = {'new_kind'}

def to_flag(value):
    """セル値を bool に揃える（欠損や bool 以外は False）"""
    return bool(value) if pd.api.types.is_bool(value) else False

def same_path(a, b):
    """同じディレクトリを指すか（Windows の大文字小文字・区切り文字の違いは無視）"""
    return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))

class CaptionTool:
    def __init__(self, base_dir=None):
        # data_out / data_work の置き場所
        self.base_dir = Path(base_dir) if base_dir is not None else APP_DIR
        self.data_out_dir = self.base_dir / "data_out"
        self.data_work_dir = self.base_dir / "data_work"
        self.image_dir = None
        self.dir_name = None
        self.df = pd.DataFrame()
        self.caption_info_df = pd.DataFrame(columns=['caption', 'kind'])
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
        self.check_registered_path(self.data_out_dir / image_dir.name / "tgt_path.txt", image_dir)

        self.image_dir = image_dir
        self.dir_name = self.image_dir.name

        # data_out構造作成
        self.data_out_target = self.data_out_dir / self.dir_name
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
        # キャプション情報読み込み（プロジェクト共通）
        self.caption_info_df = pd.DataFrame()
        caption_info_path = self.data_work_dir / "df_captioninfo.dump"
        if caption_info_path.exists():
            try:
                with open(caption_info_path, 'rb') as f:
                    self.caption_info_df = pickle.load(f)
                logger.info(f"Loaded caption info: {len(self.caption_info_df)} entries")
            except Exception as e:
                logger.warning(f"Failed to load caption info: {e}")
                self.caption_info_df = pd.DataFrame(columns=['caption', 'kind'])
        else:
            self.caption_info_df = pd.DataFrame(columns=['caption', 'kind'])
        
        # tgt_path.txt作成
        tgt_path_file = self.data_out_target / "tgt_path.txt"
        if not tgt_path_file.exists():
            with open(tgt_path_file, 'w', encoding='utf-8') as f:
                f.write(str(self.image_dir))
            logger.info(f"Created tgt_path.txt: {self.image_dir}")
        
        # Dumpファイル処理
        dump_path = self.data_out_target / "df_isflaged.dump"
        if dump_path.exists():
            try:
                with open(dump_path, 'rb') as f:
                    self.df = pickle.load(f)
                logger.info(f"Loaded dump file: {len(self.df)} rows")
            except Exception as e:
                logger.warning(f"Failed to load dump: {e}")
                self.df = pd.DataFrame()
        else:
            self.df = pd.DataFrame()
        
        # 画像ファイル存在チェックと dead/alive 状態管理
        self.manage_dead_alive_status()
        
        # 既存のDataFrameカラムでキャプション情報に未登録のものをundef種別で登録
        self.sync_existing_columns_to_caption_info()
        
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
        # 画像名ごとの行を1回だけ引いておく。旧版のバグで入った サムネイル=NaN の行は捨てる
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

        # タグ列: 保存済みの表があればその列を保つ（「表から削除」した列を戻さない）
        # 新規プロジェクトはキャプション情報の全タグから始める
        if has_table:
            additional_columns = [col for col in self.df.columns if col not in ['サムネイル', 'is_dead']]
        elif not self.caption_info_df.empty:
            additional_columns = self.caption_info_df['caption'].tolist()
        else:
            additional_columns = []
        additional_columns = list(dict.fromkeys(additional_columns))  # 重複除去（順序は保つ）

        # DataFrameを再構築
        columns = ['サムネイル', 'is_dead'] + additional_columns
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

    def sync_existing_columns_to_caption_info(self):
        """既存のDataFrameカラムをキャプション情報に同期"""
        if self.df.empty:
            return
        
        df_columns = [col for col in self.df.columns if col not in ['サムネイル', 'is_dead']]
        
        for col in df_columns:
            # キャプション情報に存在しない場合はundef種別で追加
            if self.caption_info_df.empty or not (self.caption_info_df['caption'] == col).any():
                new_entry = pd.DataFrame({'caption': [col], 'kind': ['undef']})
                if self.caption_info_df.empty:
                    self.caption_info_df = new_entry
                else:
                    self.caption_info_df = pd.concat([self.caption_info_df, new_entry], ignore_index=True)
                logger.info(f"Added existing column '{col}' as undef kind to caption info")
    
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
    
    def add_column(self, column_name, kind, default_value=False):
        """カラム追加"""
        self.last_error = ''
        try:
            # 文字列のstrip処理
            column_name = column_name.strip()
            kind = kind.strip()

            logger.info(f"add_column called: name='{column_name}', kind='{kind}', default={default_value}")

            # 空白文字チェック
            if not column_name or not kind:
                return self.fail(f"Empty column name or kind: '{column_name}', '{kind}'")

            if self.image_dir is None:
                return self.fail('先にプロジェクトを読み込んでください')

            if column_name in RESERVED_CAPTIONS:
                return self.fail(f'「{column_name}」はカラム名に使えません')
            if kind in RESERVED_KINDS:
                return self.fail(f'「{kind}」は種別名に使えません')

            if column_name in self.df.columns:
                return self.fail(f'カラム「{column_name}」は表に既にあります')

            # キャプション情報に別の種別で登録済みなら追加しない（同じタグが2つの種別に分かれるため）
            registered_kinds = []
            if not self.caption_info_df.empty:
                registered_kinds = self.caption_info_df.loc[self.caption_info_df['caption'] == column_name, 'kind'].tolist()
            if registered_kinds and kind not in registered_kinds:
                return self.fail(f'「{column_name}」は種別「{registered_kinds[0]}」に登録済みです')

            # 表が無い場合の対応（画像0枚のプロジェクトでも既存の列は消さない）
            if 'サムネイル' not in self.df.columns:
                logger.info("DataFrame is empty, creating minimal structure")
                self.df = pd.DataFrame(columns=['サムネイル', 'is_dead'])

            # DataFrameにカラム追加
            logger.info(f"Adding column '{column_name}' to DataFrame")
            self.df[column_name] = to_flag(default_value)
            
            # キャプション情報に追加
            new_entry = pd.DataFrame({'caption': [column_name], 'kind': [kind]})
            if self.caption_info_df.empty:
                self.caption_info_df = new_entry
            else:
                # 既存にない場合のみ追加
                existing_check = ((self.caption_info_df['caption'] == column_name) & 
                                (self.caption_info_df['kind'] == kind)).any()
                if not existing_check:
                    self.caption_info_df = pd.concat([self.caption_info_df, new_entry], ignore_index=True)
            
            logger.info(f"Successfully added column: '{column_name}' (kind: '{kind}')")
            return True
            
        except Exception as e:
            logger.error(f"Error in add_column: {e}")
            return False
    
    def rename_kind(self, old_kind, new_kind):
        """種別名変更"""
        self.last_error = ''
        old_kind = old_kind.strip()
        new_kind = new_kind.strip()

        if not old_kind or not new_kind or old_kind == new_kind:
            return False

        if new_kind in RESERVED_KINDS:
            return self.fail(f'「{new_kind}」は種別名に使えません')

        # キャプション情報の種別名を更新
        self.caption_info_df.loc[self.caption_info_df['kind'] == old_kind, 'kind'] = new_kind
        
        logger.info(f"Renamed kind: '{old_kind}' -> '{new_kind}'")
        return True
    
    def rename_column(self, old_column, new_column, kind):
        """カラム名変更"""
        self.last_error = ''
        old_column = old_column.strip()
        new_column = new_column.strip()

        if not old_column or not new_column:
            return False

        # 同じ名前の場合はTrueを返す（修正箇所）
        if old_column == new_column:
            return True

        if old_column not in self.df.columns:
            return self.fail(f'カラム「{old_column}」は表にありません')

        if new_column in RESERVED_CAPTIONS:
            return self.fail(f'「{new_column}」はカラム名に使えません')

        # 既存のカラムや辞書のタグと同じ名前にはしない（列・タグが重複して表が壊れるため）
        in_caption_info = not self.caption_info_df.empty and (self.caption_info_df['caption'] == new_column).any()
        if new_column in self.df.columns or in_caption_info:
            return self.fail(f'「{new_column}」は既にあります')

        # DataFrameのカラム名変更
        self.df = self.df.rename(columns={old_column: new_column})
        
        # キャプション情報のカラム名を更新
        self.caption_info_df.loc[self.caption_info_df['caption'] == old_column, 'caption'] = new_column
        
        logger.info(f"Renamed column: '{old_column}' -> '{new_column}'")
        return True
    
    def remove_column_from_table(self, column_name):
        """テーブルからカラム削除（キャプション情報は保持）"""
        if column_name not in self.df.columns or column_name in ['サムネイル', 'is_dead']:
            return False
        
        self.df = self.df.drop(columns=[column_name])
        logger.info(f"Removed column from table: {column_name}")
        return True
    
    def remove_column_completely(self, column_name):
        """テーブルとキャプション情報からカラム完全削除"""
        if column_name in ['サムネイル', 'is_dead']:
            return False
        
        # テーブルから削除（存在する場合のみ）
        if not self.df.empty and column_name in self.df.columns:
            self.df = self.df.drop(columns=[column_name])
            logger.info(f"Removed column from table: {column_name}")
        
        # キャプション情報から削除
        if not self.caption_info_df.empty and (self.caption_info_df['caption'] == column_name).any():
            self.caption_info_df = self.caption_info_df[self.caption_info_df['caption'] != column_name]
            logger.info(f"Removed column from caption info: {column_name}")
            return True
        else:
            logger.warning(f"Column '{column_name}' not found in caption info")
            return False
    
    def update_cell(self, row_index, column_name, value):
        """セル更新（表にある行・タグ列に bool だけ書く。それ以外を .at に渡すと行や列が勝手に増える）"""
        if column_name in ['サムネイル', 'is_dead'] or column_name not in self.df.columns:
            return False

        if type(row_index) is not int or row_index not in self.df.index or not isinstance(value, bool):
            return False

        self.df.at[row_index, column_name] = value
        return True
    
    def get_kinds(self):
        """種別一覧取得"""
        if self.caption_info_df.empty:
            return ['new_kind', 'undef']
        
        kinds = ['new_kind'] + sorted(self.caption_info_df['kind'].drop_duplicates().tolist())
        return kinds
    
    def get_captions_by_kind(self, kind):
        """指定種別のキャプション一覧取得"""
        if self.caption_info_df.empty or kind == 'new_kind':
            return ['new_column']
        
        captions = self.caption_info_df[self.caption_info_df['kind'] == kind]['caption'].drop_duplicates().tolist()
        return ['new_column'] + sorted(captions)
    
    def get_columns_by_kind(self):
        """種別ごとにグループ化されたカラム情報取得"""
        if self.df.empty:
            return {}
        
        columns_info = {}
        df_columns = [col for col in self.df.columns if col not in ['サムネイル', 'is_dead']]
        
        for col in df_columns:
            # キャプション情報から種別取得
            kind_row = self.caption_info_df[self.caption_info_df['caption'] == col]
            if not kind_row.empty:
                kind = kind_row.iloc[0]['kind']
            else:
                kind = 'undef'
            
            if kind not in columns_info:
                columns_info[kind] = []
            columns_info[kind].append(col)
        
        return columns_info
    
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

        # Dump保存
        dump_path = self.data_out_target / "df_isflaged.dump"
        with open(dump_path, 'wb') as f:
            pickle.dump(self.df, f)
        
        # キャプション情報保存（プロジェクト共通）
        caption_info_path = self.data_work_dir / "df_captioninfo.dump"
        with open(caption_info_path, 'wb') as f:
            pickle.dump(self.caption_info_df, f)
        
        # captionsディレクトリ作成
        captions_dir = self.data_out_target / "captions"
        captions_dir.mkdir(exist_ok=True)
        
        # txtファイル保存
        for index, row in self.df.iterrows():
            image_name = row['サムネイル']
            is_dead = row.get('is_dead', False)
            image_stem = Path(image_name).stem
            
            # 保存先ディレクトリを決定
            if is_dead:
                txt_path = self.captions_dead_dir / f"{image_stem}.txt"
            else:
                txt_path = self.captions_dir / f"{image_stem}.txt"
            
            # Trueのカラム名を取得（空白文字を除外、is_deadは除外）
            true_tags = []
            for col in self.df.columns:
                if col not in ['サムネイル', 'is_dead'] and to_flag(row[col]):
                    stripped_col = col.strip()
                    if stripped_col:
                        true_tags.append(stripped_col)
            
            # txtファイル書き出し
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(','.join(true_tags))
        
        logger.info(f"Data saved: {len(self.df)} rows, caption info: {len(self.caption_info_df)} entries")

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

@app.route('/get_table_data')
def get_table_data():
    """テーブルデータ取得"""
    if caption_tool.df.empty:
        return jsonify({'columns': [], 'data': []})
    
    # サムネイル列は画像ファイル名（URL はフロントで /thumbnail/<名前>, /image/<名前> を組み立てる）
    table_data = []
    for index, row in caption_tool.df.iterrows():
        row_data = {'index': index}
        for col in caption_tool.df.columns:
            row_data[col] = row[col]
        table_data.append(row_data)
    
    return jsonify({
        'columns': caption_tool.df.columns.tolist(),
        'data': table_data
    })

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

@app.route('/get_kinds')
def get_kinds():
    """種別一覧取得"""
    try:
        if hasattr(caption_tool, 'caption_info_df') and not caption_tool.caption_info_df.empty:
            kinds = caption_tool.get_kinds()
        else:
            kinds = ['new_kind', 'undef']
        
        return jsonify({'kinds': kinds})
    except Exception as e:
        logger.error(f"Error in get_kinds: {e}")
        return jsonify({'kinds': ['new_kind', 'undef']})

@app.route('/get_captions_by_kind')
@app.route('/get_captions_by_kind/<path:kind>')
def get_captions_by_kind(kind=None):
    """指定種別のキャプション一覧取得（種別は ?kind= でも指定できる。/ や ? を含む種別名用）"""
    if kind is None:
        kind = request.args.get('kind', '')
    try:
        if hasattr(caption_tool, 'caption_info_df') and not caption_tool.caption_info_df.empty:
            captions = caption_tool.get_captions_by_kind(kind)
        else:
            captions = ['new_column']
        
        return jsonify({'captions': captions})
    except Exception as e:
        logger.error(f"Error in get_captions_by_kind: {e}")
        return jsonify({'captions': ['new_column']})

@app.route('/get_table_captions_by_kind')
@app.route('/get_table_captions_by_kind/<path:kind>')
def get_table_captions_by_kind(kind=None):
    """指定種別のテーブル内カラム一覧取得（種別は ?kind= でも指定できる）"""
    if kind is None:
        kind = request.args.get('kind', '')
    try:
        if hasattr(caption_tool, 'df') and not caption_tool.df.empty:
            table_columns = [col for col in caption_tool.df.columns if col != 'サムネイル']
            
            if hasattr(caption_tool, 'caption_info_df') and not caption_tool.caption_info_df.empty:
                kind_captions = caption_tool.caption_info_df[
                    (caption_tool.caption_info_df['kind'] == kind) & 
                    (caption_tool.caption_info_df['caption'].isin(table_columns))
                ]['caption'].drop_duplicates().tolist()
                
                captions = ['new_column'] + sorted(kind_captions)
            else:
                captions = ['new_column']
        else:
            captions = ['new_column']
        
        return jsonify({'captions': captions})
    except Exception as e:
        logger.error(f"Error in get_table_captions_by_kind: {e}")
        return jsonify({'captions': ['new_column']})

@app.route('/get_columns_by_kind')
def get_columns_by_kind():
    """種別ごとのカラム情報取得"""
    try:
        if hasattr(caption_tool, 'df') and not caption_tool.df.empty:
            columns_by_kind = caption_tool.get_columns_by_kind()
        else:
            columns_by_kind = {}
        
        return jsonify({'columns_by_kind': columns_by_kind})
    except Exception as e:
        logger.error(f"Error in get_columns_by_kind: {e}")
        return jsonify({'columns_by_kind': {}})

@app.route('/add_column', methods=['POST'])
def add_column():
    """カラム追加API"""
    try:
        data = request.get_json()
        column_name = data.get('column_name')
        kind = data.get('kind')
        default_value = data.get('default_value', False)
        
        logger.info(f"API: add_column called with name='{column_name}', kind='{kind}', default={default_value}")
        
        result = caption_tool.add_column(column_name, kind, default_value)

        logger.info(f"API: add_column result={result}")
        if not result:
            return jsonify({'success': False, 'error': caption_tool.last_error})
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"API: Error in add_column: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update_cell', methods=['POST'])
def update_cell():
    """セル更新"""
    data = request.get_json()
    row_index = data.get('row_index')
    column_name = data.get('column_name')
    value = data.get('value')
    
    success = caption_tool.update_cell(row_index, column_name, value)
    return jsonify({'success': success})

@app.route('/rename_kind', methods=['POST'])
def rename_kind():
    """種別名変更API"""
    data = request.get_json()
    old_kind = data.get('old_kind')
    new_kind = data.get('new_kind')
    
    success = caption_tool.rename_kind(old_kind, new_kind)
    return jsonify({'success': success, 'message': caption_tool.last_error})

@app.route('/rename_column', methods=['POST'])
def rename_column():
    """カラム名変更API"""
    data = request.get_json()
    old_column = data.get('old_column')
    new_column = data.get('new_column')
    kind = data.get('kind')
    
    success = caption_tool.rename_column(old_column, new_column, kind)
    return jsonify({'success': success, 'message': caption_tool.last_error})

@app.route('/rename_both', methods=['POST'])
def rename_both():
    """種別名とカラム名の両方変更API"""
    data = request.get_json()
    old_kind = data.get('old_kind')
    new_kind = data.get('new_kind')
    old_column = data.get('old_column')
    new_column = data.get('new_column')

    # 種別名を先に検証（カラム名だけ変わって種別が変わらない、を防ぐ）
    new_kind = (new_kind or '').strip()
    if not new_kind or new_kind in RESERVED_KINDS:
        return jsonify({'success': False, 'message': f'「{new_kind}」は種別名に使えません'})

    # カラム名変更（同じ名前でも成功するように修正済み）
    column_success = caption_tool.rename_column(old_column, new_column, old_kind)
    if not column_success:
        return jsonify({'success': False, 'message': caption_tool.last_error})
    new_column = new_column.strip()
    
    # 特定のカラムの種別のみ変更（修正箇所）
    if old_kind != new_kind:
        # 該当するカラムの種別のみを変更
        mask = (caption_tool.caption_info_df['caption'] == new_column) & (caption_tool.caption_info_df['kind'] == old_kind)
        caption_tool.caption_info_df.loc[mask, 'kind'] = new_kind
        logger.info(f"Changed kind for column '{new_column}': '{old_kind}' -> '{new_kind}'")
    
    return jsonify({'success': True})

@app.route('/remove_column_from_table', methods=['POST'])
def remove_column_from_table():
    """テーブルからカラム削除API"""
    data = request.get_json()
    column_name = data.get('column_name')
    
    success = caption_tool.remove_column_from_table(column_name)
    return jsonify({'success': success})

@app.route('/remove_column_completely', methods=['POST'])
def remove_column_completely():
    """カラム完全削除API"""
    data = request.get_json()
    column_name = data.get('column_name')
    
    success = caption_tool.remove_column_completely(column_name)
    return jsonify({'success': success})

@app.route('/remove_all_dead', methods=['POST'])
def remove_all_dead():
    """削除済み画像に対応するdumpデータを完全に削除"""
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
            'message': f'{dead_count}件の削除済み画像のdumpデータを削除しました',
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