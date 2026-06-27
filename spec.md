# Invest & Crypto Market Web 仕様案

## 目的

Googleスプレッドシートで運用している「一般＆暗号通貨マーケット情報」を、`cnp-times` や `FiNANCiE-times-web` と同じようにWebサイト化する。

最終的には、スプレッドシートを表示用の中間成果物として使わず、データ取得・集計・JSON生成・Web表示をこのリポジトリ側に寄せる。

## 作業場所

`/Users/kurokzhr/.hermes/ruku_data/00_products/invest_and_crypto_mkt`

元スクリプトは参照のみとし、直接編集しない。移植・改修する場合はこのフォルダ配下へコピーして作業する。

## 参照した既存実装

- `cnp-times`
  - 静的HTML/CSS/JS
  - Pythonで外部データ取得
  - JSONを生成してWeb側はJSONを読む
  - GitHub Actionsで定期実行し、GitHub Pagesへ反映
- `FiNANCiE-times-web`
  - `scripts/` でスプレッドシートや履歴JSONからWeb用JSONを生成
  - `data/` にランキング・履歴・詳細JSONを配置
  - クラシック版と高機能版を分ける

今回も同じ方針で、まずは静的サイト + JSONデータ + 定期ビルドを基本構成にする。

## 対象スプレッドシート

URL:

`https://docs.google.com/spreadsheets/d/1hE1h47W1Ev2vCpuCQwaXU2cUivKfmiUymP8RCNG6CkY/edit?gid=0#gid=0`

`gid=0` の公開CSVで確認できた表示内容:

- タイトル: 一般＆暗号通貨マーケット情報
- データ取得日: 例 `2026/06/27`
- データ取得時刻: 例 `6:02`
- 表示項目:
  - 日経225
  - NYダウ
  - S&P500
  - NYSE FANG+
  - ドル円
  - BTC
  - ETH
  - SOL
  - GCHO
  - 1億BONSAI
- 各項目の主な表示値:
  - 終値または現在値
  - 前日比

## 関連スクリプト

### `getMarketInfo.py`

場所:

`/Users/kurokzhr/Library/CloudStorage/GoogleDrive-ruku.practice@gmail.com/マイドライブ/00_XXX_TIMES/00_CreateAutoTimes/getMarketInfo.py`

現状の役割:

- 市場価格を取得する
- Googleスプレッドシート `1hE1h47W1Ev2vCpuCQwaXU2cUivKfmiUymP8RCNG6CkY` の `stats` シートへ列追加で追記する

取得している主なデータ:

- `yfinance`
  - S&P500: `^GSPC`
  - 日経225: `^N225`
  - NYダウ: `^DJI`
  - NYSE FANG+: `^NYFANG`
  - ドル円: `USDJPY=X`
- CoinGecko API
  - ETH
  - BTC
  - BNB
  - SOL
- GeckoTerminalスクレイピング
  - Ninja
  - BonsaiCoin
- JupiterページのPlaywrightスクレイピング
  - GCHO
- Google Sheets
  - `stats` シートへ `[列番号, 日付, 時刻, 各種価格]` を縦方向に追記

現状の注意点:

- サービスアカウントJSONのパスがローカル前提になっている
- GCHOなど一部取得はブラウザスクレイピング依存
- 取得失敗時に `0` を入れる挙動があるため、Web化時は「本当に0」か「取得失敗」かを分けたい
- `API_KEY = 'A5J1PUIHJR8ZGETX'` がコード内にあるが、現状参照用途は未確認

### `getArticleFromKabutan.py`

場所:

`/Users/kurokzhr/Library/CloudStorage/GoogleDrive-ruku.practice@gmail.com/マイドライブ/00_XXX_TIMES/00_CreateAutoTimes/getArticleFromKabutan.py`

現状の役割:

- 株探とCoinPostから市況記事を取得する
- 投稿文風のテキストを作る
- 別スプレッドシート `1MNQuV9PODKDm9gqEddL3q7keBC92LkV5ZOYEPNa0ijY` の `09_General` シート `B2` へ書き込む

取得している主なニュース:

- 株探 市況カテゴリ
  - 日経平均 大引け
  - ダウ平均
- 株探 為替カテゴリ
  - NY為替
  - NY外為
