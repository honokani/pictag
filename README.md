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
[uv](https://docs.astral.sh/uv/) を使います（Python 3.12 以降。手元に無ければ uv が用意します）。

```bash
uv sync                 # 依存を入れる（初回と、依存が変わったとき）
uv run python app.py
```

ブラウザで [http://127.0.0.1:5000](http://127.0.0.1:5000) を開くと利用できます。  
LAN 内の他の機器から使う場合は `PICTAG_HOST=0.0.0.0 uv run python app.py` で起動します。

## 出力
保存すると、アプリのフォルダ配下に書き出します（`<フォルダ名>` は読み込んだ画像ディレクトリの名前）。

```
data_out/<フォルダ名>/captions/<画像名>.txt       # 学習用キャプション（拡張子を除いた画像名。改行は LF）
data_out/<フォルダ名>/captions_dead/<画像名>.txt  # 元フォルダから消えた画像のキャプション
data_out/<フォルダ名>/table.json                  # 画像 × 列（大kind・中kind・小kind・値）のチェック
data_out/<フォルダ名>/tgt_path.txt                # 画像ディレクトリの絶対パス
data_work/kinds.json                             # 辞書（全プロジェクト共通）
data_work/<フォルダ名>/                           # サムネイル
```

キャプションは Krea 2 向けの構造化テキストです。大kind ごとに段落を分け、小kind の値はまとめて書き出します（hair の long と black → `long black hair`）。

```
girl:
  - looks: full body shot, standing
  - body: long black hair, bare hands
```

SDXL 版のプロジェクト（`df_isflaged.dump` があるフォルダ）は開けません。SDXL 版は `sdxl` ブランチにあります。

## テスト
```bash
uv run pytest                 # すべて
uv run pytest -m "not e2e"    # ブラウザを使うテストを除く
```

`tests/e2e/` はブラウザ（インストール済みの Chrome / Edge）で画面を操作するテストです。Bootstrap を CDN から読むため、ネットワーク接続が必要です。

## ファイル構成
```
app.py         # Flaskサーバー本体
templates/     # index.htmlなどのUIテンプレート
static/
 └─ control.js # フロントエンド制御スクリプト
tests/         # pytest（e2e/ は Playwright）
```
