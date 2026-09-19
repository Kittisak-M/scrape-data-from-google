# Google Maps Business Scraper

สคริปต์ Python สำหรับค้นหาธุรกิจจาก Google Maps อ่านรายละเอียดที่แสดงบนหน้าเว็บด้วย Selenium และบันทึกเป็นไฟล์ CSV

## สิ่งที่ต้องมี

- Python 3.10 ขึ้นไป
- Google Chrome
- อินเทอร์เน็ต

## ติดตั้งครั้งแรก

เปิด PowerShell แล้วเข้าโฟลเดอร์ที่ clone โปรเจกต์ไว้ (แก้ `path\to` ให้ตรงกับเครื่องของคุณ):

```powershell
cd "path\to\scrape-data-from-google"
```

สร้าง virtual environment และติดตั้งแพ็กเกจ:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

ครั้งต่อไปให้เปิดใช้งาน environment ก่อนรัน:

```powershell
.\.venv\Scripts\Activate.ps1
```

## วิธีใช้งานแบบแนะนำ

ตัวอย่างค้นหา `คลินิกเสริมความงาม สีลม` และดึงต่อเนื่องจนไม่มีรายการใหม่:

```powershell
python google_places_scraper.py `
  "คลินิกเสริมความงาม สีลม" `
  --limit 0 `
  --wait 10 `
  --retries 4 `
  --retry-wait 3 `
  --keep-open
```

ข้อความในเครื่องหมายคำพูดคือคำค้นหา เปลี่ยนเป็นคำอื่นได้ เช่น:

```powershell
python google_places_scraper.py "ร้านอาหารญี่ปุ่น เชียงใหม่" --limit 0 --keep-open
python google_places_scraper.py "โรงแรม พัทยา ชลบุรี" --limit 100 --keep-open
```

## พารามิเตอร์

| พารามิเตอร์ | ค่าเริ่มต้น | ความหมาย |
|---|---:|---|
| `query` | `คลินิกเสริมความงาม สีลม` | คำที่ใช้ค้นหาใน Google Maps |
| `--limit 20` | `20` | จำนวนธุรกิจสูงสุดที่จะดึง |
| `--limit 0` | - | ดึงต่อจนเลื่อนแล้วไม่มีรายการใหม่ |
| `--wait` | `8` | เวลาสูงสุดที่รอ element สำคัญโหลด หน่วยวินาที |
| `--retries` | `3` | จำนวนครั้งสูงสุดที่ลองอ่านธุรกิจแต่ละรายการ |
| `--retry-wait` | `2` | เวลารอก่อน retry หน่วยวินาที |
| `--keep-open` | ปิด | ให้ Chrome ค้างไว้จนกว่าจะกด Enter |
| `--profile` | `.chrome-profile` | โฟลเดอร์เก็บ session ของ Chrome |
| `--captcha-profiles` | ไม่มี | โปรไฟล์สำรองตามลำดับ เมื่อเจอ CAPTCHA |
| `--output-dir` | `save_file` | โฟลเดอร์เก็บไฟล์ CSV |
| `-o`, `--output` | อัตโนมัติ | ระบุชื่อไฟล์ CSV เอง |

> สำคัญ: ทุก parameter ต้องอยู่ในคำสั่งเดียวกับ `python google_places_scraper.py`
> ห้ามรัน `--limit`, `--wait` หรือ `--retries` แยกเป็นคำสั่งใหม่ เพราะ PowerShell
> จะมองว่าเป็นคำสั่งที่ไม่ถูกต้อง

## ค้นหาหลาย Keyword

ใช้ `multi_keyword_scraper.py` และใส่ทุก keyword ไว้ในคำสั่งเดียว:

```powershell
python multi_keyword_scraper.py `
  "คลินิกเสริมความงาม สีลม" `
  "คลินิกทันตกรรม พร้อมพงษ์" `
  "ร้านอาหาร ลาดพร้าว" `
  --limit 20 `
  --wait 8 `
  --retries 3 `
  --retry-wait 3 `
  --keep-open
```

