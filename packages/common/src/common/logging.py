"""stdlib logging ベースの JSON 構造化ログ。

CloudWatch Logs で構造化ログとして扱えるよう、1 レコード = 1 行 JSON で出力する。
追加依存は持たない（stdlib のみ）。日本語メッセージを保つため `ensure_ascii=False`。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """LogRecord を 1 行 JSON に整形するフォーマッタ。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str, *, level: int = logging.INFO) -> logging.Logger:
    """JSON フォーマッタ付きのロガーを返す。多重 handler を避けるため冪等。"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger
