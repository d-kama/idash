# Google Spreadsheet データストア撤去とドキュメント最新化

- **short-topic**: `remove-sheets-datastore`
- **作業ブランチ**: `chore/remove-sheets-datastore`
- **ステータス**: 計画中

## 目的・背景

データストアを Google Spreadsheet から DuckDB + S3 単一 Parquet へ移行済み（PR #25 / ADR-0005、実デプロイ＆動作確認まで完了）。本番 handler（`handler_collect` / `handler_notify`）と infra（`batch-stack.ts`）は既に DuckDB 系のみを参照しており、Sheets への依存は**死にコード・移行済みツール・陳腐化したテスト/ドキュメント**として残存しているだけ。

これらを削除・修正してリポジトリから Sheets 由来の痕跡を一掃し、現行のデータストア（DuckDB+S3 Parquet）に記述を揃える。`gspread` 依存も外して配布物を軽量化する。

## スコープ

### 対象（やること）

- **死にコード削除**: `packages/infrastructure/src/infrastructure/sheets.py` とそのテスト（`tests/test_sheets.py` / `tests/test_sheets_read.py`）。
- **依存削除**: `packages/infrastructure/pyproject.toml` の `gspread` を除去し、`uv sync` で lock を更新。
- **ローカル実行スクリプトの DuckDB 移行**: `scripts/run_collect_local.py` / `scripts/run_notify_local.py` を `SheetsAssetRepository` から `DuckDbAssetRepository` へ書き換え（本番 handler と整合させる）。
- **移行ツール削除**: 一度きりの `scripts/csv_to_parquet.py`（移行完了済み）を削除。
- **陳腐化テスト修正**: `packages/common/tests/test_ssm.py` の `/idash/dev/sheets-sa`、`apps/batch/tests/test_handler_notify.py` のドックストリング「sheets-sa」を現行 SSM 名に修正。
- **ドキュメント最新化**: `CLAUDE.md` / `CONTEXT.md` / `PROJECT_PLAN.md` / `README.md` から Sheets 記述（データフロー・SSM `/idash/<env>/sheets-sa`・用語）を除去または DuckDB+S3 へ書き換え。

### 対象外（やらないこと）

- **`docs/progress/issue-*.md` の修正**（ユーザー合意：作成時点の事実を残す歴史的記録として保持）。
- **`docs/adr/0005-datastore-duckdb-s3-parquet.md` の本文書き換え**（移行決定を記録する ADR。Sheets は「移行元」として正しく残す。ただし削除する `csv_to_parquet.py` への「実行手順」的な参照が残るなら過去形へ最小修正する）。
- **infra（`batch-stack.ts` / `app.ts`）の変更**（既に Sheets 非依存でクリーン。`sheets-sa` SSM の参照なし）。
- **本番 handler / `duckdb_store.py` 等の現行データストア実装の変更**。
- **AWS 側に手動作成済みの `/idash/<env>/sheets-sa` SSM パラメータの削除**（IaC 管理外。必要なら別途手動運用。本計画では扱わない）。

## 実装ステップ

> implement スキルがステップごとに実装・レビューを回す。各ステップは
> 独立してテスト・レビューできる粒度に分割し、完了したら `[x]` にする。

- [ ] 1. **`run_collect_local.py` を DuckDB へ移行**。`infrastructure.sheets` の import と `--write` 時の `SheetsAssetRepository` 分岐を `DuckDbAssetRepository(DuckDbConfig(location=...))` へ置換。ローカル JSON の `sheets` ブロックを `data_location`（ローカル Parquet パス or `s3://...` 文字列）へ変更し、docstring の設定例・役割表・`--write` 説明文を Sheets → DuckDB+S3 に更新。検証: `task lint` / `task typecheck`（スクリプトは ruff/ty のみ対象）が通る。
- [ ] 2. **`run_notify_local.py` を DuckDB へ移行**。同様に `SheetsAssetRepository` を `DuckDbAssetRepository` へ置換し、JSON の `sheets` を `data_location` へ、docstring（役割表・設定例）を更新。検証: `task lint` / `task typecheck`。
- [ ] 3. **Sheets 実装と依存を削除**。`sheets.py` / `test_sheets.py` / `test_sheets_read.py` を削除し、`pyproject.toml` から `gspread` を除去、`uv sync` で lock 更新。検証: `rg -i "sheets|gspread" packages/ apps/`（cdk.out 除く）でソースに残存参照なし、`task check` が通る。
- [ ] 4. **陳腐化したテスト参照を修正**。`test_ssm.py` の fixture 名 `/idash/dev/sheets-sa` を現行の実在名（例 `/idash/dev/source-login`）へ、`test_handler_notify.py` のドックストリング「SSM(2本: sheets-sa / notify-line)」を notify の現行構成（`notify-line` のみ）へ修正。検証: `uv run pytest packages/common/tests/test_ssm.py apps/batch/tests/test_handler_notify.py`。
- [ ] 5. **移行ツール `scripts/csv_to_parquet.py` を削除**。削除前に `rg "csv_to_parquet"` で他ドキュメント（README / ADR-0005 等）からの参照を確認し、残るなら過去形へ最小修正。検証: `task check`。
- [ ] 6. **ドキュメント最新化**。`CLAUDE.md`（実行時データフロー「Sheets を介して連携」→ DuckDB+S3 Parquet 経由、SSM 節の `/idash/<env>/sheets-sa` 記述除去）、`CONTEXT.md`（`AssetRepository` 等の Sheets 由来の語彙）、`PROJECT_PLAN.md`、`README.md` を DuckDB+S3 へ更新。検証: `rg -i "spreadsheet|sheets|gspread|シート|スプレッドシート" CLAUDE.md CONTEXT.md PROJECT_PLAN.md README.md` で残存なし（意図的な歴史記述を除く）。

## 未確定事項・リスク

- **ローカルスクリプトの S3 認証**: DuckDB の S3 location をローカルから叩く場合は `credential_chain`（ローカル AWS 認証）に依存する。ローカル開発の既定はローカル Parquet パス（例 `./data.local.parquet`）とし、S3 検証は任意とする想定。必要なら `--data-location` 引数の追加を検討。
- **`gspread` の間接利用**: lock 上で他パッケージが間接依存していないか `uv sync` 後に確認（想定では `infrastructure` のみが直接依存）。
- **ドキュメントの Sheets 記述の網羅性**: 図（データフロー図）やアーキ節に画像/ASCII で Sheets が残っていないか、ステップ 6 の `rg` で取りこぼさないよう確認する。

## 参照リンク

- `docs/adr/0005-datastore-duckdb-s3-parquet.md` — データストア移行の決定記録
- PR #25（feature/duckdb-s3-datastore）— 移行本体
- `packages/infrastructure/src/infrastructure/duckdb_store.py` — 現行 `DuckDbAssetRepository`
- `apps/batch/src/batch/handler_collect.py` / `handler_notify.py` — 現行 composition root（移行先の整合基準）
