from __future__ import annotations

import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from backend.app import build_uploaded_image_name, create_app


class WebAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = self.app.test_client()

    def test_index_page_loads(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("声骸频整识别记录", body)
        self.assertIn("识别成功后上传词条、特征码和图片", body)
        self.assertIn("默认折叠", body)
        self.assertIn("点击空白处、图片或按 Esc 关闭", body)
        self.assertIn("tesseract.min.js", body)
        self.assertIn("./static/favicon.svg?v=20260402b", body)
        self.assertIn("./static/styles.css?v=20260402b", body)
        self.assertIn("./static/app.js?v=20260402d", body)
        self.assertIn('id="history-latest"', body)
        self.assertIn('id="history-prev"', body)
        self.assertIn('id="history-next"', body)
        self.assertIn('id="history-page-input"', body)
        self.assertIn('id="history-jump"', body)
        self.assertIn('id="uploader-nickname"', body)
        self.assertIn('id="uploader-email"', body)
        self.assertIn('id="uploader-wechat"', body)
        self.assertIn('id="uploader-qq"', body)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})

    def test_prefixed_index_page_loads(self) -> None:
        response = self.client.get("/browser-ocr/")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("./static/favicon.svg?v=20260402b", body)
        self.assertIn("./static/styles.css?v=20260402b", body)
        self.assertIn("./static/app.js?v=20260402d", body)

    def test_prefixed_health_endpoint(self) -> None:
        response = self.client.get("/browser-ocr/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})

    @patch("backend.app.insert_rebuild_log", return_value=(123, False))
    def test_create_rebuild_log(self, insert_rebuild_log) -> None:
        payload = {
            "filename": "sample.png",
            "uploader": {
                "nickname": "测试上传者",
                "email": "tester@example.com",
            },
            "result": {
                "user_id": "120003177",
                "original_stats": [{"name": "暴击", "value": "6.3%", "tier": 1, "is_locked": True}],
                "new_stats": [{"name": "暴击伤害", "value": "12.6%", "tier": 1, "is_locked": False}],
            },
        }
        response = self.client.post("/api/rebuild_log", json=payload, headers={"X-Forwarded-For": "203.0.113.8, 10.0.0.1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "id": 123, "duplicated": False})
        insert_rebuild_log.assert_called_once_with(
            {
                **payload,
                "request_meta": {"ip": "203.0.113.8"},
            }
        )

    @patch("backend.app.insert_rebuild_log", return_value=(123, True))
    def test_create_rebuild_log_duplicate(self, insert_rebuild_log) -> None:
        payload = {
            "filename": "sample.png",
            "result": {
                "user_id": "120003177",
                "original_stats": [{"name": "暴击", "value": "6.3%", "tier": 1, "is_locked": True}],
                "new_stats": [{"name": "暴击伤害", "value": "12.6%", "tier": 1, "is_locked": False}],
            },
        }
        response = self.client.post("/api/rebuild_log", json=payload, headers={"X-Real-IP": "198.51.100.9"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "id": 123, "duplicated": True})
        insert_rebuild_log.assert_called_once_with(
            {
                **payload,
                "request_meta": {"ip": "198.51.100.9"},
            }
        )

    def test_create_rebuild_log_rejects_invalid_json(self) -> None:
        response = self.client.post("/api/rebuild_log", data="oops", content_type="text/plain")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "invalid_json"})

    @patch("backend.app.update_rebuild_log_uploaded_image", return_value=True)
    @patch("backend.app.save_uploaded_image", return_value="N_测试上传者_20260402_120102.png")
    def test_create_rebuild_image(self, save_uploaded_image, update_rebuild_log_uploaded_image) -> None:
        response = self.client.post(
            "/api/rebuild_image",
            data={
                "log_id": "123",
                "nickname": "测试上传者",
                "image": (io.BytesIO(b"fake-image-bytes"), "sample.png"),
            },
            content_type="multipart/form-data",
            headers={"X-Forwarded-For": "203.0.113.8, 10.0.0.1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "filename": "N_测试上传者_20260402_120102.png"})

        args, kwargs = save_uploaded_image.call_args
        self.assertTrue(args)
        self.assertEqual(kwargs["uploader_nickname"], "测试上传者")
        self.assertEqual(kwargs["request_ip"], "203.0.113.8")
        update_rebuild_log_uploaded_image.assert_called_once_with(123, "N_测试上传者_20260402_120102.png")

    def test_create_rebuild_image_requires_log_id(self) -> None:
        response = self.client.post(
            "/api/rebuild_image",
            data={"image": (io.BytesIO(b"fake-image-bytes"), "sample.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "missing_log_id"})

    def test_create_rebuild_image_rejects_invalid_log_id(self) -> None:
        response = self.client.post(
            "/api/rebuild_image",
            data={
                "log_id": "abc",
                "image": (io.BytesIO(b"fake-image-bytes"), "sample.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "invalid_log_id"})

    def test_create_rebuild_image_requires_file(self) -> None:
        response = self.client.post(
            "/api/rebuild_image",
            data={"log_id": "123", "nickname": "测试上传者"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "missing_image"})

    @patch("backend.app.save_uploaded_image", side_effect=ValueError("invalid_image_type"))
    def test_create_rebuild_image_rejects_invalid_type(self, save_uploaded_image) -> None:
        response = self.client.post(
            "/api/rebuild_image",
            data={"log_id": "123", "image": (io.BytesIO(b"not-an-image"), "sample.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"ok": False, "error": "invalid_image_type"})
        save_uploaded_image.assert_called_once()

    @patch("backend.app.update_rebuild_log_uploaded_image", return_value=False)
    @patch("backend.app.save_uploaded_image", return_value="N_测试上传者_20260402_120102.png")
    def test_create_rebuild_image_rejects_missing_log(self, save_uploaded_image, update_rebuild_log_uploaded_image) -> None:
        response = self.client.post(
            "/api/rebuild_image",
            data={
                "log_id": "999",
                "image": (io.BytesIO(b"fake-image-bytes"), "sample.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json(), {"ok": False, "error": "log_not_found"})
        update_rebuild_log_uploaded_image.assert_called_once_with(999, "N_测试上传者_20260402_120102.png")

    @patch("backend.app.list_rebuild_logs", return_value=([{"id": 1, "user_id": 120003177, "locked_count": 2, "locked_positions": [1, 3], "uploaded_image": "N_test_20260402_120102.png"}], True))
    def test_fetch_rebuild_logs(self, list_rebuild_logs) -> None:
        response = self.client.get("/api/rebuild_logs?limit=20&offset=40&user_id=120003177")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "items": [{"id": 1, "user_id": 120003177, "locked_count": 2, "locked_positions": [1, 3], "uploaded_image": "N_test_20260402_120102.png"}], "limit": 20, "offset": 40, "has_more": True})
        list_rebuild_logs.assert_called_once_with(limit=20, offset=40, user_id=120003177)

    @patch("backend.app.get_rebuild_log", return_value={"id": 7, "locked_count": 1, "locked_positions": [2], "uploaded_image": "N_test_20260402_120102.png", "payload": {"filename": "a.png"}})
    def test_fetch_rebuild_log(self, get_rebuild_log) -> None:
        response = self.client.get("/api/rebuild_log/7")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "item": {"id": 7, "locked_count": 1, "locked_positions": [2], "uploaded_image": "N_test_20260402_120102.png", "payload": {"filename": "a.png"}}})
        get_rebuild_log.assert_called_once_with(7)

    def test_build_uploaded_image_name_uses_nickname_when_present(self) -> None:
        filename = build_uploaded_image_name(
            uploader_nickname="IceHe 上传者",
            request_ip="203.0.113.8",
            original_filename="sample.png",
            now=datetime(2026, 4, 2, 12, 1, 2),
            images_dir=Path("/tmp/nonexistent-images-dir"),
        )
        self.assertEqual(filename, "N_IceHe_上传者_20260402_120102.png")

    def test_build_uploaded_image_name_uses_ip_when_nickname_missing(self) -> None:
        filename = build_uploaded_image_name(
            uploader_nickname="",
            request_ip="203.0.113.8",
            original_filename="sample.webp",
            now=datetime(2026, 4, 2, 12, 1, 2),
            images_dir=Path("/tmp/nonexistent-images-dir"),
        )
        self.assertEqual(filename, "IP_203.0.113.8_20260402_120102.webp")

    @patch("backend.app.random.choice", return_value="Q")
    def test_build_uploaded_image_name_adds_random_suffix_on_conflict(self, random_choice) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            images_dir = Path(temp_dir)
            existing = images_dir / "N_测试上传者_20260402_120102.png"
            existing.write_bytes(b"existing")

            filename = build_uploaded_image_name(
                uploader_nickname="测试上传者",
                request_ip="203.0.113.8",
                original_filename="sample.png",
                now=datetime(2026, 4, 2, 12, 1, 2),
                images_dir=images_dir,
            )

        self.assertEqual(filename, "N_测试上传者_20260402_120102_Q.png")
        random_choice.assert_called_once()


if __name__ == "__main__":
    unittest.main()
