"""Scraper ポートの具象（Selenium）と、page_source からの純粋抽出関数。

ADR-0002（コンテキストマネージャ方式のセッション）と ADR-0003（Selenium + 版ピン
chromium/chromedriver を Lambda コンテナに同梱）に従う。Selenium のナビゲーション
（メニュー遷移・待機）と、HTML から PortfolioAsset への抽出（BeautifulSoup の純粋関数
`extract_portfolio`）を分離し、後者を fixture HTML で決定的にテストする。

抽出マッピング（旧 scraping_nrk が「正」、実セレクタ最終確定はライブ検証フェーズ）:
  商品コンテナ: #prodInfo .infoDetailUnit_02.pc_mb30
  商品名      : .infoHdWrap00（strip）
  拠出金額累計: 商品内 tr[2] の最終 td
  資産評価額  : 商品内 tr[2] の td[2]
  評価損益    : 商品内 tr[5] の最終 td
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from domain.asset import Money, PortfolioAsset, ProductAsset
from domain.collection import Credentials, ScraperError, ScraperSession


def extract_portfolio(html: str, *, base_date: date) -> PortfolioAsset:
    """page_source（HTML 文字列）から PortfolioAsset を組み立てる純粋関数。"""
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one("#prodInfo")
    if container is None:
        raise ValueError("資産情報コンテナ #prodInfo が見つかりません")

    products: list[ProductAsset] = []
    for unit in container.select(".infoDetailUnit_02.pc_mb30"):
        heading = unit.select_one(".infoHdWrap00")
        if heading is None:
            raise ValueError("商品名要素 .infoHdWrap00 が見つかりません")
        name = heading.get_text(strip=True)

        rows = unit.find_all("tr")
        cells_tr2 = rows[2].find_all("td")
        cells_tr5 = rows[5].find_all("td")
        contribution = Money.parse(cells_tr2[-1].get_text())
        valuation = Money.parse(cells_tr2[2].get_text())
        profit_loss = Money.parse(cells_tr5[-1].get_text())

        products.append(
            ProductAsset(
                name=name,
                contribution=contribution,
                profit_loss=profit_loss,
                valuation=valuation,
            )
        )

    return PortfolioAsset(base_date=base_date, products=tuple(products))


_JST = ZoneInfo("Asia/Tokyo")


class _Clock(Protocol):
    def now(self) -> datetime: ...


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(_JST)


# ScraperConfig を受け取り、起動済みの WebDriver（相当）を返すファクトリ。
DriverFactory = Callable[["ScraperConfig"], Any]


@dataclass(frozen=True)
class ScraperConfig:
    """SeleniumScraper の実行設定（ブラウザバイナリ・driver パス・挙動）。"""

    user_agent: str
    chrome_binary_location: str
    chrome_driver_path: str
    implicit_wait: int = 10
    # 移行期間中のみ必要な「転出処理中」プラン選択ステップ。
    # TODO(フェーズ4.3): プラン移行完了後に削除する。
    select_transferring_plan: bool = True


def _default_chrome_factory(config: ScraperConfig) -> Any:
    """版ピン chromium/chromedriver で headless Chrome を起動する（ADR-0003）。

    実起動はライブ依存（Lambda コンテナ）のため、決定的テストでは driver_factory を
    差し替える。オプションは umihico/docker-selenium-lambda を踏襲。
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    for argument in (
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--no-zygote",
        "--no-sandbox",
        "--single-process",
        "--hide-scrollbars",
        "--window-size=1280x1696",
    ):
        options.add_argument(argument)
    options.add_argument(f"--user-agent={config.user_agent}")
    tmp_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={tmp_dir}")
    options.binary_location = config.chrome_binary_location

    driver = webdriver.Chrome(service=Service(config.chrome_driver_path), options=options)
    driver.implicitly_wait(config.implicit_wait)
    return driver


