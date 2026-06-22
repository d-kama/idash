"""収集サブドメイン（Collection）。

外部 DC 年金サイトへの接続・ログイン・取得に関わるポートと値オブジェクト・例外。
domain 層の純粋性を保つため pydantic 等は用いず stdlib のみで構成する。
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from domain.asset import PortfolioAsset


@dataclass(frozen=True, repr=False)
class Credentials:
    """外部 DC 年金サイトへのログインに必要な認証情報。

    `__repr__` を上書きして全フィールドをマスクする。`__str__` / f-string は既定で
    `__repr__` にフォールバックするため、ログ・例外・文字列化のいずれの経路でも
    値が露出しない。値そのものは属性アクセスで取得できる。
    """

    user_id: str
    password: str
    birthdate: date

    def __repr__(self) -> str:
        return "Credentials(user_id=***, password=***, birthdate=***)"


@dataclass(frozen=True)
class ErrorPage:
    """スクレイピング失敗時点で捕捉したエラーページ（HTML 等の証跡）。

    content は失敗時点のページ本文。取得できなければ None。
    """

    url: str
    captured_at: datetime
    content: str | None

    @classmethod
    def captured(cls, *, url: str, content: str | None, at: datetime) -> ErrorPage:
        """注入された時刻 `at` で ErrorPage を組み立てる（時計を呼ばない純粋な生成）。"""
        return cls(url=url, captured_at=at, content=content)


class ScraperError(Exception):
    """スクレイピング中の失敗。失敗時点のページ本文を content に保持する（取れなければ None）。"""

    def __init__(self, message: str, *, content: str | None = None) -> None:
        super().__init__(message)
        self.content = content


class ScraperSession(Protocol):
    """ログイン済みの取得コンテキスト。"""

    def scrape(self) -> PortfolioAsset: ...


class Scraper(Protocol):
    """外部 DC 年金サイトへ接続・ログインし、セッションを通じて取得するポート。

    `session()` はコンテキストマネージャ方式のセッションを返す（ADR-0002）。`with`
    ブロックを抜ける際にログアウト・クローズの後始末が確実化される。
    """

    def session(
        self, url: str, credentials: Credentials
    ) -> AbstractContextManager[ScraperSession]: ...


class ErrorPageStore(Protocol):
    """ErrorPage を保存するポート。"""

    def save(self, page: ErrorPage) -> None: ...
