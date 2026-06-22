"""現在時刻を供給する汎用の技術ポート（Clock）。

収集・通知・将来の BFF が共有する。domain 層の純粋性を保つため stdlib のみで構成する。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """現在時刻を供給する汎用の技術ポート（収集・通知・将来の BFF が共有）。"""

    def now(self) -> datetime: ...
