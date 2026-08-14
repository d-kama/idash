"""CollectSettings / NotifySettings は os.environ（または注入された mapping）から設定値を読む。"""

import pytest

from common.settings import BffSettings, CollectSettings, NotifySettings

ENV = {
    "ENV_NAME": "dev",
    "SOURCE_LOGIN_PARAM_ARN": "/idash/dev/source-login",
    "ERROR_PAGE_BUCKET": "idash-dev-error-pages",
    "DATA_LOCATION": "s3://idash-dev-data/assets.parquet",
}

NOTIFY_ENV = {
    "ENV_NAME": "dev",
    "NOTIFY_LINE_PARAM_ARN": "/idash/dev/notify-line",
    "NOTIFY_DAYS": "14",
    "DATA_LOCATION": "s3://idash-dev-data/assets.parquet",
}


def test_from_env_reads_all_values() -> None:
    settings = CollectSettings.from_env(ENV)

    assert settings.env_name == "dev"
    assert settings.source_login_param == "/idash/dev/source-login"
    assert settings.error_page_bucket == "idash-dev-error-pages"
    assert settings.data_location == "s3://idash-dev-data/assets.parquet"


def test_from_env_missing_required_raises() -> None:
    incomplete = {k: v for k, v in ENV.items() if k != "SOURCE_LOGIN_PARAM_ARN"}

    with pytest.raises(KeyError, match="SOURCE_LOGIN_PARAM_ARN"):
        CollectSettings.from_env(incomplete)


def test_notify_from_env_reads_all_values_and_parses_days() -> None:
    settings = NotifySettings.from_env(NOTIFY_ENV)

    assert settings.env_name == "dev"
    assert settings.notify_line_param == "/idash/dev/notify-line"
    assert settings.notify_days == 14  # int 解釈
    assert settings.data_location == "s3://idash-dev-data/assets.parquet"


def test_notify_from_env_defaults_days_to_7_when_absent() -> None:
    without_days = {k: v for k, v in NOTIFY_ENV.items() if k != "NOTIFY_DAYS"}

    settings = NotifySettings.from_env(without_days)

    assert settings.notify_days == 7


def test_notify_from_env_missing_required_raises() -> None:
    incomplete = {k: v for k, v in NOTIFY_ENV.items() if k != "NOTIFY_LINE_PARAM_ARN"}

    with pytest.raises(KeyError, match="NOTIFY_LINE_PARAM_ARN"):
        NotifySettings.from_env(incomplete)


BFF_ENV = {
    "ENV_NAME": "dev",
    "DATA_LOCATION": "s3://idash-dev-data/assets.parquet",
    "ORIGIN_VERIFY_PARAM_ARN": "/idash/dev/origin-verify",
}


def test_bff_from_env_reads_all_values() -> None:
    settings = BffSettings.from_env(BFF_ENV)

    assert settings.env_name == "dev"
    assert settings.data_location == "s3://idash-dev-data/assets.parquet"
    assert settings.origin_verify_param == "/idash/dev/origin-verify"


def test_bff_from_env_missing_origin_verify_raises() -> None:
    # fail-closed: 環境変数の欠落（infra の配線漏れ等）で検証が暗黙に無効化されてはならない。
    incomplete = {k: v for k, v in BFF_ENV.items() if k != "ORIGIN_VERIFY_PARAM_ARN"}

    with pytest.raises(KeyError, match="ORIGIN_VERIFY_PARAM_ARN"):
        BffSettings.from_env(incomplete)


def test_bff_from_env_explicit_disable_allows_none() -> None:
    # ローカル（task bff 等）は ORIGIN_VERIFY_DISABLED=1 の明示 opt-out でのみ検証を無効化できる。
    env = {k: v for k, v in BFF_ENV.items() if k != "ORIGIN_VERIFY_PARAM_ARN"}
    env["ORIGIN_VERIFY_DISABLED"] = "1"

    settings = BffSettings.from_env(env)

    assert settings.origin_verify_param is None


def test_bff_from_env_missing_required_raises() -> None:
    incomplete = {k: v for k, v in BFF_ENV.items() if k != "DATA_LOCATION"}

    with pytest.raises(KeyError, match="DATA_LOCATION"):
        BffSettings.from_env(incomplete)
