"""SeleniumScraper のセッションライフサイクル（ADR-0002）を FakeWebDriver で検証する。

検証する順序契約: open→login→[plan]→scrape→logout→close。login 失敗時はその場で
close（scrape/logout に進まない）。具象 Scraper が後始末を `with` で確実化する責務を
持つ（ADR-0002 が infra 具象の責務と明記）。
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

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
    """セマンティックなライフサイクルイベントだけを記録する擬似 WebDriver。

    記録するのは open / login / plan / scrape / logout / close の6種のみ。
    送信・メニュー遷移など中間操作は記録しない（順序契約に集中するため）。
    """

    def __init__(self, *, html: str, login_succeeds: bool = True, has_plan: bool = True) -> None:
        self.events: list[str] = []
        self._html = html
        self._login_succeeds = login_succeeds
        self._has_plan = has_plan

    def get(self, _url: str) -> None:
        self.events.append("open")

    @property
    def page_source(self) -> str:
        self.events.append("scrape")
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
        self.events.append("close")


def _scraper(driver: FakeWebDriver, config: ScraperConfig = CONFIG) -> SeleniumScraper:
    return SeleniumScraper(config, driver_factory=lambda _c: driver, clock=FixedClock())


def test_session_runs_full_lifecycle_in_order() -> None:
    driver = FakeWebDriver(html=FIXTURE)

    with _scraper(driver).session(URL, CREDENTIALS) as session:
        asset = session.scrape()

    assert driver.events == ["open", "login", "plan", "scrape", "logout", "close"]
    assert len(asset.products) == 2
    assert asset.base_date == date(2026, 6, 18)  # clock の JST 日付


def test_plan_selection_skipped_when_disabled() -> None:
    driver = FakeWebDriver(html=FIXTURE)
    config = replace(CONFIG, select_transferring_plan=False)

    with _scraper(driver, config).session(URL, CREDENTIALS) as session:
        session.scrape()

    assert driver.events == ["open", "login", "scrape", "logout", "close"]


def test_login_failure_closes_without_scrape() -> None:
    driver = FakeWebDriver(html=FIXTURE, login_succeeds=False)

    with pytest.raises(ScraperError):
        with _scraper(driver).session(URL, CREDENTIALS):
            pass  # __enter__ 内の login 失敗で到達しない

    assert driver.events == ["open", "login", "close"]


def test_scrape_wraps_extraction_failure_with_page_source() -> None:
    bad_html = "<html><body>no prodInfo here</body></html>"
    driver = FakeWebDriver(html=bad_html)

    with _scraper(driver).session(URL, CREDENTIALS) as session:
        with pytest.raises(ScraperError) as exc_info:
            session.scrape()

    assert exc_info.value.content == bad_html
