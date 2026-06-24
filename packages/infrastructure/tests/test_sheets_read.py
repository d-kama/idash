"""SheetsAssetRepository.find_by_date_range は行を PortfolioAsset へ再構成する（read 経路）。

save が `ValueInputOption.raw` で保存した生整数（列順 base_date/name/contribution/
profit_loss/valuation）を round-trip で復元する。ヘッダ/空行はスキップし、基準日が
閉区間に含まれる行のみを基準日昇順で返す。
"""

from datetime import date
from typing import cast

from gspread import Client

from domain.asset import Money, PortfolioAsset, ProductAsset
from infrastructure.sheets import SheetsAssetRepository, SheetsConfig

CONFIG = SheetsConfig(
    spreadsheet_id="sheet-key-123",
    sheet_name="assets",
    credentials={"type": "service_account", "client_email": "x@y.iam"},
)


class _FakeWorksheet:
    def __init__(self, values: list[list[object]]) -> None:
        self._values = values
        self.appended: list[list[list[object]]] = []

    def get_all_values(self) -> list[list[object]]:
        return self._values

    def append_rows(self, rows: list[list[object]], **kwargs: object) -> None:
        self.appended.append(rows)


class _FakeSpreadsheet:
    def __init__(self, worksheet: _FakeWorksheet) -> None:
        self._worksheet = worksheet

    def worksheet(self, name: str) -> _FakeWorksheet:
        return self._worksheet


class _FakeClient:
    def __init__(self, spreadsheet: _FakeSpreadsheet) -> None:
        self._spreadsheet = spreadsheet

    def open_by_key(self, key: str) -> _FakeSpreadsheet:
        return self._spreadsheet


def _make_repo(values: list[list[object]]) -> SheetsAssetRepository:
    worksheet = _FakeWorksheet(values)
    client = _FakeClient(_FakeSpreadsheet(worksheet))

    def factory(credentials: dict[str, object]) -> Client:
        return cast(Client, client)

    return SheetsAssetRepository(CONFIG, client_factory=factory)


# save の出力形式に倣ったシート行（col1=base_date, name, 3列の生整数）。
ROWS: list[list[object]] = [
    ["base_date", "name", "contribution", "profit_loss", "valuation"],  # ヘッダ
    [],  # 空行
    ["2026-06-16", "ファンドA", "100000", "20000", "120000"],
    ["2026-06-16", "ファンドB", "50000", "-8000", "42000"],  # 同一基準日・別商品 / 負の損益
    ["2026-06-18", "ファンドA", "101000", "21000", "122000"],
    ["2026-06-20", "ファンドA", "102000", "22000", "124000"],  # 区間外（後で除外確認）
]


def test_skips_header_and_blank_rows_and_filters_closed_range() -> None:
    repo = _make_repo(ROWS)

    result = repo.find_by_date_range(date(2026, 6, 16), date(2026, 6, 18))

    # ヘッダ・空行はスキップ、2026-06-20 は閉区間外で除外 → 基準日2件。
    assert [a.base_date for a in result] == [date(2026, 6, 16), date(2026, 6, 18)]


def test_closed_range_includes_boundaries() -> None:
    repo = _make_repo(ROWS)

    # from/to を基準日にちょうど一致させると境界が含まれる（閉区間）。
    result = repo.find_by_date_range(date(2026, 6, 18), date(2026, 6, 18))

    assert [a.base_date for a in result] == [date(2026, 6, 18)]


def test_money_round_trip_including_negative() -> None:
    repo = _make_repo(ROWS)

    result = repo.find_by_date_range(date(2026, 6, 16), date(2026, 6, 16))

    assert result == [
        PortfolioAsset(
            base_date=date(2026, 6, 16),
            products=(
                ProductAsset(
                    name="ファンドA",
                    contribution=Money(100_000),
                    profit_loss=Money(20_000),
                    valuation=Money(120_000),
                ),
                ProductAsset(
                    name="ファンドB",
                    contribution=Money(50_000),
                    profit_loss=Money(-8_000),  # 負の損益も exact round-trip
                    valuation=Money(42_000),
                ),
            ),
        )
    ]


def test_groups_multiple_products_under_one_base_date() -> None:
    repo = _make_repo(ROWS)

    result = repo.find_by_date_range(date(2026, 6, 16), date(2026, 6, 16))

    assert len(result) == 1
    assert [p.name for p in result[0].products] == ["ファンドA", "ファンドB"]


def test_returns_assets_in_ascending_base_date_order() -> None:
    # 入力をあえて降順にしても昇順で返す。
    unsorted_rows: list[list[object]] = [
        ["2026-06-18", "ファンドA", "101000", "21000", "122000"],
        ["2026-06-16", "ファンドA", "100000", "20000", "120000"],
        ["2026-06-17", "ファンドA", "100500", "20500", "121000"],
    ]
    repo = _make_repo(unsorted_rows)

    result = repo.find_by_date_range(date(2026, 6, 16), date(2026, 6, 18))

    assert [a.base_date for a in result] == [
        date(2026, 6, 16),
        date(2026, 6, 17),
        date(2026, 6, 18),
    ]


def test_returns_empty_when_no_row_in_range() -> None:
    repo = _make_repo(ROWS)

    result = repo.find_by_date_range(date(2026, 1, 1), date(2026, 1, 31))

    assert result == []


def test_save_then_find_round_trip() -> None:
    # save の出力（append_rows）を get_all_values が返すと仮定した round-trip。
    worksheet = _FakeWorksheet([])
    client = _FakeClient(_FakeSpreadsheet(worksheet))

    def factory(credentials: dict[str, object]) -> Client:
        return cast(Client, client)

    repo = SheetsAssetRepository(CONFIG, client_factory=factory)
    asset = PortfolioAsset(
        base_date=date(2026, 6, 18),
        products=(
            ProductAsset(
                name="ファンドA",
                contribution=Money(100_000),
                profit_loss=Money(-5_000),
                valuation=Money(95_000),
            ),
        ),
    )
    repo.save(asset)
    # append された行を get_all_values の戻りへ反映（実シートの追記を模す）。
    worksheet._values = [list(row) for row in worksheet.appended[0]]

    result = repo.find_by_date_range(date(2026, 6, 18), date(2026, 6, 18))

    assert result == [asset]