- CoinPost 市況・解説
  - ビットコイン
  - イーサリアム

現状の注意点:

- Selenium + ローカルChromeDriver前提
- Chrome for Testingをホームディレクトリへダウンロードする処理がある
- Web化時はPlaywrightへ寄せた方が、既存プロダクトやGitHub Actionsと合わせやすい
- 記事は現在スプレッドシートにテキストだけを書いているが、Web側ではタイトル・URL・日付・ソースをJSONで持つ方が扱いやすい

## Web化の基本方針

### フェーズ1: スプレッドシート表示のWeb化

目的:

既存スプレッドシートの見た目・情報量を保ったまま、Webで閲覧できるようにする。

実装方針:

- `index.html` をクラシック版として作る
- `data/latest.json` を読み込んで表示する
- 初期はGoogle Sheetsの `gid=0` から表示データを取得してJSON化してもよい
- `getMarketInfo.py` の取得処理を移植する前に、Web表示の仕様を固定する

表示案:

- ヘッダー
  - サイト名: `INVEST & CRYPTO MKT`
  - サブタイトル: `一般＆暗号通貨マーケット情報`
  - データ取得日時
- 市場インデックス
  - 日経225
  - NYダウ
  - S&P500
  - NYSE FANG+
  - ドル円
- 暗号資産
  - BTC
  - ETH
  - SOL
  - GCHO
  - 1億BONSAI
- 市況ニュース
  - 日経平均
  - 海外
  - ドル円
  - クリプト

### フェーズ2: 集計をWebリポジトリ側へ移植

目的:

スプレッドシートの計算・表示依存を減らし、Web側のJSON生成スクリプトで集計を完結させる。

実装方針:

- `scripts/fetch_market_data.py`
  - 外部API・スクレイピングから最新価格を取得
  - 生データを `data/raw/YYYY-MM-DD_HHMM.json` へ保存
- `scripts/fetch_market_news.py`
  - 株探・CoinPostから記事を取得
  - `data/news/latest.json` と履歴を保存
- `scripts/build_site_data.py`
  - 生データと履歴からWeb表示用JSONを生成
  - 前日比・前回比・ランキング・チャート用データを生成
- `data/latest.json`
  - トップページ表示用
- `data/history.json`
  - 時系列グラフ用
- `data/news/latest.json`
  - 市況ニュース表示用

### フェーズ3: 高機能版

目的:

スプレッドシートでは見づらい推移・比較・過去データをWebで見られるようにする。

ページ案:

- `advanced.html`
  - 指標ごとの時系列チャート
  - 指標の表示/非表示切り替え
  - 期間切り替え: 7日 / 30日 / 90日 / 1年 / 全期間
  - 前日比・前週比・前月比
  - 取得失敗・欠損値の可視化
- `news.html`
  - 市況ニュース履歴
  - ソース別フィルタ
  - 投稿文候補の表示

## 想定ディレクトリ構成

```text
invest_and_crypto_mkt/
  README.md
  spec.md
  index.html
  advanced.html
  news.html
  css/
    style.css
    advanced.css
  js/
    app.js
    advanced.js
    news.js
  data/
    latest.json
    history.json
    raw/
    news/
      latest.json
      history.json
  scripts/
    fetch_market_data.py
    fetch_market_news.py
    build_site_data.py
    migrate_sheet_history.py
  requirements.txt
  .github/
    workflows/
      daily.yml
```

## JSON仕様案

### `data/latest.json`

```json
{
  "generated_at": "2026-06-27T06:02:00+09:00",
  "source": "web-fetch",
  "markets": [
    {
      "id": "nikkei225",
      "name": "日経225",
      "category": "index",
      "price": 69360.8828125,
      "display_price": "¥69,361",
      "change_rate": -4.15,
      "display_change_rate": "-4.15%",
      "currency": "JPY",
      "status": "ok"
    }
  ],
  "crypto": [
    {
      "id": "btc",
      "name": "BTC",
      "category": "crypto",
      "price": 9645010,
      "display_price": "¥9,645,010",
      "change_rate": 0.41,
      "display_change_rate": "+0.41%",
      "currency": "JPY",
      "status": "ok"
    }
  ],
  "news": {
    "nikkei": null,
    "overseas": null,
    "fx": null,
    "crypto": null
  }
}
```

