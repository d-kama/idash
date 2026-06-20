"""データ収集バッチの Lambda ハンドラ（composition root）。

環境変数と SSM SecureString(2本) から設定を読み、具象アダプタ
（SeleniumScraper / SheetsAssetRepository / S3ErrorPageStore / SystemClock）を構築して
CollectionUseCase に DI し、収集を実行する。具象は SSM を知らない（ここで注入する）。

例外は捕捉せず再送出して Lambda を失敗扱いにする（収集失敗はリトライ/通知に委ねる）。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date
from typing import Any

from application.collection import CollectionInputBoundary, CollectionUseCase
from common import ssm
from common.logging import get_logger
from common.settings import CollectSettings
from domain.collection import Credentials
from infrastructure.clock import SystemClock
from infrastructure.error_store import S3ErrorPageStore
from infrastructure.scraper import ScraperConfig, SeleniumScraper
from infrastructure.sheets import SheetsAssetRepository, SheetsConfig

_logger = get_logger("idash.collect")

# Lambda コンテナ内の版ピン chromium/chromedriver の配置（Dockerfile が設定; フェーズ4.1）。
_DEFAULT_CHROME_BINARY = "/opt/chrome/chrome"
_DEFAULT_CHROME_DRIVER = "/opt/chromedriver/chromedriver"

# (settings, source, sheets_cfg) -> (use_case, url, credentials)
UseCaseFactory = Callable[
    [CollectSettings, dict[str, Any], dict[str, Any]],
    "tuple[CollectionInputBoundary, str, Credentials]",
]


def build_use_case(
    settings: CollectSettings,
    source: dict[str, Any],
    sheets_cfg: dict[str, Any],
) -> tuple[CollectionUseCase, str, Credentials]:
    """SSM 復号 JSON から具象を組み立て、CollectionUseCase と実行引数を返す。"""
    scraper = SeleniumScraper(
        ScraperConfig(
            user_agent=source["user_agent"],
            chrome_binary_location=os.environ.get("CHROME_BINARY_LOCATION", _DEFAULT_CHROME_BINARY),
            chrome_driver_path=os.environ.get("CHROME_DRIVER_PATH", _DEFAULT_CHROME_DRIVER),
        )
    )
    repository = SheetsAssetRepository(
        SheetsConfig(
            spreadsheet_id=sheets_cfg["spreadsheet_id"],
            sheet_name=sheets_cfg["sheet_name"],
            credentials=sheets_cfg["credentials"],
        )
    )
    error_store = S3ErrorPageStore(settings.error_page_bucket)
    use_case = CollectionUseCase(scraper, repository, error_store, SystemClock())

    credentials = Credentials(
        user_id=source["user_id"],
        password=source["password"],
        birthdate=date.fromisoformat(source["birthdate"]),
    )
    return use_case, source["start_url"], credentials


def handler(
    event: dict[str, Any],
    context: Any,
    *,
    use_case_factory: UseCaseFactory = build_use_case,
) -> dict[str, Any]:
    """EventBridge から起動される収集エントリポイント。"""
    settings = CollectSettings.from_env()
    source = ssm.get_secure_json(settings.source_login_param)
    sheets_cfg = ssm.get_secure_json(settings.sheets_sa_param)

    use_case, url, credentials = use_case_factory(settings, source, sheets_cfg)
    asset = use_case.execute(url, credentials)

    result = {
        "status": "ok",
        "base_date": asset.base_date.isoformat(),
        "products": len(asset.products),
    }
    _logger.info("collection finished: %s", result)
    return result
