#!/usr/bin/env bash
# 一般＆暗号通貨マーケット情報 日次更新（Cloud Run Job のエントリポイント）
# 必要env:
#   GH_TOKEN  … repo push 権限トークン（Secret Manager: gh-token）
#   JOB_MODE  … data(市場データ) / news(市況ニュース) / both（既定）
set -euo pipefail

REPO="ruku-practice/invest_and_crypto_mkt"
JOB_MODE="${JOB_MODE:-both}"
GH_TOKEN="$(printf '%s' "${GH_TOKEN:-}" | tr -d '\r\n[:space:]')"
ORIGIN="https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git"
WORK=/work

echo "==================== $(date) invest ${JOB_MODE} (cloud run) start ====================="
rm -rf "$WORK"
git clone --quiet --depth 1 "$ORIGIN" "$WORK"
cd "$WORK"
git config user.name  "cloud-run-bot"
git config user.email "cloud-run-bot@users.noreply.github.com"
export PYTHONUNBUFFERED=1

run_with_retry() {
  local script="$1"
  local ok=0
  for a in 1 2 3; do
    echo "----- $script 試行 $a/3 $(date) -----"
    if python3 "$script"; then ok=1; break; fi
    if [ "$a" -lt 3 ]; then echo "失敗 → 120秒後に再試行"; sleep 120; fi
  done
  [ "$ok" -eq 1 ] || { echo "❌ $script 3回とも失敗"; return 1; }
}

case "$JOB_MODE" in
  data) run_with_retry scripts/fetch_market_data.py ;;
  news) run_with_retry scripts/fetch_market_news.py ;;
  both)
    run_with_retry scripts/fetch_market_data.py
    run_with_retry scripts/fetch_market_news.py
    ;;
  *) echo "❌ 未知の JOB_MODE: $JOB_MODE"; exit 1 ;;
esac

# データ更新を main へ push（差分がある時のみ）
git add data/
if git diff --staged --quiet; then
  echo "変更なし"
else
  git commit -q -m "chore: market ${JOB_MODE} update $(date -u +%Y-%m-%dT%H:%MZ) [cloud-run]"
  # 走行中に他ジョブ/手動pushが入っても衝突しないよう rebase してから push
  git pull --rebase --quiet origin main || true
  git push --quiet origin HEAD:main
  echo "✓ main に push"
fi

echo "==================== $(date) invest ${JOB_MODE} done ====================="
