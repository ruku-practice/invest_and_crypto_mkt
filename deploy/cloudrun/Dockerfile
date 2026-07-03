# 一般＆暗号通貨マーケット情報 日次更新ジョブ（Cloud Run Job）
# 起動時にリポジトリを clone → データ/ニュース取得・更新 → main へ push。
# JOB_MODE で処理を切り替える（data: 市場データ / news: 市況ニュース）。
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      yfinance requests beautifulsoup4 playwright
RUN playwright install --with-deps chromium

ENV TZ=Asia/Tokyo \
    PYTHONUNBUFFERED=1

COPY run.sh /run.sh
RUN chmod +x /run.sh

ENTRYPOINT ["/run.sh"]
