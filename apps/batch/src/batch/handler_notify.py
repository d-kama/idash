"""サマリ通知バッチの Lambda ハンドラ（composition root）。

環境変数と SSM SecureString(2本: sheets-sa / notify-line) から設定を読み、具象アダプタ
（SheetsAssetRepository / LineNotifier / SystemClock）を構築して NotifySummaryUseCase に
DI し、直近 N 日のサマリ通知を実行する。具象は SSM を知らない（ここで注入する）。

notify 経路は収集の重依存（selenium）を持ち込まないため `infrastructure.scraper` を
import しない。同一コンテナイメージを `cmd` 違いで再利用するが、本ハンドラ起動経路では
`sheets` + `notifier` のみを参照する。

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
from infrastructure.notifier import LineConfig, LineNotifier
from infrastructure.sheets import SheetsAssetRepository, SheetsConfig

_logger = get_logger("idash.notify")

# (settings, sheets_cfg, line_cfg) -> use_case
UseCaseFactory = Callable[
    [NotifySettings, dict[str, Any], dict[str, Any]],
    NotifySummaryInputBoundary,
]


def build_use_case(
    settings: NotifySettings,
    sheets_cfg: dict[str, Any],
    line_cfg: dict[str, Any],
) -> NotifySummaryUseCase:
    """SSM 復号 JSON から具象を組み立て、NotifySummaryUseCase を返す。"""
    repository = SheetsAssetRepository(
        SheetsConfig(
            spreadsheet_id=sheets_cfg["spreadsheet_id"],
            sheet_name=sheets_cfg["sheet_name"],
            credentials=sheets_cfg["credentials"],
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
    sheets_cfg = ssm.get_secure_json(settings.sheets_sa_param)
    line_cfg = ssm.get_secure_json(settings.notify_line_param)

    # 集計対象日数は event 優先・既定は env（NOTIFY_DAYS / 既定7）。
    days = (event or {}).get("days") or settings.notify_days

    use_case = use_case_factory(settings, sheets_cfg, line_cfg)
    notification = use_case.execute(days)

    if notification is None:
        result: dict[str, Any] = {"status": "skipped", "days": days}
    else:
        result = {"status": "ok", "days": days, "subject": notification.subject}
    _logger.info("notify finished: %s", result)
    return result
