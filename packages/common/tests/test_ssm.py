"""ssm.get_secure_json は SecureString を復号して JSON を返し、結果をキャッシュする。"""

import json

import boto3
import pytest
from moto import mock_aws

from common import ssm

NAME = "/idash/dev/sheets-sa"
PAYLOAD = {"spreadsheet_id": "abc123", "sheet_name": "assets"}


@mock_aws
def test_get_secure_json_decrypts_and_parses() -> None:
    client = boto3.client("ssm", region_name="ap-northeast-1")
    client.put_parameter(Name=NAME, Value=json.dumps(PAYLOAD), Type="SecureString")

    assert ssm.get_secure_json(NAME) == PAYLOAD


@mock_aws
def test_get_secure_json_caches_first_value() -> None:
    client = boto3.client("ssm", region_name="ap-northeast-1")
    client.put_parameter(Name=NAME, Value=json.dumps(PAYLOAD), Type="SecureString")

    first = ssm.get_secure_json(NAME)
    # SSM 側の値を更新しても、キャッシュ済みのため取得結果は変わらない（コールドスタートのみ取得）。
    client.put_parameter(
        Name=NAME,
        Value=json.dumps({"spreadsheet_id": "changed"}),
        Type="SecureString",
        Overwrite=True,
    )

    assert ssm.get_secure_json(NAME) == first == PAYLOAD


@mock_aws
def test_get_secure_json_missing_parameter_raises() -> None:
    with pytest.raises(Exception):  # noqa: B017  ParameterNotFound（boto3 例外型に依存しない）
        ssm.get_secure_json("/idash/dev/does-not-exist")
