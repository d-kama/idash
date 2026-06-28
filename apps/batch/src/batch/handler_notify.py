"""サマリ通知バッチの Lambda ハンドラ（composition root）。

環境変数（`DATA_LOCATION`）と SSM SecureString(notify-line) から設定を読み、具象アダプタ
（DuckDbAssetRepository / LineNotifier / SystemClock）を構築して NotifySummaryUseCase に
DI し、直近 N 日のサマリ通知を実行する。データストアは DuckDB + S3 単一 Parquet（実行
ロール認証）。具象は SSM を知らない（ここで注入する）。

notify 経路は収集の重依存（selenium）を持ち込まないため `infrastructure.scraper` を
import しない。同一コンテナイメージを `cmd` 違いで再利用するが、本ハンドラ起動経路では
`duckdb_store` + `notifier` のみを参照する。

例外は捕捉せず再送出して Lambda を失敗扱いにする（通知失敗はリトライ/検知に委ねる）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from application.notification import NotifySummaryInputBoundary, NotifySummaryUseCase
from common import ssm
from common.logging import get_logger
from common.settings import NotifySettings
from infrastructure.clock import SystemClock
from infrastructure.duckdb_store import DuckDbAssetRepository, DuckDbConfig
from infrastructure.notifier import LineConfig, LineNotifier

_logger = get_logger("idash.notify")

# DuckDB の拡張同梱先（Dockerfile の事前 INSTALL 先）と肥大時スピル先。
_DUCKDB_EXTENSION_DIR = "/opt/duckdb-extensions"
_DUCKDB_TEMP_DIR = "/tmp"  # noqa: S108 -- Lambda の書き込み可能領域（スピル用）
_DUCKDB_MEMORY_LIMIT = "256MB"  # notify は軽量（read のみ）。スピル併用で OOM を避ける保険値

# (settings, line_cfg) -> use_case
UseCaseFactory = Callable[
    [NotifySettings, dict[str, Any]],
    NotifySummaryInputBoundary,
]


def build_use_case(
    settings: NotifySettings,
    line_cfg: dict[str, Any],
) -> NotifySummaryUseCase:
    """SSM 復号 JSON / env から具象を組み立て、NotifySummaryUseCase を返す。"""
    repository = DuckDbAssetRepository(
        DuckDbConfig(
            location=settings.data_location,
            memory_limit=_DUCKDB_MEMORY_LIMIT,
            temp_directory=_DUCKDB_TEMP_DIR,
            extension_directory=_DUCKDB_EXTENSION_DIR,
        )
    )
    notifier = LineNotifier(
        LineConfig(
            channel_access_token=line_cfg["channel_access_token"],
            to=line_cfg["to"],
        )
    )
    return NotifySummaryUseCase(repository, notifier, SystemClock())


def handler(
    event: dict[str, Any] | None,
    context: Any,
    *,
    use_case_factory: UseCaseFactory = build_use_case,
) -> dict[str, Any]:
    """EventBridge から起動されるサマリ通知エントリポイント。"""
    settings = NotifySettings.from_env()
    line_cfg = ssm.get_secure_json(settings.notify_line_param)

    # 集計対象日数は event 優先・既定は env（NOTIFY_DAYS / 既定7）。`or` ではなく None 判定で、
    # 明示された days=0 / 負値を既定値へ握り潰さず use case の検証（days>=1）へ素通しする。
    raw_days = (event or {}).get("days")
    days = settings.notify_days if raw_days is None else raw_days

    use_case = use_case_factory(settings, line_cfg)
    notification = use_case.execute(days)

    if notification is None:
        result: dict[str, Any] = {"status": "skipped", "days": days}
    else:
        result = {"status": "ok", "days": days, "subject": notification.subject}
    _logger.info("notify finished: %s", result)
    return result
