"""GetVisualizationDataUseCase は全期間 read を DTO へ詰め替える。

集計（summarize）・合計（PortfolioAsset.total）は domain に委譲し、ここは orchestration と
詰め替えのみ。0件（summary=None/series=[]）/ 1件（前回比±0）/ 複数件（直近2基準日の前回比・
series 昇順・商品欠測日の素通し）を InMemoryAssetRepository で検証する。
"""

from __future__ import annotations

from datetime import date

from application.visualization import GetVisualizationDataUseCase
from domain.asset import Money, PortfolioAsset, ProductAsset

from .conftest import InMemoryAssetRepository


def _asset(base: date, *products: tuple[str, int, int, int]) -> PortfolioAsset:
    return PortfolioAsset(
        base_date=base,
        products=tuple(
            ProductAsset(
                name=name,
                contribution=Money(contribution),
                profit_loss=Money(profit_loss),
                valuation=Money(valuation),
            )
            for name, contribution, profit_loss, valuation in products
        ),
    )


def test_empty_returns_null_summary_and_empty_series() -> None:
    use_case = GetVisualizationDataUseCase(InMemoryAssetRepository())

    result = use_case.execute()

    assert result.summary is None
    assert result.series == []


def test_single_base_date_has_zero_change_summary() -> None:
    repo = InMemoryAssetRepository()
    repo.save(_asset(date(2026, 7, 1), ("商品A", 100_000, 20_000, 120_000)))
    use_case = GetVisualizationDataUseCase(repo)

    result = use_case.execute()

    assert result.summary is not None
    assert result.summary.base_date == date(2026, 7, 1)
    assert result.summary.total.valuation == 120_000
    assert result.summary.valuation_change == 0  # 前回基準日がない → ±0
    assert result.summary.profit_change == 0
    assert result.summary.profit_rate == 20_000 / 100_000
    assert len(result.series) == 1


def test_summary_uses_latest_two_base_dates_for_change() -> None:
    repo = InMemoryAssetRepository()
    # あえて非昇順に save。前回比は直近2基準日（7/2 → 7/3）で計算されるべき。
    repo.save(_asset(date(2026, 7, 3), ("商品A", 300_000, 60_000, 360_000)))
    repo.save(_asset(date(2026, 7, 1), ("商品A", 100_000, 10_000, 110_000)))
    repo.save(_asset(date(2026, 7, 2), ("商品A", 200_000, 30_000, 230_000)))
    use_case = GetVisualizationDataUseCase(repo)

    result = use_case.execute()

    assert result.summary is not None
    assert result.summary.base_date == date(2026, 7, 3)
    # 7/2(360k-... ) 前回比: 最新 360k − 前回 230k = 130k / 損益 60k − 30k = 30k
    assert result.summary.valuation_change == 130_000
    assert result.summary.profit_change == 30_000
    # series は昇順・全期間（7/1 は summary の対象外でも series には含む）
    assert [p.base_date for p in result.series] == [
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
    ]


def test_series_passes_product_lineup_through_including_gaps() -> None:
    repo = InMemoryAssetRepository()
    # 商品入れ替え: 7/1 は A のみ、7/2 は A+B。BFF はあるがまま返す（欠測補完しない）。
    repo.save(_asset(date(2026, 7, 1), ("商品A", 100_000, 0, 100_000)))
    repo.save(
        _asset(
            date(2026, 7, 2),
            ("商品A", 110_000, 5_000, 115_000),
            ("商品B", 50_000, -2_000, 48_000),
        )
    )
    use_case = GetVisualizationDataUseCase(repo)

    result = use_case.execute()

    assert [p.name for p in result.series[0].products] == ["商品A"]
    assert [p.name for p in result.series[1].products] == ["商品A", "商品B"]
    # 合計は PortfolioAsset.total() 由来（B 込み）
    assert result.series[1].total.valuation == 163_000
    assert result.series[1].total.profit_loss == 3_000
    # 商品スナップショットの金額もそのまま（負の損益含む）
    assert result.series[1].products[1].profit_loss == -2_000
