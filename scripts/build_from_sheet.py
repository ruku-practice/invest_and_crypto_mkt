#!/usr/bin/env python3
"""Build web JSON from the public Google Sheets view.

This is the phase-1 bridge. Later scripts can replace the sheet source with
direct market fetchers while keeping the frontend JSON contract stable.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


SPREADSHEET_ID = "1hE1h47W1Ev2vCpuCQwaXU2cUivKfmiUymP8RCNG6CkY"
DEFAULT_GID = "0"
STATS_SHEET = "stats"
BASELINE_DATE = "2024/01/01"
JST = timezone(timedelta(hours=9))


MARKET_IDS = {
    "日経225": ("nikkei225", "index", "JPY"),
    "NYダウ": ("dow", "index", "USD"),
    "S&P500": ("sp500", "index", "USD"),
    "NYSE FANG+": ("fang", "index", "USD"),
    "ドル円": ("usdjpy", "fx", "JPY"),
}

CRYPTO_IDS = {
    "BTC": ("btc", "crypto", "JPY"),
    "ETH": ("eth", "crypto", "JPY"),
    "SOL": ("sol", "crypto", "JPY"),
    "GCHO": ("gcho", "crypto", "JPY"),
    "1億BONSAI": ("bonsai_100m", "crypto", "JPY"),
}

HISTORY_ITEMS = {
    "日経225": ("nikkei225", "日経225", "index", "JPY"),
    "N225": ("nikkei225", "日経225", "index", "JPY"),
    "NYダウ": ("dow", "NYダウ", "index", "USD"),
    "DJIA": ("dow", "NYダウ", "index", "USD"),
    "S&P500": ("sp500", "S&P500", "index", "USD"),
    "SPX": ("sp500", "S&P500", "index", "USD"),
    "NYSE FANG+": ("fang", "NYSE FANG+", "index", "USD"),
    "FANG": ("fang", "NYSE FANG+", "index", "USD"),
    "ドル円": ("usdjpy", "ドル円", "fx", "JPY"),
    "USDJPY": ("usdjpy", "ドル円", "fx", "JPY"),
    "BTC": ("btc", "BTC", "crypto", "JPY"),
    "ETH": ("eth", "ETH", "crypto", "JPY"),
    "BNB": ("bnb", "BNB", "crypto", "JPY"),
    "SOL": ("sol", "SOL", "crypto", "JPY"),
    "GCHO": ("gcho", "GCHO", "crypto", "JPY"),
    "1億BONSAI": ("bonsai_100m", "1億BONSAI", "crypto", "JPY"),
    "BonsaiCoin_Price_Multiplied": ("bonsai_100m", "1億BONSAI", "crypto", "JPY"),
    "1okuBONSAI": ("bonsai_100m", "1億BONSAI", "crypto", "JPY"),
    "Ninja": ("ninja", "Ninja", "crypto", "USD"),
    "NINJA INU": ("ninja", "Ninja", "crypto", "USD"),
}


def fetch_gviz(spreadsheet_id: str, gid: str | None = None, sheet: str | None = None) -> dict[str, Any]:
    query = {"tqx": "out:json"}
    if sheet:
        query["sheet"] = sheet
    elif gid:
        query["gid"] = gid
    params = urllib.parse.urlencode(query)
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        text = res.read().decode("utf-8")

    match = re.search(r"setResponse\((.*)\);?$", text, flags=re.S)
    if not match:
        raise RuntimeError("Google Visualization response could not be parsed")
    return json.loads(match.group(1))


def cell_display(cell: dict[str, Any] | None) -> str:
    if not cell:
        return ""
    return str(cell.get("f", cell.get("v", ""))).strip()


def cell_value(cell: dict[str, Any] | None) -> Any:
    if not cell:
        return None
    return cell.get("v")


def number_value(cell: dict[str, Any] | None) -> float | None:
    value = cell_value(cell)
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def table_rows(gviz: dict[str, Any]) -> list[list[dict[str, Any] | None]]:
    raw_rows = gviz.get("table", {}).get("rows", [])
    rows: list[list[dict[str, Any] | None]] = []
    for raw in raw_rows:
        rows.append(raw.get("c", []))
    return rows


def parse_change_rate(text: str) -> float | None:
    if not text:
        return None
    cleaned = text.replace("%", "").replace("+", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_datetime(rows: list[list[dict[str, Any] | None]]) -> tuple[str, str, str]:
    date_text = ""
    time_text = ""
    for row in rows:
        for cell in row:
            value = cell_display(cell)
            if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", value):
                date_text = value
            elif re.fullmatch(r"\d{1,2}:\d{2}", value):
                time_text = value

    if date_text and time_text:
        dt = datetime.strptime(f"{date_text} {time_text}", "%Y/%m/%d %H:%M").replace(tzinfo=JST)
        return dt.isoformat(), date_text, time_text

    now = datetime.now(JST).replace(second=0, microsecond=0)
    return now.isoformat(), now.strftime("%Y/%m/%d"), now.strftime("%H:%M")


def find_pair_rows(rows: list[list[dict[str, Any] | None]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    markets: list[dict[str, Any]] = []
    crypto: list[dict[str, Any]] = []

    for row in rows:
        left_name = cell_display(row[1] if len(row) > 1 else None)
        left_price_cell = row[2] if len(row) > 2 else None
        left_change = cell_display(row[3] if len(row) > 3 else None)
        right_name = cell_display(row[5] if len(row) > 5 else None)
        right_price_cell = row[6] if len(row) > 6 else None
        right_change = cell_display(row[7] if len(row) > 7 else None)

        if left_name in MARKET_IDS:
            item_id, category, currency = MARKET_IDS[left_name]
            markets.append(
                make_item(item_id, left_name, category, currency, left_price_cell, left_change)
            )

        if right_name in CRYPTO_IDS:
            item_id, category, currency = CRYPTO_IDS[right_name]
            crypto.append(
                make_item(item_id, right_name, category, currency, right_price_cell, right_change)
            )

    return markets, crypto


def make_item(
    item_id: str,
    name: str,
    category: str,
    currency: str,
    price_cell: dict[str, Any] | None,
    change_text: str,
) -> dict[str, Any]:
    price = cell_value(price_cell)
    display_price = cell_display(price_cell)
    status = "ok" if price is not None and display_price else "missing"
    return {
        "id": item_id,
        "name": name,
        "category": category,
        "price": price,
        "display_price": display_price or "--",
        "change_rate": parse_change_rate(change_text),
        "display_change_rate": change_text or "--",
        "currency": currency,
        "status": status,
    }


def build_payload(gviz: dict[str, Any]) -> dict[str, Any]:
    rows = table_rows(gviz)
    generated_at, display_date, display_time = parse_datetime(rows)
    markets, crypto = find_pair_rows(rows)
    return {
        "generated_at": generated_at,
        "display_date": display_date,
        "display_time": display_time,
        "source": "google-sheet-gviz",
        "spreadsheet_id": SPREADSHEET_ID,
        "gid": DEFAULT_GID,
        "markets": markets,
        "crypto": crypto,
        "news": {
            "items": [],
            "post_text": "",
            "status": "not_integrated",
        },
    }


def parse_sheet_date(cell: dict[str, Any] | None) -> str:
    display = cell_display(cell)
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", display):
        dt = datetime.strptime(display, "%Y/%m/%d")
        return dt.strftime("%Y/%m/%d")
    value = cell_value(cell)
    if isinstance(value, (int, float)):
        dt = datetime(1899, 12, 30) + timedelta(days=float(value))
        return dt.strftime("%Y/%m/%d")
    return ""


def build_history_payload(gviz: dict[str, Any], baseline_date: str = BASELINE_DATE) -> dict[str, Any]:
    rows = table_rows(gviz)
    date_row = next((row for row in rows if cell_display(row[1] if len(row) > 1 else None) == "date"), None)
    if not date_row:
        raise RuntimeError("stats sheet date row was not found")

    dates = [parse_sheet_date(cell) for cell in date_row]
    baseline_dt = datetime.strptime(baseline_date, "%Y/%m/%d")
    items: list[dict[str, Any]] = []

    for row in rows:
        label = cell_display(row[1] if len(row) > 1 else None)
        if label not in HISTORY_ITEMS:
            continue

        item_id, name, category, currency = HISTORY_ITEMS[label]
        raw_points: list[dict[str, Any]] = []
        for index in range(2, min(len(row), len(dates))):
            date = dates[index]
            if not date:
                continue
            dt = datetime.strptime(date, "%Y/%m/%d")
            if dt < baseline_dt:
                continue
            value = number_value(row[index])
            if value is None:
                continue
            raw_points.append({"date": date, "value": value})

        base_point = next((point for point in raw_points if point["value"] not in (0, None)), None)
        if not base_point:
            continue

        base_value = base_point["value"]
        points = []
        for point in raw_points:
            value = point["value"]
            change_pct = None if value in (0, None) else ((value / base_value) - 1) * 100
            points.append(
                {
                    "date": point["date"],
                    "value": value,
                    "change_from_base_pct": round(change_pct, 4) if change_pct is not None else None,
                }
            )

        items.append(
            {
                "id": item_id,
                "name": name,
                "category": category,
                "currency": currency,
                "baseline_date": base_point["date"],
                "baseline_value": base_value,
                "points": points,
            }
        )

    return {
        "generated_at": datetime.now(JST).replace(microsecond=0).isoformat(),
        "source": "google-sheet-gviz",
        "spreadsheet_id": SPREADSHEET_ID,
        "sheet": STATS_SHEET,
        "baseline_date": baseline_date,
        "items": items,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spreadsheet-id", default=SPREADSHEET_ID)
    parser.add_argument("--gid", default=DEFAULT_GID)
    parser.add_argument("--stats-sheet", default=STATS_SHEET)
    parser.add_argument("--out", default="data/latest.json")
    parser.add_argument("--history-out", default="data/history.json")
    args = parser.parse_args()

    gviz = fetch_gviz(args.spreadsheet_id, gid=args.gid)
    payload = build_payload(gviz)
    payload["spreadsheet_id"] = args.spreadsheet_id
    payload["gid"] = args.gid
    write_json(Path(args.out), payload)

    stats_gviz = fetch_gviz(args.spreadsheet_id, sheet=args.stats_sheet)
    history_payload = build_history_payload(stats_gviz)
    history_payload["spreadsheet_id"] = args.spreadsheet_id
    history_payload["sheet"] = args.stats_sheet
    write_json(Path(args.history_out), history_payload)

    print(
        f"Wrote {args.out} ({len(payload['markets'])} markets, {len(payload['crypto'])} crypto) "
        f"and {args.history_out} ({len(history_payload['items'])} series)"
    )


if __name__ == "__main__":
    main()
