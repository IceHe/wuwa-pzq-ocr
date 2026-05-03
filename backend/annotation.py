from __future__ import annotations

import hashlib
import hmac
import json
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from flask import Flask, jsonify, render_template, request, send_from_directory, session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS_DIR = PROJECT_ROOT / "annotations"
LABELS_PATH = ANNOTATIONS_DIR / "rebuild_labels.json"
REPORTS_DIR = PROJECT_ROOT / "reports" / "ocr-regression"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class SampleGroup:
    key: str
    label: str
    directory: Path


SAMPLE_GROUPS = (
    SampleGroup("failed-samples", "失败待标注", PROJECT_ROOT / "failed-samples"),
    SampleGroup("samples-20260503", "2026-05-03 新样本", PROJECT_ROOT / "samples-20260503"),
    SampleGroup("images", "线上上传样本", PROJECT_ROOT / "images"),
    SampleGroup("samples", "旧回归样本", PROJECT_ROOT / "samples"),
)

STAT_NAMES = (
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
)

STAT_VALUE_TABLE = {
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


def configure_annotation_session(app: Flask) -> None:
    if app.secret_key:
        return

    import os

    configured_secret = app.config.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if configured_secret:
        app.secret_key = configured_secret
        return

    password = _annotation_password()
    secret_source = f"wuwa-annotation:{password}" if password else "wuwa-annotation:unconfigured"
    app.secret_key = hashlib.sha256(secret_source.encode("utf-8")).hexdigest()


def register_annotation_routes(app: Flask) -> None:
    @app.get("/annotation")
    @app.get("/annotation/")
    def annotation_index():
        return render_template(
            "annotation.html",
            annotation_configured=bool(_annotation_password()),
            annotation_authenticated=_is_authenticated(),
        )

    @app.post("/annotation/api/login")
    def annotation_login():
        password = _annotation_password()
        if not password:
            return _json_error("annotation_password_not_configured", 503)

        payload = request.get_json(silent=True) or {}
        candidate = str(payload.get("password") or "")
        if not hmac.compare_digest(candidate, password):
            session.pop("annotation_authenticated", None)
            return _json_error("invalid_password", 401)

        session["annotation_authenticated"] = True
        return jsonify({"ok": True})

    @app.post("/annotation/api/logout")
    def annotation_logout():
        session.pop("annotation_authenticated", None)
        return jsonify({"ok": True})

    @app.get("/annotation/api/session")
    def annotation_session():
        return jsonify(
            {
                "ok": True,
                "configured": bool(_annotation_password()),
                "authenticated": _is_authenticated(),
            }
        )

    @app.get("/annotation/api/samples")
    @_annotation_auth_required
    def annotation_samples():
        labels = _load_label_store()
        groups_payload = []
        items = []

        for group in SAMPLE_GROUPS:
            samples = _list_group_samples(group)
            completed_count = 0
            for path in samples:
                sample_id = _sample_id(group.key, path.name)
                label = labels["items"].get(sample_id)
                completed = bool(label)
                completed_count += 1 if completed else 0
                encoded_filename = quote(path.name)
                items.append(
                    {
                        "id": sample_id,
                        "group": group.key,
                        "group_label": group.label,
                        "filename": path.name,
                        "image_url": f"/annotation/api/image/{group.key}/{encoded_filename}",
                        "label_url": f"/annotation/api/label/{group.key}/{encoded_filename}",
                        "completed": completed,
                        "updated_at": label.get("updated_at") if isinstance(label, dict) else None,
                        "image_size": _read_image_size(path),
                    }
                )

            groups_payload.append(
                {
                    "key": group.key,
                    "label": group.label,
                    "count": len(samples),
                    "completed": completed_count,
                }
            )

        return jsonify(
            {
                "ok": True,
                "groups": groups_payload,
                "items": items,
                "stats": {
                    "total": len(items),
                    "completed": sum(1 for item in items if item["completed"]),
                },
            }
        )

    @app.get("/annotation/api/image/<group_key>/<path:filename>")
    @_annotation_auth_required
    def annotation_image(group_key: str, filename: str):
        try:
            group, path = _resolve_sample_path(group_key, filename)
        except ValueError as exc:
            return _json_error(str(exc), 404)
        return send_from_directory(group.directory, path.name)

    @app.get("/annotation/api/label/<group_key>/<path:filename>")
    @_annotation_auth_required
    def annotation_label(group_key: str, filename: str):
        try:
            _, path = _resolve_sample_path(group_key, filename)
        except ValueError as exc:
            return _json_error(str(exc), 404)

        labels = _load_label_store()
        sample_id = _sample_id(group_key, path.name)
        return jsonify({"ok": True, "label": labels["items"].get(sample_id)})

    @app.get("/annotation/api/labels")
    @_annotation_auth_required
    def annotation_labels():
        labels = _load_label_store()
        return jsonify({"ok": True, "labels": labels["items"], "updated_at": labels.get("updated_at")})

    @app.put("/annotation/api/label/<group_key>/<path:filename>")
    @app.post("/annotation/api/label/<group_key>/<path:filename>")
    @_annotation_auth_required
    def annotation_save_label(group_key: str, filename: str):
        try:
            _, path = _resolve_sample_path(group_key, filename)
        except ValueError as exc:
            return _json_error(str(exc), 404)

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _json_error("invalid_json", 400)

        try:
            label = _normalize_label(group_key, path, payload)
        except ValueError as exc:
            return _json_error(str(exc), 400)

        labels = _load_label_store()
        labels["items"][_sample_id(group_key, path.name)] = label
        labels["updated_at"] = _now_iso()
        _save_label_store(labels)
        return jsonify({"ok": True, "label": label})

    @app.post("/annotation/api/regression_reports")
    @_annotation_auth_required
    def annotation_save_regression_report():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _json_error("invalid_json", 400)
        filename = _save_regression_report(payload)
        return jsonify({"ok": True, "filename": filename})


def _annotation_password() -> str:
    import os

    return str(os.environ.get("ANNOTATION_PASSWORD") or "").strip()


def _is_authenticated() -> bool:
    return bool(_annotation_password() and session.get("annotation_authenticated"))


def _annotation_auth_required(view_func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view_func)
    def wrapped(*args: Any, **kwargs: Any):
        if not _annotation_password():
            return _json_error("annotation_password_not_configured", 503)
        if not session.get("annotation_authenticated"):
            return _json_error("not_authenticated", 401)
        return view_func(*args, **kwargs)

    return wrapped


def _json_error(error: str, status_code: int):
    return jsonify({"ok": False, "error": error}), status_code


def _sample_id(group_key: str, filename: str) -> str:
    return f"{group_key}/{filename}"


def _group_by_key(group_key: str) -> SampleGroup:
    for group in SAMPLE_GROUPS:
        if group.key == group_key:
            return group
    raise ValueError("invalid_group")


def _safe_filename(filename: str) -> str:
    raw_filename = str(filename or "")
    if not raw_filename or raw_filename != Path(raw_filename).name:
        raise ValueError("invalid_filename")
    if "/" in raw_filename or "\\" in raw_filename or "\x00" in raw_filename:
        raise ValueError("invalid_filename")
    if Path(raw_filename).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("invalid_image_type")
    return raw_filename


def _resolve_sample_path(group_key: str, filename: str) -> tuple[SampleGroup, Path]:
    group = _group_by_key(group_key)
    safe_filename = _safe_filename(filename)
    path = group.directory / safe_filename
    if not path.is_file():
        raise ValueError("sample_not_found")
    return group, path


def _list_group_samples(group: SampleGroup) -> list[Path]:
    if not group.directory.is_dir():
        return []
    return sorted(
        path
        for path in group.directory.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
    )


def _load_label_store() -> dict[str, Any]:
    if not LABELS_PATH.exists():
        return {"version": 1, "updated_at": None, "items": {}}

    with LABELS_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        return {"version": 1, "updated_at": None, "items": {}}
    items = data.get("items")
    if not isinstance(items, dict):
        data["items"] = {}
    data.setdefault("version", 1)
    data.setdefault("updated_at", None)
    return data


def _save_label_store(labels: dict[str, Any]) -> None:
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = LABELS_PATH.with_name(f"{LABELS_PATH.name}.tmp")
    temp_path.write_text(json.dumps(labels, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(LABELS_PATH)


def _save_regression_report(report: dict[str, Any]) -> str:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ocr_regression_{timestamp}.json"
    output = {
        "version": 1,
        "created_at": _now_iso(),
        "report": report,
    }
    target_path = REPORTS_DIR / filename
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    temp_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(target_path)
    return filename


def _normalize_label(group_key: str, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    user_id = str(payload.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("missing_user_id")
    if not user_id.isdigit():
        raise ValueError("invalid_user_id")

    original_stats = _normalize_rows(payload.get("original_stats"), side="original")
    new_stats = _normalize_rows(payload.get("new_stats"), side="new")
    notes = str(payload.get("notes") or "").strip()[:1000]

    return {
        "sample_group": group_key,
        "filename": path.name,
        "image_size": _read_image_size(path),
        "updated_at": _now_iso(),
        "user_id": user_id,
        "original_stats": original_stats,
        "new_stats": new_stats,
        "notes": notes,
    }


def _normalize_rows(raw_rows: Any, *, side: str) -> list[dict[str, Any]]:
    if not isinstance(raw_rows, list) or len(raw_rows) != 5:
        raise ValueError(f"invalid_{side}_stats")

    rows = []
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict):
            raise ValueError(f"invalid_{side}_row_{index + 1}")

        name = str(raw_row.get("name") or "").strip()
        value = str(raw_row.get("value") or "").strip()
        if name not in STAT_NAMES:
            raise ValueError(f"invalid_{side}_name_{index + 1}")
        if not value:
            raise ValueError(f"missing_{side}_value_{index + 1}")

        tier = raw_row.get("tier")
        normalized_tier = _infer_tier(name, value)
        if normalized_tier is None and tier not in ("", None):
            try:
                normalized_tier = int(tier)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid_{side}_tier_{index + 1}") from exc
            if normalized_tier < 1 or normalized_tier > 8:
                raise ValueError(f"invalid_{side}_tier_{index + 1}")

        rows.append(
            {
                "name": name,
                "value": value,
                "tier": normalized_tier,
                "is_locked": bool(raw_row.get("is_locked")),
                "is_new": bool(raw_row.get("is_new", side == "new")),
            }
        )

    return rows


def _parse_stat_number(raw_value: str) -> float | None:
    text = str(raw_value or "").replace("%", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _resolve_value_table(name: str, raw_value: str) -> tuple[tuple[float, ...], bool] | None:
    if name in {"攻击", "生命", "防御"} and "%" not in str(raw_value or ""):
        return STAT_VALUE_TABLE.get(f"固定{name}")
    return STAT_VALUE_TABLE.get(name)


def _infer_tier(name: str, raw_value: str) -> int | None:
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_image_size(path: Path) -> dict[str, int] | None:
    try:
        suffix = path.suffix.lower()
        if suffix == ".png":
            return _read_png_size(path)
        if suffix in {".jpg", ".jpeg"}:
            return _read_jpeg_size(path)
        if suffix == ".webp":
            return _read_webp_size(path)
    except OSError:
        return None
    return None


def _read_png_size(path: Path) -> dict[str, int] | None:
    with path.open("rb") as file:
        header = file.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return {"width": int(width), "height": int(height)}


def _read_jpeg_size(path: Path) -> dict[str, int] | None:
    with path.open("rb") as file:
        if file.read(2) != b"\xff\xd8":
            return None
        while True:
            byte = file.read(1)
            if not byte:
                return None
            if byte != b"\xff":
                continue
            marker = file.read(1)
            while marker == b"\xff":
                marker = file.read(1)
            if not marker:
                return None
            marker_value = marker[0]
            if marker_value in {0xD8, 0xD9}:
                continue
            length_bytes = file.read(2)
            if len(length_bytes) != 2:
                return None
            segment_length = int.from_bytes(length_bytes, "big")
            if segment_length < 2:
                return None
            if marker_value in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                data = file.read(5)
                if len(data) != 5:
                    return None
                height = int.from_bytes(data[1:3], "big")
                width = int.from_bytes(data[3:5], "big")
                return {"width": int(width), "height": int(height)}
            file.seek(segment_length - 2, 1)


def _read_webp_size(path: Path) -> dict[str, int] | None:
    with path.open("rb") as file:
        header = file.read(30)
    if len(header) < 30 or header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return None

    chunk_type = header[12:16]
    if chunk_type == b"VP8X":
        width = 1 + int.from_bytes(header[24:27], "little")
        height = 1 + int.from_bytes(header[27:30], "little")
        return {"width": int(width), "height": int(height)}
    if chunk_type == b"VP8L" and header[20] == 0x2F:
        bits = int.from_bytes(header[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return {"width": int(width), "height": int(height)}
    if chunk_type == b"VP8 " and header[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(header[26:28], "little") & 0x3FFF
        height = int.from_bytes(header[28:30], "little") & 0x3FFF
        return {"width": int(width), "height": int(height)}
    return None
