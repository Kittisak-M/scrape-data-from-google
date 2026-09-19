"""Merge CSV files from raw_data, remove duplicates, and save one clean CSV."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd


DEFAULT_COLUMNS = ["business_name", "tel"]
ENCODINGS = ("utf-8-sig", "utf-8", "cp874")
CATEGORY_RULES_FILE = Path(__file__).with_name("category_rules.json")


def load_category_rules(source: Path = CATEGORY_RULES_FILE) -> tuple[tuple[str, str, str], ...]:
    """Load ordered category rules from an editable JSON file."""
    try:
        rules = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"อ่าน category rules ไม่ได้: {source} ({error})") from error
    if not isinstance(rules, list):
        raise ValueError("category_rules.json ต้องเป็น list ของ rules")
    loaded: list[tuple[str, str, str]] = []
    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict) or not all(key in rule for key in ("pattern", "main_category", "sub_category")):
            raise ValueError(f"rule ลำดับ {index} ต้องมี pattern, main_category และ sub_category")
        pattern, main, sub = (str(rule[key]).strip() for key in ("pattern", "main_category", "sub_category"))
        if not pattern or not main or not sub:
            raise ValueError(f"rule ลำดับ {index} ห้ามมีค่าว่าง")
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(f"pattern ของ rule ลำดับ {index} ใช้ไม่ได้: {error}") from error
        loaded.append((pattern, main, sub))
    return tuple(loaded)


CATEGORY_RULES = load_category_rules()


def read_csv(source: Path) -> pd.DataFrame:
    last_error: UnicodeDecodeError | None = None
    for encoding in ENCODINGS:
        try:
            return pd.read_csv(source, dtype=str, keep_default_na=False, encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error
    raise last_error or UnicodeDecodeError("utf-8", b"", 0, 1, "อ่านไฟล์ไม่ได้")


def normalized_key(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    """Normalize comparison values without changing the original output."""
    normalized = frame[columns].fillna("").astype(str)
    for column in columns:
        normalized[column] = (
            normalized[column]
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
            .str.casefold()
        )
    return normalized.agg("\x1f".join, axis=1)


def map_lead_category(value: object) -> tuple[str, str]:
    if pd.isna(value):
        return "", ""
    text = str(value or "").strip().lower()
    if not text:
        return "", ""
    for pattern, main_category, sub_category in CATEGORY_RULES:
        if re.search(pattern, text):
            return main_category, sub_category
    return "other", "other_unspecified"


def cleanse_data(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply consistent output cleanup before duplicate detection and export."""
    cleaned = frame.copy()
    if "raw_category" not in cleaned.columns and "category" in cleaned.columns:
        cleaned = cleaned.rename(columns={"category": "raw_category"})
    elif "raw_category" in cleaned.columns and "category" in cleaned.columns:
        raw_is_blank = cleaned["raw_category"].fillna("").astype(str).str.strip().eq("")
        cleaned.loc[raw_is_blank, "raw_category"] = cleaned.loc[raw_is_blank, "category"]
        cleaned = cleaned.drop(columns=["category"])
    if "tel" in cleaned.columns:
        # Remove the label sometimes copied from Google Maps before normalizing.
        normalized_tel = (
            cleaned["tel"]
            .fillna("")
            .astype(str)
            .str.replace(r"^\s*โทรศัพท์\s*:\s*", "", regex=True, case=False)
            .str.replace(r"\D", "", regex=True)
        )
        # Google sometimes omits the Bangkok/Thai fixed-line leading 0.
        # Restore it for an 8-digit local fixed-line number.
        missing_zero = normalized_tel.str.fullmatch(r"[2-7]\d{7}").fillna(False)
        cleaned["tel"] = normalized_tel.where(~missing_zero, "0" + normalized_tel)
    if "district" in cleaned.columns:
        # Google Maps may append province text, e.g. "ปทุมวัน กรุงเทพมหานคร".
        cleaned["district"] = (
            cleaned["district"]
            .fillna("")
            .astype(str)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
            .str.split()
            .str[0]
            .fillna("")
        )
    if "raw_category" in cleaned.columns:
        cleaned = cleaned.drop(
            columns=[column for column in ("main_category", "sub_category") if column in cleaned.columns]
        )
        mapped = cleaned["raw_category"].apply(map_lead_category)
        raw_position = cleaned.columns.get_loc("raw_category") + 1
        cleaned.insert(raw_position, "main_category", mapped.str[0])
        cleaned.insert(raw_position + 1, "sub_category", mapped.str[1])
    return cleaned


def output_path(output_dir: Path, requested_name: str | None) -> Path:
    filename = (
        Path(requested_name).name
        if requested_name
        else f"{datetime.now():%Y_%m_%d_%H-%M}_merged_clean.csv"
    )
    if not filename.lower().endswith(".csv"):
        filename += ".csv"
    return output_dir / filename


