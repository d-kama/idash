"""S3ErrorPageStore は証跡を S3 に保存する（ErrorPageStore の具象）。

content があれば HTML 本文、None でもマーカーを必ず書く。url / captured_at は
オブジェクトメタデータに付与する。
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import boto3
from moto import mock_aws

from domain.collection import ErrorPage
from infrastructure.error_store import S3ErrorPageStore

BUCKET = "idash-dev-error-pages"
URL = "https://dc.example/portfolio"
JST = ZoneInfo("Asia/Tokyo")
CAPTURED_AT = datetime(2026, 6, 18, 9, 0, 0, tzinfo=JST)
EXPECTED_KEY = "collect/2026/06/18T090000.html"


def _make_bucket() -> Any:
    s3 = boto3.client("s3", region_name="ap-northeast-1")
    s3.create_bucket(
        Bucket=BUCKET,
        CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
    )
    return s3


@mock_aws
def test_save_with_content_writes_html_body_and_metadata() -> None:
    s3 = _make_bucket()
    store = S3ErrorPageStore(BUCKET)

    store.save(ErrorPage(url=URL, captured_at=CAPTURED_AT, content="<html>boom</html>"))

    obj = s3.get_object(Bucket=BUCKET, Key=EXPECTED_KEY)
    assert obj["Body"].read().decode("utf-8") == "<html>boom</html>"
    assert obj["ContentType"] == "text/html"
    assert obj["Metadata"]["url"] == URL
    assert obj["Metadata"]["captured_at"] == "2026-06-18T09:00:00+09:00"


@mock_aws
def test_save_without_content_writes_marker_object() -> None:
    s3 = _make_bucket()
    store = S3ErrorPageStore(BUCKET)

    store.save(ErrorPage(url=URL, captured_at=CAPTURED_AT, content=None))

    obj = s3.get_object(Bucket=BUCKET, Key=EXPECTED_KEY)
    assert obj["Body"].read().decode("utf-8") != ""  # マーカー本文を必ず書く
    assert obj["ContentType"] == "text/plain"
    assert obj["Metadata"]["url"] == URL
    assert obj["Metadata"]["captured_at"] == "2026-06-18T09:00:00+09:00"
