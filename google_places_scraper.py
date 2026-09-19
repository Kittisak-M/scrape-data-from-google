"""Scrape public business details from Google Maps and export to CSV.

The browser profile is persisted so consent/session state is retained. The script
does not solve or bypass CAPTCHA; when one appears the user must complete it.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def configure_terminal_output() -> None:
    """Keep Thai CLI output from failing on Windows legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


configure_terminal_output()


CAPTCHA_WORDS = (
    "captcha",
    "recaptcha",
    "unusual traffic",
    "our systems have detected unusual traffic",
    "verify that you're not a robot",
    "ตรวจพบการรับส่งข้อมูลที่ผิดปกติ",
    "โปรดยืนยันว่าคุณไม่ใช่โปรแกรมอัตโนมัติ",
)


class CaptchaDetected(Exception):
    """Signal that another browser profile can be tried for this page."""


PROVINCES = (
    "กรุงเทพมหานคร", "กระบี่", "กาญจนบุรี", "กาฬสินธุ์", "กำแพงเพชร", "ขอนแก่น",
    "จันทบุรี", "ฉะเชิงเทรา", "ชลบุรี", "ชัยนาท", "ชัยภูมิ", "ชุมพร", "เชียงราย",
    "เชียงใหม่", "ตรัง", "ตราด", "ตาก", "นครนายก", "นครปฐม", "นครพนม",
    "นครราชสีมา", "นครศรีธรรมราช", "นครสวรรค์", "นนทบุรี", "นราธิวาส", "น่าน",
    "บึงกาฬ", "บุรีรัมย์", "ปทุมธานี", "ประจวบคีรีขันธ์", "ปราจีนบุรี", "ปัตตานี",
    "พระนครศรีอยุธยา", "พะเยา", "พังงา", "พัทลุง", "พิจิตร", "พิษณุโลก",
    "เพชรบุรี", "เพชรบูรณ์", "แพร่", "ภูเก็ต", "มหาสารคาม", "มุกดาหาร",
    "แม่ฮ่องสอน", "ยโสธร", "ยะลา", "ร้อยเอ็ด", "ระนอง", "ระยอง", "ราชบุรี",
    "ลพบุรี", "ลำปาง", "ลำพูน", "เลย", "ศรีสะเกษ", "สกลนคร", "สงขลา",
    "สตูล", "สมุทรปราการ", "สมุทรสงคราม", "สมุทรสาคร", "สระแก้ว", "สระบุรี",
    "สิงห์บุรี", "สุโขทัย", "สุพรรณบุรี", "สุราษฎร์ธานี", "สุรินทร์", "หนองคาย",
    "หนองบัวลำภู", "อ่างทอง", "อำนาจเจริญ", "อุดรธานี", "อุตรดิตถ์", "อุทัยธานี",
    "อุบลราชธานี",
)

CSV_FIELDS = [
    "query", "business_name", "tel", "website", "raw_category",
    "rating", "review_count", "price_level", "subdistrict", "district",
    "province", "postal_code", "latitude", "longitude", "google_maps_url",
    "scraped_at",
]


def clean_text(value: str) -> str:
    return " ".join(value.split())


def safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return (value[:150] or "google_maps")


def available_captcha_profiles(profile_dir: str) -> list[str]:
    """Find higher-numbered Chrome profiles beside the active profile."""
    current = Path(profile_dir)
    match = re.fullmatch(r"\.chrome-profile(?:-(\d+))?", current.name)
    if not match:
        return []
    current_number = int(match.group(1) or 0)
    candidates: list[tuple[int, str]] = []
    for path in current.parent.glob(".chrome-profile-*"):
        suffix = re.fullmatch(r"\.chrome-profile-(\d+)", path.name)
        if path.is_dir() and suffix and int(suffix.group(1)) > current_number:
            candidates.append((int(suffix.group(1)), str(path)))
    return [path for _, path in sorted(candidates)]


def output_path(query: str, output_dir: str, requested: str | None) -> Path:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    date_text = datetime.now().strftime("%Y_%m_%d_%H-%M")
    filename = Path(requested).name if requested else f"{date_text}_{safe_filename(query)}.csv"
    if not filename.lower().endswith(".csv"):
        filename += ".csv"
    path = folder / filename
    counter = 2
    while path.exists():
        path = folder / f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
        counter += 1
    return path


