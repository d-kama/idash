"""通知サブドメインの集計（summarize）と整形（render_summary）を検証する。"""

from datetime import date

from domain.asset import AssetTotal, Money, PortfolioAsset, ProductAsset
from domain.notification import Notification, Summary, render_summary, summarize


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


def test_summarize_multiple_dates_computes_latest_and_changes() -> None:
    oldest = _portfolio(date(2026, 6, 1), 90_000, 5_000, 100_000)
    latest = _portfolio(date(2026, 6, 18), 100_000, 20_000, 120_000)

    summary = summarize((oldest, latest))

    assert summary == Summary(
        period_from=date(2026, 6, 1),
        latest_date=date(2026, 6, 18),
        latest_total=AssetTotal(
            contribution=Money(100_000),
            profit_loss=Money(20_000),
            valuation=Money(120_000),
        ),
        profit_rate=20_000 / 100_000,
        valuation_change=Money(20_000),
        profit_change=Money(15_000),
    )


def test_summarize_single_date_has_zero_changes() -> None:
    only = _portfolio(date(2026, 6, 18), 100_000, 20_000, 120_000)

    summary = summarize((only,))

    assert summary.period_from == date(2026, 6, 18)
    assert summary.latest_date == date(2026, 6, 18)
    assert summary.latest_total == AssetTotal(
        contribution=Money(100_000),
        profit_loss=Money(20_000),
        valuation=Money(120_000),
    )
    assert summary.valuation_change == Money(0)
    assert summary.profit_change == Money(0)


def test_summarize_is_independent_of_input_order() -> None:
    oldest = _portfolio(date(2026, 6, 1), 90_000, 5_000, 100_000)
    latest = _portfolio(date(2026, 6, 18), 100_000, 20_000, 120_000)

    # 未ソート（最新を先頭）でも min/max を base_date で選ぶ。
    summary = summarize((latest, oldest))

    assert summary.period_from == date(2026, 6, 1)
    assert summary.latest_date == date(2026, 6, 18)
    assert summary.valuation_change == Money(20_000)
    assert summary.profit_change == Money(15_000)


def test_summarize_guards_zero_contribution_profit_rate() -> None:
    only = _portfolio(date(2026, 6, 18), 0, 10_000, 10_000)

    summary = summarize((only,))

    assert summary.profit_rate == 0.0


def test_render_summary_snapshot() -> None:
    oldest = _portfolio(date(2026, 6, 1), 90_000, 5_000, 100_000)
    latest = _portfolio(date(2026, 6, 18), 100_000, 20_000, 120_000)

    notification = render_summary(summarize((oldest, latest)))

    assert notification == Notification(
        subject="iDeCo 運用サマリ（2026-06-01〜2026-06-18）",
        body=(
            "■ 最新（2026-06-18 時点）\n"
            "  資産評価額: ¥120,000\n"
            "  評価損益: +¥20,000（+20.00%）\n"
            "  拠出累計: ¥100,000\n"
            "■ この期間の変化（2026-06-01 → 2026-06-18）\n"
            "  評価額: +¥20,000\n"
            "  評価損益: +¥15,000"
        ),
    )
