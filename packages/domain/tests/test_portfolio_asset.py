"""PortfolioAsset.total() の合算ロジックを検証する。"""

from datetime import date

from domain.asset import AssetTotal, Money, PortfolioAsset, ProductAsset


def _product(name: str, contribution: int, profit_loss: int, valuation: int) -> ProductAsset:
    return ProductAsset(
        name=name,
        contribution=Money(contribution),
        profit_loss=Money(profit_loss),
        valuation=Money(valuation),
    )


def test_total_sums_each_field_across_products() -> None:
    portfolio = PortfolioAsset(
        base_date=date(2026, 6, 18),
        products=[
            _product("ファンドA", 100_000, 20_000, 120_000),
            _product("ファンドB", 50_000, -5_000, 45_000),
        ],
    )

    assert portfolio.total() == AssetTotal(
        contribution=Money(150_000),
        profit_loss=Money(15_000),
        valuation=Money(165_000),
    )


def test_total_of_empty_portfolio_is_zero() -> None:
    portfolio = PortfolioAsset(base_date=date(2026, 6, 18), products=[])

    assert portfolio.total() == AssetTotal(
        contribution=Money(0),
        profit_loss=Money(0),
        valuation=Money(0),
    )
