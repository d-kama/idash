"""AssetRepository ポートの具象（DuckDB + 単一 Parquet）。

PortfolioAsset を商品ごと1行で単一 Parquet に保存する。型を保持して保存し
（base_date=DATE / 金額3列=BIGINT）、read 時の再パースを不要にして exact round-trip する。

Parquet はイミュータブルなため `save` は read-modify-write になる。既存を読み、当該
base_date の行を除外して新行と結合した全件を書き戻す（= base_date 単位の冪等 upsert）。
同一日に複数回走らせてもその日が置換されるだけで重複しない。

location は `s3://bucket/key` でもローカルパスでもよい。`s3://` の場合のみ httpfs / aws
拡張を LOAD し、`CREATE SECRET (TYPE s3, PROVIDER credential_chain)` で実行ロール認証を
使う（静的キーを持たない）。拡張は Lambda イメージへ事前同梱する前提（実行時 DL なし）。
テストはローカルパスを注入し、httpfs/S3 なしで実 SQL を検証する。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import duckdb

from domain.asset import Money, PortfolioAsset, ProductAsset

# read で返す商品列（base_date は外側のグルーピングキー）。`seq` は保存順の復元用で
# 値としては返さず ORDER BY にのみ使う。
_PRODUCT_COLUMNS = ("name", "contribution", "profit_loss", "valuation")


@dataclass(frozen=True)
class DuckDbConfig:
    """保存先 location と DuckDB セッション設定。

    location は `s3://bucket/key.parquet` またはローカルパス。memory_limit /
    temp_directory は None なら設定しない（既定に委ねる）。Lambda では肥大時の
    スピルに備えて handler が `temp_directory='/tmp'` 等を渡す。

    extension_directory は httpfs/aws 拡張の所在。Lambda ではビルド時に固定ディレクトリへ
    事前 INSTALL した拡張を実行時 LOAD だけで使うため、その同一ディレクトリを handler が
    渡す（HOME 差異による解決失敗を避ける）。None なら DuckDB 既定（`~/.duckdb`）。
    """

    location: str
    memory_limit: str | None = None
    temp_directory: str | None = None
    extension_directory: str | None = None


class DuckDbAssetRepository:
    """PortfolioAsset を単一 Parquet に保存・取得する AssetRepository。"""

    def __init__(self, config: DuckDbConfig) -> None:
        self._config = config
        self._is_s3 = config.location.startswith("s3://")

    def _connect(self) -> duckdb.DuckDBPyConnection:
        # 1 操作 = 1 接続（in-memory connect は安価で、温起動間の TEMP 表汚染も避けられる）。
        con = duckdb.connect()
        if self._config.memory_limit is not None:
            con.execute(f"SET memory_limit = '{self._config.memory_limit}'")
        if self._config.temp_directory is not None:
            con.execute(f"SET temp_directory = '{self._config.temp_directory}'")
        if self._config.extension_directory is not None:
            # 事前 INSTALL したディレクトリを LOAD の解決先に固定する（INSTALL より前に設定）。
            con.execute(f"SET extension_directory = '{self._config.extension_directory}'")
        if self._is_s3:
            # 事前同梱済み拡張を LOAD のみ（ネット DL なし）。credential_chain は aws 拡張が提供。
            con.execute("LOAD httpfs")
            con.execute("LOAD aws")
            con.execute("CREATE SECRET (TYPE s3, PROVIDER credential_chain)")
        return con

    def _exists(self, con: duckdb.DuckDBPyConnection) -> bool:
        # glob はローカル/S3 を統一的に扱える。未存在なら 0 件。
        row = con.execute(f"SELECT count(*) FROM glob({self._quoted_location})").fetchone()
        return row is not None and row[0] > 0

    @property
    def _quoted_location(self) -> str:
        # 自前 config 値を SQL リテラルへ。単一引用符は二重化してエスケープする。
        escaped = self._config.location.replace("'", "''")
        return f"'{escaped}'"

    def save(self, asset: PortfolioAsset) -> None:
        con = self._connect()
        try:
            # `seq` は商品の保存順（read の ORDER BY で順序を確実に復元するため）。
            con.execute(
                "CREATE TEMP TABLE new_rows "
                "(base_date DATE, name VARCHAR, contribution BIGINT, "
                "profit_loss BIGINT, valuation BIGINT, seq INTEGER)"
            )
            con.executemany(
                "INSERT INTO new_rows VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        asset.base_date,
                        product.name,
                        product.contribution.yen,
                        product.profit_loss.yen,
                        product.valuation.yen,
                        seq,
                    )
                    for seq, product in enumerate(asset.products)
                ],
            )

            # 既存を TEMP 表へ materialize してから書き戻す（同一パスの read-while-write を回避）。
            # 当該 base_date の既存行を除外し新行と結合する = base_date 単位の冪等 upsert。
            if self._exists(con):
                con.execute(
                    f"CREATE TEMP TABLE merged AS "  # noqa: S608 -- location は自前 config（引用符エスケープ済み）
                    f"SELECT * FROM read_parquet({self._quoted_location}) WHERE base_date <> ? "
                    f"UNION ALL SELECT * FROM new_rows",
                    [asset.base_date],
                )
            else:
                con.execute("CREATE TEMP TABLE merged AS SELECT * FROM new_rows")

            con.execute(f"COPY merged TO {self._quoted_location} (FORMAT parquet)")
        finally:
            con.close()

    def find_by_date_range(self, from_date: date, to_date: date) -> Sequence[PortfolioAsset]:
        con = self._connect()
        try:
            if not self._exists(con):
                return []

            # seq で保存順を復元（同一 base_date 内の商品順を安定化）。
            rows = con.execute(
                f"SELECT base_date, {', '.join(_PRODUCT_COLUMNS)} "  # noqa: S608
                f"FROM read_parquet({self._quoted_location}) "
                f"WHERE base_date BETWEEN ? AND ? ORDER BY base_date, seq",
                [from_date, to_date],
            ).fetchall()
        finally:
            con.close()

        # 基準日でグルーピング（SELECT は base_date 昇順 / dict は挿入順を保持）。
        products_by_date: dict[date, list[ProductAsset]] = {}
        for base_date, name, contribution, profit_loss, valuation in rows:
            products_by_date.setdefault(base_date, []).append(
                ProductAsset(
                    name=name,
                    contribution=Money(contribution),
                    profit_loss=Money(profit_loss),
                    valuation=Money(valuation),
                )
            )
        return [
            PortfolioAsset(base_date=base_date, products=tuple(products))
            for base_date, products in products_by_date.items()
        ]
