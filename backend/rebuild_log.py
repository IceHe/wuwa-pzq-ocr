from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from backend.model import RebuildLogDetail, RebuildLogListItem

try:
    import psycopg
    from psycopg.types.json import Jsonb
except ModuleNotFoundError:
    psycopg = None
    Jsonb = None

SUBSTAT_BIT_WIDTH = 13
SUBSTAT_ALL_MASK = (1 << SUBSTAT_BIT_WIDTH) - 1


@dataclass(frozen=True)
class StatDefinition:
    number: int
    canonical_name: str
    values: tuple[float, ...]
    is_percent: bool


STAT_DEFINITIONS = {
    "暴击": StatDefinition(0, "暴击", (6.3, 6.9, 7.5, 8.1, 8.7, 9.3, 9.9, 10.5), True),
    "暴击伤害": StatDefinition(1, "暴击伤害", (12.6, 13.8, 15.0, 16.2, 17.4, 18.6, 19.8, 21.0), True),
    "攻击": StatDefinition(2, "攻击", (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "防御": StatDefinition(3, "防御", (8.1, 9.0, 10.0, 10.9, 11.8, 12.8, 13.8, 14.7), True),
    "生命": StatDefinition(4, "生命", (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "攻击固定值": StatDefinition(5, "攻击固定值", (30.0, 40.0, 50.0, 60.0), False),
    "防御固定值": StatDefinition(6, "防御固定值", (40.0, 50.0, 60.0, 70.0), False),
    "生命固定值": StatDefinition(7, "生命固定值", (320.0, 360.0, 390.0, 430.0, 470.0, 510.0, 540.0, 580.0), False),
    "共鸣效率": StatDefinition(8, "共鸣效率", (6.8, 7.6, 8.4, 9.2, 10.0, 10.8, 11.6, 12.4), True),
    "普攻": StatDefinition(9, "普攻", (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "重击": StatDefinition(10, "重击", (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "共鸣技能": StatDefinition(11, "共鸣技能", (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
    "共鸣解放": StatDefinition(12, "共鸣解放", (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6), True),
}

NAME_ALIASES = {
    "普攻伤害加成": "普攻",
    "重击伤害加成": "重击",
    "共鸣技能伤害加成": "共鸣技能",
    "共鸣解放伤害加成": "共鸣解放",
}

INSERT_SQL = """
INSERT INTO public.wuwa_rebuild_log (
    user_id,
    locked_bitmap,
    locked_count,
    original_stat1,
    original_stat2,
    original_stat3,
    original_stat4,
    original_stat5,
    original_stat_all,
    o1_desc,
    o2_desc,
    o3_desc,
    o4_desc,
    o5_desc,
    new_stat1,
    new_stat2,
    new_stat3,
    new_stat4,
    new_stat5,
    new_stat_all,
    n1_desc,
    n2_desc,
    n3_desc,
    n4_desc,
    n5_desc,
    source_image,
    uploader_nickname,
    uploader_email,
    uploader_wechat,
    uploader_qq,
    request_ip,
    raw_json
) VALUES (
    %(user_id)s,
    %(locked_bitmap)s,
    %(locked_count)s,
    %(original_stat1)s,
    %(original_stat2)s,
    %(original_stat3)s,
    %(original_stat4)s,
    %(original_stat5)s,
    %(original_stat_all)s,
    %(o1_desc)s,
    %(o2_desc)s,
    %(o3_desc)s,
    %(o4_desc)s,
    %(o5_desc)s,
    %(new_stat1)s,
    %(new_stat2)s,
    %(new_stat3)s,
    %(new_stat4)s,
    %(new_stat5)s,
    %(new_stat_all)s,
    %(n1_desc)s,
    %(n2_desc)s,
    %(n3_desc)s,
    %(n4_desc)s,
    %(n5_desc)s,
    %(source_image)s,
    %(uploader_nickname)s,
    %(uploader_email)s,
    %(uploader_wechat)s,
    %(uploader_qq)s,
    %(request_ip)s,
    %(raw_json)s
)
RETURNING id
"""

FIND_RECENT_DUPLICATE_SQL = """
SELECT id
FROM public.wuwa_rebuild_log
WHERE deleted = 0
  AND user_id = %(user_id)s
  AND locked_bitmap = %(locked_bitmap)s
  AND original_stat1 = %(original_stat1)s
  AND original_stat2 = %(original_stat2)s
  AND original_stat3 = %(original_stat3)s
  AND original_stat4 = %(original_stat4)s
  AND original_stat5 = %(original_stat5)s
  AND new_stat1 = %(new_stat1)s
  AND new_stat2 = %(new_stat2)s
  AND new_stat3 = %(new_stat3)s
  AND new_stat4 = %(new_stat4)s
  AND new_stat5 = %(new_stat5)s
  AND created_at >= NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC, id DESC
LIMIT 1
"""

LIST_SQL_BASE = """
SELECT
    id,
    user_id,
    locked_bitmap,
    locked_count,
    source_image,
    uploaded_image,
    uploader_nickname,
    uploader_email,
    uploader_wechat,
    uploader_qq,
    request_ip,
    created_at,
    updated_at,
    o1_desc,
    o2_desc,
    o3_desc,
    o4_desc,
    o5_desc,
    n1_desc,
    n2_desc,
    n3_desc,
    n4_desc,
    n5_desc
FROM public.wuwa_rebuild_log
WHERE deleted = 0
"""

DETAIL_SQL = """
SELECT
    id,
    user_id,
    locked_bitmap,
    locked_count,
    source_image,
    uploaded_image,
    uploader_nickname,
    uploader_email,
    uploader_wechat,
    uploader_qq,
    request_ip,
    created_at,
    updated_at,
    raw_json
FROM public.wuwa_rebuild_log
WHERE id = %(id)s
  AND deleted = 0
"""

UPDATE_UPLOADED_IMAGE_SQL = """
UPDATE public.wuwa_rebuild_log
SET uploaded_image = %(uploaded_image)s,
    updated_at = NOW()
WHERE id = %(id)s
  AND deleted = 0
RETURNING id
"""


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if not database_url.startswith("postgresql://"):
        return database_url
    parts = urlsplit(database_url)
    if parts.scheme == "postgresql":
        return urlunsplit(("postgresql", parts.netloc, parts.path, parts.query, parts.fragment))
    return database_url


def _get_connection():
    if psycopg is None:
        raise RuntimeError("psycopg is not installed.")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    return psycopg.connect(normalize_database_url(database_url))


def _parse_numeric(raw_value: Any) -> float | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    text = text.replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _format_desc(definition: StatDefinition, numeric: float | None, raw_value: Any) -> str:
    if numeric is None:
        value_text = str(raw_value or "").strip()
    elif definition.is_percent:
        value_text = f"{numeric:.1f}%"
    elif numeric.is_integer():
        value_text = str(int(numeric))
    else:
        value_text = f"{numeric:.1f}"
    if not value_text:
        return ""
    return f"{definition.canonical_name} {value_text}"


def _resolve_definition(raw_name: Any, raw_value: Any) -> StatDefinition | None:
    name = str(raw_name or "").strip()
    if not name:
        return None
    name = NAME_ALIASES.get(name, name)
    value_text = str(raw_value or "")
    if name in {"攻击", "防御", "生命"} and "%" not in value_text:
        name = f"{name}固定值"
    return STAT_DEFINITIONS.get(name)


def _build_stat_bitmap(row: dict[str, Any]) -> tuple[int, str]:
    definition = _resolve_definition(row.get("name"), row.get("value"))
    if definition is None:
        return 0, ""

    numeric = _parse_numeric(row.get("value"))
    tier = row.get("tier")
    value_number: int | None = None
    if isinstance(tier, int) and tier > 0:
        value_number = tier - 1
    elif numeric is not None:
        for index, candidate in enumerate(definition.values):
            if abs(candidate - numeric) < 1e-9:
                value_number = index
                break

    stat_bitmap = 1 << definition.number
    if value_number is not None:
        stat_bitmap |= 1 << (SUBSTAT_BIT_WIDTH + value_number)

    return stat_bitmap, _format_desc(definition, numeric, row.get("value"))


def _encode_rows(rows: list[dict[str, Any]]) -> tuple[list[int], list[str], int, int]:
    stat_values = [0, 0, 0, 0, 0]
    desc_values = ["", "", "", "", ""]
    stat_all = 0
    locked_bitmap = 0

    for index, row in enumerate(rows[:5]):
        stat_bitmap, desc = _build_stat_bitmap(row)
        stat_values[index] = stat_bitmap
        desc_values[index] = desc
        stat_all |= stat_bitmap & SUBSTAT_ALL_MASK
        if row.get("is_locked"):
            locked_bitmap |= 1 << index

    return stat_values, desc_values, stat_all, locked_bitmap


def _count_locked_bits(locked_bitmap: int) -> int:
    return max(locked_bitmap, 0).bit_count()


def _locked_positions_from_bitmap(locked_bitmap: int) -> list[int]:
    bitmap = max(locked_bitmap, 0)
    return [index + 1 for index in range(5) if bitmap & (1 << index)]


def _normalize_optional_text(raw_value: Any, max_length: int) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    return value[:max_length]


def _mask_preserving_edges(value: str, prefix: int = 1, suffix: int = 1) -> str:
    if not value:
        return ""
    if len(value) <= prefix + suffix:
        return value[0] + "*" * (len(value) - 1)
    return f"{value[:prefix]}{'*' * (len(value) - prefix - suffix)}{value[-suffix:]}"


def _mask_email(email: str) -> str:
    if not email:
        return ""
    local_part, separator, domain = email.partition("@")
    if not separator:
        return _mask_preserving_edges(email, prefix=1, suffix=1)
    masked_local = _mask_preserving_edges(local_part, prefix=1, suffix=1)
    return f"{masked_local}@{domain}"


def _mask_ip(ip: str) -> str:
    if not ip:
        return ""
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.*.*"
    if ":" in ip:
        parts = [part for part in ip.split(":") if part]
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}:*:*"
    return _mask_preserving_edges(ip, prefix=2, suffix=2)


def _masked_sensitive_fields(
    uploader_nickname: str,
    uploader_email: str,
    uploader_wechat: str,
    uploader_qq: str,
    request_ip: str,
) -> dict[str, str]:
    return {
        "uploader_nickname": _mask_preserving_edges(uploader_nickname, prefix=1, suffix=1),
        "uploader_email": _mask_email(uploader_email),
        "uploader_wechat": _mask_preserving_edges(uploader_wechat, prefix=2, suffix=1),
        "uploader_qq": _mask_preserving_edges(uploader_qq, prefix=2, suffix=2),
        "request_ip": _mask_ip(request_ip),
    }


def _mask_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe_payload = json.loads(json.dumps(payload, ensure_ascii=False))

    uploader = safe_payload.get("uploader")
    if isinstance(uploader, dict):
        masked = _masked_sensitive_fields(
            str(uploader.get("nickname") or ""),
            str(uploader.get("email") or ""),
            str(uploader.get("wechat") or ""),
            str(uploader.get("qq") or ""),
            "",
        )
        uploader["nickname"] = masked["uploader_nickname"]
        uploader["email"] = masked["uploader_email"]
        uploader["wechat"] = masked["uploader_wechat"]
        uploader["qq"] = masked["uploader_qq"]

    request_meta = safe_payload.get("request_meta")
    if isinstance(request_meta, dict):
        request_meta["ip"] = _mask_ip(str(request_meta.get("ip") or ""))

    return safe_payload


def build_insert_params(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result") or {}
    uploader = payload.get("uploader") if isinstance(payload.get("uploader"), dict) else {}
    request_meta = payload.get("request_meta") if isinstance(payload.get("request_meta"), dict) else {}
    original_stats = result.get("original_stats") or []
    new_stats = result.get("new_stats") or []

    original_values, original_descs, original_all, locked_bitmap = _encode_rows(original_stats)
    new_values, new_descs, new_all, _ = _encode_rows(new_stats)

    user_id = result.get("user_id")
    if user_id is None:
        user_id = result.get("user_id_raw")
    try:
        user_id = int(str(user_id).replace("特征码:", "").replace("特征码", "").strip()) if user_id else 0
    except ValueError:
        user_id = 0

    return {
        "user_id": user_id,
        "locked_bitmap": locked_bitmap,
        "locked_count": _count_locked_bits(locked_bitmap),
        "original_stat1": original_values[0],
        "original_stat2": original_values[1],
        "original_stat3": original_values[2],
        "original_stat4": original_values[3],
        "original_stat5": original_values[4],
        "original_stat_all": original_all,
        "o1_desc": original_descs[0],
        "o2_desc": original_descs[1],
        "o3_desc": original_descs[2],
        "o4_desc": original_descs[3],
        "o5_desc": original_descs[4],
        "new_stat1": new_values[0],
        "new_stat2": new_values[1],
        "new_stat3": new_values[2],
        "new_stat4": new_values[3],
        "new_stat5": new_values[4],
        "new_stat_all": new_all,
        "n1_desc": new_descs[0],
        "n2_desc": new_descs[1],
        "n3_desc": new_descs[2],
        "n4_desc": new_descs[3],
        "n5_desc": new_descs[4],
        "source_image": str(payload.get("filename") or ""),
        "uploader_nickname": _normalize_optional_text(uploader.get("nickname"), 64),
        "uploader_email": _normalize_optional_text(uploader.get("email"), 128),
        "uploader_wechat": _normalize_optional_text(uploader.get("wechat"), 64),
        "uploader_qq": _normalize_optional_text(uploader.get("qq"), 32),
        "request_ip": _normalize_optional_text(request_meta.get("ip"), 64),
        "raw_json": Jsonb(json.loads(json.dumps(payload, ensure_ascii=False))) if Jsonb else json.loads(json.dumps(payload, ensure_ascii=False)),
    }


def insert_rebuild_log(payload: dict[str, Any]) -> tuple[int, bool]:
    params = build_insert_params(payload)
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(FIND_RECENT_DUPLICATE_SQL, params)
            duplicate_row = cursor.fetchone()
            if duplicate_row:
                return int(duplicate_row[0]), True
            cursor.execute(INSERT_SQL, params)
            inserted_id = cursor.fetchone()[0]
        connection.commit()
    return int(inserted_id), False


def list_rebuild_logs(limit: int = 50, offset: int = 0, user_id: int | None = None) -> tuple[list[RebuildLogListItem], bool]:
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(offset, 0)
    query = f"{LIST_SQL_BASE}\nORDER BY created_at DESC, id DESC\nLIMIT %(fetch_limit)s OFFSET %(offset)s"
    params: dict[str, Any] = {"fetch_limit": safe_limit + 1, "offset": safe_offset}
    if user_id is not None:
        query = f"{LIST_SQL_BASE}\n  AND user_id = %(user_id)s\nORDER BY created_at DESC, id DESC\nLIMIT %(fetch_limit)s OFFSET %(offset)s"
        params["user_id"] = user_id

    with _get_connection() as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()

    has_more = len(rows) > safe_limit
    rows = rows[:safe_limit]

    logs: list[RebuildLogListItem] = []
    for row in rows:
        locked_bitmap = row["locked_bitmap"]
        masked_fields = _masked_sensitive_fields(
            row["uploader_nickname"],
            row["uploader_email"],
            row["uploader_wechat"],
            row["uploader_qq"],
            row["request_ip"],
        )
        logs.append(
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "locked_bitmap": locked_bitmap,
                "locked_count": row["locked_count"],
                "locked_positions": _locked_positions_from_bitmap(locked_bitmap),
                "source_image": row["source_image"],
                "uploaded_image": row["uploaded_image"],
                "uploader_nickname": masked_fields["uploader_nickname"],
                "uploader_email": masked_fields["uploader_email"],
                "uploader_wechat": masked_fields["uploader_wechat"],
                "uploader_qq": masked_fields["uploader_qq"],
                "request_ip": masked_fields["request_ip"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                "original_descs": [row["o1_desc"], row["o2_desc"], row["o3_desc"], row["o4_desc"], row["o5_desc"]],
                "new_descs": [row["n1_desc"], row["n2_desc"], row["n3_desc"], row["n4_desc"], row["n5_desc"]],
            }
        )
    return logs, has_more


def get_rebuild_log(log_id: int) -> RebuildLogDetail | None:
    with _get_connection() as connection:
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
            cursor.execute(DETAIL_SQL, {"id": log_id})
            row = cursor.fetchone()

    if not row:
        return None

    payload = _mask_payload(row["raw_json"] or {})
    locked_bitmap = row["locked_bitmap"]
    masked_fields = _masked_sensitive_fields(
        row["uploader_nickname"],
        row["uploader_email"],
        row["uploader_wechat"],
        row["uploader_qq"],
        row["request_ip"],
    )
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "locked_bitmap": locked_bitmap,
        "locked_count": row["locked_count"],
        "locked_positions": _locked_positions_from_bitmap(locked_bitmap),
        "source_image": row["source_image"],
        "uploaded_image": row["uploaded_image"],
        "uploader_nickname": masked_fields["uploader_nickname"],
        "uploader_email": masked_fields["uploader_email"],
        "uploader_wechat": masked_fields["uploader_wechat"],
        "uploader_qq": masked_fields["uploader_qq"],
        "request_ip": masked_fields["request_ip"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "payload": payload,
    }
def update_rebuild_log_uploaded_image(log_id: int, uploaded_image: str) -> bool:
    with _get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(UPDATE_UPLOADED_IMAGE_SQL, {"id": log_id, "uploaded_image": str(uploaded_image or "")})
            row = cursor.fetchone()
        connection.commit()
    return row is not None
