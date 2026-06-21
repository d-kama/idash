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

    def test_sets_base_date(self) -> None:
        portfolio = extract_portfolio(FIXTURE, base_date=date(2026, 1, 5))

        assert portfolio.base_date == date(2026, 1, 5)


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
    """send_keys/click/find_element を最小実装する擬似 WebElement。

    find_element はセル → 祖先 tr → ラジオのチェーンを表すため、設定された子要素
    `child` を返す（無ければ素の要素）。
    """

    def __init__(
        self,
        *,
        on_click=None,
        text: str = "",
        child: _FakeElement | None = None,
    ) -> None:
        self._on_click = on_click
        self.text = text
        self._child = child

    def send_keys(self, *_args: object) -> None:
        pass

    def click(self) -> None:
        if self._on_click is not None:
            self._on_click()

    def find_element(self, by: str, value: str) -> _FakeElement:
        return self._child if self._child is not None else _FakeElement()


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
        plan_raises: bool = False,
        quit_raises: bool = False,
    ) -> None:
        self.events: list[str] = []
        self._html = html
        self._login_succeeds = login_succeeds
        self._has_plan = has_plan
        self._plan_raises = plan_raises
        self._quit_raises = quit_raises

    def get(self, _url: str) -> None:
        self.events.append("open")

    @property
    def page_source(self) -> str:
        return self._html

    def find_element(self, by: str, value: str) -> _FakeElement:
        if "inputTable" in value and self._plan_raises:
            # ログイン成立後のプラン選択ステップ（セル描画待ち）が失敗する状況を再現する。
            raise NoSuchElementException("プラン選択セルが見つかりません")
        if by == By.ID and value == "btnLogin":
            return _FakeElement(on_click=lambda: self.events.append("login"))
        if by == By.ID and value == "btnSubmit":
            return _FakeElement(on_click=lambda: self.events.append("plan"))
        if by == By.LINK_TEXT and value == "ログアウト":
            if not self._login_succeeds:
                raise NoSuchElementException("ログアウト リンクが見つかりません")
            return _FakeElement(on_click=lambda: self.events.append("logout"))
        return _FakeElement()

    def find_elements(self, by: str, value: str) -> list[_FakeElement]:
        if "inputTable" in value:
            # 「異動状況」データセル列。見出し行は th のみで td を持たないため、本物の
            # td セレクタには現れない（＝走査対象から外れる）ことを模す。
            return self._plan_cells() if self._has_plan else []
        return []

    def _plan_cells(self) -> list[_FakeElement]:
        # 「転出処理中」の行のラジオを選んで「決定」する。転入処理中の行は選ばない。
        # 各セルは find_element(祖先 tr) → find_element(ラジオ) のチェーンで辿られる。
        out_row = _FakeElement(
            child=_FakeElement(on_click=lambda: self.events.append("plan-radio"))
        )
        in_row = _FakeElement(
            child=_FakeElement(on_click=lambda: self.events.append("plan-radio-wrong"))
        )
        return [
            _FakeElement(text="転入処理中", child=in_row),
            _FakeElement(text="転出処理中", child=out_row),
        ]

    def quit(self) -> None:
        if self._quit_raises:
            raise RuntimeError("quit failed")
        self.events.append("close")


def _scraper(driver: FakeWebDriver, config: ScraperConfig = CONFIG) -> SeleniumScraper:
    return SeleniumScraper(
        config, driver_factory=lambda _c: cast(WebDriver, driver), clock=FixedClock()
    )


class TestSessionLifecycle:
    """SeleniumScraper のセッション後始末契約（ADR-0002）を FakeWebDriver で検証する。

    検証するのは後始末の保証であり、各操作の網羅的な発生順ではない:
      - 正常終了 / スクレイピング失敗 → logout → close（この順）で後始末される
      - ログイン確立前の失敗 → logout は呼ばれず close のみ
      - ログイン確立後の失敗（プラン選択など）→ logout → close で後始末される
      - 後始末（quit）失敗は主例外（ScraperError）を隠さない
    """

    def test_normal_completion_logs_out_then_closes(self) -> None:
        driver = FakeWebDriver(html=FIXTURE)

        with _scraper(driver).session(URL, CREDENTIALS) as session:
            asset = session.scrape()

        assert driver.events[-2:] == ["logout", "close"]
        assert len(asset.products) == 2
        assert asset.base_date == date(2026, 6, 18)  # clock の JST 日付

    def test_plan_selection_selects_transfer_out_row(self) -> None:
        # プラン選択テーブルに見出し行（th のみ）が混じっても、データセル（td[data-lang='jp']）
        # を直接走査して「転出処理中」の行のラジオを選ぶ。見出し行は td を持たず走査に現れない
        # ため、行を総なめして td を引いていた頃の NoSuchElementException は起きない。
        driver = FakeWebDriver(html=FIXTURE)

        with _scraper(driver).session(URL, CREDENTIALS) as session:
            session.scrape()

        # 転出行のラジオ → 決定（btnSubmit=plan）の順で押し、転入行は選ばない。
        assert "plan-radio-wrong" not in driver.events
        assert driver.events.index("plan-radio") < driver.events.index("plan")

    def test_login_failure_closes_without_logout(self) -> None:
        driver = FakeWebDriver(html=FIXTURE, login_succeeds=False)

        with pytest.raises(ScraperError):
            with _scraper(driver).session(URL, CREDENTIALS):
                pass  # __enter__ 内の login 失敗で到達しない

        assert "logout" not in driver.events
        assert driver.events[-1] == "close"

    def test_post_login_failure_logs_out_then_closes(self) -> None:
        # ログインは成立（サーバ側セッション確立）したが、その後の過渡ステップ（プラン選択）で
        # 失敗するケース。残存セッションでの再ログイン不能を防ぐため logout→close する（ADR-0002）。
        driver = FakeWebDriver(html=FIXTURE, plan_raises=True)

        with pytest.raises(NoSuchElementException):
            with _scraper(driver).session(URL, CREDENTIALS):
                pass  # __enter__ 内の確立後ステップ失敗で到達しない

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
