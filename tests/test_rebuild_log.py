from __future__ import annotations

import unittest

from backend.rebuild_log import (
    FIND_RECENT_DUPLICATE_SQL,
    _locked_positions_from_bitmap,
    _mask_ip,
    _mask_payload,
    _masked_sensitive_fields,
    build_insert_params,
)


class RebuildLogTest(unittest.TestCase):
    def test_build_insert_params_counts_locked_stats(self) -> None:
        payload = {
            "filename": "sample.png",
            "uploader": {
                "nickname": "  昵称  ",
                "email": " uploader@example.com ",
                "wechat": "  wx-id  ",
                "qq": " 123456 ",
            },
            "request_meta": {
                "ip": " 203.0.113.20 ",
            },
            "result": {
                "user_id": "120003177",
                "original_stats": [
                    {"name": "暴击", "value": "6.3%", "tier": 1, "is_locked": True},
                    {"name": "攻击", "value": "6.4%", "tier": 1, "is_locked": False},
                    {"name": "生命", "value": "6.4%", "tier": 1, "is_locked": True},
                ],
                "new_stats": [],
            },
        }

        params = build_insert_params(payload)

        self.assertEqual(params["locked_bitmap"], 5)
        self.assertEqual(params["locked_count"], 2)
        self.assertEqual(params["uploader_nickname"], "昵称")
        self.assertEqual(params["uploader_email"], "uploader@example.com")
        self.assertEqual(params["uploader_wechat"], "wx-id")
        self.assertEqual(params["uploader_qq"], "123456")
        self.assertEqual(params["request_ip"], "203.0.113.20")

    def test_locked_positions_from_bitmap(self) -> None:
        self.assertEqual(_locked_positions_from_bitmap(0), [])
        self.assertEqual(_locked_positions_from_bitmap(5), [1, 3])

    def test_duplicate_query_includes_locked_bitmap(self) -> None:
        self.assertIn("AND locked_bitmap = %(locked_bitmap)s", FIND_RECENT_DUPLICATE_SQL)

    def test_duplicate_query_uses_one_hour_window(self) -> None:
        self.assertIn("AND created_at >= NOW() - INTERVAL '1 hour'", FIND_RECENT_DUPLICATE_SQL)

    def test_masked_sensitive_fields(self) -> None:
        masked = _masked_sensitive_fields("测试上传者", "tester@example.com", "wechat001", "12345678", "203.0.113.20")

        self.assertEqual(masked["uploader_nickname"], "测***者")
        self.assertEqual(masked["uploader_email"], "t****r@example.com")
        self.assertEqual(masked["uploader_wechat"], "we******1")
        self.assertEqual(masked["uploader_qq"], "12****78")
        self.assertEqual(masked["request_ip"], "203.0.*.*")

    def test_mask_ip_supports_ipv6(self) -> None:
        self.assertEqual(_mask_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334"), "2001:0db8:*:*")

    def test_mask_payload_hides_nested_sensitive_fields(self) -> None:
        payload = {
            "uploader": {
                "nickname": "测试上传者",
                "email": "tester@example.com",
                "wechat": "wechat001",
                "qq": "12345678",
            },
            "request_meta": {
                "ip": "203.0.113.20",
            },
        }

        masked = _mask_payload(payload)

        self.assertEqual(masked["uploader"]["nickname"], "测***者")
        self.assertEqual(masked["uploader"]["email"], "t****r@example.com")
        self.assertEqual(masked["uploader"]["wechat"], "we******1")
        self.assertEqual(masked["uploader"]["qq"], "12****78")
        self.assertEqual(masked["request_meta"]["ip"], "203.0.*.*")
        self.assertEqual(payload["uploader"]["nickname"], "测试上传者")


if __name__ == "__main__":
    unittest.main()
