"""handler_notify（composition root）の DI 結線を検証する。

env → SSM(2本: sheets-sa / notify-line) → config → 具象構築 → NotifySummaryUseCase.execute
の結線を、use_case を fake に差し替えて粗粒度で確認する。併せて、SSM JSON から具象
（SheetsAssetRepository / LineNotifier）を組み立てる実配線（build_use_case）も moto 下で確認する。
"""

import json

import boto3
import pytest
from moto import mock_aws

from application.notification import NotifySummaryUseCase
from batch import handler_notify
from domain.notification import Notification

SHEETS_PARAM = "/idash/dev/sheets-sa"
NOTIFY_PARAM = "/idash/dev/notify-line"

SHEETS_JSON = {
    "credentials": {"type": "service_account", "client_email": "x@y.iam"},
    "spreadsheet_id": "sheet-key-123",
    "sheet_name": "assets",
}
NOTIFY_JSON = {
    "channel_access_token": "token-abc",
    "to": "Uxxxxxxxx",
}

ENV = {
    "ENV_NAME": "dev",
    "SHEETS_SA_PARAM_ARN": SHEETS_PARAM,
    "NOTIFY_LINE_PARAM_ARN": NOTIFY_PARAM,
    "NOTIFY_DAYS": "7",
}

NOTIFICATION = Notification(subject="iDeCo 運用サマリ", body="本文")


def _put_params() -> None:
    client = boto3.client("ssm", region_name="ap-northeast-1")
    client.put_parameter(Name=SHEETS_PARAM, Value=json.dumps(SHEETS_JSON), Type="SecureString")
    client.put_parameter(Name=NOTIFY_PARAM, Value=json.dumps(NOTIFY_JSON), Type="SecureString")


class _FakeUseCase:
    def __init__(self, result: Notification | None) -> None:
        self.result = result
        self.calls: list[int] = []

    def execute(self, days: int) -> Notification | None:
        self.calls.append(days)
        return self.result


@mock_aws
def test_handler_uses_env_days_and_returns_ok(monkeypatch) -> None:
    _put_params()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    fake = _FakeUseCase(NOTIFICATION)
    captured: dict[str, object] = {}

    def factory(settings, sheets_cfg, line_cfg):
        captured["sheets_cfg"] = sheets_cfg
        captured["line_cfg"] = line_cfg
        return fake

    result = handler_notify.handler({}, None, use_case_factory=factory)

    # SSM 復号 JSON が wiring に渡っている。
    assert captured["sheets_cfg"] == SHEETS_JSON
    assert captured["line_cfg"] == NOTIFY_JSON
    # event に days 無し → env 既定7で execute。
    assert fake.calls == [7]
    assert result == {"status": "ok", "days": 7, "subject": "iDeCo 運用サマリ"}


@mock_aws
def test_handler_prefers_event_days(monkeypatch) -> None:
    _put_params()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    fake = _FakeUseCase(NOTIFICATION)

    result = handler_notify.handler({"days": 30}, None, use_case_factory=lambda *_: fake)

    assert fake.calls == [30]  # event 優先。
    assert result["days"] == 30


@mock_aws
def test_handler_passes_explicit_zero_days_through(monkeypatch) -> None:
    # event の days=0 は falsy だが既定値へ握り潰さず、そのまま use case へ渡す
    # （不正値の検証は use case の責務 days>=1 に委ねる）。
    _put_params()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    fake = _FakeUseCase(NOTIFICATION)

    handler_notify.handler({"days": 0}, None, use_case_factory=lambda *_: fake)

    assert fake.calls == [0]  # 既定7に化けていない。


@mock_aws
def test_handler_returns_skipped_when_no_assets(monkeypatch) -> None:
    _put_params()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    fake = _FakeUseCase(None)  # 0件 skip を模す。

    result = handler_notify.handler({}, None, use_case_factory=lambda *_: fake)

    assert result == {"status": "skipped", "days": 7}


@mock_aws
def test_handler_propagates_use_case_error(monkeypatch) -> None:
    _put_params()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    class _Boom:
        def execute(self, days: int) -> Notification | None:
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        handler_notify.handler({}, None, use_case_factory=lambda *_: _Boom())


@mock_aws
def test_build_use_case_wires_concrete_adapters(monkeypatch) -> None:
    _put_params()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    settings = handler_notify.NotifySettings.from_env()

    use_case = handler_notify.build_use_case(settings, SHEETS_JSON, NOTIFY_JSON)

    assert isinstance(use_case, NotifySummaryUseCase)
