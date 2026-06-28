#!/usr/bin/env python
"""Sheets エクスポート CSV を データストア用 Parquet へ変換する使い捨てスクリプト。

データストア移行（Sheets → DuckDB+S3 単一 Parquet, issue #23）の一回限りの手順。
役割分担は以下で、本スクリプトは **②（CSV → ローカル Parquet 変換）だけ** を担う。

  ① ユーザー : Google Sheets を CSV エクスポートし、所定位置へ配置する
  ② 本script : CSV を読み、DuckDbAssetRepository のスキーマで Parquet を生成する
  ③ ユーザー : 生成した Parquet を S3（DATA_LOCATION）へ `aws s3 cp` 等でアップロードする

Sheets / gspread / SSM / S3 には一切触れない（ネット非依存・ローカル完結）。生成は
テスト済みの `DuckDbAssetRepository.save()` を再利用するため、本番 read 経路と Parquet
スキーマ（base_date / name / 金額3列 / seq）が必ず一致する。

CSV フォーマットの前提（SheetsAssetRepository の保存形式に対応）:
  - 列順: base_date, name, contribution, profit_loss, valuation の 5 列固定。
  - base_date は ISO 形式（例 2026-06-16）。金額3列は円整数（生整数。例 100000 / -8000）。
  - ヘッダ行・空行は許容（col0 が date として解釈できない行は自動スキップ）。
  - 同一 base_date 内の行順がそのまま商品の表示順（seq）として保存される。

変換後は行数・基準日数を標準出力に表示するので、目視で件数を検証すること。
実依存は無いが決定的テスト対象外（scripts/ の使い捨て）。ruff / ty だけは通す。

使い方:
  uv run python scripts/csv_to_parquet.py --in ./assets.csv --out ./assets.parquet
  # 検証後:
  aws s3 cp ./assets.parquet "$DATA_LOCATION"
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import OrderedDict
from datetime import date
from pathlib import Path

from domain.asset import Money, PortfolioAsset, ProductAsset
from infrastructure.duckdb_store import DuckDbAssetRepository, DuckDbConfig


def _parse_rows(csv_path: Path) -> OrderedDict[date, list[ProductAsset]]:
    """CSV を読み、基準日ごとの商品リストへ（行順＝商品順を保持）。

    col0 が date として解釈できない行（ヘッダ・空行）は SheetsAssetRepository.
    find_by_date_range と同じ流儀でスキップする（ヘッダ有無に頑健）。
    """
    products_by_date: OrderedDict[date, list[ProductAsset]] = OrderedDict()
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 5:
                continue
            try:
                base_date = date.fromisoformat(str(row[0]).strip())
            except ValueError:
                continue  # ヘッダ / 空行 / 日付以外の col0 はスキップ。
            product = ProductAsset(
                name=str(row[1]),
                contribution=Money(int(row[2])),
                profit_loss=Money(int(row[3])),
                valuation=Money(int(row[4])),
            )
            products_by_date.setdefault(base_date, []).append(product)
    return products_by_date


def convert(csv_path: Path, parquet_path: Path) -> tuple[int, int]:
    """CSV を Parquet へ変換し、(基準日数, 総行数) を返す。"""
    products_by_date = _parse_rows(csv_path)

    # 出力先ディレクトリを先に作る（未作成だと repo.save 内の COPY が不親切に落ちるため）。
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    # 既存の Parquet を消してから作り直す（再実行で重複しないように）。
    parquet_path.unlink(missing_ok=True)
    repo = DuckDbAssetRepository(DuckDbConfig(location=str(parquet_path)))

    total_rows = 0
    for base_date, products in products_by_date.items():
        repo.save(PortfolioAsset(base_date=base_date, products=tuple(products)))
        total_rows += len(products)
    return len(products_by_date), total_rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sheets エクスポート CSV を データストア用 Parquet へ変換"
    )
    parser.add_argument("--in", dest="csv_in", required=True, type=Path, help="入力 CSV パス")
    parser.add_argument(
        "--out", dest="parquet_out", required=True, type=Path, help="出力 Parquet パス"
    )
    args = parser.parse_args(argv)

    if not args.csv_in.exists():
        print(f"入力 CSV が見つかりません: {args.csv_in}", file=sys.stderr)
        return 1

    dates, rows = convert(args.csv_in, args.parquet_out)
    print(f"変換完了: {args.parquet_out}（基準日 {dates} 件 / 総行数 {rows}）")
    print("次の手順: 内容を検証し、`aws s3 cp` で DATA_LOCATION へアップロードしてください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