def _format_birthdate(birthdate: date) -> str:
    # TODO(フェーズ4.3): 実サイトのフォーム入力フォーマットを確定する（暫定 %Y%m%d）。
    return birthdate.strftime("%Y%m%d")


class _SeleniumScraperSession:
    """ログイン済みドライバを用いて資産ページを取得する ScraperSession 具象。"""

    def __init__(self, driver: Any, clock: _Clock) -> None:
        self._driver = driver
        self._clock = clock

    def scrape(self) -> PortfolioAsset:
        try:
            self._driver.find_element(By.ID, "mainMenu01").click()
            self._driver.find_element(By.CLASS_NAME, "total")  # 読み込み完了の確認
            html = self._driver.page_source
            return extract_portfolio(html, base_date=self._clock.now().date())
        except ScraperError:
            raise
        except Exception as error:
            # 取得・抽出の失敗は失敗時点のページ本文を添えて ScraperError に包む
            # （取得自体が不能なら content=None）。主例外は隠さない。
            raise ScraperError(
                f"資産情報の取得・抽出に失敗しました: {error}",
                content=_safe_page_source(self._driver),
            ) from error


def _safe_page_source(driver: Any) -> str | None:
    try:
        return driver.page_source
    except Exception:
        return None


class SeleniumScraper:
    """Scraper ポートの具象（Selenium）。ADR-0002 のセッションライフサイクルを満たす。"""

    def __init__(
        self,
        config: ScraperConfig,
        *,
        driver_factory: DriverFactory = _default_chrome_factory,
        clock: _Clock | None = None,
    ) -> None:
        self._config = config
        self._driver_factory = driver_factory
        self._clock = clock if clock is not None else _SystemClock()

    @contextmanager
    def session(self, url: str, credentials: Credentials) -> Iterator[ScraperSession]:
        driver = self._driver_factory(self._config)
        try:
            self._open_and_login(driver, url, credentials)
        except BaseException:
            # login/確立に失敗したらその場でクローズして送出（yield 前なので finally に入らない）。
            driver.quit()
            raise
        try:
            yield _SeleniumScraperSession(driver, self._clock)
        finally:
            self._logout_quietly(driver)
            driver.quit()

    def _open_and_login(self, driver: Any, url: str, credentials: Credentials) -> None:
        driver.get(url)
        driver.find_element(By.NAME, "userId").send_keys(credentials.user_id)
        driver.find_element(By.NAME, "password").send_keys(credentials.password)
        birth_field = driver.find_element(By.NAME, "birthDate")
        birth_field.send_keys(_format_birthdate(credentials.birthdate))
        driver.find_element(By.ID, "btnLogin").click()
        if not self._is_logged_in(driver):
            raise ScraperError("ログインに失敗しました（ログアウトリンクが見つかりません）")
        if self._config.select_transferring_plan:
            self._select_transferring_out_plan(driver)

    @staticmethod
    def _is_logged_in(driver: Any) -> bool:
        try:
            driver.find_element(By.LINK_TEXT, "ログアウト")
        except NoSuchElementException:
            return False
        return True

    @staticmethod
    def _select_transferring_out_plan(driver: Any) -> None:
        # TODO(フェーズ4.3): プラン移行完了後に削除する過渡ステップ。
        rows = driver.find_elements(By.CSS_SELECTOR, "table.inputTable tbody tr")
        for row in rows:
            cell = row.find_element(By.CSS_SELECTOR, "td[data-lang='jp']")
            if "転出処理中" in cell.text:
                row.find_element(By.CSS_SELECTOR, "input[type='radio']").click()
                driver.find_element(By.ID, "btnSubmit").click()
                return

    @staticmethod
    def _logout_quietly(driver: Any) -> None:
        # 後始末。失敗は握り潰して主例外を隠さない（ADR-0002）。
        try:
            driver.find_element(By.LINK_TEXT, "ログアウト").click()
        except Exception:
            pass