def save_csv(rows: list[dict[str, str]], target: Path) -> None:
    with open(target, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def autosave_paths(target: Path) -> tuple[Path, Path]:
    """Return unused final/partial names without overwriting an older run."""
    original_stem = target.stem
    counter = 2
    while True:
        partial = target.with_name(f"{target.stem}_partial{target.suffix}")
        if not target.exists() and not partial.exists():
            return target, partial
        target = target.with_name(f"{original_stem}_{counter}{target.suffix}")
        counter += 1


def initialize_csv(target: Path) -> None:
    save_csv([], target)


def append_csv_row(row: dict[str, str], target: Path) -> None:
    """Append one completed record so earlier records survive an interruption."""
    with open(target, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writerow(row)


def print_summary(rows: list[dict[str, str]], target: Path) -> None:
    print(f"บันทึกแล้ว {len(rows)} รายการ -> {target}")
    print("สรุป:")
    print(f"  มีเบอร์โทร: {sum(bool(row['tel']) for row in rows)}")
    print(f"  มีเว็บไซต์: {sum(bool(row['website']) for row in rows)}")
    print(f"  มีหมวดหมู่: {sum(bool(row['raw_category']) for row in rows)}")
    print(f"  มีที่อยู่: {sum(bool(row['location']) for row in rows)}")
    print(f"  มีจังหวัด: {sum(bool(row['province']) for row in rows)}")


def element_text(driver, selector: str) -> str:
    for _ in range(3):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            return clean_text(elements[0].text) if elements else ""
        except StaleElementReferenceException:
            time.sleep(0.2)
    return ""


def item_text(driver, item_id_prefix: str) -> str:
    value = element_text(driver, f'[data-item-id^="{item_id_prefix}"] .Io6YTe')
    if value:
        return value
    for _ in range(3):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, f'[data-item-id^="{item_id_prefix}"]')
            if not elements:
                return ""
            return clean_text(elements[0].get_attribute("aria-label") or elements[0].text)
        except StaleElementReferenceException:
            time.sleep(0.2)
    return ""


def item_link(driver, item_id_prefix: str) -> str:
    for _ in range(3):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, f'a[data-item-id^="{item_id_prefix}"]')
            return (elements[0].get_attribute("href") or "") if elements else ""
        except StaleElementReferenceException:
            time.sleep(0.2)
    return ""


def address_part(address: str, labels: tuple[str, ...]) -> str:
    alternatives = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:{alternatives})\s*([^,\s]+(?:\s+[^,\d]+)?)", address)
    return clean_text(match.group(1)) if match else ""


def first_address_word(value: str) -> str:
    """ใช้ชื่อแขวง/ตำบลส่วนแรก เมื่อ Google Maps ต่อข้อความพื้นที่ถัดไปมาให้"""
    return value.split(maxsplit=1)[0] if value else ""


def rating_and_reviews(driver) -> tuple[str, str]:
    block = element_text(driver, "div.F7nice")
    rating_match = re.search(r"\b([0-5](?:[.,]\d)?)\b", block)
    reviews_match = re.search(r"\(([\d,.]+[KkMm]?)\)", block)
    rating = rating_match.group(1).replace(",", ".") if rating_match else ""
    reviews = reviews_match.group(1) if reviews_match else ""
    return rating, reviews


def opening_hours(driver) -> str:
    buttons = driver.find_elements(By.CSS_SELECTOR, '[data-item-id^="oh"]')
    if not buttons:
        return ""
    summary = clean_text(buttons[0].get_attribute("aria-label") or buttons[0].text)
    try:
        buttons[0].click()
        time.sleep(0.3)
        rows = [clean_text(row.text) for row in driver.find_elements(By.CSS_SELECTOR, "table.eK4R0e tr")]
        rows = [row for row in rows if row]
        return " | ".join(rows) if rows else summary
    except WebDriverException:
        return summary


def raw_item_details(driver) -> str:
    details: dict[str, str] = {}
    for element in driver.find_elements(By.CSS_SELECTOR, "[data-item-id]"):
        try:
            key = element.get_attribute("data-item-id") or ""
            value = clean_text(element.get_attribute("aria-label") or element.text)
            if key and value and key not in details:
                details[key] = value
        except StaleElementReferenceException:
            continue
    return json.dumps(details, ensure_ascii=False)


def visible_reviews(driver) -> str:
    reviews = []
    for element in driver.find_elements(By.CSS_SELECTOR, "span.wiI7pd, div.MyEned"):
        try:
            value = clean_text(element.text)
            if value and value not in reviews:
                reviews.append(value)
        except StaleElementReferenceException:
            continue
    return json.dumps(reviews, ensure_ascii=False)


