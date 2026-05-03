from __future__ import annotations

import re
from typing import Any


STAT_VALUE_TABLE: dict[str, tuple[tuple[float, ...], bool]] = {
    "暴击": ((6.3, 6.9, 7.5, 8.1, 8.7, 9.3, 9.9, 10.5), True),
    "暴击伤害": ((12.6, 13.8, 15.0, 16.2, 17.4, 18.6, 19.8, 21.0), True),
    "攻击": ((6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "生命": ((6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "防御": ((8.1, 9.0, 10.0, 10.9, 11.8, 12.8, 13.8, 14.7), True),
    "共鸣效率": ((6.8, 7.6, 8.4, 9.2, 10.0, 10.8, 11.6, 12.4), True),
    "普攻伤害加成": ((6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "重击伤害加成": ((6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "共鸣技能伤害加成": ((6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "共鸣解放伤害加成": ((6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "固定攻击": ((30.0, 40.0, 50.0, 60.0), False),
    "固定生命": ((320.0, 360.0, 390.0, 430.0, 470.0, 510.0, 540.0, 580.0), False),
    "固定防御": ((40.0, 50.0, 60.0, 70.0), False),
}

STAT_NAMES = {
    "暴击",
    "暴击伤害",
    "攻击",
    "生命",
    "防御",
    "共鸣效率",
    "普攻伤害加成",
    "重击伤害加成",
    "共鸣技能伤害加成",
    "共鸣解放伤害加成",
}

MIN_ROW_CONFIDENCE = 0.35


def validate_recognition_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []

    user_id = str(result.get("user_id") or result.get("user_id_raw") or "")
    if not re.search(r"\d{6,}", user_id):
        errors.append({"code": "invalid_user_id", "path": "result.user_id", "message": "missing valid user id"})

    _validate_rows(errors, warnings, failed_rows, "original_stats", result.get("original_stats"))
    _validate_rows(errors, warnings, failed_rows, "new_stats", result.get("new_stats"))

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "failed_rows": failed_rows,
    }


def _validate_rows(
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    failed_rows: list[dict[str, Any]],
    field: str,
    raw_rows: Any,
) -> None:
    if not isinstance(raw_rows, list) or len(raw_rows) != 5:
        errors.append({"code": "invalid_row_count", "path": f"result.{field}", "message": "expected five rows"})
        return

    for index, row in enumerate(raw_rows):
        path = f"result.{field}[{index}]"
        if not isinstance(row, dict):
            errors.append({"code": "invalid_row", "path": path, "message": "row must be an object"})
            failed_rows.append({"field": field, "index": index + 1, "codes": ["invalid_row"]})
            continue

        row_codes: list[str] = []
        name = str(row.get("name") or "").strip()
        value = str(row.get("value") or "").strip()

        if name not in STAT_NAMES:
            errors.append({"code": "invalid_name", "path": f"{path}.name", "message": "stat name is not recognized", "actual": name})
            row_codes.append("invalid_name")

        if not value:
            errors.append({"code": "missing_value", "path": f"{path}.value", "message": "stat value is missing"})
            row_codes.append("missing_value")
        elif name in STAT_NAMES:
            inferred_tier = infer_tier(name, value)
            if inferred_tier is None:
                errors.append({"code": "invalid_value", "path": f"{path}.value", "message": "stat value does not match any valid tier", "actual": value})
                row_codes.append("invalid_value")
            elif row.get("tier") not in (None, "", inferred_tier):
                try:
                    row_tier = int(row.get("tier"))
                except (TypeError, ValueError):
                    row_tier = None
                if row_tier != inferred_tier:
                    errors.append({"code": "invalid_tier", "path": f"{path}.tier", "message": "tier does not match value", "actual": row.get("tier"), "expected": inferred_tier})
                    row_codes.append("invalid_tier")

        confidence = _parse_confidence(row.get("confidence"))
        if confidence is not None and confidence < MIN_ROW_CONFIDENCE:
            errors.append({"code": "low_confidence", "path": f"{path}.confidence", "message": "OCR confidence is too low", "actual": confidence, "minimum": MIN_ROW_CONFIDENCE})
            row_codes.append("low_confidence")

        if row.get("name_raw") and name and name not in STAT_NAMES:
            warnings.append({"code": "raw_name_unmatched", "path": f"{path}.name_raw", "actual": row.get("name_raw")})

        if row_codes:
            failed_rows.append({"field": field, "index": index + 1, "codes": row_codes, "name": name, "value": value})


def infer_tier(name: str, raw_value: str) -> int | None:
    table = _resolve_value_table(name, raw_value)
    numeric = _parse_stat_number(raw_value)
    if table is None or numeric is None:
        return None

    values, is_percent = table
    nearest_index = min(range(len(values)), key=lambda index: abs(values[index] - numeric))
    tolerance = 0.11 if is_percent else 0.5
    if abs(values[nearest_index] - numeric) <= tolerance:
        return nearest_index + 1
    return None


def _resolve_value_table(name: str, raw_value: str) -> tuple[tuple[float, ...], bool] | None:
    if name in {"攻击", "生命", "防御"} and "%" not in str(raw_value or ""):
        return STAT_VALUE_TABLE.get(f"固定{name}")
    return STAT_VALUE_TABLE.get(name)


def _parse_stat_number(raw_value: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", str(raw_value or "").replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _parse_confidence(raw_value: Any) -> float | None:
    if raw_value in (None, ""):
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if value > 1:
        value = value / 100
    return max(0.0, min(1.0, value))
