from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import annotation
from backend.app import create_app
from backend.annotation import SampleGroup


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _valid_rows(*, locked: bool = False, is_new: bool = False) -> list[dict[str, object]]:
    return [
        {"name": "暴击", "value": "6.3%", "tier": 1, "is_locked": locked and index == 0, "is_new": is_new}
        for index in range(5)
    ]


class AnnotationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.groups = (
            SampleGroup("samples-20260503", "2026-05-03 新样本", self.root / "samples-20260503"),
            SampleGroup("images", "线上上传样本", self.root / "images"),
            SampleGroup("samples", "旧回归样本", self.root / "samples"),
        )
        for group in self.groups:
            group.directory.mkdir(parents=True)
            (group.directory / "sample.png").write_bytes(PNG_1X1)

        self.env_patch = patch.dict(
            os.environ,
            {
                "ANNOTATION_PASSWORD": "secret",
                "FLASK_SECRET_KEY": "test-secret",
            },
        )
        self.groups_patch = patch.object(annotation, "SAMPLE_GROUPS", self.groups)
        self.labels_path = self.root / "annotations" / "rebuild_labels.json"
        self.labels_patch = patch.object(annotation, "LABELS_PATH", self.labels_path)
        self.reports_dir = self.root / "reports" / "ocr-regression"
        self.reports_patch = patch.object(annotation, "REPORTS_DIR", self.reports_dir)

        self.env_patch.start()
        self.groups_patch.start()
        self.labels_patch.start()
        self.reports_patch.start()
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.reports_patch.stop()
        self.labels_patch.stop()
        self.groups_patch.stop()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def login(self) -> None:
        response = self.client.post("/annotation/api/login", json={"password": "secret"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})

    def test_samples_requires_login(self) -> None:
        response = self.client.get("/annotation/api/samples")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"ok": False, "error": "not_authenticated"})

    def test_login_rejects_wrong_password(self) -> None:
        response = self.client.post("/annotation/api/login", json={"password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"ok": False, "error": "invalid_password"})

    def test_samples_lists_all_groups_after_login(self) -> None:
        self.login()
        response = self.client.get("/annotation/api/samples")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual([group["key"] for group in payload["groups"]], ["samples-20260503", "images", "samples"])
        self.assertEqual([group["count"] for group in payload["groups"]], [1, 1, 1])
        self.assertEqual(payload["stats"], {"total": 3, "completed": 0})
        self.assertEqual(payload["items"][0]["image_size"], {"width": 1, "height": 1})

    def test_image_route_serves_sample_after_login(self) -> None:
        self.login()
        response = self.client.get("/annotation/api/image/images/sample.png")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"\x89PNG"))
        response.close()

    def test_save_label_writes_independent_json_file(self) -> None:
        self.login()
        payload = {
            "user_id": "120003177",
            "original_stats": _valid_rows(locked=True),
            "new_stats": _valid_rows(is_new=True),
            "notes": "人工确认",
        }
        response = self.client.put("/annotation/api/label/images/sample.png", json=payload)
        self.assertEqual(response.status_code, 200)
        saved = response.get_json()["label"]
        self.assertEqual(saved["sample_group"], "images")
        self.assertEqual(saved["filename"], "sample.png")
        self.assertEqual(saved["user_id"], "120003177")
        self.assertEqual(saved["original_stats"][0]["is_locked"], True)

        disk_payload = json.loads(self.labels_path.read_text(encoding="utf-8"))
        self.assertIn("images/sample.png", disk_payload["items"])
        self.assertEqual(disk_payload["items"]["images/sample.png"]["notes"], "人工确认")

        samples_response = self.client.get("/annotation/api/samples")
        groups = samples_response.get_json()["groups"]
        images_group = next(group for group in groups if group["key"] == "images")
        self.assertEqual(images_group["completed"], 1)

        labels_response = self.client.get("/annotation/api/labels")
        self.assertEqual(labels_response.status_code, 200)
        self.assertIn("images/sample.png", labels_response.get_json()["labels"])

    def test_save_label_inferrs_tier_from_name_and_value(self) -> None:
        self.login()
        rows_without_tier = [
            {"name": "攻击", "value": "60", "is_locked": False, "is_new": False},
            {"name": "暴击伤害", "value": "21.0%", "is_locked": False, "is_new": False},
            {"name": "防御", "value": "14.7%", "is_locked": False, "is_new": False},
            {"name": "共鸣效率", "value": "12.4%", "is_locked": False, "is_new": False},
            {"name": "生命", "value": "580", "is_locked": False, "is_new": False},
        ]
        response = self.client.put(
            "/annotation/api/label/images/sample.png",
            json={
                "user_id": "120003177",
                "original_stats": rows_without_tier,
                "new_stats": [{**row, "is_new": True} for row in rows_without_tier],
            },
        )
        self.assertEqual(response.status_code, 200)
        saved = response.get_json()["label"]
        self.assertEqual([row["tier"] for row in saved["original_stats"]], [4, 8, 8, 8, 8])

    def test_save_regression_report_writes_ignored_report_file(self) -> None:
        self.login()
        response = self.client.post(
            "/annotation/api/regression_reports",
            json={"total": 1, "passed": 1, "failed": 0, "items": []},
        )
        self.assertEqual(response.status_code, 200)
        filename = response.get_json()["filename"]
        self.assertTrue(filename.startswith("ocr_regression_"))
        report_path = self.reports_dir / filename
        self.assertTrue(report_path.exists())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["report"]["passed"], 1)

    def test_save_label_rejects_invalid_filename(self) -> None:
        self.login()
        response = self.client.put(
            "/annotation/api/label/images/%2E%2E/evil.png",
            json={
                "user_id": "120003177",
                "original_stats": _valid_rows(),
                "new_stats": _valid_rows(is_new=True),
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"ok": False, "error": "invalid_filename"})


class AnnotationConfigurationTest(unittest.TestCase):
    def test_annotation_api_is_closed_without_password(self) -> None:
        with patch.dict(os.environ, {"ANNOTATION_PASSWORD": "", "FLASK_SECRET_KEY": "test-secret"}):
            app = create_app()
            client = app.test_client()
            response = client.get("/annotation/api/samples")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"ok": False, "error": "annotation_password_not_configured"})


if __name__ == "__main__":
    unittest.main()
