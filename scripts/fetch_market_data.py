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
    {"id": "gcho", "name": "GCHO", "category": "crypto", "url": "https://jup.ag/tokens/gcho94FhdhJNDhVEnHHskXP7PcSKDqCs3GKEj5zrewn", "currency": "USD"},
    {"id": "bonsai_100m", "name": "1億BONSAI", "category": "crypto", "url": "https://www.geckoterminal.com/base/pools/0x4fe87203b27a105a772f195d3f30dea714d1ecf0", "currency": "USD"},
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
        return f"¥{value:,.0f}"
    if currency == "USD":
        if abs(value) >= 1:
            return f"${value:,.2f}"
        return f"${value:,.6f}".rstrip("0").rstrip(".")
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


def fetch_yfinance_series(ticker: str) -> tuple[float | None, float | None, str]:
    try:
        hist = yf.Ticker(ticker).history(period="7d", interval="1d")
        close_series = hist["Close"] if "Close" in hist else None
        if close_series is None:
            return None, None, "error"
        closes = [float(value) for value in close_series.dropna().tolist()]
        if not closes:
            return None, None, "error"
        current = closes[-1]
        previous = closes[-2] if len(closes) >= 2 else None
        change = ((current / previous) - 1) * 100 if previous else None
        return current, change, "ok"
    except Exception:
        return None, None, "error"


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


def fetch_gcho_price() -> tuple[float | None, float | None, str]:
    # Web側では失敗時にダッシュボードを壊さないことを優先する。
    try:
        from playwright.sync_api import sync_playwright

        url = "https://jup.ag/tokens/gcho94FhdhJNDhVEnHHskXP7PcSKDqCs3GKEj5zrewn"
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            try:
                page.wait_for_function("document.title.includes('$')", timeout=45_000)
            except Exception:
                pass
            title = page.title()
            browser.close()

        if "$" not in title:
            return None, None, "error"

        price_start = title.find("$") + 1
        price_end = price_start
        while price_end < len(title) and (title[price_end].isdigit() or title[price_end] == "." or title[price_end] in "₀₁₂₃₄₅₆₇₈₉"):
            price_end += 1
        price_text = title[price_start:price_end]
        subs = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9"}
        for key, value in subs.items():
            if key in price_text:
                left, right = price_text.split(key, 1)
                if left.endswith("0"):
                    left = left[:-1]
                price_text = left + ("0" * int(value)) + right
                break
        price = float(price_text)
        if not is_valid_price(price):
            return None, None, "error"
        return price, None, "ok"
    except Exception:
        return None, None, "error"


def fetch_bonsai_price() -> tuple[float | None, float | None, str]:
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
        price, change, status = fetch_yfinance_series(item["ticker"])
        values[item["id"]] = {
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "currency": item["currency"],
            "price": price,
            "display_price": format_price(price, item["currency"]),
            "change_rate": change,
            "display_change_rate": format_change(change),
            "status": status,
        }

    crypto_prices = fetch_coin_gecko_price()
    for item in CRYPTOS:
        if item["id"] in crypto_prices:
            price, change, status = crypto_prices[item["id"]]
        elif item["id"] == "gcho":
            price, change, status = fetch_gcho_price()
        elif item["id"] == "bonsai_100m":
            price, change, status = fetch_bonsai_price()
        else:
            price, change, status = None, None, "error"

        values[item["id"]] = {
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "currency": item["currency"],
            "price": price,
            "display_price": format_price(price, item["currency"]),
            "change_rate": change,
            "display_change_rate": format_change(change),
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
        collect(existing_by_id.get(item_id, {}).get("points"), points_by_date)
        collect(item.get("points"), points_by_date)
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
        entry = by_id.get(item_id)
        if not entry:
            entry = {
                "id": item_id,
                "name": current["name"],
                "category": current["category"],
                "currency": current["currency"],
                "baseline_date": today,
                "baseline_value": current["price"],
                "points": [],
            }
            by_id[item_id] = entry

        points = [point for point in entry.get("points", []) if isinstance(point, dict) and point.get("date")]
        points = [point for point in points if point["date"] != today]
        today_price = current["price"] if is_valid_price(current["price"]) else None
        points.append({
            "date": today,
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
            baseline_date = today

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
