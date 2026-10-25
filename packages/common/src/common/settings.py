"""環境変数と SSM 復号 JSON の型付き設定。

Lambda の環境変数（CDK が付与）や復号済み JSON を読む薄い読み取り層。pydantic 等は
使わず stdlib のみで構成する。機密は環境変数では渡さず、SSM の
パラメータ名（ARN/Name）だけを環境変数で受け取り、実体は `common.ssm` で取得する。
SSM の I/O は handler に残し、`from_mapping` は渡された値の検証・変換だけを行う。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date


def _require(env: Mapping[str, str], key: str) -> str:
    try:
        return env[key]
    except KeyError as error:
        raise KeyError(f"必須の環境変数が未設定です: {key}") from error


def _require_string(values: Mapping[str, object], key: str) -> str:
    value = values[key]
    if not isinstance(value, str):
        raise TypeError(f"SSM 設定は文字列で指定してください: {key}")
    return value


@dataclass(frozen=True)
class SourceLogin:
    """収集用 SSM JSON。認証情報は repr に含めない（属性からは取得可能）。"""

    user_id: str = field(repr=False)
    password: str = field(repr=False)
    birthdate: date = field(repr=False)
    start_url: str
    user_agent: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> SourceLogin:
        """必須キーと文字列型を検証し、生年月日を date に変換する。余分なキーは無視する。"""
        birthdate = _require_string(values, "birthdate")
        try:
            parsed_birthdate = date.fromisoformat(birthdate)
        except ValueError:
            raise ValueError("birthdate は ISO 形式の日付で指定してください") from None
        return cls(
            user_id=_require_string(values, "user_id"),
            password=_require_string(values, "password"),
            birthdate=parsed_birthdate,
            start_url=_require_string(values, "start_url"),
            user_agent=_require_string(values, "user_agent"),
        )


@dataclass(frozen=True)
class NotifyLine:
    """通知用 SSM JSON。トークンと送信先は repr に含めない（属性からは取得可能）。"""

    channel_access_token: str = field(repr=False)
    to: str = field(repr=False)

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> NotifyLine:
        """必須キーと文字列型を検証する。余分なキーは無視する。"""
        return cls(
            channel_access_token=_require_string(values, "channel_access_token"),
            to=_require_string(values, "to"),
        )


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
    パラメータ名で、**未設定なら検証を行わない**（ローカル `task bff` / 未配線環境向け・任意）。
    """

    env_name: str
    data_location: str
    origin_verify_param: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> BffSettings:
        """環境変数（既定で `os.environ`）から BffSettings を構築する。"""
        env = os.environ if env is None else env
        return cls(
            env_name=_require(env, "ENV_NAME"),
            data_location=_require(env, "DATA_LOCATION"),
            # 任意: 未設定（ローカル等）なら origin-verify 検証は無効。
            origin_verify_param=env.get("ORIGIN_VERIFY_PARAM_ARN"),
        )
