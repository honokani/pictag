# pictag

画像ごとのキャプションを書いて、Krea 2 の LoRA 学習用の txt に書き出すローカル Web アプリです。  
縦に画像、横に段落（picture / action / girl など）を並べた表で、段落ごとの入力欄に辞書の語句を引き出しながら書きます。

## 主な特徴
- 段落ごとの確定タグ（looks / clothes / body など）を空の欄にも出し、characters（1 girl + 1 guy など）は自動で作る
- 入力欄で、辞書からあいまい検索の候補（語句・単語）を出す。共用辞書と「1つだけ」のグループを管理できる
- 複数行への一括入力と、作業用のマーク（A〜D・★●▲■）での絞り込み
- view のボタン（🎥 向き・高さ・ショットの大きさ、👀 POV）
- 右端の列に hint（画像と同じ名前の .txt）か、書き出す文面の preview を出す
- 行ごとのトークン数と上限（507）
- qwen 版（`--qwen`）では、Qwen（ComfyUI）に空の欄を下書きさせられる

画面の操作と細かい動きは [docs/usage.md](docs/usage.md) にあります。

## 起動方法
[uv](https://docs.astral.sh/uv/) を使います（Python 3.12 以降。手元に無ければ uv が用意します）。

```bash
uv sync                 # 依存を入れる（初回と、依存が変わったとき）
uv run python app.py
```

ブラウザで [http://127.0.0.1:5000](http://127.0.0.1:5000) を開くと利用できます。  
LAN 内の他の機器から使う場合は `PICTAG_HOST=0.0.0.0 uv run python app.py` で起動します。  
qwen 版は `uv run python app.py --qwen` で起動します（ComfyUI を先に起動しておく。詳しくは [docs/usage.md](docs/usage.md#qwen-版qwen-で下書き)）。

初回の起動時に、トークン数を数えるトークナイザー（約 7MB）を Hugging Face から取得します。取得できないときはトークン数が「—」になり、ほかの機能はそのまま使えます。

## 出力
保存すると、アプリのフォルダ配下に書き出します（`<フォルダ名>` は読み込んだ画像ディレクトリの名前）。

```
data_out/<フォルダ名>/captions/<画像名>.caption   # 学習用キャプション（拡張子を除いた画像名 + .caption。改行は LF）
data_out/<フォルダ名>/captions_dead/<画像名>.caption  # 元フォルダから消えた画像のキャプション
data_out/<フォルダ名>/table.json                  # 画像 × 段落の入力
data_out/<フォルダ名>/tgt_path.txt                # 画像ディレクトリの絶対パス
data_work/<フォルダ名>/                           # サムネイル
data_work/<フォルダ名>/qwen/<画像名>.txt           # Qwen の答え（qwen 版の 🤖。右端の列の hint_by_qwen で見る）
data_work/<フォルダ名>/qwen/<画像名>.json          # Qwen が欄に入れたもの（押し直したときに置き換える下書き）
data_work/shared.json                            # 共用辞書（語句・単語、確定タグ、1つだけのグループ。全プロジェクト共通）
data_work/tokenizer/qwen3vl_tokenizer.json        # トークン数を数えるトークナイザー
```

キャプションは Krea 2 向けの構造化テキストです。段落ごとにまとめ、空の段落は出しません。キー付きの行では、末尾の語が同じ語句をまとめます（`long hair, black hair` → `long black hair`）。

```
girl:
  - looks: full body shot, standing
  - body: long black hair, bare hands
```

トークンの上限 507 は、musubi-tuner と Krea 公式の実装でキャプションに使える長さです。超えた分は末尾から黙って切られます。

SDXL 版のプロジェクト（`df_isflaged.dump` があるフォルダ）は開けません。SDXL 版は `sdxl` ブランチにあります。

## テスト
```bash
uv run pytest                 # すべて
uv run pytest -m "not e2e"    # ブラウザを使うテストを除く
```

`tests/e2e/` は、ブラウザ（インストール済みの Chrome / Edge）で画面を操作するテストです。

## ファイル構成
```
app.py             # Flask サーバー本体（表・保存・API）
caption_format.py  # 段落の入力 → キャプション
words.py           # 使用中の語句（辞書）、共用辞書の登録・削除・改名、一括入力の足し引き
groups.py          # 「1つだけ」のグループ
subjects.py        # 人物などの段落の自動命名、characters、view の選択肢
marks.py           # マーキング
tokens.py          # トークン数（Qwen3-VL のトークナイザー）
qwen.py            # qwen 版の 🤖: Qwen（ComfyUI の TextGenerate）に送る文面、答えの分け方、空の欄への入れ方
templates/         # index.html
static/            # control.js（画面制御）、dictionary.js（共用辞書の画面）、style.css
docs/usage.md      # 画面の操作と細かい動き
tests/             # pytest（e2e/ は Playwright。scenes.py は映画の有名なシーンの入力例）
```
