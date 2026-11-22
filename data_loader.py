"""Load and validate inspection data from Excel/CSV files."""
import os
import csv
import re
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class InspectionItem:
    """Single question/item in an inspection."""
    section: str
    question: str
    answer: str  # Yes / No / N/A / Safe / Compliant / At Risk / etc.
    notes: str = ""
    image_paths: List[str] = field(default_factory=list)
    image_required: bool = False  # If True, upload failure blocks submit
    question_alias: str = ""  # Alternative text to match on SC


@dataclass
class InspectionData:
    """Full inspection data parsed from a row group."""
    site_location: str
    inspection_date: str
    template_name: str
    run_time: str = ""
    account_name: str = ""
    template_folder_url: str = ""
    template_folder_name: str = ""
    items: List[InspectionItem] = field(default_factory=list)


REQUIRED_COLUMNS = [
    "site_location",
    "inspection_date",
    "template_name",
    "section",
    "question",
    "answer",
]

OPTIONAL_COLUMNS = [
    "notes", "image_path", "image_required", "question_alias",
    "question_key", "run_time", "schedule_time", "scheduled_time", "run_at",
    "account", "account_name", "account_profile", "safetyculture_account", "sc_account",
    "template_folder_url", "template_folder_name",
]
ACCOUNT_COLUMNS = ("account", "account_name", "account_profile", "profile", "safetyculture_account", "sc_account")
NO_ANSWER_VALUES = {"skip", "noanswer", "no answer", "ignore", "none"}


def is_no_answer(value: str) -> bool:
    return str(value or "").strip().lower() in NO_ANSWER_VALUES


def normalize_run_time(value: str) -> str:
    """Normalize values like 7am, 7:00 AM, 17:00 to HH:MM."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    cleaned = raw.lower().replace(".", "").replace(" ", "")
    match = re.match(r"^(\d{1,2})(?::?(\d{2}))?(am|pm)?$", cleaned)
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    suffix = match.group(3)
    if minute < 0 or minute > 59:
        return ""
    if suffix:
        if hour < 1 or hour > 12:
            return ""
        if suffix == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    elif hour < 0 or hour > 23:
        return ""
    return f"{hour:02d}:{minute:02d}"


def _derive_group_run_time(group) -> str:
    for col in ("run_time", "schedule_time", "run_at", "scheduled_time"):
        if col in group.columns:
            for value in group[col].tolist():
                normalized = normalize_run_time(value)
                if normalized:
                    return normalized
    conducted = group[
        group["question"].astype(str).str.strip().str.lower().str.contains("conducted on", na=False)
    ]
    for value in conducted.get("answer", []).tolist():
        normalized = normalize_run_time(value)
        if normalized:
            return normalized
    return ""


def _first_group_value(group, columns) -> str:
    for col in columns:
        if col in group.columns:
            for value in group[col].tolist():
                text = str(value or "").strip()
                if text:
                    return text
    return ""


def _row_first_value(row, columns) -> str:
    for col in columns:
        value = str(row.get(col, "") or "").strip()
        if value:
            return value
    return ""


def get_inspection_schedule_times(inspections: List["InspectionData"]) -> List[str]:
    return sorted({insp.run_time for insp in inspections if getattr(insp, "run_time", "")})


def filter_inspections_for_run_time(inspections: List["InspectionData"], run_time: str) -> List["InspectionData"]:
    target = normalize_run_time(run_time)
    if not target:
        return []
    return [insp for insp in inspections if getattr(insp, "run_time", "") == target]


def load_data(file_path: str, image_folder: str = "") -> List[InspectionData]:
    """
    Load inspection data from Excel (.xlsx) or CSV file.
    
    Expected columns:
        site_location, inspection_date, template_name, section, question, answer, notes, image_path
    
    Returns list of InspectionData grouped by (site_location, inspection_date, template_name).
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Use .csv or .xlsx")

    # Normalize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Validate required columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Fill NaN
    df = df.fillna("")

    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df["_cp_account_name"] = df.apply(lambda row: _row_first_value(row, ACCOUNT_COLUMNS), axis=1)
    df["_cp_template_folder_url"] = df["template_folder_url"].astype(str).str.strip()
    df["_cp_template_folder_name"] = df["template_folder_name"].astype(str).str.strip()

    # Group by inspection
    group_cols = [
        "_cp_account_name",
        "_cp_template_folder_url",
        "_cp_template_folder_name",
        "site_location",
        "inspection_date",
        "template_name",
    ]
    grouped = df.groupby(group_cols, sort=False, dropna=False)

    inspections: List[InspectionData] = []
    for (account_name, folder_url, folder_name, site, date, template), group in grouped:
        inspection = InspectionData(
            site_location=str(site).strip(),
            inspection_date=str(date).strip(),
            template_name=str(template).strip(),
            run_time=_derive_group_run_time(group),
            account_name=str(account_name).strip(),
            template_folder_url=str(folder_url).strip() or _first_group_value(group, ("template_folder_url",)),
            template_folder_name=str(folder_name).strip() or _first_group_value(group, ("template_folder_name",)),
        )

        for _, row in group.iterrows():
            # Resolve image paths
            images = []
            raw_image = str(row.get("image_path", "")).strip()
            if raw_image:
                for img in raw_image.split(";"):
                    img = img.strip()
                    if not img:
                        continue
                    # If relative path, join with image_folder
                    if not os.path.isabs(img) and image_folder:
                        full_path = os.path.join(image_folder, img)
                    else:
                        full_path = img
                    # Always add the path; upload will handle missing files.
                    images.append(full_path)

            # image_required flag
            img_req_raw = str(row.get("image_required", "")).strip().lower()
            img_required = img_req_raw in ("true", "1", "yes", "y")

            # question_alias for flexible matching
            q_alias = str(row.get("question_alias", row.get("question_key", ""))).strip()

            item = InspectionItem(
                section=str(row["section"]).strip(),
                question=str(row["question"]).strip(),
                answer=str(row["answer"]).strip(),
                notes=str(row.get("notes", "")).strip(),
                image_paths=images,
                image_required=img_required if img_req_raw else bool(images),
                question_alias=q_alias,
            )
            inspection.items.append(item)

        inspections.append(inspection)

    return inspections


