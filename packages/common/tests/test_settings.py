"""環境変数の読み取りと、SSM 復号 JSON の検証・変換・repr 保護を検証する。"""

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from common.settings import BffSettings, CollectSettings, NotifyLine, NotifySettings, SourceLogin

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

SOURCE_JSON = {
    "user_id": "user01",
    "password": "source-password",
    "birthdate": "1990-01-01",
    "start_url": "https://dc.example/login",
    "user_agent": "idash-bot",
}

NOTIFY_JSON = {
    "channel_access_token": "line-token",
    "to": "Urecipient",
}


def test_source_login_from_mapping_reads_values_and_parses_birthdate() -> None:
    source = SourceLogin.from_mapping(SOURCE_JSON)

    assert source.user_id == "user01"
    assert source.password == "source-password"
    assert source.birthdate == date(1990, 1, 1)
    assert source.start_url == "https://dc.example/login"
    assert source.user_agent == "idash-bot"
    assert SOURCE_JSON["birthdate"] == "1990-01-01"


@pytest.mark.parametrize("key", SOURCE_JSON)
def test_source_login_missing_key_raises_without_values(key: str) -> None:
    incomplete = {k: v for k, v in SOURCE_JSON.items() if k != key}

    with pytest.raises(KeyError) as error:
        SourceLogin.from_mapping(incomplete)

    assert error.value.args == (key,)


@pytest.mark.parametrize("birthdate", ["not-a-date", "1990-02-30", "1990/01/01"])
def test_source_login_invalid_birthdate_raises_without_value(birthdate: str) -> None:
    with pytest.raises(ValueError, match="birthdate") as error:
        SourceLogin.from_mapping({**SOURCE_JSON, "birthdate": birthdate})

    assert birthdate not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("key", SOURCE_JSON)
@pytest.mark.parametrize("value", [None, 123, True, [], {}])
def test_source_login_rejects_non_string_values(key: str, value: object) -> None:
    values: dict[str, object] = {**SOURCE_JSON, key: value}

    with pytest.raises(TypeError, match=key):
        SourceLogin.from_mapping(values)


def test_source_login_repr_hides_credentials() -> None:
    source = SourceLogin.from_mapping(SOURCE_JSON)

    for rendered in (repr(source), str(source), f"{source}"):
        assert SOURCE_JSON["user_id"] not in rendered
        assert SOURCE_JSON["password"] not in rendered
        assert "1990" not in rendered
        assert SOURCE_JSON["start_url"] in rendered
        assert SOURCE_JSON["user_agent"] in rendered


def test_source_login_ignores_extra_keys() -> None:
    source = SourceLogin.from_mapping(SOURCE_JSON)
    assert SourceLogin.from_mapping({**SOURCE_JSON, "extra": "ignored"}) == source


@pytest.mark.parametrize("key", SOURCE_JSON)
def test_source_login_is_frozen(key: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(SourceLogin.from_mapping(SOURCE_JSON), key, "changed")


def test_notify_line_from_mapping_reads_values() -> None:
    line = NotifyLine.from_mapping(NOTIFY_JSON)

    assert line.channel_access_token == "line-token"
    assert line.to == "Urecipient"


@pytest.mark.parametrize("key", NOTIFY_JSON)
def test_notify_line_missing_key_raises_without_values(key: str) -> None:
    incomplete = {k: v for k, v in NOTIFY_JSON.items() if k != key}

    with pytest.raises(KeyError) as error:
        NotifyLine.from_mapping(incomplete)

    assert error.value.args == (key,)


@pytest.mark.parametrize("key", NOTIFY_JSON)
@pytest.mark.parametrize("value", [None, 123, True, [], {}])
def test_notify_line_rejects_non_string_values(key: str, value: object) -> None:
    values: dict[str, object] = {**NOTIFY_JSON, key: value}

    with pytest.raises(TypeError, match=key):
        NotifyLine.from_mapping(values)


def test_notify_line_repr_hides_token_and_recipient() -> None:
    line = NotifyLine.from_mapping(NOTIFY_JSON)

    for rendered in (repr(line), str(line), f"{line}"):
        assert NOTIFY_JSON["channel_access_token"] not in rendered
        assert NOTIFY_JSON["to"] not in rendered


def test_notify_line_ignores_extra_keys() -> None:
    assert NotifyLine.from_mapping({**NOTIFY_JSON, "extra": "ignored"}) == NotifyLine.from_mapping(
        NOTIFY_JSON
    )


@pytest.mark.parametrize("key", NOTIFY_JSON)
def test_notify_line_is_frozen(key: str) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(NotifyLine.from_mapping(NOTIFY_JSON), key, "changed")


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
}


def test_bff_from_env_reads_all_values() -> None:
    settings = BffSettings.from_env(BFF_ENV)

    assert settings.env_name == "dev"
    assert settings.data_location == "s3://idash-dev-data/assets.parquet"
    assert settings.origin_verify_param is None  # 未設定なら検証無効


def test_bff_from_env_reads_optional_origin_verify() -> None:
    env = {**BFF_ENV, "ORIGIN_VERIFY_PARAM_ARN": "/idash/dev/origin-verify"}
    settings = BffSettings.from_env(env)

    assert settings.origin_verify_param == "/idash/dev/origin-verify"


def test_bff_from_env_missing_required_raises() -> None:
    incomplete = {k: v for k, v in BFF_ENV.items() if k != "DATA_LOCATION"}

    with pytest.raises(KeyError, match="DATA_LOCATION"):
        BffSettings.from_env(incomplete)
