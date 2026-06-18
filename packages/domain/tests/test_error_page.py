"""ErrorPage.captured() の純粋性を検証する。

captured() は時計を呼ばず、注入された時刻 `at` をそのまま使う（決定論的）。
"""

from datetime import datetime

from domain.collection import ErrorPage


def test_captured_uses_injected_time() -> None:
    at = datetime(2026, 6, 18, 9, 0, 0)

    page = ErrorPage.captured(url="https://example/error", content="<html>boom</html>", at=at)

    assert page == ErrorPage(
        url="https://example/error",
        captured_at=at,
        content="<html>boom</html>",
    )


def test_captured_allows_none_content() -> None:
    at = datetime(2026, 6, 18, 9, 0, 0)

    page = ErrorPage.captured(url="https://example/error", content=None, at=at)

    assert page.content is None
    assert page.captured_at == at
