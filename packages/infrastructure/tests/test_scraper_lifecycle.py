"""SeleniumScraper のセッション後始末契約（ADR-0002）を FakeWebDriver で検証する。

検証するのは後始末の保証であり、各操作の網羅的な発生順ではない:
  - 正常終了 / スクレイピング失敗 → logout → close（この順）で後始末される
  - ログイン失敗 → logout は呼ばれず close のみ
  - 後始末（quit）失敗は主例外（ScraperError）を隠さない
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from domain.collection import Credentials, ScraperError
from infrastructure.scraper import ScraperConfig, SeleniumScraper

FIXTURE = (Path(__file__).parent / "fixtures" / "asset_page.html").read_text(encoding="utf-8")
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
    """send_keys/click/find_element を最小実装する擬似 WebElement。"""

    def __init__(self, *, on_click=None, text: str = "") -> None:
        self._on_click = on_click
        self.text = text

    def send_keys(self, *_args: object) -> None:
        pass

    def click(self) -> None:
        if self._on_click is not None:
            self._on_click()

    def find_element(self, by: str, value: str) -> "_FakeElement":
        if "data-lang" in value:
            return _FakeElement(text="転出処理中")
        return _FakeElement()


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
            return [_FakeElement()] if self._has_plan else []
        return []

    def quit(self) -> None:
        if self._quit_raises:
            raise RuntimeError("quit failed")
        self.events.append("close")


def _scraper(driver: FakeWebDriver, config: ScraperConfig = CONFIG) -> SeleniumScraper:
    return SeleniumScraper(
        config, driver_factory=lambda _c: cast(WebDriver, driver), clock=FixedClock()
    )


def test_normal_completion_logs_out_then_closes() -> None:
    driver = FakeWebDriver(html=FIXTURE)

    with _scraper(driver).session(URL, CREDENTIALS) as session:
        asset = session.scrape()

    assert driver.events[-2:] == ["logout", "close"]
    assert len(asset.products) == 2
    assert asset.base_date == date(2026, 6, 18)  # clock の JST 日付


def test_login_failure_closes_without_logout() -> None:
    driver = FakeWebDriver(html=FIXTURE, login_succeeds=False)

    with pytest.raises(ScraperError):
        with _scraper(driver).session(URL, CREDENTIALS):
            pass  # __enter__ 内の login 失敗で到達しない

    assert "logout" not in driver.events
    assert driver.events[-1] == "close"


def test_scrape_failure_logs_out_then_closes_with_page_source() -> None:
    bad_html = "<html><body>no prodInfo here</body></html>"
    driver = FakeWebDriver(html=bad_html)

    with _scraper(driver).session(URL, CREDENTIALS) as session:
        with pytest.raises(ScraperError) as exc_info:
            session.scrape()

    assert exc_info.value.content == bad_html
    assert driver.events[-2:] == ["logout", "close"]


def test_quit_failure_does_not_mask_scraper_error() -> None:
    bad_html = "<html><body>no prodInfo here</body></html>"
    driver = FakeWebDriver(html=bad_html, quit_raises=True)

    # quit() が失敗しても scrape の ScraperError が伝播する（後始末失敗で上書きされない）。
    with pytest.raises(ScraperError):
        with _scraper(driver).session(URL, CREDENTIALS) as session:
            session.scrape()
