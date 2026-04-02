from __future__ import annotations

from typing import Any, TypedDict


class RebuildLogListItem(TypedDict):
    id: int
    user_id: int
    locked_bitmap: int
    locked_count: int
    locked_positions: list[int]
    source_image: str
    uploaded_image: str
    uploader_nickname: str
    uploader_email: str
    uploader_wechat: str
    uploader_qq: str
    request_ip: str
    created_at: str | None
    updated_at: str | None
    original_descs: list[str]
    new_descs: list[str]


class RebuildLogDetail(TypedDict):
    id: int
    user_id: int
    locked_bitmap: int
    locked_count: int
    locked_positions: list[int]
    source_image: str
    uploaded_image: str
    uploader_nickname: str
    uploader_email: str
    uploader_wechat: str
    uploader_qq: str
    request_ip: str
    created_at: str | None
    updated_at: str | None
    payload: dict[str, Any]