def archive_path(done_dir: Path, source: Path) -> Path:
    """Choose a destination name without overwriting an archived source file."""
    destination = done_dir / source.name
    counter = 2
    while destination.exists():
        destination = done_dir / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    return destination


def archive_sources(sources: list[Path], done_dir: Path) -> tuple[int, int]:
    moved = 0
    failed = 0
    for source in sources:
        try:
            destination = archive_path(done_dir, source)
            shutil.move(str(source), str(destination))
            moved += 1
            print(f"ย้าย {source.name} -> {destination}")
        except OSError as error:
            failed += 1
            print(f"ย้าย {source.name} ไม่สำเร็จ: {error}")
    return moved, failed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="รวม CSV ใน raw_data แล้วลบข้อมูลซ้ำลง clean_data"
    )
    parser.add_argument(
        "filenames",
        nargs="*",
        help="ชื่อ CSV ใน raw_data ที่ต้องการประมวลผล (ไม่ระบุ = ประมวลผลทุกไฟล์)",
    )
    parser.add_argument("--input-dir", default="raw_data", help="โฟลเดอร์ CSV ต้นฉบับ")
    parser.add_argument("--output-dir", default="clean_data", help="โฟลเดอร์ไฟล์ผลลัพธ์")
    parser.add_argument(
        "--done-dir",
        default="done_raw_data",
        help="โฟลเดอร์เก็บไฟล์ต้นฉบับหลังบันทึกผลสำเร็จ",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="ชื่อไฟล์ผลลัพธ์ (ค่าเริ่มต้น: YYYY_MM_DD_HH-MM_merged_clean.csv)",
    )
    parser.add_argument(
        "--columns",
        nargs="+",
        default=DEFAULT_COLUMNS,
        help="คอลัมน์ที่ใช้ตรวจซ้ำ (ค่าเริ่มต้น: business_name tel)",
    )
    args = parser.parse_args()

    source_dir = Path(args.input_dir)
    destination_dir = Path(args.output_dir)
    done_dir = Path(args.done_dir)
    source_dir.mkdir(parents=True, exist_ok=True)
    destination_dir.mkdir(parents=True, exist_ok=True)
    done_dir.mkdir(parents=True, exist_ok=True)
    if args.filenames:
        sources = []
        missing_files: list[str] = []
        for filename in args.filenames:
            safe_name = Path(filename.strip().strip('"')).name
            if not safe_name.lower().endswith(".csv"):
                safe_name += ".csv"
            source = source_dir / safe_name
            if source.is_file():
                sources.append(source)
            else:
                missing_files.append(safe_name)
        if missing_files:
            print(f"ไม่พบไฟล์ใน {source_dir}: {', '.join(missing_files)}")
        sources = sorted(set(sources))
    else:
        sources = sorted(path for path in source_dir.glob("*.csv") if path.is_file())

    if not sources:
        print(f"ไม่พบไฟล์ CSV ใน {source_dir}")
        print("นำไฟล์ CSV ไปวางใน raw_data แล้วรันคำสั่งเดิมอีกครั้ง")
        return

    frames: list[pd.DataFrame] = []
    failed = 0
    print(f"พบ {len(sources)} ไฟล์ | ตรวจซ้ำด้วย: {', '.join(args.columns)}")
    for source in sources:
        try:
            frame = read_csv(source)
            missing = [column for column in args.columns if column not in frame.columns]
            if missing:
                raise ValueError(f"ไม่พบคอลัมน์ {', '.join(missing)}")
            frames.append(frame)
            print(f"อ่าน {source.name}: {len(frame)} แถว")
        except (OSError, UnicodeDecodeError, ValueError, pd.errors.ParserError) as error:
            failed += 1
            print(f"ข้าม {source.name}: {error}")

    if not frames:
        print("ไม่มีไฟล์ที่สามารถนำมารวมได้")
        return

    merged = cleanse_data(pd.concat(frames, ignore_index=True, sort=False))
    key = normalized_key(merged, args.columns)
    cleaned = merged.loc[~key.duplicated(keep="first")]
    destination = output_path(destination_dir, args.output)
    cleaned.to_csv(destination, index=False, encoding="utf-8-sig")

    print(f"รวมก่อนลบซ้ำ: {len(merged)} แถว")
    print(f"ลบรายการซ้ำ: {len(merged) - len(cleaned)} แถว")
    print(f"เหลือข้อมูล: {len(cleaned)} แถว")
    print(f"บันทึกแล้ว -> {destination}")
    if failed:
        print(f"มี {failed} ไฟล์ที่ถูกข้ามเพราะอ่านไม่ได้หรือไม่มีคอลัมน์ที่กำหนด")

    moved, move_failed = archive_sources(sources, done_dir)
    print(f"ย้ายไฟล์ต้นฉบับแล้ว {moved}/{len(sources)} ไฟล์ -> {done_dir}")
    if move_failed:
        print(f"มี {move_failed} ไฟล์ที่ย้ายไม่สำเร็จและยังอยู่ใน {source_dir}")


if __name__ == "__main__":
    main()
