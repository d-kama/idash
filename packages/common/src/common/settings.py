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
class CollectSettings:
    """収集バッチの実行に必要な環境変数。

    フィールドは収集バッチ固有。サマリ通知バッチ / BFF はそれぞれ別の設定
    dataclass を定義する（`common` は SSM / logging / `_require` 等の共通ヘルパを提供する）。
    """

    env_name: str
    source_login_param: str
    error_page_bucket: str
    data_location: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> CollectSettings:
        """環境変数（既定で `os.environ`）から CollectSettings を構築する。"""
        env = os.environ if env is None else env
        return cls(
            env_name=_require(env, "ENV_NAME"),
            source_login_param=_require(env, "SOURCE_LOGIN_PARAM_ARN"),
            error_page_bucket=_require(env, "ERROR_PAGE_BUCKET"),
            data_location=_require(env, "DATA_LOCATION"),
        )


@dataclass(frozen=True)
class NotifySettings:
    """サマリ通知バッチの実行に必要な環境変数。

    データストア read（`data_location` の単一 Parquet）と LINE 通知（`notify-line`）の
    みを要し、収集固有の `source-login` / `error_page_bucket` は持たない。`notify_days`
    は集計対象の日数で、env 欠落時は 7 を既定とする（event の `days` で上書き可）。
    """

    env_name: str
    notify_line_param: str
    notify_days: int
    data_location: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> NotifySettings:
        """環境変数（既定で `os.environ`）から NotifySettings を構築する。"""
        env = os.environ if env is None else env
        notify_days = env.get("NOTIFY_DAYS")
        return cls(
            env_name=_require(env, "ENV_NAME"),
            notify_line_param=_require(env, "NOTIFY_LINE_PARAM_ARN"),
            notify_days=int(notify_days) if notify_days is not None else 7,
            data_location=_require(env, "DATA_LOCATION"),
        )


@dataclass(frozen=True)
class BffSettings:
    """BFF（可視化 API）の実行に必要な環境変数。

    データストア read（`data_location` の単一 Parquet）は実行ロール認証（静的キーなし）で
    SSM 不要。`origin_verify_param` は CloudFront 経由限定化（ADR-0006）用の SSM SecureString
    パラメータ名。**fail-closed**: 未設定はエラーとし、検証を無効化するには
    `ORIGIN_VERIFY_DISABLED=1` を明示する（ローカル `task bff` 等向け。このとき None）。
    """

    env_name: str
    data_location: str
    origin_verify_param: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> BffSettings:
        """環境変数（既定で `os.environ`）から BffSettings を構築する。"""
        env = os.environ if env is None else env
        # fail-closed: 環境変数の欠落（タイポ・infra の配線漏れ）で検証が暗黙にスキップされる
        # ことを許さない。無効化はローカル向けの明示 opt-out のみ。
        origin_verify_param = env.get("ORIGIN_VERIFY_PARAM_ARN")
        if origin_verify_param is None and env.get("ORIGIN_VERIFY_DISABLED") != "1":
            raise KeyError(
                "必須の環境変数が未設定です: ORIGIN_VERIFY_PARAM_ARN"
                "（origin-verify 検証を無効化する場合は ORIGIN_VERIFY_DISABLED=1 を明示する）"
            )
        return cls(
            env_name=_require(env, "ENV_NAME"),
            data_location=_require(env, "DATA_LOCATION"),
            origin_verify_param=origin_verify_param,
        )
