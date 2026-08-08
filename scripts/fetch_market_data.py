#!/usr/bin/env python3
"""Fetch market data on the web side and persist latest/history JSON.

This keeps the frontend contract used by `js/app.js` stable while moving the
daily aggregation away from Google Sheets.
"""

from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
import yfinance as yf

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LATEST_PATH = DATA_DIR / "latest.json"
HISTORY_PATH = DATA_DIR / "history.json"
NEWS_PATH = DATA_DIR / "news" / "latest.json"
HISTORICAL_START = datetime(2024, 1, 1, tzinfo=JST)

MARKETS = [
    {"id": "nikkei225", "name": "日経225", "category": "index", "ticker": "^N225", "currency": "JPY"},
    {"id": "dow", "name": "NYダウ", "category": "index", "ticker": "^DJI", "currency": "USD"},
    {"id": "sp500", "name": "S&P500", "category": "index", "ticker": "^GSPC", "currency": "USD"},
    {"id": "fang", "name": "NYSE FANG+", "category": "index", "ticker": "^NYFANG", "currency": "USD"},
    {"id": "usdjpy", "name": "ドル円", "category": "fx", "ticker": "USDJPY=X", "currency": "JPY"},
]

CRYPTOS = [
    {"id": "btc", "name": "BTC", "category": "crypto", "cg_id": "bitcoin", "currency": "JPY"},
    {"id": "eth", "name": "ETH", "category": "crypto", "cg_id": "ethereum", "currency": "JPY"},
    {"id": "sol", "name": "SOL", "category": "crypto", "cg_id": "solana", "currency": "JPY"},
    # GCHO/1億BONSAIは取得元がUSD建てのため、ドル円レートで円換算して保存する（2026-08-08ルク決裁）。
    # 1億BONSAIは名前のとおり「価格×1億」の表示値（spec.md §データ項目）。
    {"id": "gcho", "name": "GCHO", "category": "crypto", "url": "https://jup.ag/tokens/gcho94FhdhJNDhVEnHHskXP7PcSKDqCs3GKEj5zrewn", "currency": "JPY", "usd_source": True, "unit_multiplier": 1},
    {"id": "bonsai_100m", "name": "1億BONSAI", "category": "crypto", "url": "https://www.geckoterminal.com/base/pools/0x4fe87203b27a105a772f195d3f30dea714d1ecf0", "currency": "JPY", "usd_source": True, "unit_multiplier": 100_000_000},
]

def now_jst() -> datetime:
    return datetime.now(JST).replace(microsecond=0)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_price(value: float | None, currency: str) -> str:
    if value is None or not math.isfinite(value):
        return "--"
    if currency == "JPY":
        if abs(value) >= 1:
            return f"¥{value:,.0f}"
        # GCHOのような1円未満の価格は整数表示だと¥0になるため、有効数字3桁で出す。
        decimals = min(12, 2 - math.floor(math.log10(abs(value)))) if value else 2
        return f"¥{value:,.{decimals}f}".rstrip("0").rstrip(".")
    if currency == "USD":
        if abs(value) >= 1:
            return f"${value:,.2f}"
        # BONSAIのような極小価格（1e-9台）は6桁固定だと "$0" になるため、
        # 有効数字が3桁見えるまで小数桁を広げる。
        decimals = min(12, 2 - math.floor(math.log10(abs(value)))) if value else 6
        return f"${value:,.{decimals}f}".rstrip("0").rstrip(".")
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def format_change(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "--"
    return f"{value:+.2f}%"


def latest_numeric(points: list[dict[str, Any]]) -> float | None:
    for point in reversed(points):
        value = point.get("value")
        if isinstance(value, (int, float)):
            return float(value)
    return None


def is_valid_price(value: Any) -> bool:
    # 取得失敗時の 0 や NaN を履歴・前日比計算に混ぜない。
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def fetch_yfinance_series(ticker: str) -> tuple[float | None, float | None, str, str | None]:
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="7d", interval="1d")
        close_series = hist["Close"] if "Close" in hist else None
        if close_series is None:
            return None, None, "error", None
        close_series = close_series.dropna()
        closes = [float(value) for value in close_series.tolist()]
        if not closes:
            return None, None, "error", None
        current = closes[-1]
        previous = closes[-2] if len(closes) >= 2 else None
        # yfinanceの最新値は「実行日」ではなく、最後に成立した取引日の値。
        # 休場中に実行日の履歴として保存すると同じ終値が複製され、前日比が0%になる。
        price_date = close_series.index[-1].date().isoformat()

        # Yahooの日足は前営業日の終値の反映が朝まで遅れることがある（^N225で実測）。
        # 分足の最終バーが日足より新しい日付なら、その値を当日終値として採用する。
        # ジョブは市場が閉まっている06:00 JSTに走るため、分足の最終値＝その日の引け値。
        try:
            intra = tk.history(period="5d", interval="15m")
            iclose = intra["Close"].dropna() if intra is not None and "Close" in intra else None
            if iclose is not None and len(iclose):
                intra_date = iclose.index[-1].date()
                if intra_date > close_series.index[-1].date():
                    previous = current
                    current = float(iclose.iloc[-1])
                    price_date = intra_date.isoformat()
        except Exception:
            pass

        change = ((current / previous) - 1) * 100 if previous else None
        return current, change, "ok", price_date
    except Exception:
        return None, None, "error", None


