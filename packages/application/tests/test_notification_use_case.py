"""NotifySummaryUseCase の振る舞いを Fake で検証する。

application の関心事のみを観測する: 直近 N 日の窓を計算して資産を読み、集計・整形した
Notification を notifier へ1回送り同一物を返すこと、窓内0件なら送らず None を返すこと、
窓境界の基準日が正しく含包/除外されること。集計・整形そのものは domain のテストで見る。
"""

from datetime import date

from application.notification import NotifySummaryUseCase
from domain.asset import Money, PortfolioAsset, ProductAsset
from domain.notification import render_summary, summarize

from .conftest import (
    FixedClock,
    InMemoryAssetRepository,
    RecordingNotifier,
)

# FIXED_NOW = 2026-06-18 09:00 → today = 2026-06-18
DAYS = 7  # 窓 = [2026-06-12, 2026-06-18]


def _portfolio(
    base_date: date, contribution: int, profit_loss: int, valuation: int
) -> PortfolioAsset:
    return PortfolioAsset(
        base_date=base_date,
        products=(
            ProductAsset(
                name="ファンドA",
                contribution=Money(contribution),
                profit_loss=Money(profit_loss),
                valuation=Money(valuation),
            ),
        ),
    )


def test_sends_rendered_summary_and_returns_it(
    repository: InMemoryAssetRepository,
    notifier: RecordingNotifier,
    clock: FixedClock,
) -> None:
    oldest = _portfolio(date(2026, 6, 12), 90_000, 5_000, 100_000)
    latest = _portfolio(date(2026, 6, 18), 100_000, 20_000, 120_000)
    repository.save(oldest)
    repository.save(latest)
    use_case = NotifySummaryUseCase(repository, notifier, clock)

    result = use_case.execute(DAYS)

    expected = render_summary(summarize((oldest, latest)))
    assert result == expected
    assert notifier.sent == [expected]


def test_no_assets_in_window_skips_send_and_returns_none(
    repository: InMemoryAssetRepository,
    notifier: RecordingNotifier,
    clock: FixedClock,
) -> None:
    use_case = NotifySummaryUseCase(repository, notifier, clock)

    result = use_case.execute(DAYS)

    assert result is None
    assert notifier.sent == []


def test_window_excludes_out_of_range_dates(
    repository: InMemoryAssetRepository,
    notifier: RecordingNotifier,
    clock: FixedClock,
) -> None:
    before_window = _portfolio(date(2026, 6, 11), 80_000, 1_000, 90_000)  # < from_date
    from_edge = _portfolio(date(2026, 6, 12), 90_000, 5_000, 100_000)  # = from_date
    to_edge = _portfolio(date(2026, 6, 18), 100_000, 20_000, 120_000)  # = today
    after_window = _portfolio(date(2026, 6, 19), 110_000, 30_000, 140_000)  # > today
    for asset in (before_window, from_edge, to_edge, after_window):
        repository.save(asset)
    use_case = NotifySummaryUseCase(repository, notifier, clock)

    result = use_case.execute(DAYS)

    # 集計対象は窓内の from_edge/to_edge のみ（境界含包、範囲外は除外）。
    expected = render_summary(summarize((from_edge, to_edge)))
    assert result == expected
    assert notifier.sent == [expected]


def test_single_asset_in_window_sends_with_zero_changes(
    repository: InMemoryAssetRepository,
    notifier: RecordingNotifier,
    clock: FixedClock,
) -> None:
    only = _portfolio(date(2026, 6, 18), 100_000, 20_000, 120_000)
    repository.save(only)
    use_case = NotifySummaryUseCase(repository, notifier, clock)

    result = use_case.execute(DAYS)

    assert result is not None
    assert len(notifier.sent) == 1
    assert "評価額: ¥0" in result.body
    assert "評価損益: ¥0" in result.body
