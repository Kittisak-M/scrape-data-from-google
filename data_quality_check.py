"""Profile and validate one CSV file from clean_data."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


ENCODINGS = ("utf-8-sig", "utf-8", "cp874")

# Columns written by google_places_scraper.py.  main_category and
# sub_category are added later by remove_duplicate.py.
SCRAPE_COLUMNS = (
    "query", "business_name", "tel", "website", "raw_category", "rating",
    "review_count", "price_level", "subdistrict", "district", "province",
    "postal_code", "latitude", "longitude", "google_maps_url", "scraped_at",
)
CLEAN_COLUMNS = ("main_category", "sub_category")
CATEGORY_RULES_FILE = Path(__file__).with_name("category_rules.json")
TERMINAL_REQUIRED_COLUMNS = (
    "business_name",
    "tel",
    "province",
    "scraped_at",
    "raw_category",
    "google_maps_url",
)
OPTIONAL_COLUMNS = {"rating", "review_count", "website"}
WARNING_ONLY_COLUMNS = {
    "tel",
    "price_level",
    "subdistrict",
    "district",
    "postal_code",
    "latitude",
    "longitude",
}
# Thai local numbers accepted by the lead importer:
# 9-digit fixed line (02-07) or 10-digit mobile (06, 08, 09).
THAI_PHONE_PATTERN = r"(?:0[2-7]\d{7}|0[689]\d{8})"


def load_category_rules(source: Path = CATEGORY_RULES_FILE) -> tuple[tuple[str, str, str], ...]:
    """Load the same ordered mapping used by remove_duplicate.py."""
    try:
        rules = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"อ่าน category rules ไม่ได้: {source} ({error})") from error
    loaded: list[tuple[str, str, str]] = []
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict) or not all(key in rule for key in ("pattern", "main_category", "sub_category")):
            raise ValueError(f"category rule ลำดับ {index} ต้องมี pattern, main_category และ sub_category")
        pattern, main, sub = (str(rule[key]).strip() for key in ("pattern", "main_category", "sub_category"))
        if not pattern or not main or not sub:
            raise ValueError(f"category rule ลำดับ {index} ห้ามมีค่าว่าง")
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(f"pattern ของ category rule ลำดับ {index} ใช้ไม่ได้: {error}") from error
        loaded.append((pattern, main, sub))
    return tuple(loaded)


def expected_category(value: object, rules: tuple[tuple[str, str, str], ...]) -> tuple[str, str]:
    text = str(value or "").strip().casefold()
    if not text:
        return "", ""
    for pattern, main, sub in rules:
        if re.search(pattern, text):
            return main, sub
    return "other", "other_unspecified"


def read_csv(source: Path) -> pd.DataFrame:
    last_error: UnicodeDecodeError | None = None
    for encoding in ENCODINGS:
        try:
            return pd.read_csv(source, dtype=str, keep_default_na=False, encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error
    raise last_error or UnicodeDecodeError("utf-8", b"", 0, 1, "อ่านไฟล์ไม่ได้")


def resolve_source(clean_dir: Path, filename: str) -> Path:
    safe_name = Path(filename.strip().strip('"')).name
    if not safe_name.lower().endswith(".csv"):
        safe_name += ".csv"
    source = clean_dir / safe_name
    if not source.is_file():
        raise FileNotFoundError(f"ไม่พบไฟล์: {source}")
    return source


def invalid_format_mask(column: str, values: pd.Series) -> tuple[pd.Series, str]:
    nonblank = values.ne("")
    empty_mask = pd.Series(False, index=values.index)

    if column == "business_name":
        return ~nonblank, "ต้องมีชื่อธุรกิจ"
    if column == "query":
        return ~nonblank, "ต้องมีคำค้นที่ใช้ scrape"
    if column == "tel":
        normalized = values.str.replace(r"\D", "", regex=True)
        return nonblank & ~normalized.str.fullmatch(THAI_PHONE_PATTERN), "เบอร์ไทยต้องเป็นเบอร์บ้าน 9 หลัก หรือมือถือ 10 หลัก"
    if column == "website":
        return nonblank & ~values.str.match(r"^https?://", case=False), "ต้องขึ้นต้นด้วย http:// หรือ https://"
    if column == "rating":
        numbers = pd.to_numeric(values, errors="coerce")
        return nonblank & (numbers.isna() | ~numbers.between(0, 5)), "คะแนนต้องอยู่ระหว่าง 0–5"
    if column == "review_count":
        normalized = values.str.replace(",", "", regex=False)
        return nonblank & ~normalized.str.fullmatch(r"\d+"), "จำนวนรีวิวต้องเป็นจำนวนเต็ม"
    if column == "price_level":
        return nonblank & ~values.str.fullmatch(r"\${1,4}"), "ระดับราคาต้องเป็น $, $$, $$$ หรือ $$$$"
    if column in {"subdistrict", "district", "province"}:
        return pd.Series(False, index=values.index), "ควรเป็นชื่อพื้นที่เพียงค่าเดียว; ตรวจแถวที่ว่างตามการใช้งาน"
    if column == "postal_code":
        return nonblank & ~values.str.fullmatch(r"\d{5}(?:-\d{4})?"), "รหัสไปรษณีย์ต้องเป็น 5 หลัก หรือ ZIP+4"
    if column in {"latitude", "longitude"}:
        numbers = pd.to_numeric(values, errors="coerce")
        lower, upper = (-90, 90) if column == "latitude" else (-180, 180)
        return nonblank & (numbers.isna() | ~numbers.between(lower, upper)), f"ค่าต้องอยู่ระหว่าง {lower} ถึง {upper}"
    if column == "google_maps_url":
        return nonblank & ~values.str.match(r"^https?://(?:www\.)?google\.", case=False), "ต้องเป็น Google URL"
    if column == "scraped_at":
        parsed = pd.to_datetime(values.where(nonblank), errors="coerce", utc=True)
        return nonblank & parsed.isna(), "ต้องเป็นวันเวลา ISO ที่อ่านได้"
    if column == "main_category":
        return pd.Series(False, index=values.index), "ตรวจความตรงกับ raw_category จาก category_rules.json"
    if column == "sub_category":
        return pd.Series(False, index=values.index), "ตรวจความตรงกับ raw_category จาก category_rules.json"
    return empty_mask, ""


def profile_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    total = len(frame)
    for column in frame.columns:
        values = frame[column].fillna("").astype(str)
        missing = values.str.strip().eq("")
        whitespace = values.ne(values.str.strip()) | values.str.contains(r"\s{2,}", regex=True)
        nonblank = ~missing
        repeated = nonblank & values.duplicated(keep=False)
        invalid, rule = invalid_format_mask(column, values)
        status = "CHECK" if invalid.any() or whitespace.any() else "OK"
        rows.append(
            {
                "column": column,
                "row_count": total,
                "missing_count": int(missing.sum()),
                "missing_percent": round(float(missing.mean() * 100), 2) if total else 0,
                "unique_nonblank_count": int(values[nonblank].nunique()),
                "repeated_value_rows": int(repeated.sum()),
                "whitespace_issue_count": int(whitespace.sum()),
                "invalid_format_count": int(invalid.sum()),
                "validation_rule": rule,
                "status": status,
            }
        )
    return pd.DataFrame(rows)


def schema_checks(frame: pd.DataFrame) -> pd.DataFrame:
    """Return required scraper/cleaning columns that are absent from a file."""
    rows: list[dict[str, object]] = []
    available = set(frame.columns)
    for column in SCRAPE_COLUMNS + CLEAN_COLUMNS:
        required = column in SCRAPE_COLUMNS
        present = column in available
        if present:
            continue
        rows.append(
            {
                "column": column,
                "row_count": len(frame),
                "missing_count": 0 if present else len(frame),
                "missing_percent": 0 if present else 100,
                "unique_nonblank_count": 0,
                "repeated_value_rows": 0,
                "whitespace_issue_count": 0,
                "invalid_format_count": 0 if present or not required else len(frame),
                "validation_rule": (
                    "ต้องมีในไฟล์ scrape" if required else "เพิ่มโดย remove_duplicate.py (ไฟล์ scrape ดิบยังไม่มีได้)"
                ),
                "status": "CHECK" if required else "OK",
            }
        )
    return pd.DataFrame(rows)


def relationship_checks(frame: pd.DataFrame, rules: tuple[tuple[str, str, str], ...]) -> pd.DataFrame:
    """Checks involving more than one column."""
    checks: list[dict[str, object]] = []
    total = len(frame)
    if {"raw_category", "main_category", "sub_category"}.issubset(frame.columns):
        raw = frame["raw_category"].fillna("").astype(str).str.strip()
        main = frame["main_category"].fillna("").astype(str).str.strip()
        sub = frame["sub_category"].fillna("").astype(str).str.strip()
        expected = raw.apply(lambda value: expected_category(value, rules))
        expected_main = expected.str[0]
        expected_sub = expected.str[1]
        invalid = main.ne(expected_main) | sub.ne(expected_sub)
        checks.append(
            {
                "column": "raw_category -> main_category + sub_category (match)",
                "row_count": total,
                "missing_count": int(invalid.sum()),
                "missing_percent": round(float(invalid.mean() * 100), 2) if total else 0,
                "unique_nonblank_count": 0,
                "repeated_value_rows": 0,
                "whitespace_issue_count": 0,
                "invalid_format_count": int(invalid.sum()),
                "validation_rule": "main_category และ sub_category ต้องตรงกับ category_rules.json ตาม raw_category",
                "status": "CHECK" if invalid.any() else "OK",
            }
        )
    return pd.DataFrame(checks)


def duplicate_business_count(frame: pd.DataFrame) -> int | None:
    columns = ["business_name", "tel"]
    if not all(column in frame.columns for column in columns):
        return None
    keys = frame[columns].fillna("").astype(str)
    for column in columns:
        replacement = "" if column == "tel" else " "
        keys[column] = keys[column].str.replace(r"\s+", replacement, regex=True).str.strip().str.casefold()
    return int(keys.agg("\x1f".join, axis=1).duplicated(keep="first").sum())


def print_tel_issues(frame: pd.DataFrame, max_rows: int = 50) -> None:
    """Print phone values that are blank or not Thai local phone format."""
    if "tel" not in frame.columns:
        return
    values = frame["tel"].fillna("").astype(str).str.strip()
    digits = values.str.replace(r"\D", "", regex=True)
    valid = digits.str.fullmatch(THAI_PHONE_PATTERN).fillna(False)
    issues = frame.loc[values.eq("") | ~valid, [column for column in ("business_name", "tel") if column in frame.columns]].copy()
    if issues.empty:
        print("เบอร์โทรที่ต้องตรวจสอบ: 0 แถว")
        return
    print(f"เบอร์โทรที่ต้องตรวจสอบ: {len(issues):,} แถว")
    issues.insert(0, "source_row", issues.index + 2)
    with pd.option_context("display.max_columns", None, "display.max_colwidth", 80, "display.width", 160):
        print(issues.head(max_rows).to_string(index=False))
    if len(issues) > max_rows:
        print(f"แสดง {max_rows:,} แถวแรกจากทั้งหมด {len(issues):,} แถว")


def print_required_field_checks(frame: pd.DataFrame) -> None:
    """Show completion of the fields required for a usable lead in Terminal."""
    print("ตรวจฟิลด์สำคัญ:")
    for column in TERMINAL_REQUIRED_COLUMNS:
        if column not in frame.columns:
            print(f"  ❌  CHECK {column}: ไม่พบคอลัมน์")
            continue
        values = frame[column].fillna("").astype(str).str.strip()
        missing = int(values.eq("").sum())
        if column in WARNING_ONLY_COLUMNS:
            status = "⚠️  WARNING"
        else:
            status = "✅  PASS" if missing == 0 else "❌  CHECK"
        print(f"  {status} {column}: ว่าง {missing:,}/{len(frame):,} แถว")


def print_column_quality_summary(report: pd.DataFrame) -> None:
    """Print missing/format results for every actual data column."""
    actual_columns = set(SCRAPE_COLUMNS + CLEAN_COLUMNS)
    rows = report[report["column"].isin(actual_columns)]
    print("ตรวจค่าว่างและรูปแบบ:")
    for _, row in rows.iterrows():
        issues: list[str] = []
        if row["missing_count"] and row["column"] not in OPTIONAL_COLUMNS:
            issues.append(f"ว่าง {int(row['missing_count']):,}")
        if row["invalid_format_count"]:
            issues.append(f"format ผิด {int(row['invalid_format_count']):,}")
        if row["whitespace_issue_count"]:
            issues.append(f"space ผิด {int(row['whitespace_issue_count']):,}")
        if row["column"] in WARNING_ONLY_COLUMNS:
            status = "⚠️  WARNING"
        else:
            status = "✅  PASS" if not issues else "❌  CHECK"
        detail = ", ".join(issues) if issues else "ครบและ format ถูกต้อง"
        print(f"  {status} {row['column']}: {detail}")


def print_category_match_check(frame: pd.DataFrame, rules: tuple[tuple[str, str, str], ...]) -> None:
    columns = {"raw_category", "main_category", "sub_category"}
    if not columns.issubset(frame.columns):
        print("  ❌  CHECK category match: ไม่พบ raw_category, main_category หรือ sub_category")
        return
    raw = frame["raw_category"].fillna("").astype(str).str.strip()
    actual = frame[["main_category", "sub_category"]].fillna("").astype(str).apply(lambda col: col.str.strip())
    expected = raw.apply(lambda value: expected_category(value, rules))
    mismatch = actual["main_category"].ne(expected.str[0]) | actual["sub_category"].ne(expected.str[1])
    status = "✅  PASS" if not mismatch.any() else "❌  CHECK"
    print(f"  {status} category match: ไม่ตรง {int(mismatch.sum()):,}/{len(frame):,} แถว")


def main() -> None:
    parser = argparse.ArgumentParser(description="ตรวจ Data Quality ของ CSV ใน clean_data")
    parser.add_argument("filename", nargs="?", help="ชื่อไฟล์ CSV ภายใน clean_data")
    parser.add_argument("--clean-dir", default="clean_data", help="โฟลเดอร์ไฟล์ที่ต้องการตรวจ")
    parser.add_argument("--report-dir", default="quality_reports", help="โฟลเดอร์เก็บรายงาน")
    args = parser.parse_args()

    filename = args.filename or input("กรอกชื่อไฟล์ CSV ใน clean_data: ").strip()
    if not filename:
        parser.error("กรุณาระบุชื่อไฟล์ CSV")

    try:
        source = resolve_source(Path(args.clean_dir), filename)
        frame = read_csv(source)
    except (FileNotFoundError, OSError, UnicodeDecodeError, pd.errors.ParserError) as error:
        print(error)
        raise SystemExit(1) from error

    try:
        category_rules = load_category_rules()
    except ValueError as error:
        print(error)
        raise SystemExit(1) from error

    report = pd.concat(
        [profile_columns(frame), schema_checks(frame), relationship_checks(frame, category_rules)],
        ignore_index=True,
    )
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y_%m_%d_%H-%M")
    destination = report_dir / f"{timestamp}_{source.stem}_quality_report.csv"
    report.to_csv(destination, index=False, encoding="utf-8-sig")

    duplicate_count = duplicate_business_count(frame)
    print(f"ไฟล์: {source}")
    print(f"จำนวนแถว: {len(frame):,}")
    print(f"จำนวนคอลัมน์: {len(frame.columns)}")
    print()
    print_required_field_checks(frame)
    print()
    print_column_quality_summary(report)
    print()
    print_category_match_check(frame, category_rules)
    print()
    print_tel_issues(frame)
    print()
    if duplicate_count is not None:
        print(f"รายการซ้ำ business_name + tel: {duplicate_count:,}")
    print(f"คอลัมน์ที่ควรตรวจสอบ: {(report['status'] == 'CHECK').sum()}")
    print(f"บันทึกรายงานแล้ว -> {destination}")


if __name__ == "__main__":
    main()
