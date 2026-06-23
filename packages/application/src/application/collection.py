"""収集ユースケース。

具象（Scraper / AssetRepository / ErrorPageStore / Clock）を DI で受け取り、
セッションを開いて scrape し、結果を保存する。フレームワークや具象実装には依存しない。
"""

from __future__ import annotations

from typing import Protocol

from domain.asset import AssetRepository, PortfolioAsset
from domain.clock import Clock
from domain.collection import (
    Credentials,
    ErrorPage,
    ErrorPageStore,
    Scraper,
    ScraperError,
)


class CollectionInputBoundary(Protocol):
    """収集ユースケースの入力境界。"""

    def execute(self, url: str, credentials: Credentials) -> PortfolioAsset: ...


class CollectionUseCase(CollectionInputBoundary):
    def __init__(
        self,
        scraper: Scraper,
        repository: AssetRepository,
        error_store: ErrorPageStore,
        clock: Clock,
    ) -> None:
        self._scraper = scraper
        self._repository = repository
        self._error_store = error_store
        self._clock = clock

    def execute(self, url: str, credentials: Credentials) -> PortfolioAsset:
        with self._scraper.session(url, credentials) as session:
            try:
                asset = session.scrape()
            except ScraperError as error:
                # scrape 失敗時のみ、失敗時点のページを ErrorPage として証跡保存して再送出。
                # login / session 失敗・save 失敗は捕捉せずそのまま送出する。
                self._error_store.save(
                    ErrorPage.captured(url=url, content=error.content, at=self._clock.now())
                )
                raise
        self._repository.save(asset)  # with を抜けてから保存する。
        return asset