สคริปต์จะค้นหาทีละ keyword แล้วรวมทุกแถวเป็น CSV ไฟล์เดียวใน `save_file`
คอลัมน์ `query` ใช้บอกว่าแต่ละแถวมาจาก keyword ใด และคอลัมน์อื่นเหมือนกับ
`google_places_scraper.py` ทุกประการ

หลังจบแต่ละ keyword โปรแกรมจะแสดงผล เช่น `✅ Keyword "ฟิตเนส พหลโยธิน" complete 20/20`
หมายถึงเก็บสำเร็จครบ 20 จาก 20 ลิงก์ที่พบ หากมีรายการที่ข้ามหลัง retry หรือเกิด error
จะแสดง `❌ ... incomplete 18/20` เพื่อให้เห็น keyword ที่ข้อมูลยังไม่ครบ
แต่ละรายการจะแสดงเวลาที่ใช้ระหว่าง scrape และรายงานท้ายงานจะแสดงเวลาเฉลี่ยต่อรายการ
ของแต่ละ keyword พร้อมค่าเฉลี่ยรวม

ถ้ามี keyword จำนวนมาก ให้สร้างไฟล์ `keywords.txt` แบบหนึ่งคำค้นหาต่อหนึ่งบรรทัด:

```text
คลินิกเสริมความงาม สีลม
คลินิกทันตกรรม พร้อมพงษ์
ร้านอาหาร ลาดพร้าว
```

แล้วรัน:

```powershell
python multi_keyword_scraper.py `
  --keywords-file keywords.txt `
  --limit 20 `
  --wait 8 `
  --retries 3 `
  --retry-wait 3 `
  --keep-open
```

คำค้นหาที่ซ้ำกันจะถูกตัดออก และ `--limit` ใช้แยกต่อ keyword เช่น 3 keyword กับ
`--limit 20` จะดึงได้สูงสุดประมาณ 60 ธุรกิจ

ชื่อไฟล์รวมจะเป็น `{YYYY_MM_DD_HH-MM}_multi_keywords.csv` หรือกำหนดเองได้ด้วย:

```powershell
python multi_keyword_scraper.py --keywords-file keywords.txt --limit 10 -o businesses.csv --keep-open
```

## ไฟล์ผลลัพธ์

หากไม่ระบุ `-o` สคริปต์จะสร้างโฟลเดอร์ `save_file` และตั้งชื่อไฟล์อัตโนมัติ:

```text
{YYYY_MM_DD_HH-MM}_{คำค้นหา}.csv
```

ตัวอย่าง:

```text
save_file/2026_09_13_14-30_คลินิกเสริมความงาม สีลม.csv
```

ถ้ามีชื่อไฟล์ซ้ำ สคริปต์จะเติม `_2`, `_3` เพื่อไม่เขียนทับไฟล์เดิม

สคริปต์บันทึกอัตโนมัติทันทีหลังเก็บแต่ละธุรกิจสำเร็จ ระหว่างทำงานชื่อไฟล์จะลงท้าย
ด้วย `_partial.csv` หากกด `Ctrl+C`, Chrome หลุด, เกิด error หรือมีรายการที่ retry
แล้วยังไม่สำเร็จ ไฟล์ `_partial.csv` จะยังเก็บข้อมูลทั้งหมดที่บันทึกได้ไว้ หากงานสำเร็จ
ครบทุกลิงก์ที่พบและทุก keyword สคริปต์จะเปลี่ยนชื่อเป็น `.csv` ปกติโดยอัตโนมัติ

หากต้องการกำหนดชื่อไฟล์เอง:

```powershell
python google_places_scraper.py "คลินิกเสริมความงาม สีลม" -o silom_clinics.csv
```

ไฟล์ยังคงถูกเก็บภายในโฟลเดอร์ `save_file`

## ลบข้อมูลซ้ำจาก CSV

Workflow ของไฟล์:

