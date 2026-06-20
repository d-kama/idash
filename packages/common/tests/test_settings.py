"""CollectSettings は os.environ（または注入された mapping）から設定値を読む。"""

import pytest

from common.settings import CollectSettings

ENV = {
    "ENV_NAME": "dev",
    "SHEETS_SA_PARAM_ARN": "/idash/dev/sheets-sa",
    "SOURCE_LOGIN_PARAM_ARN": "/idash/dev/source-login",
    "ERROR_PAGE_BUCKET": "idash-dev-error-pages",
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
