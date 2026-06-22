"""サマリ通知ユースケース。

具象（AssetRepository / Notifier / Clock）を DI で受け取り、直近 N 日の窓を計算して
資産を読み取り、集計・整形し、通知を送る。集計（summarize）・整形（render_summary）は
domain に委譲し、ここは orchestration（窓計算・fetch・skip 判定・send）のみを持つ。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol

from domain.asset import AssetRepository
from domain.clock import Clock
from domain.notification import Notification, Notifier, render_summary, summarize


class NotifySummaryInputBoundary(Protocol):
    """サマリ通知ユースケースの入力境界。"""

    def execute(self, days: int) -> Notification | None:
        """直近 days 日のサマリを通知する（days は 1 以上）。"""
        ...


class NotifySummaryUseCase(NotifySummaryInputBoundary):
    def __init__(
        self,
        repository: AssetRepository,
        notifier: Notifier,
        clock: Clock,
    ) -> None:
        self._repository = repository
        self._notifier = notifier
        self._clock = clock

    def execute(self, days: int) -> Notification | None:
        if days < 1:
            # days<1 だと from_date が未来になり窓が空集合化 → 0件 skip と区別できず
            # 設定不備（env/event の不正値）をサイレントに握り潰すため早期に弾く。
            raise ValueError(f"days must be >= 1, got {days}")
        today = self._clock.now().date()
        from_date = today - timedelta(days=days - 1)  # 直近 N 日 = today を含む閉区間
        assets = self._repository.find_by_date_range(from_date, today)
        if not assets:
            return None  # 窓内 0件 = 送信せず skip
        summary = summarize(assets)
        notification = render_summary(summary)
        self._notifier.send(notification)
        return notification
