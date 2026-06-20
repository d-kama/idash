"""Clock ポートの具象（システム時計）。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_JST = ZoneInfo("Asia/Tokyo")


class SystemClock:
    """JST aware な現在時刻を返す Clock。"""

    def now(self) -> datetime:
        return datetime.now(_JST)
