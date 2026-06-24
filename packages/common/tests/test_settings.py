"""CollectSettings / NotifySettings は os.environ（または注入された mapping）から設定値を読む。"""

import pytest

from common.settings import CollectSettings, NotifySettings

ENV = {
    "ENV_NAME": "dev",
    "SHEETS_SA_PARAM_ARN": "/idash/dev/sheets-sa",
    "SOURCE_LOGIN_PARAM_ARN": "/idash/dev/source-login",
    "ERROR_PAGE_BUCKET": "idash-dev-error-pages",
}

NOTIFY_ENV = {
    "ENV_NAME": "dev",
    "SHEETS_SA_PARAM_ARN": "/idash/dev/sheets-sa",
    "NOTIFY_LINE_PARAM_ARN": "/idash/dev/notify-line",
    "NOTIFY_DAYS": "14",
}


def test_from_env_reads_all_values() -> None:
    settings = CollectSettings.from_env(ENV)

    assert settings.env_name == "dev"
    assert settings.sheets_sa_param == "/idash/dev/sheets-sa"
    assert settings.source_login_param == "/idash/dev/source-login"
    assert settings.error_page_bucket == "idash-dev-error-pages"


def test_from_env_missing_required_raises() -> None:
    incomplete = {k: v for k, v in ENV.items() if k != "SOURCE_LOGIN_PARAM_ARN"}

    with pytest.raises(KeyError, match="SOURCE_LOGIN_PARAM_ARN"):
        CollectSettings.from_env(incomplete)


def test_notify_from_env_reads_all_values_and_parses_days() -> None:
    settings = NotifySettings.from_env(NOTIFY_ENV)

    assert settings.env_name == "dev"
    assert settings.sheets_sa_param == "/idash/dev/sheets-sa"
    assert settings.notify_line_param == "/idash/dev/notify-line"
    assert settings.notify_days == 14  # int 解釈


def test_notify_from_env_defaults_days_to_7_when_absent() -> None:
    without_days = {k: v for k, v in NOTIFY_ENV.items() if k != "NOTIFY_DAYS"}

    settings = NotifySettings.from_env(without_days)

    assert settings.notify_days == 7


def test_notify_from_env_missing_required_raises() -> None:
    incomplete = {k: v for k, v in NOTIFY_ENV.items() if k != "NOTIFY_LINE_PARAM_ARN"}

    with pytest.raises(KeyError, match="NOTIFY_LINE_PARAM_ARN"):
        NotifySettings.from_env(incomplete)
