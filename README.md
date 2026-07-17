# 一般＆暗号通貨マーケット情報

Googleスプレッドシート由来の「一般＆暗号通貨マーケット情報」をWeb化するプロジェクト。

## コンセプト

株価指数・為替・暗号資産の最新値、前日比、年初来推移を一画面で確認できる静的ダッシュボード。外部データをPythonで取得してJSONへ保存し、GitHub Pages上のJavaScriptが表示する。

## 現在の構成

- `index.html`: 統合ダッシュボード
- `advanced.html`: 旧高機能版の仮ページ（現在はトップ画面へ統合方針）
- `scripts/fetch_market_data.py`: Web側で `data/latest.json` と `data/history.json` を生成
- `scripts/fetch_market_news.py`: Kabutan / CoinPost 由来の市況ニュースを `data/news/latest.json` に保存
- `data/latest.json`: Web表示用の最新データ
- `data/history.json`: 2026年1月1日基準の推移グラフ用データ
- 詳細仕様: [[ruku_data/00_products/invest_and_crypto_mkt/spec.md|仕様書]]
- 作業状況: [[ruku_data/00_products/invest_and_crypto_mkt/progress.md|進捗ログ]]

トップページでは、表示日を切り替えて各指標の価格と2026年1月1日比を確認できる。グラフは `data/history.json` を使った「2026年1月1日からの増減比較推移」で、全期間 / 90日 / 30日 / 7日に加えて 2026/1/1・2025/1/1・2024/1/1 の開始日プリセットとカスタム範囲に対応する。

### 市場データの日付ルール

yfinanceの最新終値は、スクリプト実行日ではなく実際の最終取引日へ記録する。休日や日本時間早朝の実行時に、同じ終値を異なる日付へ複製して前日比を0%にしないためのルールである。暗号資産など24時間取引のデータは取得日へ記録する。

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

## スケジュール・タイムライン

定期実行は Cloud Scheduler → Cloud Run Job 方式（CNP TIMES / FiNANCiE TIMES と同じ構成）。
GitHub Actions の `schedule` は発火が不安定だったため廃止した。

- GCPプロジェクト: `writeinfo2spreadsheet` / リージョン `asia-northeast1`
- Cloud Run Job `invest-daily`（`JOB_MODE=data`）… 市場データ更新
- Cloud Run Job `invest-news`（`JOB_MODE=news`）… 市況ニュース更新
- Cloud Scheduler `invest-daily-trigger`（毎日 06:00 JST）→ invest-daily 実行
- Cloud Scheduler `invest-news-trigger`（毎日 06:10 JST）→ invest-news 実行
- 各Jobは `deploy/cloudrun/`（Dockerfile / run.sh）から作られ、起動時にリポジトリを clone → 取得スクリプト実行 → `data/` の差分を main へ push する。
- push用トークンは Secret Manager の `gh-token` を参照。

### イメージ再ビルド（スクリプト依存を変えたとき）

```bash
gcloud run jobs deploy invest-daily \
  --source deploy/cloudrun --region asia-northeast1 \
  --project writeinfo2spreadsheet \
  --service-account 289412336991-compute@developer.gserviceaccount.com \
  --set-secrets GH_TOKEN=gh-token:latest --set-env-vars JOB_MODE=data \
  --tasks 1 --max-retries 1 --task-timeout 1800 --memory 2Gi --cpu 2
# invest-news は同じイメージを --image 指定で参照（JOB_MODE=news）
```

### 手動実行

```bash
gcloud run jobs execute invest-daily --region asia-northeast1 --project writeinfo2spreadsheet
gcloud run jobs execute invest-news  --region asia-northeast1 --project writeinfo2spreadsheet
```

## GitHub Actions（手動フォールバック）

- `.github/workflows/daily.yml` / `news.yml` は `schedule` を廃止し、`workflow_dispatch`（手動）と `repository_dispatch` のみ。Cloud Run が使えないときの緊急用。

## Python環境構築（ローカル）

本番（Cloud Run Job）は `python:3.12-slim`。ローカルで動かす場合は venv を推奨：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install  # スクレイピングにplaywrightを使う場合
```

※2026-07-12 開発部によるPython環境統一調査で追記（非破壊）。requirements.txtの中身は既存のまま（バージョン未固定）。

## 参考リンク・素材

- 公開サイト: https://ruku-practice.github.io/invest_and_crypto_mkt/
