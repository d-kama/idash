"""AssetRepository ポートの具象（Google Spreadsheet, gspread）。

PortfolioAsset を商品ごと1行に展開して worksheet へ append する。金額は円整数
（`Money.yen`）を数値のまま保存する（表示整形はしない）。シートのヘッダ・存在は
既存前提で、初期化はしない（append のみ）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import gspread
from gspread import Client, Worksheet
from gspread.utils import ValueInputOption

from domain.asset import PortfolioAsset

# credentials(SA JSON) を受け取り gspread クライアントを返すファクトリ。
# テストではダミークライアントを `cast(Client, ...)` で注入する（注入点でのみ回避）。
ClientFactory = Callable[[dict[str, Any]], Client]


@dataclass(frozen=True)
class SheetsConfig:
    """保存先スプレッドシートと認証情報。"""

    spreadsheet_id: str
    sheet_name: str
    credentials: dict[str, Any]


class SheetsAssetRepository:
    """PortfolioAsset を Google Spreadsheet に append する AssetRepository。"""

    def __init__(
        self,
        config: SheetsConfig,
        *,
        client_factory: ClientFactory = gspread.service_account_from_dict,
    ) -> None:
        self._config = config
        self._client_factory = client_factory
        self._worksheet: Worksheet | None = None

    def _worksheet_handle(self) -> Worksheet:
        # 認証・シート解決はコールドスタート時のみ（取得結果をキャッシュ）。
        if self._worksheet is None:
            client = self._client_factory(self._config.credentials)
            spreadsheet = client.open_by_key(self._config.spreadsheet_id)
            self._worksheet = spreadsheet.worksheet(self._config.sheet_name)
        return self._worksheet

    def save(self, asset: PortfolioAsset) -> None:
        rows = [
            [
                asset.base_date.isoformat(),
                product.name,
                product.contribution.yen,
                product.profit_loss.yen,
                product.valuation.yen,
            ]
            for product in asset.products
        ]
        self._worksheet_handle().append_rows(rows, value_input_option=ValueInputOption.raw)