def fetch_yfinance_history(ticker: str, start: datetime, end: datetime | None = None) -> dict[str, float]:
    try:
        stop = (end or now_jst()) + timedelta(days=1)
        hist = yf.Ticker(ticker).history(
            start=start.strftime("%Y-%m-%d"),
            end=stop.strftime("%Y-%m-%d"),
            interval="1d",
        )
    except Exception:
        return {}

    if hist is None or hist.empty or "Close" not in hist:
        return {}

    close = hist["Close"].dropna()
    series: dict[str, float] = {}
    for idx, value in close.items():
        try:
            date_key = idx.date().isoformat()
            series[date_key] = float(value)
        except Exception:
            continue
    return series


def fetch_coin_gecko_price() -> dict[str, tuple[float | None, float | None, str]]:
    ids = ",".join(item["cg_id"] for item in CRYPTOS if "cg_id" in item)
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ids, "vs_currencies": "jpy", "include_24hr_change": "true"}
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        payload = {}

    out: dict[str, tuple[float | None, float | None, str]] = {}
    for item in CRYPTOS:
        if "cg_id" not in item:
            continue
        node = payload.get(item["cg_id"], {}) if isinstance(payload, dict) else {}
        price = node.get("jpy") if isinstance(node, dict) else None
        change = node.get("jpy_24h_change") if isinstance(node, dict) else None
        out[item["id"]] = (
            float(price) if isinstance(price, (int, float)) else None,
            float(change) if isinstance(change, (int, float)) else None,
            "ok" if isinstance(price, (int, float)) else "error",
        )
    return out


def fetch_gecko_terminal_price(url: str, selector: str) -> float | None:
    try:
        response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        html = response.text
    except Exception:
        return None

    marker = f'id="{selector}"'
    if marker not in html:
        return None
    start = html.find(marker)
    if start < 0:
        return None
    window = html[start:start + 4000]
    try:
        import re

        matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)", window)
        if not matches:
            return None
        return float(matches[0])
    except Exception:
        return None


GECKO_API_HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}


def fetch_gcho_price() -> tuple[float | None, float | None, str]:
    # jup.agのタイトルスクレイプは値が数日間張り付く事故があったため、
    # GeckoTerminal公式APIから取得する（2026-08-08実測でAPI値とタイトル値の乖離を確認）。
    url = "https://api.geckoterminal.com/api/v2/networks/solana/tokens/gcho94FhdhJNDhVEnHHskXP7PcSKDqCs3GKEj5zrewn"
    try:
        response = requests.get(url, headers=GECKO_API_HEADERS, timeout=30)
        response.raise_for_status()
        attributes = response.json().get("data", {}).get("attributes", {})
        price = float(attributes.get("price_usd"))
        if not is_valid_price(price):
            return None, None, "error"
        return price, None, "ok"
    except Exception:
        return None, None, "error"


