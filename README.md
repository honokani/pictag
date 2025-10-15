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
```bash
# 仮想環境を作成（任意）
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

ブラウザで [http://127.0.0.1:5000](http://127.0.0.1:5000) を開くと利用できます。

## ファイル構成
```
app.py         # Flaskサーバー本体
templates/     # index.htmlなどのUIテンプレート
static/
 └─ control.js # フロントエンド制御スクリプト
```