### `data/history.json`

```json
{
  "items": {
    "nikkei225": {
      "name": "日経225",
      "currency": "JPY",
      "points": [
        {
          "datetime": "2026-06-27T06:02:00+09:00",
          "price": 69360.8828125,
          "change_rate": -4.15,
          "status": "ok"
        }
      ]
    }
  }
}
```

### `data/news/latest.json`

```json
{
  "generated_at": "2026-06-27T06:02:00+09:00",
  "items": [
    {
      "category": "nikkei",
      "source": "kabutan",
      "title": "日経平均 大引け...",
      "url": "https://kabutan.jp/...",
      "published_at": "2026-06-26",
      "summary_for_post": "..."
    }
  ],
  "post_text": "・日経平均：...\n・海外：...\n・ドル円：...\n・クリプト：..."
}
```

## データ取得・集計仕様案

### 価格取得

優先方針:

- 可能なものはAPIを優先
- HTMLスクレイピングは最後の手段
- 取得失敗時は `0` ではなく `null` と `status: "error"` を保存
- 表示用には最後に成功した値をフォールバック表示できるようにする

対象:

| ID | 表示名 | 現行取得元 | Web側方針 |
| --- | --- | --- | --- |
| `nikkei225` | 日経225 | yfinance `^N225` | 継続 |
| `dow` | NYダウ | yfinance `^DJI` | 継続 |
| `sp500` | S&P500 | yfinance `^GSPC` | 継続 |
| `fang` | NYSE FANG+ | yfinance `^NYFANG` | 継続 |
| `usdjpy` | ドル円 | yfinance `USDJPY=X` | 継続 |
| `btc` | BTC | CoinGecko | 継続 |
| `eth` | ETH | CoinGecko | 継続 |
| `sol` | SOL | CoinGecko | 継続 |
| `gcho` | GCHO | Jupiter Playwright | 要検討 |
| `bonsai_100m` | 1億BONSAI | GeckoTerminal | 要検討 |

### 前日比

現行スプレッドシートでは表示済みの前日比があるが、Web側集計では以下のどちらかに寄せる。

- 案A: 取得元APIの前日比を使う
- 案B: `history.json` の前日同時刻または前営業日終値からWeb側で算出する

推奨は案B。理由は、取得元ごとに前日比の基準がずれる問題を抑えやすいため。

### ニュース取得

現行:

- 株探から日経平均・ダウ平均・NY為替/NY外為を取得
- CoinPostからBTC/ETH系の記事を取得
- 火曜から土曜のみ投稿文をスプレッドシートへ書き込み

Web側:

- 記事データは毎日保存
- 投稿文を出す/出さないの曜日ルールは `post_text` 生成時に適用
- URL・ソース・日付はWeb上で確認できるように保持

## 自動更新仕様案

GitHub Actionsで定期実行する。

候補:

- 朝更新: JST 6:10
- 昼更新: JST 12:10
- 夕方更新: JST 18:10
- 夜更新: JST 23:10

ただし、日経・米国市場・暗号資産で更新タイミングが違うため、最初は1日1回から始める方が安全。

ワークフロー案:

1. Python依存関係をインストール
2. Playwrightブラウザをインストール
3. 06:00 JST に `scripts/fetch_market_data.py` を実行
4. 06:10 JST に `scripts/fetch_market_news.py` を実行
5. `data/` に差分があればコミット
6. GitHub Pagesへ反映

## UI仕様案

### トップページ

方向性:

- `cnp-times` の新聞風に近い、一覧性重視のマーケット紙面
- 投資・暗号資産向けなので、過度な装飾よりも数値の読みやすさを優先

必要な状態:

- 読み込み中
- 取得成功
- 一部取得失敗
- 全体取得失敗
- 最終更新から時間が経っている場合の警告

### 高機能版

必要な機能:

- 指標別チャート
- 期間切り替え
- 表示指標の選択
- 前日比ランキング
- 暗号資産だけ表示
- 株価指数だけ表示
- ニュース履歴への導線

## 移行手順案

