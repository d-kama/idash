"""環境変数ベースの設定。

Lambda の環境変数（CDK が付与）から設定値を読む薄い読み取り層。pydantic 等は
使わず stdlib の `os.environ` のみで構成する。機密は環境変数では渡さず、SSM の
パラメータ名（ARN/Name）だけを環境変数で受け取り、実体は `common.ssm` で取得する。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


def _require(env: Mapping[str, str], key: str) -> str:
    try:
        return env[key]
    except KeyError as error:
        raise KeyError(f"必須の環境変数が未設定です: {key}") from error


@dataclass(frozen=True)
class Settings:
    """収集バッチの実行に必要な環境変数。"""

    env_name: str
    sheets_sa_param: str
    source_login_param: str
    error_page_bucket: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """環境変数（既定で `os.environ`）から Settings を構築する。"""
        env = os.environ if env is None else env
        return cls(
            env_name=_require(env, "ENV_NAME"),
            sheets_sa_param=_require(env, "SHEETS_SA_PARAM_ARN"),
            source_login_param=_require(env, "SOURCE_LOGIN_PARAM_ARN"),
            error_page_bucket=_require(env, "ERROR_PAGE_BUCKET"),
        )
