"""LineNotifier は Notification を LINE Messaging API push へ POST する（Notifier 具象）。

HTTP 実行は transport シームで注入し、ネットワーク非依存に検証する。url / Bearer /
Content-Type / body JSON（to・messages・text）を確認し、非2xx 相当の例外伝播も見る。
"""

import json
from collections.abc import Mapping

import pytest

from domain.notification import Notification
from infrastructure.notifier import LineConfig, LineNotifier

CONFIG = LineConfig(channel_access_token="token-abc", to="Uxxxxxxxx")

NOTIFICATION = Notification(subject="件名", body="本文1行目\n本文2行目")


class _RecordingTransport:
    def __init__(self) -> None:
        self.url: str | None = None
        self.body: bytes | None = None
        self.headers: Mapping[str, str] | None = None

    def __call__(self, url: str, body: bytes, headers: Mapping[str, str]) -> None:
        self.url = url
        self.body = body
        self.headers = headers


def test_posts_to_push_endpoint_with_bearer_and_json_content_type() -> None:
    transport = _RecordingTransport()
    notifier = LineNotifier(CONFIG, transport=transport)

    notifier.send(NOTIFICATION)

    assert transport.url == "https://api.line.me/v2/bot/message/push"
    assert transport.headers is not None
    assert transport.headers["Authorization"] == "Bearer token-abc"
    assert transport.headers["Content-Type"] == "application/json"


def test_body_carries_to_and_single_text_message() -> None:
    transport = _RecordingTransport()
    notifier = LineNotifier(CONFIG, transport=transport)

    notifier.send(NOTIFICATION)

    assert transport.body is not None
    payload = json.loads(transport.body.decode("utf-8"))
    assert payload["to"] == "Uxxxxxxxx"
    assert len(payload["messages"]) == 1
    message = payload["messages"][0]
    assert message["type"] == "text"
    # subject と body を空行区切りで1通にまとめる。
    assert message["text"] == "件名\n\n本文1行目\n本文2行目"


def test_propagates_transport_error() -> None:
    def failing_transport(url: str, body: bytes, headers: Mapping[str, str]) -> None:
        # 非2xx で urlopen が送出する HTTPError を模す（捕捉せず伝播する契約）。
        raise RuntimeError("non-2xx")

    notifier = LineNotifier(CONFIG, transport=failing_transport)

    with pytest.raises(RuntimeError, match="non-2xx"):
        notifier.send(NOTIFICATION)
