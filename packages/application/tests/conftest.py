"""CollectionUseCase 検証用の Fake と fixture。

Fake は application が観測する範囲（セッションを開く→scrape→後始末）だけを表現する。
open/login/logout/close という細かなライフサイクル順序は具象アダプタ（ADR-0002）の
契約であり、その検証は後続フェーズの infrastructure 具象 Scraper のテストで行う。
ここでは「scrape の結果がどう扱われるか」と「outcome によらず後始末されるか」のみ見る。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from types import TracebackType

import pytest

from domain.asset import Money, PortfolioAsset, ProductAsset
from domain.collection import Credentials, ErrorPage, ScraperError
from domain.notification import Notification

FIXED_NOW = datetime(2026, 6, 18, 9, 0, 0)

CREDENTIALS = Credentials(user_id="user01", password="secret", birthdate=date(1990, 1, 1))

URL = "https://dc.example/portfolio"


class _FakeSession:
    """`with` で開かれ scrape を提供するセッション兼コンテキストマネージャ。"""

    def __init__(self, scraper: FakeScraper) -> None:
        self._scraper = scraper

    def __enter__(self) -> _FakeSession:
        if self._scraper.login_error is not None:
            # login/session 確立に失敗（__enter__ で送出）。__exit__ は呼ばれない。
            raise self._scraper.login_error
        return self

    def scrape(self) -> PortfolioAsset:
        if self._scraper.scrape_error is not None:
            raise self._scraper.scrape_error
        assert self._scraper.asset is not None
        return self._scraper.asset

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self._scraper.closed = True  # 後始末。例外は抑制しない。
        return False


class FakeScraper:
    """`session(url, credentials)` でコンテキストマネージャ方式のセッションを返す。

    `closed` は __enter__ 成功後に session が後始末されたか（=__exit__ 到達）を示す。
    """

    def __init__(
        self,
        *,
        asset: PortfolioAsset | None = None,
        scrape_error: ScraperError | None = None,
        login_error: BaseException | None = None,
    ) -> None:
        self.asset = asset
        self.scrape_error = scrape_error
        self.login_error = login_error
        self.closed = False

    def session(self, url: str, credentials: Credentials) -> _FakeSession:
        return _FakeSession(self)


class InMemoryAssetRepository:
    """保存された PortfolioAsset を記録するインメモリ AssetRepository。"""

    def __init__(self) -> None:
        self.saved: list[PortfolioAsset] = []

    def save(self, asset: PortfolioAsset) -> None:
        self.saved.append(asset)

    def find_by_date_range(self, from_date: date, to_date: date) -> list[PortfolioAsset]:
        in_range = [a for a in self.saved if from_date <= a.base_date <= to_date]
        return sorted(in_range, key=lambda a: a.base_date)

    def find_all(self) -> list[PortfolioAsset]:
        return sorted(self.saved, key=lambda a: a.base_date)


class RecordingNotifier:
    """受領した Notification を記録するインメモリ Notifier。"""

    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


class InMemoryErrorPageStore:
    """保存された ErrorPage を記録するインメモリ ErrorPageStore。"""

    def __init__(self) -> None:
        self.saved: list[ErrorPage] = []

    def save(self, page: ErrorPage) -> None:
        self.saved.append(page)


@dataclass
class FixedClock:
    """常に固定時刻を返す Clock。"""

    fixed: datetime = FIXED_NOW

    def now(self) -> datetime:
        return self.fixed


@pytest.fixture
def repository() -> InMemoryAssetRepository:
    return InMemoryAssetRepository()


@pytest.fixture
def error_store() -> InMemoryErrorPageStore:
    return InMemoryErrorPageStore()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def sample_asset() -> PortfolioAsset:
    return PortfolioAsset(
        base_date=date(2026, 6, 18),
        products=(
            ProductAsset(
                name="ファンドA",
                contribution=Money(100_000),
                profit_loss=Money(20_000),
                valuation=Money(120_000),
            ),
        ),
    )


@pytest.fixture
def make_scraper() -> Callable[..., FakeScraper]:
    """FakeScraper を組み立てるファクトリ。"""

    def _make(
        *,
        asset: PortfolioAsset | None = None,
        scrape_error: ScraperError | None = None,
        login_error: BaseException | None = None,
    ) -> FakeScraper:
        return FakeScraper(asset=asset, scrape_error=scrape_error, login_error=login_error)

    return _make
