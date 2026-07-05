"""可視化データ取得ユースケース。

`AssetRepository.find_all()` で全期間を読み、可視化 DTO（schemas）へ詰め替える。集計は
既存 `summarize()` / `PortfolioAsset.total()` を再利用し、ここは orchestration と詰め替えの
みを持つ。Clock 不要（「今日」に依存せず、最新=データ内の最新基準日）。
"""

from __future__ import annotations

from typing import Protocol

from domain.asset import AssetRepository, AssetTotal, PortfolioAsset
from domain.notification import Summary, summarize
from schemas.visualization import (
    AssetAmounts,
    ProductSnapshot,
    SeriesPoint,
    VisualizationResponse,
    VisualizationSummary,
)


class GetVisualizationDataInputBoundary(Protocol):
    """可視化データ取得ユースケースの入力境界。"""

    def execute(self) -> VisualizationResponse: ...


class GetVisualizationDataUseCase(GetVisualizationDataInputBoundary):
    def __init__(self, repository: AssetRepository) -> None:
        self._repository = repository

    def execute(self) -> VisualizationResponse:
        assets = self._repository.find_all()
        if not assets:
            # データ未収集: フロントは空状態を表示。
            return VisualizationResponse(summary=None, series=[])

        # find_all は基準日昇順。直近2基準日（1件しかなければ1件）を summarize に渡すと
        # oldest=前回 / newest=最新 となり、valuation_change/profit_change が前回基準日比になる。
        summary = summarize(assets[-2:])
        return VisualizationResponse(
            summary=_to_summary(summary),
            series=[_to_point(asset) for asset in assets],
        )


def _to_summary(summary: Summary) -> VisualizationSummary:
    return VisualizationSummary(
        base_date=summary.latest_date,
        total=_to_amounts(summary.latest_total),
        profit_rate=summary.profit_rate,
        valuation_change=summary.valuation_change.yen,
        profit_change=summary.profit_change.yen,
    )


def _to_point(asset: PortfolioAsset) -> SeriesPoint:
    return SeriesPoint(
        base_date=asset.base_date,
        products=[
            ProductSnapshot(
                name=product.name,
                contribution=product.contribution.yen,
                profit_loss=product.profit_loss.yen,
                valuation=product.valuation.yen,
            )
            for product in asset.products
        ],
        total=_to_amounts(asset.total()),
    )


def _to_amounts(total: AssetTotal) -> AssetAmounts:
    return AssetAmounts(
        contribution=total.contribution.yen,
        profit_loss=total.profit_loss.yen,
        valuation=total.valuation.yen,
    )
