#!/usr/bin/env python3
"""Fetch market news and write `data/news/latest.json`.

This mirrors the old spreadsheet-side news aggregation, but stores the result in
JSON so the web app can read it directly.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LATEST_PATH = DATA_DIR / "latest.json"
NEWS_PATH = DATA_DIR / "news" / "latest.json"


def now_jst() -> datetime:
    return datetime.now(JST).replace(microsecond=0)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return json.loads(json.dumps(default, ensure_ascii=False))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(default, ensure_ascii=False))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_title(title: str) -> str:
    title = title.strip()
    title = title.replace("＝米国株概況", "").strip()
    if "｜" in title:
        title = title.split("｜", 1)[1].strip()
    if "（" in title:
        title = title.split("（", 1)[0].strip()
    elif "(" in title:
        title = title.split("(", 1)[0].strip()
    return title


def get_news_from_url(base_url: str, filter_conditions: list[str], max_pages: int = 5) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for current_page in range(1, max_pages + 1):
        url = f"{base_url}&page={current_page}"
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
        except Exception:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for table in soup.find_all("table", {"class": "s_news_list"}):
            for row in table.find_all("tr"):
                tds = row.find_all("td")
                if len(tds) < 3:
                    continue
                time_tag = tds[0].find("time")
                link_tag = tds[2].find("a", href=True)
                if not time_tag or not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                if not any(condition in title for condition in filter_conditions):
                    continue

                results.append(
                    {
                        "title": title,
                        "url": f"https://kabutan.jp{link_tag['href']}",
                        "date": time_tag.get("datetime", ""),
                    }
                )

                if "日経平均 大引け" in title:
                    return results

    return results


def get_crypto_news_from_coinpost() -> dict[str, Any] | None:
    url = "https://coinpost.jp/?category=market-news"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    mkt_section = soup.find("div", class_="hmml-mct")
    if not mkt_section:
        return None

    for article in mkt_section.find_all("div", class_="homelist-in"):
        links = article.find_all("a", href=True)
        title_link = next((a for a in links if len(a.get_text(strip=True)) > 10), None)
        if not title_link:
            continue
        title = title_link.get_text(strip=True)
        if not (title.startswith("ビットコイン") or title.startswith("イーサリアム") or title.startswith("BTC") or title.startswith("ETH")):
            continue

        if "｜" in title:
            title = title.split("｜", 1)[0].strip()
        time_span = article.find("span", class_="hometimes")
        return {
            "title": title,
            "url": title_link["href"],
            "time": time_span.get_text(strip=True) if time_span else "",
        }

    return None


def build_items() -> list[dict[str, Any]]:
    market_news = get_news_from_url(
        "https://kabutan.jp/news/marketnews/?category=1",
        ["ダウ平均", "日経平均 大引け"],
    )
    fx_news = get_news_from_url(
        "https://kabutan.jp/news/marketnews/?category=11",
        ["NY為替", "NY外為"],
    )
    crypto_news = get_crypto_news_from_coinpost()

    items: list[dict[str, Any]] = []

    for news in market_news:
        if "日経平均 大引け" in news["title"]:
            items.append(
                {
                    "category": "nikkei",
                    "source": "kabutan",
                    "title": clean_title(news["title"]),
                    "url": news["url"],
                    "published_at": news["date"],
                    "summary_for_post": clean_title(news["title"]),
                }
            )
            break

    for news in market_news:
        if news["title"].startswith("ダウ平均"):
            items.append(
                {
                    "category": "overseas",
                    "source": "kabutan",
                    "title": clean_title(news["title"]),
                    "url": news["url"],
                    "published_at": news["date"],
                    "summary_for_post": clean_title(news["title"]),
                }
            )
            break

    for news in fx_news:
        if news["title"].startswith("NY外為：ドル") or news["title"].startswith("NY為替：ドル"):
            items.append(
                {
                    "category": "fx",
                    "source": "kabutan",
                    "title": clean_title(news["title"]),
                    "url": news["url"],
                    "published_at": news["date"],
                    "summary_for_post": clean_title(news["title"]),
                }
            )
            break

    if crypto_news:
        items.append(
            {
                "category": "crypto",
                "source": "coinpost",
                "title": crypto_news["title"],
                "url": crypto_news["url"],
                "published_at": crypto_news["time"],
                "summary_for_post": crypto_news["title"],
            }
        )
    else:
        for news in fx_news:
            if any(token in news["title"] for token in ("ビットコイン", "イーサ", "BTC", "ETH")):
                items.append(
                    {
                        "category": "crypto",
                        "source": "kabutan",
                        "title": clean_title(news["title"]),
                        "url": news["url"],
                        "published_at": news["date"],
                        "summary_for_post": clean_title(news["title"]),
                    }
                )
                break

    return items


def build_post_text(items: list[dict[str, Any]]) -> str:
    mapping = {item["category"]: item for item in items}
    crypto = mapping.get("crypto")
    crypto_label = f"クリプト({crypto['published_at'].split(' ')[0]})" if crypto and crypto.get("published_at") else "クリプト"

    lines = [
        f"・日経平均：{mapping.get('nikkei', {}).get('summary_for_post', '未取得')}",
        f"・海外：{mapping.get('overseas', {}).get('summary_for_post', '未取得')}",
        f"・ドル円：{mapping.get('fx', {}).get('summary_for_post', '未取得')}",
        f"・{crypto_label}：{mapping.get('crypto', {}).get('summary_for_post', '未取得')}",
    ]
    return "\n".join(lines)


def merge_into_latest(news_payload: dict[str, Any]) -> None:
    latest = load_json(LATEST_PATH, {})
    if not isinstance(latest, dict):
        latest = {}
    latest["news"] = news_payload
    generated_at = now_jst()
    latest["generated_at"] = generated_at.isoformat()
    latest["display_date"] = generated_at.strftime("%Y/%m/%d")
    latest["display_time"] = generated_at.strftime("%H:%M")
    latest["source"] = "web-fetch"
    write_json(LATEST_PATH, latest)


def main() -> None:
    items = build_items()
    generated_at = now_jst()
    weekday = generated_at.weekday()
    post_text = build_post_text(items) if 1 <= weekday <= 5 else ""

    payload = {
        "generated_at": generated_at.isoformat(),
        "items": items,
        "post_text": post_text,
        "status": "ok" if items else "empty",
    }

    write_json(NEWS_PATH, payload)
    merge_into_latest(payload)
    print(f"Wrote {NEWS_PATH} and merged into {LATEST_PATH}")


if __name__ == "__main__":
    main()
