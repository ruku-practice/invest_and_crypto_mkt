# 一般＆暗号通貨マーケット情報

Googleスプレッドシート由来の「一般＆暗号通貨マーケット情報」をWeb化するプロジェクト。

## 現在の構成

- `index.html`: 統合ダッシュボード
- `advanced.html`: 旧高機能版の仮ページ（現在はトップ画面へ統合方針）
- `scripts/fetch_market_data.py`: Web側で `data/latest.json` と `data/history.json` を生成
- `scripts/fetch_market_news.py`: Kabutan / CoinPost 由来の市況ニュースを `data/news/latest.json` に保存
- `data/latest.json`: Web表示用の最新データ
- `data/history.json`: 2026年1月1日基準の推移グラフ用データ
- `spec.md`: 仕様と確認事項

トップページでは、表示日を切り替えて各指標の価格と2026年1月1日比を確認できる。グラフは `data/history.json` を使った「2026年1月1日からの増減比較推移」で、全期間 / 90日 / 30日 / 7日に加えて 2026/1/1・2025/1/1・2024/1/1 の開始日プリセットとカスタム範囲に対応する。

## ローカル生成

```bash
python3 scripts/fetch_market_data.py
python3 scripts/fetch_market_news.py
```

## ローカル表示

```bash
python3 -m http.server 8000
```

ブラウザで `http://localhost:8000/` を開く。

## 次の実装

1. `history.json` の前日比再計算をWeb側で継続する
2. `GitHub Actions` で毎朝 6:00 / 6:10 JST 更新を回す

## GitHub Actions

- `.github/workflows/daily.yml` は毎日 06:00 JST にマーケットデータを更新する。
- `.github/workflows/news.yml` は毎日 06:10 JST にニュースを更新する。

GitHubリポジトリ作成後、このままActionsを有効化すれば、Web側の取得結果を自動コミットできる。