```text
raw_data/*.csv
    ↓ รวมไฟล์ + data cleansing + remove duplicates
clean_data/{YYYY_MM_DD_HH-MM}_merged_clean.csv
    ↓ เมื่อบันทึกผลลัพธ์สำเร็จ
done_raw_data/*.csv
```

วางไฟล์ CSV ที่ต้องการรวมและลบข้อมูลซ้ำในโฟลเดอร์ `raw_data` แล้วรัน:

```powershell
python cleanse_data.py
```

สคริปต์จะอ่านและรวมทุกไฟล์ `.csv` ใน `raw_data` โดยไม่แก้ไฟล์ต้นฉบับ จากนั้นลบ
รายการซ้ำข้ามทุกไฟล์และบันทึกเป็นไฟล์เดียวในรูปแบบ
`clean_data/{YYYY_MM_DD_HH-MM}_merged_clean.csv`
ค่าเริ่มต้นจะมองว่าเป็นรายการซ้ำเมื่อ `business_name` และ `tel` เหมือนกัน โดยเก็บ
แถวแรกไว้

ก่อนลบข้อมูลซ้ำ สคริปต์จะทำความสะอาดข้อมูลดังนี้:

- ตัด whitespace ทุกตำแหน่งใน `tel` เช่น `02 123 4567` เป็น `021234567`
- เก็บเฉพาะคำแรกใน `district` เช่น `ปทุมวัน กรุงเทพมหานคร` เป็น `ปทุมวัน`
- ใช้ `raw_category` จัดกลุ่มและเพิ่ม `main_category` กับ `sub_category` ตามกฎ
  `MAP_LEAD_CATEGORY`; ค่าว่างจะได้ค่าว่าง และข้อความที่ไม่ตรงกฎจะเป็น
  `other` กับ `other_unspecified`

หลังสร้างไฟล์ใน `clean_data` สำเร็จ สคริปต์จะย้าย CSV ต้นฉบับทั้งหมดจาก
`raw_data` ไปเก็บใน `done_raw_data` อัตโนมัติ หากมีชื่อซ้ำจะเติม `_2`, `_3`
เพื่อไม่เขียนทับไฟล์เดิม หากบันทึกไฟล์ผลลัพธ์ไม่สำเร็จ จะยังไม่ย้ายไฟล์ต้นฉบับ

หลังรันสำเร็จ โฟลเดอร์ `raw_data` จะไม่มีไฟล์ CSV เหลืออยู่ จึงสามารถนำไฟล์ชุดใหม่
มาวางและรันคำสั่งเดิมได้ ส่วนไฟล์ต้นฉบับชุดก่อนยังเรียกคืนได้จาก `done_raw_data`

กำหนดโฟลเดอร์ archive อื่นแทน `done_raw_data` ได้ด้วย:

```powershell
python cleanse_data.py --done-dir archive_raw_data
```

หากต้องการใช้คอลัมน์อื่นเพื่อตรวจซ้ำ:

```powershell
python cleanse_data.py --columns business_name tel website
```

กำหนดชื่อไฟล์ผลลัพธ์เองได้:

```powershell
python cleanse_data.py -o all_businesses.csv
```

หากเพิ่งเพิ่ม Pandas หลังจากติดตั้ง dependencies ครั้งก่อน ให้รันหนึ่งครั้ง:

```powershell
python -m pip install -r requirements.txt
```

## ตรวจ Data Quality

ตรวจข้อมูลทุกคอลัมน์ของ CSV ที่อยู่ใน `clean_data` โดยระบุชื่อไฟล์:

```powershell
python data_quality_check.py "2026_09_15_16-15_merged_clean.csv"
```

หรือให้โปรแกรมถามชื่อไฟล์:

```powershell
python data_quality_check.py
```

รายงานจะถูกบันทึกใน `quality_reports/{YYYY_MM_DD_HH-MM}_{ชื่อไฟล์}_quality_report.csv`
โดยแสดงจำนวนค่าว่าง ค่าที่ไม่ซ้ำ แถวที่มีค่าซ้ำ ปัญหา whitespace จำนวนค่าที่ผิดรูปแบบ
กฎที่ใช้ตรวจ และสถานะของแต่ละคอลัมน์ นอกจากนี้ Terminal จะแสดงจำนวนรายการซ้ำจาก
`business_name + tel`

