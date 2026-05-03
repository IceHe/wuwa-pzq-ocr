from __future__ import annotations

import os
import random
import re
import string
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from backend.annotation import configure_annotation_session, register_annotation_routes
from backend.rebuild_log import (
    get_rebuild_log,
    insert_rebuild_log,
    list_rebuild_logs,
    update_rebuild_log_uploaded_image,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
IMAGES_DIR = PROJECT_ROOT / "images"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MIMETYPE_TO_EXTENSION = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _get_request_ip() -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For", "")
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(",")[0].strip()
        if client_ip:
            return client_ip

    for header_name in ("X-Real-IP", "CF-Connecting-IP"):
        header_value = request.headers.get(header_name, "").strip()
        if header_value:
            return header_value

    return (request.remote_addr or "").strip()


def _sanitize_filename_token(value: str, *, allow_dot: bool = False) -> str:
    safe_chars: list[str] = []
    for char in str(value or "").strip():
        if char.isalnum() or char in {"_", "-"} or (allow_dot and char == "."):
            safe_chars.append(char)
        else:
            safe_chars.append("_")

    normalized = re.sub(r"_+", "_", "".join(safe_chars)).strip("._-")
    return normalized


def _guess_image_extension(original_filename: str, mimetype: str | None) -> str:
    suffix = Path(original_filename or "").suffix.lower()
    if suffix in ALLOWED_IMAGE_EXTENSIONS:
        return suffix
    return MIMETYPE_TO_EXTENSION.get((mimetype or "").lower(), ".png")


def build_uploaded_image_name(
    uploader_nickname: str,
    request_ip: str,
    original_filename: str,
    mimetype: str | None = None,
    *,
    now: datetime | None = None,
    images_dir: Path | None = None,
) -> str:
    current_time = now or datetime.now()
    timestamp = current_time.strftime("%Y%m%d_%H%M%S")
    nickname_token = _sanitize_filename_token(uploader_nickname)
    ip_token = _sanitize_filename_token(request_ip, allow_dot=True) or "unknown"
    prefix = f"N_{nickname_token}" if nickname_token else f"IP_{ip_token}"
    extension = _guess_image_extension(original_filename, mimetype)
    stem = f"{prefix}_{timestamp}"
    target_dir = images_dir or IMAGES_DIR
    candidate = f"{stem}{extension}"

    while (target_dir / candidate).exists():
        random_suffix = random.choice(string.ascii_letters)
        candidate = f"{stem}_{random_suffix}{extension}"

    return candidate


def save_uploaded_image(uploaded_file, uploader_nickname: str, request_ip: str) -> str:
    if uploaded_file is None:
        raise ValueError("missing_image")

    mimetype = (uploaded_file.mimetype or "").lower()
    if not mimetype.startswith("image/"):
        raise ValueError("invalid_image_type")

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    target_name = build_uploaded_image_name(
        uploader_nickname=uploader_nickname,
        request_ip=request_ip,
        original_filename=uploaded_file.filename or "",
        mimetype=mimetype,
    )
    uploaded_file.save(IMAGES_DIR / target_name)
    return target_name


def _resolve_saved_image_path(filename: str) -> Path:
    safe_name = _sanitize_filename_token(filename, allow_dot=True)
    if not safe_name or safe_name != str(filename or "").strip():
        raise ValueError("invalid_image_name")
    if Path(safe_name).suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("invalid_image_type")

    image_path = IMAGES_DIR / safe_name
    if not image_path.is_file():
        raise FileNotFoundError(safe_name)
    return image_path


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(FRONTEND_DIR / "templates"),
        static_folder=str(FRONTEND_DIR / "static"),
        static_url_path="/static",
    )
    app.config["JSON_AS_ASCII"] = False
    configure_annotation_session(app)
    register_annotation_routes(app)

    @app.get("/")
    @app.get("/browser-ocr/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    @app.get("/browser-ocr/api/health")
    def health():
        return jsonify({"ok": True})

    @app.post("/api/rebuild_log")
    @app.post("/browser-ocr/api/rebuild_log")
    def create_rebuild_log():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid_json"}), 400

        save_payload = dict(payload)
        raw_request_meta = save_payload.get("request_meta")
        request_meta = dict(raw_request_meta) if isinstance(raw_request_meta, dict) else {}
        request_meta["ip"] = _get_request_ip()
        save_payload["request_meta"] = request_meta

        try:
            inserted_id, duplicated = insert_rebuild_log(save_payload)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

        return jsonify({"ok": True, "id": inserted_id, "duplicated": duplicated})

    @app.post("/api/rebuild_image")
    @app.post("/browser-ocr/api/rebuild_image")
    def create_rebuild_image():
        uploaded_file = request.files.get("image")
        uploader_nickname = request.form.get("nickname", "")
        raw_log_id = request.form.get("log_id", "").strip()

        if not raw_log_id:
            return jsonify({"ok": False, "error": "missing_log_id"}), 400
        try:
            log_id = int(raw_log_id)
        except ValueError:
            return jsonify({"ok": False, "error": "invalid_log_id"}), 400

        try:
            saved_filename = save_uploaded_image(
                uploaded_file,
                uploader_nickname=uploader_nickname,
                request_ip=_get_request_ip(),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

        saved_path = IMAGES_DIR / saved_filename
        try:
            updated = update_rebuild_log_uploaded_image(log_id, saved_filename)
        except Exception as exc:
            saved_path.unlink(missing_ok=True)
            return jsonify({"ok": False, "error": str(exc)}), 500

        if not updated:
            saved_path.unlink(missing_ok=True)
            return jsonify({"ok": False, "error": "log_not_found"}), 404

        return jsonify({"ok": True, "filename": saved_filename})

    @app.get("/api/rebuild_logs")
    @app.get("/browser-ocr/api/rebuild_logs")
    def fetch_rebuild_logs():
        try:
            limit = int(request.args.get("limit", "30"))
        except ValueError:
            return jsonify({"ok": False, "error": "invalid_limit"}), 400
        try:
            offset = int(request.args.get("offset", "0"))
        except ValueError:
            return jsonify({"ok": False, "error": "invalid_offset"}), 400

        raw_user_id = request.args.get("user_id")
        try:
            user_id = int(raw_user_id) if raw_user_id else None
        except ValueError:
            return jsonify({"ok": False, "error": "invalid_user_id"}), 400

        try:
            logs, has_more = list_rebuild_logs(limit=limit, offset=offset, user_id=user_id)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

        return jsonify({"ok": True, "items": logs, "limit": limit, "offset": max(offset, 0), "has_more": has_more})

    @app.get("/api/rebuild_log/<int:log_id>")
    @app.get("/browser-ocr/api/rebuild_log/<int:log_id>")
    def fetch_rebuild_log(log_id: int):
        try:
            item = get_rebuild_log(log_id)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

        if item is None:
            return jsonify({"ok": False, "error": "not_found"}), 404

        return jsonify({"ok": True, "item": item})

    @app.get("/api/rebuild_image/<path:filename>")
    @app.get("/browser-ocr/api/rebuild_image/<path:filename>")
    def fetch_rebuild_image(filename: str):
        try:
            image_path = _resolve_saved_image_path(filename)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except FileNotFoundError:
            return jsonify({"ok": False, "error": "image_not_found"}), 404

        return send_from_directory(IMAGES_DIR, image_path.name)

    @app.get("/browser-ocr/static/<path:filename>")
    def prefixed_static(filename: str):
        return send_from_directory(app.static_folder, filename)

    return app


def main() -> None:
    app = create_app()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    debug = os.environ.get("DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
