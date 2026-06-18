"""共有アセットコア（資産サブドメイン）。

すべて stdlib の frozen dataclass で表現する値オブジェクト。domain 層は何にも依存
しない純粋層であり、pydantic 等のフレームワークは持ち込まない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Protocol

# 会計表記・符号として負を表すマーカー。△/▲ は会計慣行のマイナス表記、
# `-`（ASCII ハイフンマイナス）と `−`（U+2212 全角マイナス）も負として扱う。
_NEGATIVE_MARKERS = ("-", "−", "△", "▲")


@dataclass(frozen=True)
class Money:
    """日本円の金額を円単位の整数で表す値オブジェクト。"""

    yen: int

    @classmethod
    def parse(cls, text: str) -> Money:
        """Web 取得文字列を解釈して Money を返す。

        `¥1,234,567` / `-80,000円` / `△80,000` / `▲80,000` 等の表記を受け付け、
        数字が一つも含まれない場合は ValueError を送出する。会計表記 △/▲ は負。
        """
        stripped = text.strip()
        digits = re.sub(r"[^0-9]", "", stripped)
        if not digits:
            raise ValueError(f"金額として解釈できません: {text!r}")
        magnitude = int(digits)
        negative = any(marker in stripped for marker in _NEGATIVE_MARKERS)
        return cls(-magnitude if negative else magnitude)

    def __add__(self, other: Money) -> Money:
        return Money(self.yen + other.yen)

    def __sub__(self, other: Money) -> Money:
        return Money(self.yen - other.yen)

    @property
    def is_positive(self) -> bool:
        return self.yen > 0

    @property
    def is_negative(self) -> bool:
        return self.yen < 0

    def format(self) -> str:
        """`¥1,234,567` / `-¥80,000` / `¥0` 形式の表示文字列。"""
        sign = "-" if self.yen < 0 else ""
        return f"{sign}¥{abs(self.yen):,}"

    def signed(self) -> str:
        """正の値に明示的な `+` を付す表示（損益表示向け）。ゼロは符号なし。"""
        if self.yen > 0:
            return f"+¥{self.yen:,}"
        return self.format()


@dataclass(frozen=True)
class ProductAsset:
    """単一の投資商品について、ある基準日時点の拠出金額累計・評価損益・資産評価額。"""

    name: str
    contribution: Money
    profit_loss: Money
    valuation: Money


@dataclass(frozen=True)
class AssetTotal:
    """PortfolioAsset を構成する全 ProductAsset を合算した合計。"""

    contribution: Money
    profit_loss: Money
    valuation: Money


@dataclass(frozen=True)
class PortfolioAsset:
    """ある基準日時点の全 ProductAsset の集合。"""

    base_date: date
    products: tuple[ProductAsset, ...]

    def __post_init__(self) -> None:
        # frozen でも list 内部は可変。値オブジェクトの不変性のため tuple に固定する。
        object.__setattr__(self, "products", tuple(self.products))

    def total(self) -> AssetTotal:
        """全 ProductAsset の3項目をそれぞれ Money 加算で合算する。"""
        contribution = Money(0)
        profit_loss = Money(0)
        valuation = Money(0)
        for product in self.products:
            contribution += product.contribution
            profit_loss += product.profit_loss
            valuation += product.valuation
        return AssetTotal(
            contribution=contribution,
            profit_loss=profit_loss,
            valuation=valuation,
        )


class AssetRepository(Protocol):
    """PortfolioAsset を永続化するポート。

    本フェーズでは保存（save）のみを定義する。日付/期間での取得（read 系）は
    後続フェーズで後方互換に追加する。
    """

    def save(self, asset: PortfolioAsset) -> None: ...
