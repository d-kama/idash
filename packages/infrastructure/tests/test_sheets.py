"""SheetsAssetRepository は商品ごと1行を円整数で append する（AssetRepository の具象）。"""

from datetime import date

from domain.asset import Money, PortfolioAsset, ProductAsset
from infrastructure.sheets import SheetsAssetRepository, SheetsConfig

CONFIG = SheetsConfig(
    spreadsheet_id="sheet-key-123",
    sheet_name="assets",
    credentials={"type": "service_account", "client_email": "x@y.iam"},
)

ASSET = PortfolioAsset(
    base_date=date(2026, 6, 18),
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
            profit_loss=Money(-8_000),  # 評価損益は負もありうる
            valuation=Money(42_000),
        ),
    ),
)


class _FakeWorksheet:
    def __init__(self) -> None:
        self.appended: list[list[list[object]]] = []

    def append_rows(self, rows: list[list[object]], **kwargs: object) -> None:
        self.appended.append(rows)


class _FakeSpreadsheet:
    def __init__(self, worksheet: _FakeWorksheet) -> None:
        self._worksheet = worksheet
        self.requested_sheet: str | None = None

    def worksheet(self, name: str) -> _FakeWorksheet:
        self.requested_sheet = name
        return self._worksheet


class _FakeClient:
    def __init__(self, spreadsheet: _FakeSpreadsheet) -> None:
        self._spreadsheet = spreadsheet
        self.opened_key: str | None = None

    def open_by_key(self, key: str) -> _FakeSpreadsheet:
        self.opened_key = key
        return self._spreadsheet


def _make_repo() -> tuple[SheetsAssetRepository, _FakeClient, _FakeWorksheet, dict[str, object]]:
    worksheet = _FakeWorksheet()
    spreadsheet = _FakeSpreadsheet(worksheet)
    client = _FakeClient(spreadsheet)
    captured: dict[str, object] = {}

    def factory(credentials: dict[str, object]) -> _FakeClient:
        captured["credentials"] = credentials
        return client

    repo = SheetsAssetRepository(CONFIG, client_factory=factory)
    return repo, client, worksheet, captured


def test_save_appends_one_row_per_product_with_integer_yen() -> None:
    repo, client, worksheet, _ = _make_repo()

    repo.save(ASSET)

    assert client.opened_key == "sheet-key-123"
    assert worksheet.appended == [
        [
            ["2026-06-18", "ファンドA", 100_000, 20_000, 120_000],
            ["2026-06-18", "ファンドB", 50_000, -8_000, 42_000],
        ]
    ]
    # 金額は int（数値）で保存される
    appended_row = worksheet.appended[0][0]
    assert all(isinstance(appended_row[i], int) for i in (2, 3, 4))


def test_save_uses_configured_credentials_and_sheet() -> None:
    repo, client, _, captured = _make_repo()

    repo.save(ASSET)

    assert captured["credentials"] == CONFIG.credentials
    assert client._spreadsheet.requested_sheet == "assets"
