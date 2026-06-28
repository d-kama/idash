#!/usr/bin/env python
"""サマリ通知バッチをローカルで実行する検証ランナー（ライブ依存）。

本番の Lambda ハンドラ（`apps/batch/handler_notify.py`）と同じく
**`NotifySummaryUseCase.execute(days)` を実行する composition root** であり、違いは
「**実行元（Lambda / ローカル）に応じて差し替わるアダプタ群だけ**」。use case 本体・
実行手順は共通。

  役割        | Lambda（handler_notify）   | ローカル（本スクリプト）
  ------------|----------------------------|-------------------------------------
  設定源      | SSM SecureString(1本)      | ローカル JSON（`*.local.json`）
  Repository  | `DuckDbAssetRepository`    | `DuckDbAssetRepository`（実 read・同一）
  Notifier    | `LineNotifier`（実送信）   | `LineNotifier`（`--send` 時のみ実送信／既定 print）
  Clock       | `SystemClock`              | `SystemClock`（同一）
  実行        | `execute(days)`            | `execute(days)`（同一）

本番コードは不変: `LineNotifier(transport=...)` の seam に print transport を注入して
dry-run する（`infrastructure` の公開面は広げない）。

  --dry-run（既定）: LINE へ送らず、送信内容（subject/body）を標準出力に表示する。
  --send           : 実 LINE Messaging API（push）へ送信する。
  --days N         : 集計対象日数（既定 7）。

ローカル JSON（既定 ./notify.local.json, *.local.json は gitignore 済み）の形:
  {
    // データストアの read 元。ローカル Parquet パス（例 "./data.local.parquet"）または
    // "s3://bucket/key.parquet"（実行環境の AWS 認証を使用）。
    "data_location": "./data.local.parquet",
    "line": {                          // --dry-run では未使用。--send 時のみ必要
      "channel_access_token": "...",
      "to": "Uxxxxxxxx..."            // 送信先 userId
    }
  }

実データストア / 実 LINE 依存のため決定的テスト対象外（coverage/test に含めない）。
ruff（lint / format）/ ty（型）だけは通す。

使い方:
  uv run python scripts/run_notify_local.py --dry-run --days 7
  uv run python scripts/run_notify_local.py --send --config ./notify.local.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from application.notification import NotifySummaryUseCase
from infrastructure.clock import SystemClock
from infrastructure.duckdb_store import DuckDbAssetRepository, DuckDbConfig
from infrastructure.notifier import LineConfig, LineNotifier

_DEFAULT_CONFIG = "notify.local.json"
_DEFAULT_DAYS = 7


def _print_transport(url: str, body: bytes, headers: Mapping[str, str]) -> None:
    """--dry-run 用の transport。実送信せず POST 内容を標準出力に表示する。"""
    print(f"[dry-run] POST {url}")
    print(f"[dry-run] headers: {dict(headers)}")
    payload = json.loads(body.decode("utf-8"))
    text = payload["messages"][0]["text"]
    print("[dry-run] message text:")
    print(text)


def _positive_int(value: str) -> int:
    """argparse 用バリデータ。集計対象日数として 1 以上の整数のみ許可する。"""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("--days must be >= 1")
    return parsed


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        sys.exit(
            f"ローカル認証 JSON が見つかりません: {path}\n"
            f"  {_DEFAULT_CONFIG}（または --config 指定）を作成してください。"
            f"形式は本スクリプト冒頭の docstring を参照。"
        )
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def build_use_case(config: dict[str, Any], *, send: bool) -> NotifySummaryUseCase:
    """ローカル composition root: ローカル版アダプタを組み立て use case を返す。

    本番 `handler_notify.build_use_case`（SSM/env → DuckDB / LINE）と対をなす。差し替わるのは
    設定源と Notifier の transport（dry-run では print）だけで、返す
    `NotifySummaryUseCase` と `execute(days)` の実行手順は本番と同一。
    """
    repository = DuckDbAssetRepository(DuckDbConfig(location=config["data_location"]))

    if send:
        line = config["line"]
        notifier = LineNotifier(
            LineConfig(channel_access_token=line["channel_access_token"], to=line["to"])
        )
        print("[send] 実 LINE Messaging API へ送信します")
    else:
        # 実 LINE には送らず print transport を注入（送信先設定は不要）。
        notifier = LineNotifier(
            LineConfig(channel_access_token="(dry-run)", to="(dry-run)"),
            transport=_print_transport,
        )
        print("[dry-run] 実 LINE には送信しません")

    return NotifySummaryUseCase(repository, notifier, SystemClock())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="実 LINE へ送らず送信内容を表示する（既定）",
    )
    mode.add_argument(
        "--send",
        action="store_true",
        help="実 LINE Messaging API（push）へ送信する",
    )
    parser.add_argument(
        "--days",
        type=_positive_int,
        default=_DEFAULT_DAYS,
        help=f"集計対象日数（既定 {_DEFAULT_DAYS}）",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(_DEFAULT_CONFIG),
        help=f"ローカル認証 JSON（既定 {_DEFAULT_CONFIG}）",
    )
    args = parser.parse_args(argv)
    send = args.send  # 明示 --send のときだけ実送信。既定は dry-run。

    config = _load_config(args.config)

    # Lambda 版（handler_notify.handler）と同じく「組み立て → execute」。実行元の違いは
    # build_use_case が注入するアダプタ群だけに閉じている。
    use_case = build_use_case(config, send=send)
    notification = use_case.execute(args.days)

    if notification is None:
        print(f"skipped: 直近 {args.days} 日の資産が 0 件のため送信しませんでした")
    else:
        print(f"完了: subject={notification.subject!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
