"""SystemClock は JST aware な現在時刻を返す（Clock ポートの具象）。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from infrastructure.clock import SystemClock


def test_now_is_jst_aware() -> None:
    now = SystemClock().now()

    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.utcoffset() == ZoneInfo("Asia/Tokyo").utcoffset(now)
