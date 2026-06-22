#!/usr/bin/env python
"""データ収集バッチをローカルで実行する検証ランナー（ライブ依存）。

issue-8-container フェーズ5.1（実サイト検証）の支援ツール。本番の Lambda ハンドラ
（`apps/batch/handler_collect.py`）と同じく **`CollectionUseCase.execute` を実行する
composition root** であり、違いは「**実行元（Lambda / ローカル）に応じて差し替わる
アダプタ群だけ**」。use case 本体・実行手順は共通。

  役割           | Lambda（handler_collect）       | ローカル（本スクリプト）
  ---------------|---------------------------------|-------------------------------------
  設定源         | SSM SecureString(2本)           | ローカル JSON（`*.local.json`）
  Scraper driver | `_default_chrome_factory`(版ピン)| `webdriver.Remote`（standalone-chrome）
  Repository     | `SheetsAssetRepository`         | `_PrintAssetRepository`（`--write` で Sheets）
  ErrorPageStore | `S3ErrorPageStore`              | `_LocalFileErrorPageStore`（ローカル .html）
  Clock          | `SystemClock`                   | `SystemClock`（同一）
  実行           | `CollectionUseCase.execute`     | `CollectionUseCase.execute`（同一）

本番コードは不変: `SeleniumScraper(driver_factory=...)` の seam に Remote ファクトリを
注入し、ErrorPageStore / Repository をローカル版へ差し替えるだけ（`infrastructure` の
公開面は広げない）。

  --dry-run（既定）: Repository を print 専用 fake に差し替え、実 Sheets を汚さず
                     抽出結果を目視確認する。
  --write          : 実 Google Spreadsheet へ append する。

前提（別ターミナルで standalone-chrome を起動しておく）:
  docker run --rm -p 4444:4444 -p 7900:7900 selenium/standalone-chrome:4.27.0
  # noVNC（http://localhost:7900, password=secret）で headed ブラウザを目視できる。

ローカル JSON（既定 ./collect.local.json, *.local.json は gitignore 済み）の形:
  {
    "source": {
      "start_url": "https://...",
      "user_agent": "Mozilla/5.0 ...",
      "user_id": "...",
      "password": "...",
      "birthdate": "1990-01-23"
    },
    "sheets": {                       // --dry-run では未使用。--write 時のみ必要
      "spreadsheet_id": "...",
      "sheet_name": "...",
      "credentials": { ... service account JSON ... }
    }
  }

セレクタ不一致時は `CollectionUseCase` が失敗時点のページを `_LocalFileErrorPageStore`
経由で `./errorpages/` に書き出す（`extract_portfolio` の境界チェックが投げる `ValueError`
→ `scrape()` が `ScraperError(content=page_source)` に包む経路）。その HTML を開いて DOM を
確認しながら `infrastructure/scraper.py` の抽出マッピングを調整する。

実サイト・実コンテナ依存のため決定的テスト対象外（coverage/test に含めない）。
ruff（lint / format）/ ty（型）だけは通す。

使い方:
  uv run python scripts/run_collect_local.py --dry-run
  uv run python scripts/run_collect_local.py --write --config ./collect.local.json
  uv run python scripts/run_collect_local.py --remote-url http://localhost:4444
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from application.collection import CollectionUseCase
from domain.asset import AssetRepository, PortfolioAsset
from domain.collection import Credentials, ErrorPage
from infrastructure.clock import SystemClock
from infrastructure.scraper import ScraperConfig, SeleniumScraper
from infrastructure.sheets import SheetsAssetRepository, SheetsConfig

_DEFAULT_CONFIG = "collect.local.json"
_DEFAULT_REMOTE_URL = "http://localhost:4444"
_DEFAULT_ERROR_DIR = "errorpages"


class _PrintAssetRepository:
    """--dry-run 用の AssetRepository。保存せず内容を標準出力に表示するだけ。"""

    def save(self, asset: PortfolioAsset) -> None:
        print(f"[dry-run] base_date={asset.base_date.isoformat()} products={len(asset.products)}")
        for product in asset.products:
            print(
                f"  - {product.name}: "
                f"contribution={product.contribution.yen} "
                f"valuation={product.valuation.yen} "
                f"profit_loss={product.profit_loss.yen}"
            )

    def find_by_date_range(self, from_date: date, to_date: date) -> Sequence[PortfolioAsset]:
        # 収集（dry-run）専用。read 系は使わない。
        raise NotImplementedError


class _LocalFileErrorPageStore:
    """ErrorPageStore のローカル版。失敗時点のページを `./errorpages/` 配下へ書く。

    本番 `S3ErrorPageStore` の代替。content が None でもマーカーを書き、保存先パスを
    標準出力に示す（セレクタ調整時に実 HTML を開いて DOM を確認するため）。
    """

    _MARKER_BODY = "error page content was not captured"

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def save(self, page: ErrorPage) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        # 本番 S3 key スキーム collect/YYYY/MM/DDThhmmss.html をローカルでは flat な
        # 1 ファイル名へ落とす。
        path = self._dir / f"collect-{page.captured_at:%Y%m%dT%H%M%S}.html"
        body = self._MARKER_BODY if page.content is None else page.content
        path.write_text(body, encoding="utf-8")
        print(f"[error-page] 失敗時のページを保存しました: {path}")


def _make_remote_driver_factory(remote_url: str) -> Any:
    """standalone-chrome へ `webdriver.Remote` 接続するファクトリを返す。

    本番 `_default_chrome_factory`（版ピン chrome をローカルプロセス起動）の代わりに
    `SeleniumScraper(driver_factory=...)` へ注入する。`ScraperConfig.user_agent` /
    `implicit_wait` は本番 seam と同じく尊重する（`chrome_binary_location` /
    `chrome_driver_path` は Remote では不要なので無視）。
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    def factory(config: ScraperConfig) -> Any:
        options = Options()
        options.add_argument(f"--user-agent={config.user_agent}")
        options.add_argument("--window-size=1280,1696")
        driver = webdriver.Remote(command_executor=remote_url, options=options)
        driver.implicitly_wait(config.implicit_wait)
        return driver

    return factory


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        sys.exit(
            f"ローカル認証 JSON が見つかりません: {path}\n"
            f"  {_DEFAULT_CONFIG}（または --config 指定）を作成してください。"
            f"形式は本スクリプト冒頭の docstring を参照。"
        )
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _build_credentials(source: dict[str, Any]) -> Credentials:
    return Credentials(
        user_id=source["user_id"],
        password=source["password"],
        birthdate=date.fromisoformat(source["birthdate"]),
    )


