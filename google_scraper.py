"""ค้นหาผลลัพธ์จาก Google และ export เป็น CSV

หมายเหตุ: Google อาจแสดง CAPTCHA หรือเปลี่ยนโครงสร้าง HTML ได้ ควรใช้ API
อย่างเป็นทางการสำหรับงานปริมาณมาก และอย่าใช้สคริปต์นี้เพื่อหลบข้อจำกัดของบริการ
"""

from __future__ import annotations

import argparse
import csv
import random
import time
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup


@dataclass
class SearchResult:
    query: str
    rank: int
    title: str
    url: str
    description: str


def clean_google_url(href: str) -> str | None:
    """แปลงลิงก์ redirect ของ Google ให้เป็น URL ปลายทาง"""
    if not href:
        return None
    if href.startswith("/url?"):
        redirect_params = parse_qs(urlparse(href).query)
        target = (redirect_params.get("q") or redirect_params.get("url") or [None])[0]
        return unquote(target) if target else None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return None


def parse_results(html: str, query: str, start_rank: int = 1) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []
    seen: set[str] = set()

    # Google เปลี่ยน class ของ result อยู่บ่อย จึงเริ่มจาก h3 ซึ่งคงที่กว่า
    title_nodes = soup.select("div.MjjYud h3, div.g h3, h3")
    for title_node in title_nodes:
        link = title_node.find_parent("a", href=True)
        if not link:
            # fallback: บางหน้าใส่ h3 ไว้ใน container ที่มี anchor อยู่ระดับบน
            parent = title_node.parent
            link = parent.select_one("a[href]") if parent else None
        url = clean_google_url(link.get("href", "")) if link else None
        if not url or not title_node or url in seen:
            continue
        # ตัดลิงก์ภายใน Google และองค์ประกอบที่ไม่ใช่ผลค้นหา
        host = urlparse(url).netloc.lower()
        if "google." in host or url.startswith("javascript:"):
            continue
        container = title_node
        for _ in range(4):
            if container.parent:
                container = container.parent
        description = " ".join(
            node.get_text(" ", strip=True)
            for node in container.select("div.VwiC3b, div[data-sncf], span.aCOpRe")
        )
        seen.add(url)
        results.append(
            SearchResult(
                query=query,
                rank=start_rank + len(results),
                title=title_node.get_text(" ", strip=True),
                url=url,
                description=description,
            )
        )
    return results


def search_google(
    session: requests.Session,
    query: str,
    pages: int,
    delay: float,
    base_url: str = "https://www.google.com/search",
) -> Iterable[SearchResult]:
    all_seen: set[str] = set()
    for page in range(pages):
        params = {"q": query, "start": page * 10, "num": 10, "hl": "th"}
        # ถ้าได้รับ Google URL มา ให้คง query parameters ที่เกี่ยวข้องกับรูปแบบผลลัพธ์ไว้
        if page == 0 and base_url != "https://www.google.com/search":
            original = parse_qs(urlparse(base_url).query)
            for key in ("udm", "tbm", "gl", "hl"):
                if original.get(key):
                    params[key] = original[key][0]
        response = session.get("https://www.google.com/search", params=params, timeout=20)
        response.raise_for_status()
        if "unusual traffic" in response.text.lower() or "captcha" in response.url.lower():
            raise RuntimeError("Google ขอให้ยืนยัน CAPTCHA/ตรวจพบ unusual traffic; หยุดการทำงานแล้ว")

        for result in parse_results(response.text, query, start_rank=page * 10 + 1):
            if result.url not in all_seen:
                all_seen.add(result.url)
                yield result
        if page < pages - 1:
            time.sleep(delay + random.uniform(0, max(0.0, delay * 0.25)))


def main() -> None:
    parser = argparse.ArgumentParser(description="ค้นหาผลลัพธ์จาก Google แล้ว export เป็น CSV")
    parser.add_argument("queries", nargs="*", help="คำค้นหา เช่น 'ร้านกาแฟ กรุงเทพ'")
    parser.add_argument("--url", help="Google search URL; ระบบจะอ่าน keyword จากพารามิเตอร์ q")
    parser.add_argument("-o", "--output", default="google_results.csv", help="ชื่อไฟล์ CSV ปลายทาง")
    parser.add_argument("-p", "--pages", type=int, default=1, help="จำนวนหน้าต่อ keyword (ค่าเริ่มต้น: 1)")
    parser.add_argument("--delay", type=float, default=3.0, help="เวลาหน่วงระหว่างหน้าเป็นวินาที")
    args = parser.parse_args()
    if bool(args.queries) == bool(args.url):
        parser.error("ต้องระบุ keyword หรือ --url อย่างใดอย่างหนึ่ง")
    if args.pages < 1 or args.delay < 0:
        parser.error("--pages ต้องไม่น้อยกว่า 1 และ --delay ต้องไม่ติดลบ")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
    })
    rows: list[SearchResult] = []
    queries = args.queries
    base_url = "https://www.google.com/search"
    if args.url:
        parsed = urlparse(args.url)
        if parsed.scheme not in {"http", "https"} or "google." not in parsed.netloc.lower():
            parser.error("--url ต้องเป็น URL ของ Google")
        query = parse_qs(parsed.query).get("q", [""])[0]
        if not query:
            parser.error("ไม่พบพารามิเตอร์ q ใน Google URL")
        queries = [query]
        base_url = args.url

    for query in queries:
        print(f"กำลังค้นหา: {query}")
        rows.extend(search_google(session, query, args.pages, args.delay, base_url))

    with open(args.output, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(asdict(rows[0]).keys()) if rows else ["query", "rank", "title", "url", "description"])
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    print(f"บันทึกแล้ว {len(rows)} รายการ -> {args.output}")


if __name__ == "__main__":
    main()
