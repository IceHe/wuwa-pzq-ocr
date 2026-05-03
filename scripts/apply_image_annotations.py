#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.rebuild_log import build_insert_params, normalize_database_url

LABELS_PATH = PROJECT_ROOT / "annotations" / "rebuild_labels.json"
ENV_PATH = PROJECT_ROOT / ".env"

SELECT_ROWS_SQL = """
SELECT
    id,
    user_id,
    source_image,
    uploaded_image,
    raw_json
FROM public.wuwa_rebuild_log
WHERE deleted = 0
  AND uploaded_image = %(uploaded_image)s
ORDER BY id
"""

UPDATE_ROW_SQL = """
UPDATE public.wuwa_rebuild_log
SET
    user_id = %(user_id)s,
    locked_bitmap = %(locked_bitmap)s,
    locked_count = %(locked_count)s,
    original_stat1 = %(original_stat1)s,
    original_stat2 = %(original_stat2)s,
    original_stat3 = %(original_stat3)s,
    original_stat4 = %(original_stat4)s,
    original_stat5 = %(original_stat5)s,
    original_stat_all = %(original_stat_all)s,
    o1_desc = %(o1_desc)s,
    o2_desc = %(o2_desc)s,
    o3_desc = %(o3_desc)s,
    o4_desc = %(o4_desc)s,
    o5_desc = %(o5_desc)s,
    new_stat1 = %(new_stat1)s,
    new_stat2 = %(new_stat2)s,
    new_stat3 = %(new_stat3)s,
    new_stat4 = %(new_stat4)s,
    new_stat5 = %(new_stat5)s,
    new_stat_all = %(new_stat_all)s,
    n1_desc = %(n1_desc)s,
    n2_desc = %(n2_desc)s,
    n3_desc = %(n3_desc)s,
    n4_desc = %(n4_desc)s,
    n5_desc = %(n5_desc)s,
    raw_json = %(raw_json)s,
    updated_at = NOW()
WHERE id = %(id)s
  AND deleted = 0
  AND uploaded_image = %(uploaded_image)s
RETURNING id
"""


def load_env_file() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_image_labels() -> dict[str, dict[str, Any]]:
    data = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else {}
    if not isinstance(items, dict):
        raise RuntimeError("annotations file has invalid items")
    return {
        label["filename"]: label
        for label in items.values()
        if isinstance(label, dict) and label.get("sample_group") == "images" and label.get("filename")
    }


def corrected_payload(row: dict[str, Any], label: dict[str, Any]) -> dict[str, Any]:
    existing = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    payload = json.loads(json.dumps(existing, ensure_ascii=False))
    filename = row.get("source_image") or label["filename"]
    payload["filename"] = filename
    payload["result"] = {
        **(payload.get("result") if isinstance(payload.get("result"), dict) else {}),
        "user_id": label["user_id"],
        "user_id_raw": f"特征码:{label['user_id']}",
        "original_stats": label["original_stats"],
        "new_stats": label["new_stats"],
        "corrected_from_annotation": True,
        "annotation_source": f"images/{label['filename']}",
        "annotation_updated_at": label.get("updated_at"),
    }
    return payload


def update_params(row: dict[str, Any], label: dict[str, Any]) -> dict[str, Any]:
    payload = corrected_payload(row, label)
    params = build_insert_params(payload)
    return {
        "id": row["id"],
        "uploaded_image": row["uploaded_image"],
        "user_id": params["user_id"],
        "locked_bitmap": params["locked_bitmap"],
        "locked_count": params["locked_count"],
        "original_stat1": params["original_stat1"],
        "original_stat2": params["original_stat2"],
        "original_stat3": params["original_stat3"],
        "original_stat4": params["original_stat4"],
        "original_stat5": params["original_stat5"],
        "original_stat_all": params["original_stat_all"],
        "o1_desc": params["o1_desc"],
        "o2_desc": params["o2_desc"],
        "o3_desc": params["o3_desc"],
        "o4_desc": params["o4_desc"],
        "o5_desc": params["o5_desc"],
        "new_stat1": params["new_stat1"],
        "new_stat2": params["new_stat2"],
        "new_stat3": params["new_stat3"],
        "new_stat4": params["new_stat4"],
        "new_stat5": params["new_stat5"],
        "new_stat_all": params["new_stat_all"],
        "n1_desc": params["n1_desc"],
        "n2_desc": params["n2_desc"],
        "n3_desc": params["n3_desc"],
        "n4_desc": params["n4_desc"],
        "n5_desc": params["n5_desc"],
        "raw_json": Jsonb(payload),
    }


def format_descs(params: dict[str, Any]) -> str:
    original = [params[f"o{index}_desc"] for index in range(1, 6)]
    new = [params[f"n{index}_desc"] for index in range(1, 6)]
    return f"original={original} new={new}"


def run(apply: bool) -> int:
    load_env_file()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    if not LABELS_PATH.exists():
        raise RuntimeError(f"missing labels file: {LABELS_PATH}")

    labels = load_image_labels()
    matched_rows = 0
    updated_rows = 0
    unmatched_labels: list[str] = []

    with psycopg.connect(normalize_database_url(database_url), row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            for filename, label in sorted(labels.items()):
                cursor.execute(SELECT_ROWS_SQL, {"uploaded_image": filename})
                rows = cursor.fetchall()
                if not rows:
                    unmatched_labels.append(filename)
                    continue
                for row in rows:
                    matched_rows += 1
                    params = update_params(row, label)
                    print(f"{'UPDATE' if apply else 'DRY-RUN'} id={row['id']} uploaded_image={filename} user_id={row['user_id']}->{params['user_id']}")
                    print(f"  {format_descs(params)}")
                    if apply:
                        cursor.execute(UPDATE_ROW_SQL, params)
                        if cursor.fetchone():
                            updated_rows += 1

        if apply:
            connection.commit()
        else:
            connection.rollback()

    print(f"labels={len(labels)} matched_rows={matched_rows} updated_rows={updated_rows} unmatched_labels={len(unmatched_labels)}")
    if unmatched_labels:
        print("unmatched_labels:")
        for filename in unmatched_labels:
            print(f"  {filename}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply image annotation labels to matching uploaded-image rebuild logs.")
    parser.add_argument("--apply", action="store_true", help="update public.wuwa_rebuild_log; omit for dry-run")
    args = parser.parse_args()
    raise SystemExit(run(apply=args.apply))


if __name__ == "__main__":
    main()