def build_use_case(
    config: dict[str, Any],
    *,
    remote_url: str,
    write: bool,
    error_dir: Path,
) -> tuple[CollectionUseCase, str, Credentials]:
    """ローカル composition root: ローカル版アダプタを組み立て use case と実行引数を返す。

    本番 `handler_collect.build_use_case`（SSM → 版ピン chrome / Sheets / S3）と対をなす。
    差し替わるのはアダプタ（driver / repository / error store / 設定源）だけで、返す
    `CollectionUseCase` と `execute(url, credentials)` の実行手順は本番と同一。
    """
    source = config["source"]

    scraper = SeleniumScraper(
        ScraperConfig(
            user_agent=source["user_agent"],
            # Remote 接続では未使用だが ScraperConfig の必須フィールドを満たす。
            chrome_binary_location="(remote)",
            chrome_driver_path="(remote)",
        ),
        driver_factory=_make_remote_driver_factory(remote_url),
    )

    repository: AssetRepository
    if write:
        sheets = config["sheets"]
        repository = SheetsAssetRepository(
            SheetsConfig(
                spreadsheet_id=sheets["spreadsheet_id"],
                sheet_name=sheets["sheet_name"],
                credentials=sheets["credentials"],
            )
        )
        print("[write] 実 Google Spreadsheet へ append します")
    else:
        repository = _PrintAssetRepository()
        print("[dry-run] 実 Sheets には書き込みません")

    use_case = CollectionUseCase(
        scraper,
        repository,
        _LocalFileErrorPageStore(error_dir),
        SystemClock(),
    )
    credentials = _build_credentials(source)
    return use_case, source["start_url"], credentials


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="実 Sheets を汚さず print 専用リポジトリで結果を表示（既定）",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="実 Google Spreadsheet へ append する",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(_DEFAULT_CONFIG),
        help=f"ローカル認証 JSON（既定 {_DEFAULT_CONFIG}）",
    )
    parser.add_argument(
        "--remote-url",
        default=_DEFAULT_REMOTE_URL,
        help=f"standalone-chrome の WebDriver エンドポイント（既定 {_DEFAULT_REMOTE_URL}）",
    )
    parser.add_argument(
        "--error-dir",
        type=Path,
        default=Path(_DEFAULT_ERROR_DIR),
        help=f"失敗時のページ保存先ディレクトリ（既定 ./{_DEFAULT_ERROR_DIR}/）",
    )
    args = parser.parse_args(argv)
    write = args.write  # 明示 --write のときだけ実書き込み。既定は dry-run。

    config = _load_config(args.config)

    # Lambda 版（handler_collect.handler）と同じく「組み立て → execute」。実行元の違いは
    # build_use_case が注入するアダプタ群だけに閉じている。
    use_case, url, credentials = build_use_case(
        config,
        remote_url=args.remote_url,
        write=write,
        error_dir=args.error_dir,
    )
    asset = use_case.execute(url, credentials)

    print(f"完了: base_date={asset.base_date.isoformat()} products={len(asset.products)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