def visible_photo_urls(driver) -> str:
    urls = []
    for image in driver.find_elements(By.CSS_SELECTOR, "img[src]"):
        try:
            src = image.get_attribute("src") or ""
            if src.startswith("http") and src not in urls and "googleusercontent" in src:
                urls.append(src)
        except StaleElementReferenceException:
            continue
    return json.dumps(urls[:30], ensure_ascii=False)


def province_from_address(address: str) -> str:
    for province in PROVINCES:
        if province in address:
            return province
    if "Bangkok" in address:
        return "กรุงเทพมหานคร"
    match = re.search(r"(?:จังหวัด|จ\.)\s*([^\s,]+)", address)
    return match.group(1) if match else ""


def coordinates_from_url(url: str) -> tuple[str, str]:
    match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if not match:
        match = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url)
    return (match.group(1), match.group(2)) if match else ("", "")


def page_has_captcha(driver) -> bool:
    url = driver.current_url.lower()
    if "/sorry/" in url:
        return True
    if any(frame.is_displayed() for frame in driver.find_elements(
        By.CSS_SELECTOR, 'iframe[src*="recaptcha"], iframe[src*="hcaptcha"]'
    )):
        return True
    body = driver.find_element(By.TAG_NAME, "body").text.lower()
    return any(word in body for word in CAPTCHA_WORDS)


def wait_for_manual_check(driver, rotate_on_captcha: bool = False) -> bool:
    """Pause until the user has manually completed a CAPTCHA in Chrome."""
    detected = False
    while page_has_captcha(driver):
        if rotate_on_captcha:
            raise CaptchaDetected
        detected = True
        print("พบ CAPTCHA: โปรแกรมหยุดรอ กรุณาแก้ด้วยตัวเองใน Chrome")
        input("เมื่อเห็นหน้า Google Maps ตามปกติแล้ว ให้กด Enter ที่ Terminal: ")
        time.sleep(2)
    if detected:
        print("CAPTCHA ผ่านแล้ว ทำงานต่อ")
    return detected


def collect_place_urls(
    driver, limit: int, wait_seconds: float, rotate_on_captcha: bool = False
) -> list[str]:
    wait = WebDriverWait(driver, max(10, int(wait_seconds)))
    try:
        wait.until(lambda page: page_has_captcha(page) or page.find_elements(
            By.CSS_SELECTOR, 'a[href*="/maps/place/"]'
        ))
    except TimeoutException:
        pass
    if wait_for_manual_check(driver, rotate_on_captcha):
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/maps/place/"]')))
        except TimeoutException:
            pass

    seen: set[str] = set()
    urls: list[str] = []
    stagnant = 0
    while (limit == 0 or len(urls) < limit) and stagnant < 5:
        wait_for_manual_check(driver, rotate_on_captcha)
        previous = len(urls)
        for anchor in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/maps/place/"]'):
            href = anchor.get_attribute("href") or ""
            if href and href not in seen:
                seen.add(href)
                urls.append(href)
                if limit > 0 and len(urls) >= limit:
                    break
        if limit > 0 and len(urls) >= limit:
            break
        feeds = driver.find_elements(By.CSS_SELECTOR, 'div[role="feed"]')
        if not feeds:
            break
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", feeds[0])
        time.sleep(1.5)
        stagnant = stagnant + 1 if len(urls) == previous else 0
    return urls if limit == 0 else urls[:limit]


def wait_for_place_details(
    driver, wait_seconds: float, rotate_on_captcha: bool = False
) -> None:
    """Wait only until at least one optional business detail is available."""
    try:
        WebDriverWait(driver, max(3, min(8, int(wait_seconds))), poll_frequency=0.2).until(
            lambda page: page_has_captcha(page) or page.find_elements(
                By.CSS_SELECTOR,
                '[data-item-id^="address"], [data-item-id^="phone"], '
                'a[data-item-id^="authority"]',
            )
        )
    except TimeoutException:
        # Some listings omit address, phone, and website. Keep the row instead of skipping it.
        return
    wait_for_manual_check(driver, rotate_on_captcha)


