"""SSM Parameter Store の SecureString 取得。

`GetParameter` を `WithDecryption=True` で呼び、値（JSON）を辞書に解釈する。Lambda の
コールドスタート時のみ取得すれば十分なため、結果をモジュールスコープでキャッシュする。
パラメータは SSM SecureString（AWS 管理鍵 `aws/ssm`）であり、CDK では作成しない（AWS 側で
手動作成し名前でインポート）。
"""

from __future__ import annotations

import json
from typing import Any

import boto3

# モジュールスコープのキャッシュ。同一実行環境（ウォームスタート）では SSM を再取得しない。
_cache: dict[str, dict[str, Any]] = {}


def get_secure_json(name: str) -> dict[str, Any]:
    """SecureString パラメータ `name` を復号し JSON を辞書として返す（キャッシュ付き）。"""
    cached = _cache.get(name)
    if cached is not None:
        return cached
    client = boto3.client("ssm")
    response = client.get_parameter(Name=name, WithDecryption=True)
    value: dict[str, Any] = json.loads(response["Parameter"]["Value"])
    _cache[name] = value
    return value