def fetch_bonsai_price() -> tuple[float | None, float | None, str]:
    # HTMLスクレイプはCloud RunのIPがブロックされ6日連続で取得失敗した（2026-08-08確認）。
    # GeckoTerminal公式APIを正とし、HTML正規表現は最終フォールバックに残す。
    api_url = "https://api.geckoterminal.com/api/v2/networks/base/pools/0x4fe87203b27a105a772f195d3f30dea714d1ecf0"
    try:
        response = requests.get(api_url, headers=GECKO_API_HEADERS, timeout=30)
        response.raise_for_status()
        attributes = response.json().get("data", {}).get("attributes", {})
        price = float(attributes.get("base_token_price_usd"))
        change_raw = (attributes.get("price_change_percentage") or {}).get("h24")
        change = float(change_raw) if change_raw is not None else None
        if is_valid_price(price):
            return price, change, "ok"
    except Exception:
        pass

    url = "https://www.geckoterminal.com/base/pools/0x4fe87203b27a105a772f195d3f30dea714d1ecf0"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response.raise_for_status()
        html = response.text
        import re

        match = re.search(r'id="pool-price-display".*?<sub[^>]*title="([^"]+)"', html, flags=re.S)
        if not match:
            return None, None, "error"
        raw = match.group(1).strip().replace("$", "")
        price = float(raw)
        if not is_valid_price(price):
            return None, None, "error"
        return price, None, "ok"
    except Exception:
        return None, None, "error"


def fetch_current_values() -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}

    for item in MARKETS:
        price, change, status, price_date = fetch_yfinance_series(item["ticker"])
        values[item["id"]] = {
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "currency": item["currency"],
            "price": price,
            "display_price": format_price(price, item["currency"]),
            "change_rate": change,
            "display_change_rate": format_change(change),
            "price_date": price_date.replace("-", "/") if price_date else None,
            "status": status,
        }

    crypto_prices = fetch_coin_gecko_price()
    usdjpy_rate = values.get("usdjpy", {}).get("price")
    for item in CRYPTOS:
        if item["id"] in crypto_prices:
            price, change, status = crypto_prices[item["id"]]
        elif item["id"] == "gcho":
            price, change, status = fetch_gcho_price()
        elif item["id"] == "bonsai_100m":
            price, change, status = fetch_bonsai_price()
        else:
            price, change, status = None, None, "error"

        if item.get("usd_source") and status == "ok":
            # 円換算できない値を混ぜると履歴の単位が崩れるため、レート欠損時は欠損扱い。
            if is_valid_price(usdjpy_rate) and is_valid_price(price):
                price = price * item.get("unit_multiplier", 1) * float(usdjpy_rate)
            else:
                price, status = None, "error"

        values[item["id"]] = {
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "currency": item["currency"],
            "price": price,
            "display_price": format_price(price, item["currency"]),
            "change_rate": change,
            "display_change_rate": format_change(change),
            "price_date": now_jst().strftime("%Y/%m/%d"),
            "status": status,
        }

    return values


def merge_latest_news(existing_latest: dict[str, Any]) -> dict[str, Any]:
    news_payload = load_json(NEWS_PATH, {"generated_at": "", "items": [], "post_text": "", "status": "not_integrated"})
    latest = deepcopy(existing_latest)
    latest["news"] = {
        "generated_at": news_payload.get("generated_at", ""),
        "items": news_payload.get("items", []),
        "post_text": news_payload.get("post_text", ""),
        "status": news_payload.get("status", "ok"),
    }
    return latest


def build_historical_history(current_values: dict[str, dict[str, Any]]) -> dict[str, Any]:
    end = now_jst()
    usd_jpy = fetch_yfinance_history("USDJPY=X", HISTORICAL_START, end)

    history_items: list[dict[str, Any]] = []

    def make_series(item_id: str, name: str, category: str, currency: str, raw_series: dict[str, float]) -> None:
        points = []
        for date_key in sorted(raw_series.keys()):
            value = raw_series[date_key]
            points.append({"date": date_key.replace("-", "/"), "value": value})

        if not points:
            return

        base_value = next((point["value"] for point in points if isinstance(point.get("value"), (int, float))), None)
        if base_value in (None, 0):
            baseline_date = points[0]["date"]
            baseline_value = points[0]["value"]
        else:
            baseline_date = points[0]["date"]
            baseline_value = base_value

        history_items.append(
            {
                "id": item_id,
                "name": name,
                "category": category,
                "currency": currency,
                "baseline_date": baseline_date,
                "baseline_value": baseline_value,
                "points": points,
            }
        )

    for item in MARKETS:
        series = fetch_yfinance_history(item["ticker"], HISTORICAL_START, end)
        make_series(item["id"], item["name"], item["category"], item["currency"], series)

    crypto_map = {
        "btc": "BTC-USD",
        "eth": "ETH-USD",
        "sol": "SOL-USD",
    }
    for item in CRYPTOS:
        if item["id"] not in crypto_map:
            current = current_values.get(item["id"], {})
            make_series(item["id"], item["name"], item["category"], item["currency"], {
                now_jst().strftime("%Y-%m-%d"): current.get("price"),
            } if isinstance(current.get("price"), (int, float)) else {})
            continue

        usd_series = fetch_yfinance_history(crypto_map[item["id"]], HISTORICAL_START, end)
        combined: dict[str, float] = {}
        for date_key, usd_price in usd_series.items():
            fx_price = usd_jpy.get(date_key)
            if fx_price is None:
                continue
            combined[date_key] = usd_price * fx_price
        make_series(item["id"], item["name"], item["category"], item["currency"], combined)

    ordered_ids = [item["id"] for item in MARKETS + CRYPTOS]
    ordered_items = [item for item in history_items if item["id"] in ordered_ids]
    remaining_items = [item for item in history_items if item["id"] not in ordered_ids]

    return {
        "generated_at": now_jst().isoformat(),
        "source": "web-fetch",
        "items": ordered_items + remaining_items,
    }


