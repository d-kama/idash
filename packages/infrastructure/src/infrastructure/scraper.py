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
from datetime import date

from bs4 import BeautifulSoup
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from domain.asset import Money, PortfolioAsset, ProductAsset
from domain.clock import Clock
from domain.collection import Credentials, ScraperError, ScraperSession
from infrastructure.clock import SystemClock


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


# ScraperConfig を受け取り、起動済みの WebDriver を返すファクトリ。
# テストではダミー driver を `cast(WebDriver, ...)` で注入する（注入点でのみ回避）。
DriverFactory = Callable[["ScraperConfig"], WebDriver]


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


def _default_chrome_factory(config: ScraperConfig) -> WebDriver:
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
    # MEMO: Chrome の user-data-dir 用に毎回 /tmp へ新規ディレクトリを作る（固定パスだと Lambda
    # ウォーム再利用時に "user data directory is already in use" になり得るため fresh path に
    # する）。終了後に削除はしない＝あえてのリーク。収集は日次1回・毎回コールドスタートで、
    # reservedConcurrentExecutions=1 によりウォーム環境は最大1個、プロファイル数十MB に対し
    # /tmp は既定 512MB あり、アイドルの実行環境は破棄されるため /tmp に蓄積しない。
    # 必要になったら quit 後に shutil.rmtree() することを検討。
    options.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
    options.binary_location = config.chrome_binary_location

    driver = webdriver.Chrome(service=Service(config.chrome_driver_path), options=options)
    driver.implicitly_wait(config.implicit_wait)
    return driver


def _format_birthdate(birthdate: date) -> str:
    return birthdate.strftime("%Y%m%d")


class _SeleniumScraperSession:
    """ログイン済みドライバを用いて資産ページを取得する ScraperSession 具象。"""

    def __init__(self, driver: WebDriver, clock: Clock) -> None:
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


def _safe_page_source(driver: WebDriver) -> str | None:
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
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._driver_factory = driver_factory
        self._clock = clock if clock is not None else SystemClock()

    @contextmanager
    def session(self, url: str, credentials: Credentials) -> Iterator[ScraperSession]:
        driver = self._driver_factory(self._config)
        try:
            self._open_and_login(driver, url, credentials)
        except BaseException:
            # login/確立に失敗したらその場でクローズして送出（yield 前なので finally に入らない）。
            self._safe_quit(driver)
            raise
        try:
            yield _SeleniumScraperSession(driver, self._clock)
        finally:
            self._logout_quietly(driver)
            self._safe_quit(driver)

    @staticmethod
    def _safe_quit(driver: WebDriver) -> None:
        # 後始末。quit 失敗は握り潰して主例外（特に ScraperError）を隠さない（ADR-0002）。
        # CollectionUseCase は ScraperError を捕捉してエラーページを保存するため、ここで
        # 例外型が変わるとその経路が失われる。
        try:
            driver.quit()
        except Exception:
            pass

    def _open_and_login(self, driver: WebDriver, url: str, credentials: Credentials) -> None:
        driver.get(url)
        driver.find_element(By.NAME, "userId").send_keys(credentials.user_id)
        driver.find_element(By.NAME, "password").send_keys(credentials.password)
        birth_field = driver.find_element(By.NAME, "birthDate")
        birth_field.send_keys(_format_birthdate(credentials.birthdate))
        driver.find_element(By.ID, "btnLogin").click()
        if not self._is_logged_in(driver):
            raise ScraperError("ログインに失敗しました（ログアウトリンクが見つかりません）")
        # ここでサーバ側セッション確立済み。以降の過渡ステップが失敗してもセッションを
        # 残さないよう logout を試みてから送出する（残存セッションでの再ログイン不能を防ぐ）。
        # 確立前の失敗はセッションが無いので logout 不要（session() 側で close のみ）。
        try:
            if self._config.select_transferring_plan:
                self._select_transferring_out_plan(driver)
        except BaseException:
            self._logout_quietly(driver)
            raise

    @staticmethod
    def _is_logged_in(driver: WebDriver) -> bool:
        try:
            driver.find_element(By.LINK_TEXT, "ログアウト")
        except NoSuchElementException:
            return False
        return True

    @staticmethod
    def _select_transferring_out_plan(driver: WebDriver) -> None:
        # TODO(フェーズ4.3): プラン移行完了後に削除する過渡ステップ。
        # プラン選択テーブルの「異動状況」セル（td[data-lang='jp']）が「転出処理中」の
        # 行を選び「決定」する。
        #
        # 行（tr）を総なめして行内 find_element(td) を呼ぶと、見出し行（th のみで td を
        # 持たない）で NoSuchElementException になる。そこで行ではなくデータセルを直接
        # 走査し、該当セルから祖先 tr を辿って同じ行のラジオを押す（見出し行は td を持た
        # ないため走査対象に現れない）。
        #
        # ログイン直後はテーブルが描画途中のことがあるため、セルが1つでも描画済みになる
        # のを marker として待ってから走査する（_SeleniumScraperSession.scrape() の「読み
        # 込み完了の確認」と同じ implicit_wait ベースのイディオム）。
        cell_selector = "table.inputTable tbody td[data-lang='jp']"
        driver.find_element(By.CSS_SELECTOR, cell_selector)  # 描画完了の marker 待ち
        for cell in driver.find_elements(By.CSS_SELECTOR, cell_selector):
            if "転出処理中" in cell.text:
                row = cell.find_element(By.XPATH, "./ancestor::tr[1]")
                row.find_element(By.CSS_SELECTOR, "input[type='radio']").click()
                driver.find_element(By.ID, "btnSubmit").click()
                return

    @staticmethod
    def _logout_quietly(driver: WebDriver) -> None:
        # 後始末。失敗は握り潰して主例外を隠さない（ADR-0002）。
        try:
            driver.find_element(By.LINK_TEXT, "ログアウト").click()
        except Exception:
            pass
