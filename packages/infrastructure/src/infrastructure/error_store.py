"""ErrorPageStore ポートの具象（Amazon S3, boto3）。

スクレイピング失敗の証跡（HTML 等）を S3 に保存する。`content` が None でも調査の
手がかりとしてマーカーオブジェクトを必ず書き、url / captured_at をオブジェクトメタ
データに付与する。
"""

from __future__ import annotations

from typing import Any

import boto3

from domain.collection import ErrorPage

# content が取得できなかった場合に書くマーカー本文。
_MARKER_BODY = "error page content was not captured"


class S3ErrorPageStore:
    """ErrorPage を S3 に保存する ErrorPageStore。"""

    def __init__(self, bucket: str, *, s3_client: Any | None = None) -> None:
        self._bucket = bucket
        self._client = s3_client if s3_client is not None else boto3.client("s3")

    def save(self, page: ErrorPage) -> None:
        # key スキーム: collect/YYYY/MM/DDThhmmss.html（captured_at は JST aware を想定）
        key = f"collect/{page.captured_at:%Y/%m/%dT%H%M%S}.html"
        if page.content is None:
            body = _MARKER_BODY.encode("utf-8")
            content_type = "text/plain"
        else:
            body = page.content.encode("utf-8")
            content_type = "text/html"
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata={"url": page.url, "captured_at": page.captured_at.isoformat()},
        )
