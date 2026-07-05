"""可視化 DTO のシリアライズ契約を検証する。

DTO は BFF レスポンス / OpenAPI の single source of truth。date の ISO 化・None summary・
継承（ProductSnapshot は AssetAmounts + name）の JSON 表現を固定する。
"""

from datetime import date

from schemas.visualization import (
    AssetAmounts,
    ProductSnapshot,
    SeriesPoint,
    VisualizationResponse,
    VisualizationSummary,
)


def _amounts() -> AssetAmounts:
    return AssetAmounts(contribution=2_300_000, profit_loss=180_000, valuation=2_480_000)


def test_series_point_serializes_date_as_iso_and_nests_products() -> None:
    point = SeriesPoint(
        base_date=date(2026, 7, 3),
        products=[
            ProductSnapshot(
                name="商品A",
                contribution=2_300_000,
                profit_loss=180_000,
                valuation=2_480_000,
            )
        ],
        total=_amounts(),
    )

    assert point.model_dump(mode="json") == {
        "base_date": "2026-07-03",
        "products": [
            {
                "name": "商品A",
                "contribution": 2_300_000,
                "profit_loss": 180_000,
                "valuation": 2_480_000,
            }
        ],
        "total": {"contribution": 2_300_000, "profit_loss": 180_000, "valuation": 2_480_000},
    }


def test_summary_serializes_rate_and_changes() -> None:
    summary = VisualizationSummary(
        base_date=date(2026, 7, 3),
        total=_amounts(),
        profit_rate=0.0783,
        valuation_change=12_000,
        profit_change=9_000,
    )

    dumped = summary.model_dump(mode="json")
    assert dumped["base_date"] == "2026-07-03"
    assert dumped["profit_rate"] == 0.0783
    assert dumped["valuation_change"] == 12_000
    assert dumped["profit_change"] == 9_000


def test_response_allows_null_summary_and_empty_series() -> None:
    response = VisualizationResponse(summary=None, series=[])

    assert response.model_dump(mode="json") == {"summary": None, "series": []}
