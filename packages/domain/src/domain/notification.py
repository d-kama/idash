"""通知サブドメイン（Notification）。

蓄積された PortfolioAsset を集計（summarize）し、人が読むテキストへ整形
（render_summary）する純粋部分と、整形済み通知を送るポート（Notifier）。
domain 層の純粋性を保つため stdlib のみで構成し、domain.asset のみ参照する。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from domain.asset import AssetTotal, Money, PortfolioAsset


@dataclass(frozen=True)
class Summary:
    """期間集計の結果。最新スナップショットと期間変化を保持する。"""

    period_from: date  # 区間内に実在する最古基準日
    latest_date: date  # 区間内に実在する最新基準日
    latest_total: AssetTotal  # 最新時点の合計（拠出累計 / 評価損益 / 資産評価額）
    profit_rate: float  # 損益率 = profit_loss.yen / contribution.yen（生比率）
    valuation_change: Money  # 最新評価額 − 最古評価額
    profit_change: Money  # 最新評価損益 − 最古評価損益


def summarize(assets: Sequence[PortfolioAsset]) -> Summary:
    """1件以上の PortfolioAsset を集計して Summary を返す。

    0件はユースケースが手前で弾く前提（ここでは扱わない）。入力順序は前提とせず、
    基準日の min/max で最古/最新を選ぶ（防御的）。
    """
    oldest = min(assets, key=lambda a: a.base_date)
    newest = max(assets, key=lambda a: a.base_date)

    oldest_total = oldest.total()
    latest_total = newest.total()

    contribution_yen = latest_total.contribution.yen
    profit_rate = latest_total.profit_loss.yen / contribution_yen if contribution_yen != 0 else 0.0

    return Summary(
        period_from=oldest.base_date,
        latest_date=newest.base_date,
        latest_total=latest_total,
        profit_rate=profit_rate,
        valuation_change=latest_total.valuation - oldest_total.valuation,
        profit_change=latest_total.profit_loss - oldest_total.profit_loss,
    )


@dataclass(frozen=True)
class Notification:
    """通知チャネル非依存のプレーンテキスト通知。"""

    subject: str
    body: str


def render_summary(summary: Summary) -> Notification:
    """Summary を人が読むテキストへ整形する純粋関数。"""
    latest_total = summary.latest_total
    subject = (
        f"iDeCo 運用サマリ（{summary.period_from.isoformat()}〜{summary.latest_date.isoformat()}）"
    )
    body = (
        f"■ 最新（{summary.latest_date.isoformat()} 時点）\n"
        f"  資産評価額: {latest_total.valuation.format()}\n"
        f"  評価損益: {latest_total.profit_loss.signed()}"
        f"（{summary.profit_rate * 100:+.2f}%）\n"
        f"  拠出累計: {latest_total.contribution.format()}\n"
        f"\n"
        f"■ この期間の変化（{summary.period_from.isoformat()} → "
        f"{summary.latest_date.isoformat()}）\n"
        f"  評価額: {summary.valuation_change.signed()}\n"
        f"  評価損益: {summary.profit_change.signed()}"
    )
    return Notification(subject=subject, body=body)


class Notifier(Protocol):
    """整形済み Notification を通知チャネルへ送るポート（集計・整形は持たない）。"""

    def send(self, notification: Notification) -> None: ...
