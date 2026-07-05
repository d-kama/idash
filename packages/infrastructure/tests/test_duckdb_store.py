"""DuckDbAssetRepository は PortfolioAsset を単一 Parquet に保存・取得する（具象）。

ローカルパスを location に注入して httpfs/S3 なしで実 SQL を検証する。型を保持して
保存（base_date=DATE / 金額3列=BIGINT）し、read 時の再パースなしで exact round-trip する。
save は base_date 単位の冪等 upsert（同一日再 save はその日を置換）。
"""

from datetime import date
from pathlib import Path

import pytest

from domain.asset import Money, PortfolioAsset, ProductAsset
from infrastructure.duckdb_store import DuckDbAssetRepository, DuckDbConfig

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


def _make_repo(tmp_path: Path) -> DuckDbAssetRepository:
    location = str(tmp_path / "assets.parquet")
    return DuckDbAssetRepository(DuckDbConfig(location=location))


def test_save_then_find_round_trip_including_negative(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    repo.save(ASSET)
    result = repo.find_by_date_range(date(2026, 6, 18), date(2026, 6, 18))

    assert result == [ASSET]  # 型保持で exact round-trip（負の損益含む）


def test_find_returns_empty_when_file_not_exists(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    # 一度も save していない（parquet 未存在）→ 空。
    assert repo.find_by_date_range(date(2026, 1, 1), date(2026, 12, 31)) == []


def test_save_creates_file_when_not_exists(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    # 初回 save は新行のみで parquet を新規作成する。
    repo.save(ASSET)

    assert repo.find_by_date_range(date(2026, 6, 18), date(2026, 6, 18)) == [ASSET]


def test_save_is_idempotent_per_base_date(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.save(ASSET)

    # 同一 base_date を別の内容で再 save → その日を置換（重複しない）。
    updated = PortfolioAsset(
        base_date=date(2026, 6, 18),
        products=(
            ProductAsset(
                name="ファンドA",
                contribution=Money(110_000),
                profit_loss=Money(25_000),
                valuation=Money(135_000),
            ),
        ),
    )
    repo.save(updated)

    result = repo.find_by_date_range(date(2026, 6, 18), date(2026, 6, 18))
    assert result == [updated]  # 旧2商品は消え、新1商品のみ


def test_save_different_dates_accumulates(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    earlier = PortfolioAsset(
        base_date=date(2026, 6, 16),
        products=(
            ProductAsset(
                name="ファンドA",
                contribution=Money(90_000),
                profit_loss=Money(10_000),
                valuation=Money(100_000),
            ),
        ),
    )

    repo.save(earlier)
    repo.save(ASSET)

    result = repo.find_by_date_range(date(2026, 6, 16), date(2026, 6, 18))
    assert [a.base_date for a in result] == [date(2026, 6, 16), date(2026, 6, 18)]


def test_find_closed_range_includes_boundaries_and_orders_ascending(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    for base in (date(2026, 6, 18), date(2026, 6, 16), date(2026, 6, 17)):  # あえて非昇順
        repo.save(
            PortfolioAsset(
                base_date=base,
                products=(
                    ProductAsset(
                        name="ファンドA",
                        contribution=Money(100_000),
                        profit_loss=Money(0),
                        valuation=Money(100_000),
                    ),
                ),
            )
        )

    # 閉区間 [6/16, 6/17]: 6/18 は除外、昇順で返る。
    result = repo.find_by_date_range(date(2026, 6, 16), date(2026, 6, 17))
    assert [a.base_date for a in result] == [date(2026, 6, 16), date(2026, 6, 17)]


def test_find_groups_multiple_products_under_one_base_date(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.save(ASSET)

    result = repo.find_by_date_range(date(2026, 6, 18), date(2026, 6, 18))

    assert len(result) == 1
    assert [p.name for p in result[0].products] == ["ファンドA", "ファンドB"]


def test_find_preserves_product_save_order_within_base_date(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # 保存順をアルファベット順と逆にして、seq による順序復元を検証する。
    asset = PortfolioAsset(
        base_date=date(2026, 6, 18),
        products=(
            ProductAsset(
                name="Zファンド",
                contribution=Money(1),
                profit_loss=Money(0),
                valuation=Money(1),
            ),
            ProductAsset(
                name="Aファンド",
                contribution=Money(2),
                profit_loss=Money(0),
                valuation=Money(2),
            ),
        ),
    )
    repo.save(asset)

    result = repo.find_by_date_range(date(2026, 6, 18), date(2026, 6, 18))

    assert [p.name for p in result[0].products] == ["Zファンド", "Aファンド"]


def test_find_returns_empty_when_no_row_in_range(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.save(ASSET)

    assert repo.find_by_date_range(date(2026, 1, 1), date(2026, 1, 31)) == []


def test_find_all_returns_empty_when_file_not_exists(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)

    # 一度も save していない（parquet 未存在）→ 空。
    assert repo.find_all() == []


def test_find_all_returns_every_base_date_ascending(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    for base in (date(2026, 6, 18), date(2026, 6, 16), date(2026, 6, 17)):  # あえて非昇順
        repo.save(
            PortfolioAsset(
                base_date=base,
                products=(
                    ProductAsset(
                        name="ファンドA",
                        contribution=Money(100_000),
                        profit_loss=Money(0),
                        valuation=Money(100_000),
                    ),
                ),
            )
        )

    # 全期間を基準日昇順で返す（区間指定なし）。
    result = repo.find_all()
    assert [a.base_date for a in result] == [
        date(2026, 6, 16),
        date(2026, 6, 17),
        date(2026, 6, 18),
    ]


def test_find_all_round_trip_and_preserves_product_order(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    repo.save(ASSET)

    result = repo.find_all()

    assert result == [ASSET]  # 型保持で exact round-trip・商品順維持


@pytest.mark.parametrize("location", ["s3://bucket/assets.parquet", "/tmp/x.parquet"])
def test_is_s3_detection(location: str) -> None:
    repo = DuckDbAssetRepository(DuckDbConfig(location=location))
    assert repo._is_s3 is location.startswith("s3://")


def test_session_settings_applied_and_round_trip(tmp_path: Path) -> None:
    # memory_limit / temp_directory / extension_directory を設定しても round-trip する。
    repo = DuckDbAssetRepository(
        DuckDbConfig(
            location=str(tmp_path / "assets.parquet"),
            memory_limit="256MB",
            temp_directory=str(tmp_path),
            extension_directory=str(tmp_path / "ext"),
        )
    )

    repo.save(ASSET)

    assert repo.find_by_date_range(date(2026, 6, 18), date(2026, 6, 18)) == [ASSET]