กฎหลักของข้อมูล scrape:

- `query` และ `business_name` ต้องไม่ว่าง
- `tel` ถ้ามี ต้องเป็นเบอร์ไทยตามระบบนำเข้า: เบอร์บ้าน 9 หลัก หรือเบอร์มือถือ 10 หลัก หลังตัดอักขระพิเศษ เช่น `026561050` หรือ `0891234567`
- `website` และ `google_maps_url` ถ้ามี ต้องเป็น URL ที่ถูกชนิด
- `rating` ต้องอยู่ในช่วง 0–5, `review_count` ต้องเป็นจำนวนเต็ม, `price_level` ต้องเป็น `$` ถึง `$$$$`
- `postal_code`, `latitude`, `longitude` และ `scraped_at` ต้องอยู่ในรูปแบบหรือช่วงค่าที่ถูกต้อง
- ตรวจว่ามีคอลัมน์ที่ scraper ต้องส่งออกครบ; `main_category` และ `sub_category` เป็นคอลัมน์เสริมจาก `cleanse_data.py`
- หลัง cleansing ถ้ามี `raw_category` ต้องมีทั้ง `main_category` และ `sub_category`

## แก้ไขกฎ Category

ไฟล์ [category_rules.json](category_rules.json) เป็นรายการจับคู่ที่ใช้ทั้ง
`cleanse_data.py` และ `data_quality_check.py` จึงเพิ่ม ลด หรือแก้ category ได้ที่ไฟล์นี้เพียงที่เดียว
โดย rule เรียงจากบนลงล่าง และ rule แรกที่พบคำตรงกับ `raw_category` จะถูกใช้

```json
{"pattern": "ทันต|dental|dentist", "main_category": "dental", "sub_category": "dental_clinic"}
```

หลังแก้ไฟล์ JSON ให้รัน `python cleanse_data.py` ใหม่เพื่อสร้าง category ในไฟล์ clean
และรัน `python data_quality_check.py` เพื่อตรวจว่า `main_category` กับ `sub_category` ตรงตามกฎหรือไม่
`business_name + tel`

## ข้อมูลที่บันทึก

CSV ประกอบด้วยข้อมูล เช่น:

- ชื่อธุรกิจ เบอร์โทร เว็บไซต์ และหมวดหมู่
- คะแนน จำนวนรีวิว และระดับราคา
- แขวง/ตำบล เขต/อำเภอ จังหวัด และรหัสไปรษณีย์
- Latitude, longitude และ Google Maps URL
- วันและเวลาที่เก็บแต่ละรายการใน `scraped_at` พร้อม timezone

ธุรกิจบางแห่งไม่ได้ระบุข้อมูลทุกช่อง ช่องนั้นจึงอาจว่างใน CSV

สคริปต์จะไม่โหลดรูป รีวิว หรือรายละเอียดที่ไม่ได้อยู่ใน CSV เพื่อให้การ scrape
เสถียรและใช้ทรัพยากรน้อยลง

ชื่อคอลัมน์จะเหมือนกันทุกครั้ง:

```text
query,business_name,tel,website,raw_category,rating,review_count,price_level,
subdistrict,district,province,postal_code,latitude,longitude,google_maps_url,scraped_at
```

หลังผ่าน `cleanse_data.py` จะเพิ่ม `main_category` และ `sub_category` ต่อจาก
`raw_category` ส่วนไฟล์เก่าที่ใช้ชื่อคอลัมน์ `category` จะถูกแปลงเป็น
`raw_category` อัตโนมัติ

## Infinite scrolling

`--limit 0` จะเลื่อนรายการ Google Maps ต่อเนื่องและหยุดเมื่อไม่พบธุรกิจใหม่ 5 รอบติดต่อกัน การตั้งค่านี้หมายถึงดึงทั้งหมดที่ Google Maps โหลดให้ในผลค้นหานั้น ไม่ได้หมายความว่า Google จะเปิดเผยธุรกิจทุกแห่งในพื้นที่

