"""Notifier ポートの具象（LINE Messaging API）。

整形済み Notification を LINE Messaging API の push エンドポイントへ1通の text
メッセージとして送る。LINE Notify は 2025-03-31 に終了したため、後継の Messaging
API（push: 自分の userId 宛）を採用する。

新規サードパーティ依存は持ち込まず stdlib `urllib.request` で POST する。HTTP 実行は
`transport` シームで注入できるようにし、テストはネットワーク非依存にする。非2xx は
`urllib.request.urlopen` が送出する `HTTPError` がそのまま伝播し、Lambda 失敗扱い
（リトライ / 検知）に委ねる。
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from domain.notification import Notification

# (url, body, headers) -> None。POST を実行する副作用シーム。既定は urllib、テストでは
# 記録用 fake を注入する。
Transport = Callable[[str, bytes, Mapping[str, str]], None]


def _default_transport(url: str, body: bytes, headers: Mapping[str, str]) -> None:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    # 非2xx は urlopen が HTTPError を送出 → 呼び出し元へ伝播させる（捕捉しない）。
    with urllib.request.urlopen(request):  # noqa: S310  url は固定の LINE API エンドポイント
        pass


@dataclass(frozen=True)
class LineConfig:
    """LINE Messaging API の認証情報と送信先。"""

    channel_access_token: str
    to: str  # 送信先 userId（push）
    api_url: str = "https://api.line.me/v2/bot/message/push"


class LineNotifier:
    """Notification を LINE Messaging API の push へ送る Notifier 具象。"""

    def __init__(
        self,
        config: LineConfig,
        *,
        transport: Transport = _default_transport,
    ) -> None:
        self._config = config
        self._transport = transport

    def send(self, notification: Notification) -> None:
        # subject と body を空行区切りで1通の text にまとめる（LINE text 上限 5000 文字。
        # render_summary の出力は十分小さい）。
        text = f"{notification.subject}\n\n{notification.body}"
        payload = {
            "to": self._config.to,
            "messages": [{"type": "text", "text": text}],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._config.channel_access_token}",
            "Content-Type": "application/json",
        }
        self._transport(self._config.api_url, body, headers)