def rename_account_in_csv(file_path: str, old_name: str, new_name: str) -> int:
    if os.path.splitext(file_path)[1].lower() != ".csv":
        return 0
    old_name = str(old_name or "").strip()
    new_name = str(new_name or "").strip()
    if not old_name or not new_name or not os.path.exists(file_path):
        return 0

    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    account_cols = [
        col for col in fieldnames
        if col.strip().lower().replace(" ", "_") in ACCOUNT_COLUMNS
    ]
    changed = 0
    for row in rows:
        for col in account_cols:
            if str(row.get(col, "")).strip() == old_name:
                row[col] = new_name
                changed += 1

    if changed:
        tmp = file_path + ".tmp"
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, file_path)
    return changed


def validate_data(inspections: List[InspectionData]) -> List[str]:
    """Validate loaded data, return list of warnings."""
    warnings = []
    valid_answers = {
        "yes", "no", "n/a", "safe", "at risk", "compliant", "non-compliant",
        "not applicable", "unsafe", "pass", "fail", "good", "satisfactory",
        "unsatisfactory", "acceptable", "not acceptable",
        "skip", "noanswer", "no answer", "ignore", "none",
    }

    for i, insp in enumerate(inspections):
        if not insp.template_name:
            warnings.append(f"Inspection #{i+1}: Missing template_name")
        if not insp.site_location:
            warnings.append(f"Inspection #{i+1}: Missing site_location")

        for j, item in enumerate(insp.items):
            if not item.question:
                warnings.append(f"Inspection #{i+1}, Item #{j+1}: Missing question")
            if item.answer.lower() not in valid_answers and item.answer:
                warnings.append(
                    f"Inspection #{i+1}, Q: '{item.question[:30]}...': "
                    f"Answer '{item.answer}' may not be recognized"
                )

    return warnings


