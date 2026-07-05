"""BFF アプリの HTTP 契約を検証する。

`app.dependency_overrides` でユースケースをフェイクに差し替え、実データストア（DuckDB/S3）
なしで `GET /api/visualization` の 200 応答・JSON 形・空データ応答を確認する。集計ロジック
そのものは application/domain のテストで見る。ここではエンドポイントの配線と直列化のみ。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from bff.main import app, get_use_case
from schemas.visualization import (
    AssetAmounts,
    ProductSnapshot,
    SeriesPoint,
    VisualizationResponse,
    VisualizationSummary,
)


class _StubUseCase:
    def __init__(self, response: VisualizationResponse) -> None:
        self._response = response

    def execute(self) -> VisualizationResponse:
        return self._response


def _client(response: VisualizationResponse) -> Iterator[TestClient]:
    app.dependency_overrides[get_use_case] = lambda: _StubUseCase(response)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def populated_client() -> Iterator[TestClient]:
    response = VisualizationResponse(
        summary=VisualizationSummary(
            base_date=date(2026, 7, 3),
            total=AssetAmounts(contribution=2_300_000, profit_loss=180_000, valuation=2_480_000),
            profit_rate=0.0783,
            valuation_change=12_000,
            profit_change=9_000,
        ),
        series=[
            SeriesPoint(
                base_date=date(2026, 7, 3),
                products=[
                    ProductSnapshot(
                        name="商品A",
                        contribution=2_300_000,
                        profit_loss=180_000,
                        valuation=2_480_000,
                    )
                ],
                total=AssetAmounts(
                    contribution=2_300_000, profit_loss=180_000, valuation=2_480_000
                ),
            )
        ],
    )
    yield from _client(response)


@pytest.fixture
def empty_client() -> Iterator[TestClient]:
    yield from _client(VisualizationResponse(summary=None, series=[]))


def test_get_visualization_returns_200_and_expected_json(populated_client: TestClient) -> None:
    res = populated_client.get("/api/visualization")

    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["base_date"] == "2026-07-03"
    assert body["summary"]["profit_rate"] == 0.0783
    assert body["summary"]["valuation_change"] == 12_000
    assert body["series"][0]["products"][0]["name"] == "商品A"
    assert body["series"][0]["total"]["valuation"] == 2_480_000


def test_get_visualization_empty_returns_null_summary_and_empty_series(
    empty_client: TestClient,
) -> None:
    res = empty_client.get("/api/visualization")

    assert res.status_code == 200
    assert res.json() == {"summary": None, "series": []}
