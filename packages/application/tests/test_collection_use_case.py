"""CollectionUseCase の振る舞いを Fake で検証する。

application の関心事のみを観測する: 成功時に scrape 結果を保存して返すこと、scrape 失敗時に
証跡を保存して再送出し保存しないこと、login 失敗は素通しすること、そして outcome に
よらずセッションが後始末されること。具象の細かなライフサイクル順序はここでは検証しない。
"""

from collections.abc import Callable

import pytest

from application.collection import CollectionUseCase
from domain.asset import PortfolioAsset
from domain.collection import ErrorPage, ScraperError

from .conftest import (
    CREDENTIALS,
    FIXED_NOW,
    URL,
    FakeScraper,
    FixedClock,
    InMemoryAssetRepository,
    InMemoryErrorPageStore,
)


def test_success_scrapes_then_saves_and_returns_asset(
    make_scraper: Callable[..., FakeScraper],
    repository: InMemoryAssetRepository,
    error_store: InMemoryErrorPageStore,
    clock: FixedClock,
    sample_asset: PortfolioAsset,
) -> None:
    scraper = make_scraper(asset=sample_asset)
    use_case = CollectionUseCase(scraper, repository, error_store, clock)

    result = use_case.execute(URL, CREDENTIALS)

    assert result == sample_asset
    assert repository.saved == [sample_asset]
    assert error_store.saved == []
    assert scraper.closed  # 後始末されている


def test_scrape_error_captures_error_page_then_reraises(
    make_scraper: Callable[..., FakeScraper],
    repository: InMemoryAssetRepository,
    error_store: InMemoryErrorPageStore,
    clock: FixedClock,
) -> None:
    error = ScraperError("collection failed", content="<html>error page</html>")
    scraper = make_scraper(scrape_error=error)
    use_case = CollectionUseCase(scraper, repository, error_store, clock)

    with pytest.raises(ScraperError):
        use_case.execute(URL, CREDENTIALS)

    assert error_store.saved == [
        ErrorPage(url=URL, captured_at=FIXED_NOW, content="<html>error page</html>")
    ]
    assert repository.saved == []
    assert scraper.closed  # 失敗時でもセッションは後始末される


def test_scrape_error_with_none_content_still_captures_error_page(
    make_scraper: Callable[..., FakeScraper],
    repository: InMemoryAssetRepository,
    error_store: InMemoryErrorPageStore,
    clock: FixedClock,
) -> None:
    scraper = make_scraper(scrape_error=ScraperError("collection failed", content=None))
    use_case = CollectionUseCase(scraper, repository, error_store, clock)

    with pytest.raises(ScraperError):
        use_case.execute(URL, CREDENTIALS)

    assert error_store.saved == [ErrorPage(url=URL, captured_at=FIXED_NOW, content=None)]
    assert repository.saved == []


def test_login_failure_propagates_without_capture_or_save(
    make_scraper: Callable[..., FakeScraper],
    repository: InMemoryAssetRepository,
    error_store: InMemoryErrorPageStore,
    clock: FixedClock,
) -> None:
    # login 失敗は scrape の外（セッション確立時）で起きる。ScraperError であってもユースケースの
    # 捕捉対象（scrape 周りの try）に入らないため、ErrorPage 保存も repository 保存もせず伝播する。
    scraper = make_scraper(login_error=ScraperError("login failed", content="<html>login</html>"))
    use_case = CollectionUseCase(scraper, repository, error_store, clock)

    with pytest.raises(ScraperError):
        use_case.execute(URL, CREDENTIALS)

    assert error_store.saved == []
    assert repository.saved == []
