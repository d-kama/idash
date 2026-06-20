"""apps/batch テスト共通の前処理（AWS ダミー認証 + SSM キャッシュクリア）。"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from common import ssm


@pytest.fixture(autouse=True)
def _aws_env() -> Iterator[None]:
    keys = ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def _clear_ssm_cache() -> Iterator[None]:
    ssm._cache.clear()
    yield
    ssm._cache.clear()