1. `spec.md` で仕様確定
2. Web側で `data/latest.json` / `data/history.json` を生成する
3. `index.html` で表示する
4. `getMarketInfo.py` を参考に `scripts/fetch_market_data.py` を整備する
5. `getArticleFromKabutan.py` を参考に `scripts/fetch_market_news.py` を整備する
6. 履歴JSONと前日比計算を維持する
7. GitHub Actions化する
8. 高機能版を追加する

## 仕様確定事項

### サイト・表示

- サイト名は `一般＆暗号通貨マーケット情報` とする。
- トップページに以下を表示する。
  - 市場インデックス
  - 暗号資産
  - 市況ニュース
  - 投稿文候補
- ニュースタイトルには取得元URLへのリンクを付ける。
- `cnp-times` / `FiNANCiE-times-web` と同じ静的サイト構成で進める。
- 公開URLは `invest_and_crypto_mkt` を想定する。

### データ項目

- トップページは現行 `gid=0` 相当の表示を基本にする。
- 高機能版には `BNB` を含める。
- 高機能版には `Ninja` も含める。ただし、取得値が継続的に `0` で実質停止している場合は除外または非表示にする。
- `1億BONSAI` は通常価格ではなく、1億倍した表示値だけでよい。
- `GCHO` は別APIで取得できるならAPIを優先し、難しければ現行のJupiter Playwright取得を継続する。

### 集計

- 前日比はスプレッドシートの表示値を使わず、Web側の履歴データから再計算する。
- 日本市場休日・米国市場休日などで動きがない場合は、従来通り前日比 `0` として扱ってよい。
- `yfinance` の値は、朝6時更新では基本的に終値扱いとする。
- 取得失敗時は複数回リトライする。
- リトライ後も失敗した場合は、値を無理に `0` にせず欠損として扱う。

### 更新頻度・運用

- 更新は1日1回、日本時間朝6時。
- 暗号資産も株価指数と同じタイミングで更新する。
- スプレッドシート書き込みは、他サイトと同じく当面併用する。
- Google Sheets認証情報は既存サイトと合わせ、GitHub Actions Secretsで扱う方針にする。

### ニュース

- ニュースはトップページに表示する。
- 投稿文候補もWeb上に表示する。
- `getArticleFromKabutan.py` の火曜から土曜のみ出力するルールは継続する。
- 株探・CoinPost等の記事URLはリンクとして掲載する。
- 暗号通貨ニュースはCoinPost 1件固定ではなく、複数ソースを巡回して、Bitcoin / ETH の市況または技術的ニュースのうち更新が最も新しいタイトルを採用する方向で改善する。

### 履歴移行

- 現行 `stats` シートの履歴を初回移行して `history.json` に入れる。
- 可能であれば以下のGoogle Driveフォルダにある2024年・2025年データも統合する。
  - `https://drive.google.com/drive/folders/1Fd8oK9Md7P159nnnuDFbo-162gRbO4RM`

### 実装判断

- SeleniumではなくPlaywrightへ統一してよい。ただし、Playwrightで安定取得できることを確認する。
- Chart.js等の外部ライブラリは必要に応じて使用してよい。

## 推奨判断

### GitHubリポジトリ

新規リポジトリ推奨。

理由:

- `cnp-times` / `FiNANCiE-times-web` と同じ単位で、GitHub Pages・Actions・Secrets・公開URLを独立管理しやすい。
- 市場データ取得は依存関係やスクレイピング対象が多く、既存リポジトリに混ぜるより障害範囲を分けやすい。
- 将来、ニュース取得や履歴JSONが増えても、このプロダクト単体で運用・停止・修正できる。

想定リポジトリ名:

- `invest_and_crypto_mkt`

### 取得失敗時の表示

欠損表示を推奨する。

ただし、トップページではユーザー体験を落としすぎないため、以下のように分ける。

- `data/latest.json` には `price: null`, `status: "error"` として保存する。
- UIでは `取得失敗` または `--` を表示する。
- 必要なら補助表示として `前回成功値` を小さく表示する。
- 前日比計算には失敗値を使わない。

この方針にすると、取得失敗を本当の価格 `0` と誤認しにくい。

### 暗号通貨ニュースの改善案

複数ソースを候補にして、取得できた記事の中から最新のものを選ぶ。

初期候補:

- CoinPost 市況・解説
- CoinDesk JAPAN
- あたらしい経済
- Crypto Times
- Cointelegraph Japan

