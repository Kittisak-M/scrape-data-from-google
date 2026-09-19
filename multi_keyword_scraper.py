"""Run multiple Google Maps searches and combine results into one CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

from google_places_scraper import (
    available_captcha_profiles,
    append_csv_row,
    autosave_paths,
    initialize_csv,
    output_path,
    print_summary,
    scrape,
)


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
    parser.add_argument("--captcha-profiles", nargs="+", help="profile สำรองที่จะสลับไปเมื่อพบ CAPTCHA")
    parser.add_argument("--output-dir", default="save_file")
    parser.add_argument("-o", "--output", help="ชื่อไฟล์รวม; ค่าเริ่มต้นใช้ timestamp_multi_keywords.csv")
    parser.add_argument("--keep-open", action="store_true", help="ค้าง Chrome หลัง keyword สุดท้าย")
    args = parser.parse_args()

    keywords = read_keywords(args.keywords, args.keywords_file)
    if not keywords:
        parser.error("กรุณาระบุ keyword หรือ --keywords-file")
    if args.limit < 0 or args.wait < 0 or args.retries < 1 or args.retry_wait < 0:
        parser.error("ค่าตัวเลขไม่ถูกต้อง")

    captcha_profiles = (
        args.captcha_profiles if args.captcha_profiles is not None
        else available_captcha_profiles(args.profile)
    )

    print(f"เริ่มค้นหา {len(keywords)} keyword")
    completed = 0
    profiles = list(dict.fromkeys([args.profile, *captcha_profiles]))
    active_profile = profiles[0]
    all_rows: list[dict[str, str]] = []
    keyword_summaries: list[str] = []
    all_timings: list[float] = []
    complete = True
    final_target, partial_target = autosave_paths(
        output_path("multi_keywords", args.output_dir, args.output)
    )
    initialize_csv(partial_target)

    def autosave(row: dict[str, str]) -> None:
        append_csv_row(row, partial_target)
        all_rows.append(row)

    def mark_failure(_error_name: str) -> None:
        nonlocal complete
        complete = False

    def profile_changed(profile: str) -> None:
        nonlocal active_profile
        active_profile = profile

    try:
        for index, keyword in enumerate(keywords, 1):
            print(f"\n=== Keyword {index}/{len(keywords)}: {keyword} ===")
            found = 0
            keyword_failed = False
            keyword_timings: list[float] = []

            def keyword_failure(error_name: str) -> None:
                nonlocal keyword_failed
                keyword_failed = True
                mark_failure(error_name)

            def keyword_complete(succeeded: int, discovered: int) -> None:
                nonlocal found
                found = discovered

            def item_finished(elapsed: float, _success: bool) -> None:
                keyword_timings.append(elapsed)
                all_timings.append(elapsed)

            try:
                rows = scrape(
                    query=keyword,
                    limit=args.limit,
                    wait_seconds=args.wait,
                    profile_dir=active_profile,
                    keep_open=args.keep_open and index == len(keywords),
                    retries=args.retries,
                    retry_wait=args.retry_wait,
                    on_row=autosave,
                    on_failure=keyword_failure,
                    on_complete=keyword_complete,
                    on_item_finished=item_finished,
                    captcha_profiles=profiles[profiles.index(active_profile) + 1:],
                    on_profile_change=profile_changed,
                )
            except Exception as error:
                complete = False
                keyword_summaries.append(
                    f'❌ Keyword "{keyword}" incomplete 0/? ({type(error).__name__})'
                )
                continue
            status = "✅" if not keyword_failed and len(rows) == found else "❌"
            label = "complete" if status == "✅" else "incomplete"
            average = sum(keyword_timings) / len(keyword_timings) if keyword_timings else 0
            keyword_summaries.append(
                f'{status} Keyword "{keyword}" {label} {len(rows)}/{found} '
                f"| เวลาเฉลี่ย {average:.2f} วินาที/รายการ"
            )
            completed += 1
    except KeyboardInterrupt:
        complete = False
        print("\nหยุดด้วย Ctrl+C — เก็บข้อมูลที่บันทึกสำเร็จแล้วไว้ให้")

    target = partial_target
    if complete and completed == len(keywords):
        partial_target.replace(final_target)
        target = final_target
    else:
        print("การ scrape ไม่สมบูรณ์ ไฟล์จึงลงท้ายด้วย _partial.csv")
    try:
        print(f"\nเสร็จทั้งหมด {completed}/{len(keywords)} keyword")
        print_summary(all_rows, target)
        print("\nสรุปแต่ละ keyword:")
        for summary in keyword_summaries:
            print(summary)
        if all_timings:
            print(f"เวลาเฉลี่ยรวม: {sum(all_timings) / len(all_timings):.2f} วินาที/รายการ")
    except KeyboardInterrupt:
        print("\nหยุดการแสดงสรุปแล้ว — ไฟล์ CSV ถูกบันทึกไว้แล้ว")


if __name__ == "__main__":
    main()
