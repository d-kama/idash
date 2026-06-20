"""logging は JSON 構造化ログを出し、get_logger は冪等にロガーを構成する。"""

import json
import logging

from common.logging import JsonFormatter, get_logger


def test_json_formatter_emits_structured_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="collect",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="status=%s",
        args=("ok",),
        exc_info=None,
    )

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "collect"
    assert payload["message"] == "status=ok"
    assert "time" in payload


def test_json_formatter_keeps_non_ascii() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="collect",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="資産収集を開始",
        args=None,
        exc_info=None,
    )

    assert "資産収集を開始" in formatter.format(record)


def test_get_logger_is_idempotent_and_uses_json_formatter() -> None:
    first = get_logger("idash.test")
    second = get_logger("idash.test")

    assert first is second
    assert len(first.handlers) == 1  # 二重に handler を付けない
    assert isinstance(first.handlers[0].formatter, JsonFormatter)
    assert first.propagate is False
