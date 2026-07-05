"""可視化 API（BFF）の DTO（Pydantic）。

OpenAPI の single source of truth。`domain` を import せず純粋なスキーマとして保つ
（domain → DTO の詰め替えは application 層が担う）。金額はすべて円整数（`Money.yen`）で、
恒等式 `valuation = contribution + profit_loss` が成立する。比率は生の float（表示整形は
フロント側）。基準日は `date`（OpenAPI では ISO8601 文字列にシリアライズされる）。
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class AssetAmounts(BaseModel):
    """3金額の組（合計 / 商品スナップショット共通の基底）。すべて円整数。"""

    contribution: int
    profit_loss: int
    valuation: int


class ProductSnapshot(AssetAmounts):
    """ある基準日・ある商品の3金額。"""

    name: str


class SeriesPoint(BaseModel):
    """ある基準日時点のポートフォリオ全商品と合計。"""

    base_date: date
    products: list[ProductSnapshot]
    total: AssetAmounts


class VisualizationSummary(BaseModel):
    """ヒーロー用の最新サマリ（最新基準日と前回基準日比）。"""

    base_date: date
    total: AssetAmounts
    profit_rate: float  # 生比率（表示整形はフロント）
    valuation_change: int  # 前回基準日比（評価額）
    profit_change: int  # 前回基準日比（評価損益）


class VisualizationResponse(BaseModel):
    """`GET /api/visualization` のレスポンス。

    データ0件のときは `summary=None` / `series=[]`。`series` は基準日昇順・全期間。
    """

    summary: VisualizationSummary | None
    series: list[SeriesPoint]
