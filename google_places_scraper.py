"""Scrape public business details from Google Maps and export to CSV.

The browser profile is persisted so consent/session state is retained. The script
does not solve or bypass CAPTCHA; when one appears the user must complete it.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


CAPTCHA_WORDS = ("captcha", "unusual traffic", "ตรวจพบการรับส่งข้อมูลที่ผิดปกติ")
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


def clean_text(value: str) -> str:
    return " ".join(value.split())


def safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return (value[:150] or "google_maps")


def output_path(query: str, output_dir: str, requested: str | None) -> Path:
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    date_text = datetime.now().strftime("%Y_%m_%d_%H-%M")
    filename = Path(requested).name if requested else f"{safe_filename(query)}_{date_text}.csv"
    if not filename.lower().endswith(".csv"):
        filename += ".csv"
    path = folder / filename
    counter = 2
    while path.exists():
        path = folder / f"{Path(filename).stem}_{counter}{Path(filename).suffix}"
        counter += 1
    return path


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


def wait_for_manual_check(driver) -> None:
    body = driver.find_element(By.TAG_NAME, "body").text.lower()
    if any(word in body for word in CAPTCHA_WORDS):
        print("พบ CAPTCHA: กรุณาแก้ด้วยตัวเองใน Chrome")
        input("เมื่อเห็นหน้า Google Maps ตามปกติแล้ว ให้กด Enter ที่ Terminal: ")


def collect_place_urls(driver, limit: int, wait_seconds: float) -> list[str]:
    wait = WebDriverWait(driver, max(10, int(wait_seconds)))
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/maps/place/"]')))
    except TimeoutException:
        wait_for_manual_check(driver)

    seen: set[str] = set()
    urls: list[str] = []
    stagnant = 0
    while (limit == 0 or len(urls) < limit) and stagnant < 5:
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


def scrape(
    query: str,
    limit: int,
    wait_seconds: float,
    profile_dir: str,
    keep_open: bool,
    retries: int,
    retry_wait: float,
) -> list[dict[str, str]]:
    options = Options()
    options.add_argument("--lang=th")
    options.add_argument("--window-size=1600,1100")
    options.add_argument(f"--user-data-dir={Path(profile_dir).resolve()}")
    driver = webdriver.Chrome(options=options)
    rows: list[dict[str, str]] = []
    try:
        search_url = "https://www.google.com/maps/search/" + quote(query, safe="") + "?hl=th"
        driver.get(search_url)
        time.sleep(wait_seconds)
        wait_for_manual_check(driver)
        place_urls = collect_place_urls(driver, limit, wait_seconds)
        print(f"พบลิงก์สถานที่ {len(place_urls)} รายการ")

        for rank, place_url in enumerate(place_urls, 1):
            for attempt in range(1, retries + 1):
                try:
                    driver.get(place_url)
                    WebDriverWait(driver, max(10, int(wait_seconds))).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "h1.DUwDvf, h1"))
                    )
                    time.sleep(0.7)
                    name = element_text(driver, "h1.DUwDvf") or element_text(driver, "h1")
                    address = item_text(driver, "address")
                    phone = item_text(driver, "phone")
                    category = element_text(driver, "button.DkEaL")
                    website = item_link(driver, "authority")
                    rating, review_count = rating_and_reviews(driver)
                    hours = opening_hours(driver)
                    postal_match = re.search(r"\b\d{5}\b", address)
                    latitude, longitude = coordinates_from_url(driver.current_url)
                    rows.append({
                        "query": query,
                        "rank": str(rank),
                        "business_name": name,
                        "tel": phone,
                        "website": website or "",
                        "category": category,
                        "rating": rating,
                        "review_count": review_count,
                        "price_level": element_text(driver, "span.mgr77e"),
                        "location": address,
                        "subdistrict": address_part(address, ("แขวง", "ตำบล", "ต.")),
                        "district": address_part(address, ("เขต", "อำเภอ", "อ.")),
                        "province": province_from_address(address),
                        "postal_code": postal_match.group(0) if postal_match else "",
                        "latitude": latitude,
                        "longitude": longitude,
                        "opening_hours": hours,
                        "business_status": item_text(driver, "oh"),
                        "plus_code": item_text(driver, "oloc"),
                        "description": element_text(driver, "div.WeS02d, div.PYvSYb"),
                        "service_options": element_text(driver, "div.iP2t7d, div.LBgpqf"),
                        "booking_url": item_link(driver, "appointment") or item_link(driver, "reservation"),
                        "menu_url": item_link(driver, "menu"),
                        "order_url": item_link(driver, "order"),
                        "visible_reviews_json": visible_reviews(driver),
                        "visible_photo_urls_json": visible_photo_urls(driver),
                        "raw_details_json": raw_item_details(driver),
                        "google_maps_url": driver.current_url,
                    })
                    print(f"[{rank}/{len(place_urls)}] {name}")
                    break
                except (StaleElementReferenceException, TimeoutException, WebDriverException) as error:
                    if attempt < retries:
                        delay = retry_wait * attempt
                        print(
                            f"[{rank}/{len(place_urls)}] {type(error).__name__} "
                            f"- retry {attempt}/{retries - 1} ใน {delay:g} วินาที"
                        )
                        time.sleep(delay)
                    else:
                        print(
                            f"[{rank}/{len(place_urls)}] ข้ามหลัง retry {retries} ครั้ง: "
                            f"{type(error).__name__}"
                        )
    finally:
        if keep_open:
            input("เสร็จแล้ว กด Enter เพื่อปิด Chrome: ")
        driver.quit()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Google Maps business data แล้ว export CSV")
    parser.add_argument("query", nargs="?", default="คลินิกเสริมความงาม สีลม")
    parser.add_argument("-o", "--output", help="ชื่อไฟล์เพิ่มเติม; ค่าเริ่มต้นใช้ชื่อคำค้นหา+วันที่")
    parser.add_argument("--output-dir", default="save_file", help="โฟลเดอร์สำหรับเก็บ CSV")
    parser.add_argument("--limit", type=int, default=20, help="จำนวนสูงสุด; ใช้ 0 เพื่อดึงจนไม่มีรายการใหม่")
    parser.add_argument("--wait", type=float, default=8.0)
    parser.add_argument("--profile", default=".chrome-profile", help="โฟลเดอร์เก็บ browser session")
    parser.add_argument("--keep-open", action="store_true", help="ค้าง Chrome ไว้จนกว่าจะกด Enter")
    parser.add_argument("--retries", type=int, default=3, help="จำนวนครั้งสูงสุดต่อรายการ")
    parser.add_argument("--retry-wait", type=float, default=2.0, help="เวลารอก่อน retry เป็นวินาที")
    args = parser.parse_args()
    if args.limit < 0 or args.wait < 0 or args.retries < 1 or args.retry_wait < 0:
        parser.error("ค่าตัวเลขไม่ถูกต้อง: retries ต้องอย่างน้อย 1 และค่าเวลา/limit ต้องไม่ติดลบ")

    rows = scrape(
        args.query, args.limit, args.wait, args.profile, args.keep_open,
        args.retries, args.retry_wait,
    )
    target = output_path(args.query, args.output_dir, args.output)
    fields = [
        "query", "rank", "business_name", "tel", "website", "category",
        "rating", "review_count", "price_level", "location", "subdistrict",
        "district", "province", "postal_code", "latitude", "longitude",
        "opening_hours", "business_status", "plus_code", "description",
        "service_options", "booking_url", "menu_url", "order_url",
        "visible_reviews_json", "visible_photo_urls_json", "raw_details_json",
        "google_maps_url",
    ]
    with open(target, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"บันทึกแล้ว {len(rows)} รายการ -> {target}")
    print("สรุป:")
    print(f"  มีเบอร์โทร: {sum(bool(row['tel']) for row in rows)}")
    print(f"  มีเว็บไซต์: {sum(bool(row['website']) for row in rows)}")
    print(f"  มีหมวดหมู่: {sum(bool(row['category']) for row in rows)}")
    print(f"  มีที่อยู่: {sum(bool(row['location']) for row in rows)}")
    print(f"  มีจังหวัด: {sum(bool(row['province']) for row in rows)}")


if __name__ == "__main__":
    main()
