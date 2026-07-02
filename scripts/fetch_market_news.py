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

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}


class HtmlFetcher:
    """requests を基本に、GitHub Actions 等でブロックされた場合は
    Playwright (Chromium) にフォールバックして HTML を取得する。"""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._context = None

    def _ensure_context(self):
        if self._context is None:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            self._context = self._browser.new_context(
                user_agent=BROWSER_UA,
                viewport={"width": 1280, "height": 900},
                locale="ja-JP",
            )
        return self._context

    def fetch(self, url: str, marker: str) -> str | None:
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            if response.status_code == 200 and marker in response.text:
                return response.text
            print(f"[fetch] requests insufficient for {url}: status={response.status_code} marker_found={marker in response.text}")
        except Exception as exc:
            print(f"[fetch] requests failed for {url}: {exc}")

        try:
            context = self._ensure_context()
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            html = page.content()
            page.close()
            if marker in html:
                return html
            print(f"[fetch] playwright got page but marker missing for {url}")
            return None
        except Exception as exc:
            print(f"[fetch] playwright failed for {url}: {exc}")
            return None

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
            if self._browser is not None:
                self._browser.close()
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass


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


def get_news_from_url(fetcher: HtmlFetcher, base_url: str, filter_conditions: list[str], max_pages: int = 5) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for current_page in range(1, max_pages + 1):
        url = f"{base_url}&page={current_page}"
        html = fetcher.fetch(url, "s_news_list")
        if html is None:
            continue

        soup = BeautifulSoup(html, "html.parser")
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


def parse_coinpost_time(text: str) -> datetime | None:
    # "06/26 10:25" 形式（年なし）。未来日になる場合は前年扱い。
    match = re.match(r"(\d{1,2})/(\d{1,2})", text.strip())
    if not match:
        return None
    now = now_jst()
    try:
        candidate = now.replace(month=int(match.group(1)), day=int(match.group(2)))
    except ValueError:
        return None
    if candidate > now + timedelta(days=1):
        candidate = candidate.replace(year=now.year - 1)
    return candidate


def get_crypto_news_from_coinpost(fetcher: HtmlFetcher) -> dict[str, Any] | None:
    url = "https://coinpost.jp/?category=market-news"
    html = fetcher.fetch(url, "homelist-in")
    if html is None:
        return None

    soup = BeautifulSoup(html, "html.parser")
    keywords = ("ビットコイン", "イーサリアム", "BTC", "ETH")

    def extract(article) -> dict[str, Any] | None:
        links = article.find_all("a", href=True)
        title_link = next((a for a in links if len(a.get_text(strip=True)) > 10), None)
        if not title_link:
            return None
        title = title_link.get_text(strip=True)
        if "｜" in title:
            title = title.split("｜", 1)[0].strip()
        time_span = article.find("span", class_="hometimes")
        return {
            "title": title,
            "url": title_link["href"],
            "time": time_span.get_text(strip=True) if time_span else "",
        }

    # まず市況解説欄（hmml-mct）を優先。ただし数日更新がない場合は
    # 古い記事を出し続けないよう、新着一覧へフォールバックする。
    mkt_section = soup.find("div", class_="hmml-mct")
    if mkt_section:
        for article in mkt_section.find_all("div", class_="homelist-in"):
            entry = extract(article)
            if not entry or not entry["title"].startswith(keywords):
                continue
            published = parse_coinpost_time(entry["time"])
            if published is None or published >= now_jst() - timedelta(days=3):
                return entry
            print(f"[coinpost] market section is stale ({entry['time']}), falling back to latest list")
            break

    for article in soup.find_all("div", class_="homelist-in"):
        entry = extract(article)
        if entry and any(keyword in entry["title"] for keyword in keywords):
            return entry

    return None


def build_items(fetcher: HtmlFetcher) -> list[dict[str, Any]]:
    market_news = get_news_from_url(
        fetcher,
        "https://kabutan.jp/news/marketnews/?category=1",
        ["ダウ平均", "日経平均 大引け"],
    )
    fx_news = get_news_from_url(
        fetcher,
        "https://kabutan.jp/news/marketnews/?category=11",
        ["NY為替", "NY外為"],
    )
    crypto_news = get_crypto_news_from_coinpost(fetcher)

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
        # 「NY外為：円高値圏で…」のようにドル以外始まりの日もあるため、
        # 見出し接頭辞のみで判定し、ドル/円に触れている記事を採用する。
        if news["title"].startswith(("NY外為：", "NY為替：")) and ("ドル" in news["title"] or "円" in news["title"]):
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
    # display_date 等の全体タイムスタンプは市場データ更新の目印なので触らない
    # （上書きすると daily.yml の「本日更新済み」判定が誤動作する）。
    latest = load_json(LATEST_PATH, {})
    if not isinstance(latest, dict):
        latest = {}
    latest["news"] = news_payload
    write_json(LATEST_PATH, latest)


def main() -> None:
    fetcher = HtmlFetcher()
    try:
        items = build_items(fetcher)
    finally:
        fetcher.close()
    generated_at = now_jst()
    weekday = generated_at.weekday()
    post_text = build_post_text(items) if 1 <= weekday <= 5 else ""

    payload = {
        "generated_at": generated_at.isoformat(),
        "items": items,
        "post_text": post_text,
        "status": "ok" if items else "empty",
    }

    fetched = sorted({item["category"] for item in items})
    print(f"Fetched categories: {fetched or 'none'}")
    write_json(NEWS_PATH, payload)
    merge_into_latest(payload)
    print(f"Wrote {NEWS_PATH} and merged into {LATEST_PATH}")


if __name__ == "__main__":
    main()
