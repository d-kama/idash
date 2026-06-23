"""handler_collect（composition root）の DI 結線を検証する。

env → SSM(2本) → config → 具象構築 → CollectionUseCase.execute の結線を、use_case を
fake に差し替えて粗粒度で確認する。併せて、SSM JSON から Credentials / start_url を
組み立てる実配線（build_use_case）も moto 下で確認する。
"""

import json
from datetime import date

import boto3
from moto import mock_aws

from application.collection import CollectionUseCase
from batch import handler_collect
from domain.asset import Money, PortfolioAsset, ProductAsset
from domain.collection import Credentials

SOURCE_PARAM = "/idash/dev/source-login"
SHEETS_PARAM = "/idash/dev/sheets-sa"

SOURCE_JSON = {
    "user_id": "user01",
    "password": "secret",
    "birthdate": "1990-01-01",
    "start_url": "https://dc.example/login",
    "user_agent": "idash-bot",
}
SHEETS_JSON = {
    "credentials": {"type": "service_account", "client_email": "x@y.iam"},
    "spreadsheet_id": "sheet-key-123",
    "sheet_name": "assets",
}

ENV = {
    "ENV_NAME": "dev",
    "SOURCE_LOGIN_PARAM_ARN": SOURCE_PARAM,
    "SHEETS_SA_PARAM_ARN": SHEETS_PARAM,
    "ERROR_PAGE_BUCKET": "idash-dev-error-pages",
}

ASSET = PortfolioAsset(
    base_date=date(2026, 6, 18),
    products=(
        ProductAsset(
            name="ファンドA",
            contribution=Money(100_000),
            profit_loss=Money(20_000),
            valuation=Money(120_000),
        ),
    ),
)


def _put_params() -> None:
    client = boto3.client("ssm", region_name="ap-northeast-1")
    client.put_parameter(Name=SOURCE_PARAM, Value=json.dumps(SOURCE_JSON), Type="SecureString")
    client.put_parameter(Name=SHEETS_PARAM, Value=json.dumps(SHEETS_JSON), Type="SecureString")


class _FakeUseCase:
    def __init__(self, asset: PortfolioAsset) -> None:
        self.asset = asset
        self.calls: list[tuple[str, Credentials]] = []

    def execute(self, url: str, credentials: Credentials) -> PortfolioAsset:
        self.calls.append((url, credentials))
        return self.asset


@mock_aws
def test_handler_reads_config_and_runs_use_case(monkeypatch) -> None:
    _put_params()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    fake = _FakeUseCase(ASSET)
    captured: dict[str, object] = {}

    def factory(settings, source, sheets_cfg):
        captured["source"] = source
        captured["sheets_cfg"] = sheets_cfg
        return (
            fake,
            source["start_url"],
            Credentials(
                user_id=source["user_id"], password=source["password"], birthdate=date(1990, 1, 1)
            ),
        )

    result = handler_collect.handler({}, None, use_case_factory=factory)

    # SSM 復号 JSON が wiring に渡っている
    assert captured["source"] == SOURCE_JSON
    assert captured["sheets_cfg"] == SHEETS_JSON
    # execute が start_url で 1 回呼ばれている
    assert len(fake.calls) == 1
    assert fake.calls[0][0] == "https://dc.example/login"
    # 成功時の最小サマリを返す
    assert result == {"status": "ok", "base_date": "2026-06-18", "products": 1}


@mock_aws
def test_build_use_case_wires_credentials_and_url(monkeypatch) -> None:
    _put_params()
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    settings = handler_collect.CollectSettings.from_env()
    source = SOURCE_JSON
    sheets_cfg = SHEETS_JSON

    use_case, url, credentials = handler_collect.build_use_case(settings, source, sheets_cfg)

    assert isinstance(use_case, CollectionUseCase)
    assert url == "https://dc.example/login"
    assert credentials.user_id == "user01"
    assert credentials.password == "secret"
    assert credentials.birthdate == date(1990, 1, 1)
