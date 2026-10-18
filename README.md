# pictag

画像にタグ（キャプション）を付けて管理するためのWebアプリです。  
縦に画像、横にタグを並べたグリッド形式で、タグをその場で追加・編集・保存できます。

## 特徴
- Flaskベースの軽量Webアプリ
- 画像ディレクトリを読み込み、自動でサムネイル生成
- タグ（カラム）を自由に追加・削除・改名
- タグのグループ化（kind）と管理
- 編集内容はローカルディレクトリに保存され、再読み込み可能

## 起動方法
Python 3.12 以降が必要です。

```bash
# 仮想環境を作成（任意）
python -m venv venv
source venv/bin/activate        # Windows (Git Bash) は source venv/Scripts/activate

pip install -r requirements.txt
python app.py
```

uv を使う場合:

```bash
uv venv
uv pip install -r requirements.txt
uv run python app.py
```

ブラウザで [http://127.0.0.1:5000](http://127.0.0.1:5000) を開くと利用できます。  
LAN 内の他の機器から使う場合は `PICTAG_HOST=0.0.0.0 python app.py` で起動します。

## 出力
保存すると、アプリのフォルダ配下に書き出します（`<フォルダ名>` は読み込んだ画像ディレクトリの名前）。

```
data_out/<フォルダ名>/captions/<画像名>.txt       # 学習用キャプション（チェックしたタグをカンマ区切り。拡張子を除いた画像名）
data_out/<フォルダ名>/captions_dead/<画像名>.txt  # 元フォルダから消えた画像のキャプション
data_out/<フォルダ名>/df_isflaged.dump           # 画像×タグの表
data_work/df_captioninfo.dump                    # タグ辞書（全プロジェクト共通）
data_work/<フォルダ名>/                           # サムネイル
```

## テスト
```bash
pip install -r requirements-dev.txt
python -m pytest
```

`tests/e2e/` はブラウザ（インストール済みの Chrome / Edge）で画面を操作するテストです。Bootstrap を CDN から読むため、ネットワーク接続が必要です。ブラウザ以外のテストだけを回すときは `python -m pytest -m "not e2e"`。

## ファイル構成
```
app.py         # Flaskサーバー本体
templates/     # index.htmlなどのUIテンプレート
static/
 └─ control.js # フロントエンド制御スクリプト
tests/         # pytest（e2e/ は Playwright）
```
