# TODO

## Phase 2

- `getMarketInfo.py` を `scripts/fetch_market_data.py` に移植する。
- スプレッドシート書き込みは当面併用しつつ、Web用JSONを主成果物にする。
- `history.json` を作成し、前日比をWeb側で再計算する。
- 現行 `stats` シート履歴を移行する。
- Google Driveフォルダの2024年・2025年データを統合する。

## Phase 3

- `getArticleFromKabutan.py` を `scripts/fetch_market_news.py` に移植する。
- Selenium依存をPlaywrightへ寄せる。
- 暗号通貨ニュースを複数ソースから取得する。
- トップページにニュースリンクと投稿文候補を表示する。

## Phase 4

- `advanced.html` に時系列チャートを実装する。
- 高機能版に `BNB` と、取得が有効なら `Ninja` を追加する。
- GitHubリポジトリ作成、GitHub Pages公開、Secrets設定を行う。