def validate_detailed(file_path: str, image_folder: str = "") -> dict:
    """
    Detailed validation report for UI display.
    Returns dict with: ok, errors[], warnings[], stats{}
    """
    result = {"ok": True, "errors": [], "warnings": [], "stats": {}}

    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path, dtype=str, keep_default_na=False)
        else:
            result["ok"] = False
            result["errors"].append(f"Format không hỗ trợ: {ext}")
            return result
    except Exception as e:
        result["ok"] = False
        result["errors"].append(f"Không đọc được file: {str(e)}")
        return result

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df = df.fillna("")

    # Check required columns
    required = ["site_location", "inspection_date", "template_name", "section", "question", "answer"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        result["ok"] = False
        result["errors"].append(f"Thiếu cột: {', '.join(missing_cols)}")
        return result

    total_rows = len(df)
    result["stats"]["total_rows"] = total_rows
    result["stats"]["templates"] = df["template_name"].nunique()
    result["stats"]["sites"] = df["site_location"].nunique()

    # Check empty required fields
    empty_template = df[df["template_name"].str.strip() == ""]
    if len(empty_template) > 0:
        result["errors"].append(f"{len(empty_template)} dòng thiếu template_name")
        result["ok"] = False

    empty_site = df[df["site_location"].str.strip() == ""]
    if len(empty_site) > 0:
        result["warnings"].append(f"{len(empty_site)} dòng thiếu site_location")

    empty_question = df[df["question"].str.strip() == ""]
    if len(empty_question) > 0:
        result["errors"].append(f"{len(empty_question)} dòng thiếu question")
        result["ok"] = False

    empty_answer = df[df["answer"].str.strip() == ""]
    # Only error if answer is empty AND no image_path (image-only rows are OK)
    if "image_path" in df.columns:
        truly_empty = empty_answer[empty_answer["image_path"].str.strip() == ""]
    else:
        truly_empty = empty_answer
    if len(truly_empty) > 0:
        result["errors"].append(f"{len(truly_empty)} dòng chưa có đáp án (answer trống)")
        result["ok"] = False

    # Check images
    if "image_path" in df.columns:
        missing_images = []
        for idx, row in df.iterrows():
            raw = str(row.get("image_path", "")).strip()
            if not raw:
                continue
            for img in raw.split(";"):
                img = img.strip()
                if not img:
                    continue
                full_path = img
                if not os.path.isabs(img) and image_folder:
                    full_path = os.path.join(image_folder, img)
                if not os.path.exists(full_path):
                    missing_images.append(f"Row {idx+2}: {img}")

        if missing_images:
            result["warnings"].append(f"{len(missing_images)} ảnh không tìm thấy")
            for m in missing_images[:5]:
                result["warnings"].append(f"  - {m}")
            if len(missing_images) > 5:
                result["warnings"].append(f"  ... và {len(missing_images)-5} ảnh khác")

        result["stats"]["images_total"] = df["image_path"].str.strip().ne("").sum()
        result["stats"]["images_missing"] = len(missing_images)

    # Check answer validity; only warn for answers that look wrong.
    # Skip: numbers, NEXTPAGE commands, dates, text inputs (these are valid for input fields)
    valid_answers = {
        "yes", "no", "n/a", "safe", "at risk", "compliant", "non-compliant",
        "not applicable", "unsafe", "pass", "fail", "good", "satisfactory",
        "unsatisfactory", "acceptable", "not acceptable", "nextpage", "used",
        "discarded", "white rice", "brown rice",
        "skip", "noanswer", "no answer", "ignore", "none",
    }

    def _is_valid_answer(val):
        v = str(val).strip().lower()
        if not v:
            return True  # empty is handled above
        if v in valid_answers:
            return True
        if v == "nextpage":
            return True
        # Numbers (temperatures, quantities, pH) are valid
        try:
            float(v)
            return True
        except ValueError:
            pass
        # Dates/times are valid
        if any(c in v for c in ['/', ':', 'am', 'pm']):
            return True
        # Short text inputs (initials, names, locations); allow anything under 100 chars.
        if len(v) < 100:
            return True
        return False

    invalid = df[~df["answer"].apply(_is_valid_answer)]
    if len(invalid) > 0:
        result["warnings"].append(f"{len(invalid)} đáp án có thể không nhận diện được")
        for _, row in invalid.head(3).iterrows():
            result["warnings"].append(f"  - \"{row['answer']}\" -> {row['question'][:30]}")

    return result