def scrape(
    query: str,
    limit: int,
    wait_seconds: float,
    profile_dir: str,
    keep_open: bool,
    retries: int,
    retry_wait: float,
    on_row: Callable[[dict[str, str]], None] | None = None,
    on_failure: Callable[[str], None] | None = None,
    on_complete: Callable[[int, int], None] | None = None,
    on_item_finished: Callable[[float, bool], None] | None = None,
    captcha_profiles: list[str] | None = None,
    on_profile_change: Callable[[str], None] | None = None,
) -> list[dict[str, str]]:
    profiles = list(dict.fromkeys([profile_dir, *(captcha_profiles or [])]))
    profile_index = 0
    if len(profiles) > 1:
        print(f"Chrome profile: {profiles[0]} | CAPTCHA สำรอง: {', '.join(profiles[1:])}")
    else:
        print(f"Chrome profile: {profiles[0]} | ไม่มี profile สำรอง; พบ CAPTCHA แล้วจะรอให้แก้เอง")

    def open_browser(profile: str):
        options = Options()
        options.add_argument("--lang=th")
        options.add_argument("--window-size=1600,1100")
        options.add_argument(f"--user-data-dir={Path(profile).resolve()}")
        return webdriver.Chrome(options=options)

    driver = open_browser(profiles[profile_index])

    def rotate_profile() -> None:
        nonlocal driver, profile_index
        try:
            driver.quit()
        except (ConnectionResetError, WebDriverException):
            pass
        profile_index += 1
        profile = profiles[profile_index]
        print(f"พบ CAPTCHA — เปลี่ยน Chrome profile เป็น {profile}")
        driver = open_browser(profile)
        if on_profile_change:
            on_profile_change(profile)

    rows: list[dict[str, str]] = []
    try:
        search_url = "https://www.google.com/maps/search/" + quote(query, safe="") + "?hl=th"
        while True:
            try:
                driver.get(search_url)
                rotate = profile_index < len(profiles) - 1
                place_urls = collect_place_urls(driver, limit, wait_seconds, rotate)
                break
            except CaptchaDetected:
                rotate_profile()
        print(f"พบลิงก์สถานที่ {len(place_urls)} รายการ")

        for rank, place_url in enumerate(place_urls, 1):
            item_started = time.perf_counter()
            attempt = 1
            while attempt <= retries:
                try:
                    driver.get(place_url)
                    WebDriverWait(driver, max(10, int(wait_seconds))).until(
                        lambda page: page_has_captcha(page) or page.find_elements(
                            By.CSS_SELECTOR, "h1.DUwDvf, h1"
                        )
                    )
                    wait_for_manual_check(driver, profile_index < len(profiles) - 1)
                    WebDriverWait(driver, max(10, int(wait_seconds))).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "h1.DUwDvf, h1"))
                    )
                    wait_for_place_details(
                        driver,
                        wait_seconds,
                        profile_index < len(profiles) - 1,
                    )
                    name = element_text(driver, "h1.DUwDvf") or element_text(driver, "h1")
                    if not name:
                        wait_for_manual_check(driver, profile_index < len(profiles) - 1)
                        raise TimeoutException("ไม่พบชื่อธุรกิจในหน้าสถานที่")
                    address = item_text(driver, "address")
                    phone = item_text(driver, "phone")
                    raw_category = element_text(driver, "button.DkEaL")
                    website = item_link(driver, "authority")
                    rating, review_count = rating_and_reviews(driver)
                    postal_match = re.search(r"\b\d{5}\b", address)
                    latitude, longitude = coordinates_from_url(driver.current_url)
                    row = {
                        "query": query,
                        "rank": str(rank),
                        "business_name": name,
                        "tel": phone,
                        "website": website or "",
                        "raw_category": raw_category,
                        "rating": rating,
                        "review_count": review_count,
                        "price_level": element_text(driver, "span.mgr77e"),
                        "location": address,
                        "subdistrict": first_address_word(address_part(address, ("แขวง", "ตำบล", "ต."))),
                        "district": address_part(address, ("เขต", "อำเภอ", "อ.")),
                        "province": province_from_address(address),
                        "postal_code": postal_match.group(0) if postal_match else "",
                        "latitude": latitude,
                        "longitude": longitude,
                        "google_maps_url": driver.current_url,
                        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    }
                    wait_for_manual_check(driver, profile_index < len(profiles) - 1)
                    rows.append(row)
                    if on_row:
                        on_row(row)
                    elapsed = time.perf_counter() - item_started
                    if on_item_finished:
                        on_item_finished(elapsed, True)
                    print(
                        f"[{rank}/{len(place_urls)}] {name} "
                        f"| ใช้เวลา {elapsed:.2f} วินาที"
                    )
                    break
                except CaptchaDetected:
                    rotate_profile()
                    print(f"[{rank}/{len(place_urls)}] เปิดรายการเดิมอีกครั้ง")
                except (ConnectionResetError, StaleElementReferenceException, TimeoutException, WebDriverException) as error:
                    if attempt < retries:
                        delay = retry_wait * attempt
                        print(
                            f"[{rank}/{len(place_urls)}] {type(error).__name__} "
                            f"- retry {attempt}/{retries - 1} ใน {delay:g} วินาที"
                        )
                        time.sleep(delay)
                    else:
                        elapsed = time.perf_counter() - item_started
                        print(
                            f"[{rank}/{len(place_urls)}] ข้ามหลัง retry {retries} ครั้ง: "
                            f"{type(error).__name__} | ใช้เวลา {elapsed:.2f} วินาที"
                        )
                        if on_item_finished:
                            on_item_finished(elapsed, False)
                        if on_failure:
                            on_failure(type(error).__name__)
                    attempt += 1
        if on_complete:
            on_complete(len(rows), len(place_urls))
    finally:
        if keep_open:
            input("เสร็จแล้ว กด Enter เพื่อปิด Chrome: ")
        try:
            driver.quit()
        except (ConnectionResetError, WebDriverException):
            # Chrome/ChromeDriver may already have exited after a network reset.
            pass
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Google Maps business data แล้ว export CSV")
    parser.add_argument("query", nargs="?", default="คลินิกเสริมความงาม สีลม")
    parser.add_argument("-o", "--output", help="ชื่อไฟล์เพิ่มเติม; ค่าเริ่มต้นใช้ชื่อคำค้นหา+วันที่")
    parser.add_argument("--output-dir", default="save_file", help="โฟลเดอร์สำหรับเก็บ CSV")
    parser.add_argument("--limit", type=int, default=20, help="จำนวนสูงสุด; ใช้ 0 เพื่อดึงจนไม่มีรายการใหม่")
    parser.add_argument("--wait", type=float, default=8.0)
    parser.add_argument("--profile", default=".chrome-profile", help="โฟลเดอร์เก็บ browser session")
    parser.add_argument("--captcha-profiles", nargs="+", help="profile สำรองที่จะสลับไปเมื่อพบ CAPTCHA")
    parser.add_argument("--keep-open", action="store_true", help="ค้าง Chrome ไว้จนกว่าจะกด Enter")
    parser.add_argument("--retries", type=int, default=3, help="จำนวนครั้งสูงสุดต่อรายการ")
    parser.add_argument("--retry-wait", type=float, default=2.0, help="เวลารอก่อน retry เป็นวินาที")
    args = parser.parse_args()
    if args.limit < 0 or args.wait < 0 or args.retries < 1 or args.retry_wait < 0:
        parser.error("ค่าตัวเลขไม่ถูกต้อง: retries ต้องอย่างน้อย 1 และค่าเวลา/limit ต้องไม่ติดลบ")

    captcha_profiles = (
        args.captcha_profiles if args.captcha_profiles is not None
        else available_captcha_profiles(args.profile)
    )

    final_target, partial_target = autosave_paths(
        output_path(args.query, args.output_dir, args.output)
    )
    initialize_csv(partial_target)
    rows: list[dict[str, str]] = []
    item_timings: list[float] = []
    complete = True

    def autosave(row: dict[str, str]) -> None:
        append_csv_row(row, partial_target)
        rows.append(row)

    def mark_failure(_error_name: str) -> None:
        nonlocal complete
        complete = False

    def item_finished(elapsed: float, _success: bool) -> None:
        item_timings.append(elapsed)

    try:
        scrape(
            query=args.query,
            limit=args.limit,
            wait_seconds=args.wait,
            profile_dir=args.profile,
            keep_open=args.keep_open,
            retries=args.retries,
            retry_wait=args.retry_wait,
            on_row=autosave,
            on_failure=mark_failure,
            on_item_finished=item_finished,
            captcha_profiles=captcha_profiles,
        )
    except KeyboardInterrupt:
        complete = False
        print("\nหยุดด้วย Ctrl+C — เก็บข้อมูลที่บันทึกสำเร็จแล้วไว้ให้")
    except Exception as error:
        complete = False
        print(f"\nเกิด error: {type(error).__name__}: {error}")

    target = partial_target
    if complete:
        partial_target.replace(final_target)
        target = final_target
    else:
        print("การ scrape ไม่สมบูรณ์ ไฟล์จึงลงท้ายด้วย _partial.csv")
    print_summary(rows, target)
    if item_timings:
        print(f"เวลาเฉลี่ย: {sum(item_timings) / len(item_timings):.2f} วินาที/รายการ")


if __name__ == "__main__":
    main()