## CAPTCHA

สคริปต์ตรวจ CAPTCHA ทั้งตอนเปิดหน้าค้นหา ระหว่าง infinite scrolling และตอนเปิดข้อมูล
แต่ละธุรกิจ หากใช้ `.chrome-profile-2` และมีโฟลเดอร์ `.chrome-profile-3`,
`.chrome-profile-4` อยู่ข้างกัน โปรแกรมจะใช้โปรไฟล์เลขถัดไปอัตโนมัติเมื่อเจอ CAPTCHA:

```powershell
python multi_keyword_scraper.py --keywords-file keywords-search.txt --limit 0 --wait 12 --retries 3 --retry-wait 5 --profile .chrome-profile-2
```

หรือกำหนดลำดับโปรไฟล์สำรองเองด้วย `--captcha-profiles`:

```powershell
python multi_keyword_scraper.py --keywords-file keywords-search.txt --limit 0 --wait 12 --retries 3 --retry-wait 5 --profile .chrome-profile-2 --captcha-profiles .chrome-profile-3 .chrome-profile-4
```

เมื่อเจอ CAPTCHA โปรแกรมจะปิด Chrome เดิม เปิดโปรไฟล์ถัดไป และเปิดรายการที่กำลังทำอีกครั้ง
ตอนเริ่มแต่ละ keyword Terminal จะแสดง profile ที่ใช้อยู่และรายชื่อ profile สำรอง
ถ้าขึ้นว่า `ไม่มี profile สำรอง` แปลว่าไม่พบโฟลเดอร์เลขถัดไป และคำสั่งไม่ได้ใส่
`--captcha-profiles` หากโปรไฟล์สำรองหมดแล้ว โปรแกรมจะรอให้คุณ:

1. แก้ CAPTCHA ด้วยตัวเองในหน้าต่าง Chrome
2. รอจนเห็นหน้า Google Maps ตามปกติ
3. กลับมาที่ PowerShell แล้วกด Enter

หากยังกด CAPTCHA ไม่ผ่าน โปรแกรมจะตรวจพบอีกครั้งและรอต่อจนกว่าหน้า Google Maps
จะกลับมาเป็นปกติ แต่ละแถวที่ทำเสร็จจะถูกบันทึกลงไฟล์ `_partial.csv` ทันทีอยู่แล้ว
การสลับโปรไฟล์จะไม่ใช้จำนวน retry ของรายการนั้น และสำหรับหลาย keyword จะใช้โปรไฟล์ล่าสุด
กับ keyword ถัดไปด้วย

โฟลเดอร์ `.chrome-profile` ใช้เก็บ session เพื่อให้การยืนยันถูกจดจำในการรันครั้งต่อไป

## Retry และข้อความข้ามรายการ

ถ้า Google Maps เปลี่ยน DOM ขณะกำลังอ่าน อาจเห็นข้อความ:

```text
[2/40] StaleElementReferenceException - retry 1/3 ใน 3 วินาที
```

สคริปต์จะโหลด URL เดิมและลองใหม่อัตโนมัติ หากยังไม่สำเร็จครบจำนวนครั้งจึงแสดง:

```text
[2/40] ข้ามหลัง retry 4 ครั้ง: StaleElementReferenceException
```

รายการที่ถูกข้ามจะไม่ถูกเขียนลง CSV แต่โปรแกรมจะทำรายการถัดไปต่อ

## สรุปหลังทำงาน

เมื่อเสร็จ สคริปต์จะแสดง:

- จำนวนรายการที่บันทึก
- จำนวนรายการที่มีเบอร์โทร
- จำนวนรายการที่มีเว็บไซต์
- จำนวนรายการที่มีหมวดหมู่
- จำนวนรายการที่มีที่อยู่และจังหวัด
- ตำแหน่งไฟล์ CSV

กด Enter เพื่อปิด Chrome เมื่อใช้ `--keep-open`
