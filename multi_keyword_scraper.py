"""Run multiple Google Maps searches and combine results into one CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

from google_places_scraper import output_path, print_summary, save_csv, scrape


def read_keywords(arguments: list[str], keywords_file: str | None) -> list[str]:
    keywords = [keyword.strip() for keyword in arguments if keyword.strip()]
    if keywords_file:
        file_keywords = Path(keywords_file).read_text(encoding="utf-8-sig").splitlines()
        keywords.extend(keyword.strip() for keyword in file_keywords if keyword.strip())

    # ตัดคำซ้ำโดยรักษาลำดับเดิม
    return list(dict.fromkeys(keywords))


def main() -> None:
    parser = argparse.ArgumentParser(description="ค้นหา Google Maps หลาย keyword แล้วรวมเป็น CSV เดียว")
    parser.add_argument("keywords", nargs="*", help="คำค้นหาหนึ่งคำหรือหลายคำ")
    parser.add_argument("--keywords-file", help="ไฟล์ UTF-8 ที่มีหนึ่ง keyword ต่อหนึ่งบรรทัด")
    parser.add_argument("--limit", type=int, default=20, help="จำนวนสูงสุดต่อ keyword; 0 คือจนไม่มีรายการใหม่")
    parser.add_argument("--wait", type=float, default=8.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-wait", type=float, default=2.0)
    parser.add_argument("--profile", default=".chrome-profile")
    parser.add_argument("--output-dir", default="save_file")
    parser.add_argument("-o", "--output", help="ชื่อไฟล์รวม; ค่าเริ่มต้นใช้ timestamp_multi_keywords.csv")
    parser.add_argument("--keep-open", action="store_true", help="ค้าง Chrome หลัง keyword สุดท้าย")
    args = parser.parse_args()

    keywords = read_keywords(args.keywords, args.keywords_file)
    if not keywords:
        parser.error("กรุณาระบุ keyword หรือ --keywords-file")
    if args.limit < 0 or args.wait < 0 or args.retries < 1 or args.retry_wait < 0:
        parser.error("ค่าตัวเลขไม่ถูกต้อง")

    print(f"เริ่มค้นหา {len(keywords)} keyword")
    completed = 0
    all_rows: list[dict[str, str]] = []
    for index, keyword in enumerate(keywords, 1):
        print(f"\n=== Keyword {index}/{len(keywords)}: {keyword} ===")
        rows = scrape(
            keyword,
            args.limit,
            args.wait,
            args.profile,
            args.keep_open and index == len(keywords),
            args.retries,
            args.retry_wait,
        )
        print(f"Keyword นี้ได้ {len(rows)} รายการ")
        all_rows.extend(rows)
        completed += 1

    target = output_path("multi_keywords", args.output_dir, args.output)
    save_csv(all_rows, target)
    print(f"\nเสร็จทั้งหมด {completed}/{len(keywords)} keyword")
    print_summary(all_rows, target)


if __name__ == "__main__":
    main()
