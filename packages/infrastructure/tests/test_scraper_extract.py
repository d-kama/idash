"""extract_portfolio は page_source から PortfolioAsset を組み立てる純粋関数。"""

from datetime import date
from pathlib import Path

from domain.asset import Money, PortfolioAsset, ProductAsset
from infrastructure.scraper import extract_portfolio

FIXTURE = (Path(__file__).parent / "fixtures" / "asset_page.html").read_text(encoding="utf-8")
BASE_DATE = date(2026, 6, 18)


def test_extract_portfolio_maps_each_product() -> None:
    portfolio = extract_portfolio(FIXTURE, base_date=BASE_DATE)

    assert portfolio == PortfolioAsset(
        base_date=BASE_DATE,
        products=(
            ProductAsset(
                name="ファンドA（国内株式）",
                contribution=Money(100_000),
                profit_loss=Money(20_000),
                valuation=Money(120_000),
            ),
            ProductAsset(
                name="ファンドB（外国債券）",
                contribution=Money(50_000),
                profit_loss=Money(-8_000),  # △8,000 は会計表記の負
                valuation=Money(42_000),
            ),
        ),
    )


def test_extract_portfolio_sets_base_date() -> None:
    portfolio = extract_portfolio(FIXTURE, base_date=date(2026, 1, 5))

    assert portfolio.base_date == date(2026, 1, 5)