def merge_history(existing: dict[str, Any], rebuilt: dict[str, Any]) -> dict[str, Any]:
    """既存履歴と再取得履歴を日付単位で統合する。

    yfinance で再取得できる銘柄は再取得値を優先しつつ、GCHO / BONSAI のように
    日次で積み上げるしかない銘柄の過去ポイントを消さないために必要。
    """
    existing_items = existing.get("items") if isinstance(existing, dict) else None
    existing_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(existing_items, list):
        for item in existing_items:
            if isinstance(item, dict) and item.get("id"):
                existing_by_id[str(item["id"])] = item

    def collect(points: Any, into: dict[str, dict[str, Any]]) -> None:
        if not isinstance(points, list):
            return
        for point in points:
            if isinstance(point, dict) and point.get("date") and is_valid_price(point.get("value")):
                entry = into.setdefault(str(point["date"]), {})
                entry["value"] = float(point["value"])
                # 取得時刻は再取得(yfinance終値)側には無いので、既存の記録を保持する
                if point.get("fetched_at"):
                    entry["fetched_at"] = point["fetched_at"]

    merged_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rebuilt.get("items", []):
        item_id = str(item["id"])
        seen.add(item_id)
        points_by_date: dict[str, dict[str, Any]] = {}
        existing_points = existing_by_id.get(item_id, {}).get("points")
        existing_fetched_at = {
            str(point["date"]): point["fetched_at"]
            for point in existing_points or []
            if isinstance(point, dict) and point.get("date") and point.get("fetched_at")
        }
        # 再取得結果を正としつつ、再取得に無い日付は既存ポイントで穴埋めする。
        # Yahooの日足は特定日が欠けることがあり（2026-08-08にBTC-USDの8/7バー欠損を実測）、
        # 再取得側だけを正にすると06:00に実測済みの日次ポイントまで消えてしまう。
        # ただし、直前の再取得終値と完全一致する値は旧ロジックが休場日に複製した値
        # とみなして残さない。
        rebuilt_points: dict[str, dict[str, Any]] = {}
        collect(item.get("points"), rebuilt_points)
        rebuilt_dates = sorted(rebuilt_points)

        def previous_rebuilt_value(date: str) -> float | None:
            candidate = None
            for rebuilt_date in rebuilt_dates:
                if rebuilt_date >= date:
                    break
                candidate = rebuilt_points[rebuilt_date]["value"]
            return candidate

        existing_by_date: dict[str, dict[str, Any]] = {}
        collect(existing_points, existing_by_date)
        for date, point in existing_by_date.items():
            if date in rebuilt_points:
                continue
            if point["value"] == previous_rebuilt_value(date):
                continue
            points_by_date[date] = point
        points_by_date.update(rebuilt_points)
        for date, point in points_by_date.items():
            if not point.get("fetched_at") and date in existing_fetched_at:
                point["fetched_at"] = existing_fetched_at[date]
        item["points"] = [{"date": date, **points_by_date[date]} for date in sorted(points_by_date)]
        merged_items.append(item)

    for item_id, item in existing_by_id.items():
        if item_id not in seen:
            merged_items.append(item)

    rebuilt["items"] = merged_items
    return rebuilt


