"""scraper.py のテスト。

scraper.py の 2 つの検証対象を、対象ごとにクラスで分けて検証する:
  - TestExtractPortfolio : 純粋関数 extract_portfolio（fixture HTML → PortfolioAsset）
  - TestSessionLifecycle : SeleniumScraper.session() の後始末契約（ADR-0002、FakeWebDriver）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from domain.asset import Money, PortfolioAsset, ProductAsset
from domain.collection import Credentials, ScraperError
from infrastructure.scraper import (
    ScraperConfig,
    SeleniumScraper,
    extract_portfolio,
)

FIXTURE = (Path(__file__).parent / "fixtures" / "asset_page.html").read_text(encoding="utf-8")
BASE_DATE = date(2026, 6, 18)


class TestExtractPortfolio:
    """extract_portfolio は page_source から PortfolioAsset を組み立てる純粋関数。"""

    def test_maps_each_product(self) -> None:
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


# --- SeleniumScraper のセッション後始末契約（ADR-0002）用のフィクスチャ群 ---
URL = "https://dc.example/login"
CREDENTIALS = Credentials(user_id="user01", password="secret", birthdate=date(1990, 1, 1))
CONFIG = ScraperConfig(
    user_agent="idash-bot",
    chrome_binary_location="/opt/chrome/chrome",
    chrome_driver_path="/opt/chromedriver/chromedriver",
)


@dataclass
class FixedClock:
    fixed: datetime = datetime(2026, 6, 18, 9, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))

    def now(self) -> datetime:
        return self.fixed


class _FakeElement:
    """send_keys/click を最小実装する擬似 WebElement。"""

    def __init__(self, *, on_click=None) -> None:
        self._on_click = on_click

    def send_keys(self, *_args: object) -> None:
        pass

    def click(self) -> None:
        if self._on_click is not None:
            self._on_click()


class FakeWebDriver:
    """後始末契約に関わるイベント（logout / close）を記録する擬似 WebDriver。

    quit_raises=True で `quit()` を失敗させ、後始末失敗が主例外を隠さないことを検証する。
    """

    def __init__(
        self,
        *,
        html: str,
        login_succeeds: bool = True,
        has_plan: bool = True,
        quit_raises: bool = False,
    ) -> None:
        self.events: list[str] = []
        self._html = html
        self._login_succeeds = login_succeeds
        self._has_plan = has_plan
        self._quit_raises = quit_raises

    def get(self, _url: str) -> None:
        self.events.append("open")

    @property
    def page_source(self) -> str:
        return self._html

    def find_element(self, by: str, value: str) -> _FakeElement:
        if "checkedPlanIdx" in value:
            # プラン選択テーブルのラジオ。プラン選択画面と分かる name で引かれること
            # （汎用の inputTable だけで引かないこと）をこの分岐で担保する。
            # has_plan=False でプラン選択画面が出ない（＝見つからない）状況を再現する。
            if not self._has_plan:
                raise NoSuchElementException("プラン選択のラジオが見つかりません")
            return _FakeElement(on_click=lambda: self.events.append("plan-radio"))
        if by == By.ID and value == "btnLogin":
            return _FakeElement(on_click=lambda: self.events.append("login"))
        if by == By.ID and value == "btnSubmit":
            return _FakeElement(on_click=lambda: self.events.append("plan"))
        if by == By.LINK_TEXT and value == "ログアウト":
            if not self._login_succeeds:
                raise NoSuchElementException("ログアウト リンクが見つかりません")
            return _FakeElement(on_click=lambda: self.events.append("logout"))
        return _FakeElement()

    def quit(self) -> None:
        if self._quit_raises:
            raise RuntimeError("quit failed")
        self.events.append("close")


def _scraper(driver: FakeWebDriver, config: ScraperConfig = CONFIG) -> SeleniumScraper:
    return SeleniumScraper(
        config, driver_factory=lambda _c: cast(WebDriver, driver), clock=FixedClock()
    )


def _in_order(events: list[str], *expected: str) -> bool:
    """events に expected がこの順で（連続でなくてよい）現れるか。"""
    remaining = iter(events)
    return all(event in remaining for event in expected)


class TestSessionLifecycle:
    """SeleniumScraper のセッション後始末契約（ADR-0002）を FakeWebDriver で検証する。

    検証するのは後始末の保証であり、各操作の網羅的な発生順ではない:
      - 正常終了（ログイン → scrape（プラン選択 → 抽出））→ logout → close の順で後始末される
      - ログイン失敗（yield 前）→ logout は呼ばれず close のみ
      - scrape 中のプラン選択失敗 → logout → close ＋ 失敗時点のページを ScraperError に添える
      - scrape 中の抽出失敗 → logout → close ＋ 失敗時点のページを ScraperError に添える
      - 後始末（quit）失敗は主例外（ScraperError）を隠さない
    """

    def test_normal_completion_logs_out_then_closes(self) -> None:
        driver = FakeWebDriver(html=FIXTURE)

        with _scraper(driver).session(URL, CREDENTIALS) as session:
            asset = session.scrape()

        assert _in_order(driver.events, "login", "plan-radio", "plan", "logout", "close")
        assert len(asset.products) == 2
        assert asset.base_date == date(2026, 6, 18)  # clock の JST 日付

    def test_login_failure_closes_without_logout(self) -> None:
        driver = FakeWebDriver(html=FIXTURE, login_succeeds=False)

        with pytest.raises(ScraperError):
            with _scraper(driver).session(URL, CREDENTIALS):
                pass  # __enter__ 内の login 失敗で到達しない

        assert "logout" not in driver.events
        assert driver.events[-1] == "close"

    def test_plan_selection_failure_logs_out_then_closes(self) -> None:
        driver = FakeWebDriver(html=FIXTURE, has_plan=False)

        with _scraper(driver).session(URL, CREDENTIALS) as session:
            with pytest.raises(ScraperError) as exc_info:
                session.scrape()

        assert exc_info.value.content == FIXTURE
        assert driver.events[-2:] == ["logout", "close"]

    def test_scrape_failure_logs_out_then_closes_with_page_source(self) -> None:
        bad_html = "<html><body>no prodInfo here</body></html>"
        driver = FakeWebDriver(html=bad_html)

        with _scraper(driver).session(URL, CREDENTIALS) as session:
            with pytest.raises(ScraperError) as exc_info:
                session.scrape()

        assert exc_info.value.content == bad_html
        assert driver.events[-2:] == ["logout", "close"]

    def test_quit_failure_does_not_mask_scraper_error(self) -> None:
        bad_html = "<html><body>no prodInfo here</body></html>"
        driver = FakeWebDriver(html=bad_html, quit_raises=True)

        # quit() が失敗しても scrape の ScraperError が伝播する（後始末失敗で上書きされない）。
        with pytest.raises(ScraperError):
            with _scraper(driver).session(URL, CREDENTIALS) as session:
                session.scrape()