採用条件:

- Bitcoin / BTC / ビットコイン / Ethereum / ETH / イーサリアム のいずれかに関連する
- 市況、価格、ETF、規制、主要アップデート、技術的ニュースを対象にする
- 広告、キャンペーン、個別銘柄だけの記事は除外する
- 公開日時が取れる場合は最も新しいものを採用する
- 公開日時が取れない場合はソース優先順位で補完する

## 確認事項

### 表示・仕様

- サイト名は `INVEST & CRYPTO MKT` でよいか
一般＆暗号通貨マーケット情報でお願いします。
- 日本語タイトルは `一般＆暗号通貨マーケット情報` のままでよいか
- `Ninja` と `BNB` は現行スクリプトでは取得しているが、現在の `gid=0` 表示には見えていない。Webでは表示対象に含めるか
高機能の方には含めてください。ただしNinjaはもうデータ取得が止まっている、ずっと0の状況のようであれば、その限りではありません。

- `1億BONSAI` は内部データとして通常価格と1億倍価格の両方を持つか、表示用の1億倍だけでよいか
1億倍でいいです。すごく小さいので、それぐらいしておかないと会わないのです。

- GCHOの価格はJupiter取得で継続するか、別API・別サイトへ変更するか
別APIで取得が可能ならそうして欲しいが、難しかったら継続でお願いします。

- 前日比はスプレッドシート表示値を踏襲するか、Web側で履歴から再計算するか
Web側で履歴から計算してください。

- 更新頻度は1日1回でよいか、複数回更新したいか
1日1回、日本時間朝6時でOKです。

- 暗号資産は24時間動くため、株価指数とは別更新にするか
しなくていいです。同じ時間でOKです。


### ニュース

- ニュース表示はトップページに出すか、`news.html` に分けるか
トップページに出してください。

- 投稿文候補をWeb上に表示するか
表示してください。また、できれば取得したタイトルにリンクを貼り、その取得元のURLに飛ぶようにしてください。

- `getArticleFromKabutan.py` の火曜から土曜のみ出力するルールを継続するか
継続でお願いします。

- CoinPostのBTC/ETH記事は1件だけでよいか、複数件表示するか
ここは改良できないか相談したいです。CoinPostも更新頻度が低いため、暗号通貨のマーケット情報を出しているサイトを探し、いくつか回って、更新タイミングが一番最新のタイトルを取ってきて欲しいです。もちろん、それは、BitcoinやEthの市況に関する情報もしくは技術的な新たなニュースのいずれかでお願いしたいです。

- 株探記事URL・CoinPost記事URLをWebに掲載してよいか
掲載というか、リンクを貼って飛べるようにしてください。

### データ・運用

- 過去の `stats` シート履歴を初回移行して `history.json` に入れるか
入れて欲しいです。
https://drive.google.com/drive/folders/1Fd8oK9Md7P159nnnuDFbo-162gRbO4RM
ここに2024、2025のデータもあるため、できれば合わせて統合してもらいたいです。

- スプレッドシートへの書き込みを完全停止するか、当面は併用するか
他のサイトと同じように、当面併用してください。

- GitHub Pagesの公開URLをどうするか
invest_and_crypto_mktでお願いします。
- GitHubリポジトリを新規作成するか、既存管理下に置くか
こちらはおすすめはどちらでしょうか？

- Google Sheets認証情報をGitHub Actions Secretsに入れて使うか
他と合わせてください。

- 取得失敗時に、前回成功値を表示するか、欠損として表示するか
リトライを何度かして欲しいですが、欠損として表示でしょうか。


### 実装判断

- Seleniumは使わず、Playwrightへ統一してよいか
取れるなら構いません。

- `yfinance` の値を終値扱いにするか、取得時点の最新値扱いにするか
おそらく時間的に終値扱いになると思います。

- 米国市場休日・日本市場休日の前日比計算をどう扱うか
今まで通り、前日比で動きなし（0）にしてもらってOKです。

- Chart.jsなどの外部ライブラリを使うか
こだわりはありません。使う必要があれば使ってください。

- `cnp-times` / `FiNANCiE-times-web` と同じ静的サイト構成で進めてよいか
同じでOKです。毎朝6時に更新してもらえればOKです。