def normalize_history(history: dict[str, Any], current_values: dict[str, dict[str, Any]]) -> dict[str, Any]:
    items = history.get("items")
    if not isinstance(items, list):
        items = []

    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item["id"])] = item

    today = now_jst().strftime("%Y/%m/%d")
    for item_id, current in current_values.items():
        price_date = current.get("price_date") or today
        entry = by_id.get(item_id)
        if not entry:
            entry = {
                "id": item_id,
                "name": current["name"],
                "category": current["category"],
                "currency": current["currency"],
                "baseline_date": price_date,
                "baseline_value": current["price"],
                "points": [],
            }
            by_id[item_id] = entry

        points = [point for point in entry.get("points", []) if isinstance(point, dict) and point.get("date")]
        points = [point for point in points if point["date"] != price_date]
        today_price = current["price"] if is_valid_price(current["price"]) else None
        points.append({
            "date": price_date,
            "value": today_price,
            "status": current["status"],
            "fetched_at": now_jst().strftime("%H:%M"),
        })
        points.sort(key=lambda point: point["date"])

        baseline_point = next((point for point in points if is_valid_price(point.get("value"))), None)
        if baseline_point:
            baseline_value = float(baseline_point["value"])
            baseline_date = baseline_point["date"]
        else:
            baseline_value = today_price
            baseline_date = price_date

        normalized_points = []
        prev_value: float | None = None
        for point in points:
            value = point.get("value")
            change = None
            change_prev = None
            if is_valid_price(value):
                value = float(value)
                if baseline_value:
                    change = ((value / baseline_value) - 1) * 100
                # 前日比は直近の有効値（休日や取得失敗はスキップ）と比較する。
                if prev_value:
                    change_prev = ((value / prev_value) - 1) * 100
                prev_value = value
            else:
                value = None
            normalized_point = {
                "date": point["date"],
                "value": value,
                "change_from_base_pct": round(change, 4) if change is not None else None,
                "change_from_prev_pct": round(change_prev, 4) if change_prev is not None else None,
            }
            # 当日ポイントの前日比は取得元の実測変動率を正とする。
            # 特にBTC/ETH/SOLは、履歴側の直近ポイント（06:00 JST時点ではまだ
            # 取引中のUTC日足＝ほぼ同時刻の値）との比較になり毎日ほぼ0%になるため、
            # CoinGeckoの24時間変動率で上書きしないと前日比が死ぬ。
            if point["date"] == price_date:
                source_change = current.get("change_rate")
                if isinstance(source_change, (int, float)) and math.isfinite(source_change):
                    normalized_point["change_from_prev_pct"] = round(float(source_change), 4)
            if point.get("fetched_at"):
                normalized_point["fetched_at"] = point["fetched_at"]
            normalized_points.append(normalized_point)

        entry["name"] = current["name"]
        entry["category"] = current["category"]
        entry["currency"] = current["currency"]
        entry["baseline_date"] = baseline_date
        entry["baseline_value"] = baseline_value
        entry["points"] = normalized_points

    ordered_ids = [item["id"] for item in MARKETS + CRYPTOS]
    ordered_items = [by_id[item_id] for item_id in ordered_ids if item_id in by_id]
    remaining_items = [entry for item_id, entry in by_id.items() if item_id not in ordered_ids]
    history["generated_at"] = now_jst().isoformat()
    history["source"] = "web-fetch"
    history["items"] = ordered_items + remaining_items
    return history


def build_latest_payload(current_values: dict[str, dict[str, Any]]) -> dict[str, Any]:
    markets = [current_values[item["id"]] for item in MARKETS]
    crypto = [current_values[item["id"]] for item in CRYPTOS]
    generated_at = now_jst()
    payload = {
        "generated_at": generated_at.isoformat(),
        "display_date": generated_at.strftime("%Y/%m/%d"),
        "display_time": generated_at.strftime("%H:%M"),
        "source": "web-fetch",
        "markets": markets,
        "crypto": crypto,
        "news": {
            "generated_at": "",
            "items": [],
            "post_text": "",
            "status": "not_integrated",
        },
    }
    return merge_latest_news(payload)


def main() -> None:
    current_values = fetch_current_values()
    existing_history = load_json(HISTORY_PATH, {})
    history = merge_history(existing_history, build_historical_history(current_values))
    history = normalize_history(history, current_values)
    latest = build_latest_payload(current_values)

    write_json(HISTORY_PATH, history)
    write_json(LATEST_PATH, latest)
    print(f"Wrote {LATEST_PATH} and {HISTORY_PATH}")


if __name__ == "__main__":
    main()
