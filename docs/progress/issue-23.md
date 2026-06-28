# データストア変更: Google Spreadsheet → DuckDB + S3 (単一 Parquet)

- **short-topic**: `duckdb-s3-datastore`
- **作業ブランチ**: `feature/duckdb-s3-datastore`
- **ステータス**: 実装完了（実デプロイ・データ移行は手動運用で残）
- **Issue**: [#23 データストア変更](https://github.com/d-kama/idash/issues/23)

## 目的・背景

`AssetRepository`（PortfolioAsset の永続化ポート）の具象を、現状の Google Spreadsheet
（`SheetsAssetRepository` / gspread）から **DuckDB + S3 上の単一 Parquet** へ置き換える。

Issue #23 の方針:

- Parquet を使用
- ファイル分割はしない（単一ファイル）
- 認証は DuckDB 推奨方式
- 既存の Google Spreadsheet 具象クラスは**削除しない**

### 設計の前提（grilling 合意）

- **規模**: iDeCo 個人データ。平日 1 回 × 商品 5〜10 件 ≒ 年 2,500 行、10 年でも 2.5 万行
  （Parquet 化で数百 KB）。単一ファイルの read-modify-write でも書き込み増幅・メモリは
  実質問題にならない（フル materialize でも数 MB、Lambda は 512/2048 MB）。
- **単一 Parquet が妥当な理由**: 書き込みは collect だけ（単一ライター）で、その collect 関数は
  `reservedConcurrency=1` により同時実行が 1 に制限される（＋スケジュールは `retryAttempts=0`）。
  よって並行書き込みは構造的に発生しない。notify は read-only で並行実行しても Parquet 読み取りは
  競合しない。read は「直近 N 日」を 1 GET で読めるためパーティション分割より S3 リクエスト数で
  有利。アンチパターンが牙を剥く条件（GB 級・並行ライター・高頻度）がどれも当てはまらない。
- **Parquet vs CSV**: S3 はイミュータブルで CSV でも追記は不可（どちらも read-modify-write）。
  差は「型忠実性（Parquet）」vs「可読性（CSV）」のみ。型を保持して再パース不要にできる
  Parquet を採用（Sheets 実装の `int(row[2])` / `date.fromisoformat()` の脆さを解消）。
- **MERGE/UPSERT が使えない理由**: それらはエンジン管理下の可変テーブルへの操作。Parquet は
  イミュータブルなファイル形式で行の in-place 更新概念がない。Iceberg/Delta が MERGE できるのも
  内部で新 Parquet を別ファイルとして書き manifest で論理上書きしているため（= Issue が除外した
  「ファイル分割」）。素の単一 Parquet では「新ファイルを作って差し替え」= read-modify-write のみ。

### 主要な設計判断（grilling 合意）

| 論点 | 決定 |
|---|---|
| 移行スコープ | collect/notify を**両方一括でハードカットオーバー**。Sheets 具象はコードとして残すが配線から外す。BFF(Phase5) は対象外 |
| 既存データ移行 | **役割分担**: ① ユーザーが Sheets を CSV エクスポートし所定位置へ配置 → ② `scripts/` の使い捨てスクリプトが **CSV → ローカル Parquet 変換のみ** → ③ ユーザーが S3 へアップロード。スクリプトは Sheets/gspread/SSM に触れない |
| 具象命名 | `infrastructure/duckdb_store.py` の **`DuckDbAssetRepository`**（実装技術=クエリエンジン軸。既存 `SheetsAssetRepository`=gspread と揃える） |
| 書き戻し | DuckDB で**直接上書き**（`memory_limit` + `temp_directory='/tmp'` でスピル可）。欠損/誤書きはバケットの **versioning** で巻き戻し |
| save の冪等性 | **base_date 単位の冪等 upsert**（`WHERE base_date <> $today UNION ALL new`）。同一日再実行でその日を置換するだけで重複しない |
| 認証 | `CREATE SECRET (TYPE s3, PROVIDER credential_chain)` → Lambda 実行ロールを使用。静的キーなし |
| httpfs 拡張 | **Docker build 時に事前同梱**（`INSTALL httpfs`）。実行時は `LOAD` のみ（ネット DL なし） |
| テストシーム | Config に**データ位置（`s3://...` or ローカルパス）**を注入。テストは `tmp_path` のローカル parquet を指し実 SQL を検証（httpfs/moto 不要） |
| 未存在(初回)判定 | `SELECT count(*) FROM glob($loc)` でローカル/S3 統一。未存在なら read は空、save は新行のみ write |
| env 表現 | `DATA_LOCATION` 単一 URI（`s3://<bucket>/assets.parquet`）。`s3://` 接頭辞で SECRET 実行を判定 |
| sheets-sa 依存 | 両ハンドラから `SHEETS_SA_PARAM` env と grant を除去（SSM パラメータ実体は手動作成のため AWS 側には残る） |
| データバケット | 新設。versioning 有効（noncurrent は lifecycle 失効）、`RemovalPolicy.RETAIN`、物理名は自動命名 |
| 決定記録 | 新規 **ADR-0005** を起こす |

## スコープ

### 対象（やること）

- `DuckDbAssetRepository`（`infrastructure/duckdb_store.py`）の新規実装と単体テスト
- `apps/batch` の collect/notify ハンドラ（composition root）の配線差し替え
- `common.settings`（`CollectSettings`/`NotifySettings`）の env 変更（sheets-sa 除去 / data_location 追加）
- `apps/batch/Dockerfile` への httpfs 拡張事前同梱
- infra（`IdashBatchStack`）: データバケット新設・IAM grant・env 付与・sheets-sa import/grant 除去・Vitest スナップショット更新
- CSV → Parquet 変換の一回限り移行スクリプト（`scripts/`）。Sheets エクスポートと S3 アップロードはユーザー手作業
- ドキュメント更新（ADR-0005 / CONTEXT.md / PROJECT_PLAN.md）

### 対象外（やらないこと）

- `SheetsAssetRepository` の削除（Issue 方針によりコードとして残す）
- BFF（Phase 5）/ frontend（Phase 6）の対応（未着手のため。新 repo は将来そのまま再利用）
- パーティション分割・Iceberg/Delta 等の table format 導入（単一ファイル方針）
- SSM パラメータ実体の削除（手動管理。CDK からの import/grant 除去のみ）

## 実装ステップ

> implement スキルがステップごとに実装・レビューを回す。各ステップは
> 独立してテスト・レビューできる粒度に分割し、完了したら `[x]` にする。

- [x] 1. **依存追加**: `packages/infrastructure` に `duckdb` を依存追加（`pyproject.toml` + `uv sync`）。`task typecheck` が通ることを確認。
- [x] 2. **`DuckDbAssetRepository` 実装 + 単体テスト**: `infrastructure/duckdb_store.py` に `DuckDbConfig`（データ位置を保持）と `DuckDbAssetRepository` を実装。
  - `save()`: glob で存在判定 → 既存を TEMP テーブルへ materialize（同一パスの read-while-write 回避）→ `COPY (existing WHERE base_date <> $today UNION ALL new) TO $loc (FORMAT parquet)`。
  - `find_by_date_range()`: 未存在なら空、存在すれば `read_parquet` を期間フィルタ → 基準日昇順で `PortfolioAsset` 再構成。
  - スキーマ: `base_date DATE` / `name VARCHAR` / `contribution BIGINT` / `profit_loss BIGINT` / `valuation BIGINT`（yen 整数で exact round-trip）。
  - セッション設定: `memory_limit` / `temp_directory='/tmp'` / `LOAD httpfs` / `s3://` 接頭辞時のみ `CREATE SECRET ... credential_chain`。
  - テスト: `tmp_path` のローカル parquet を指し、空→save→read の round-trip、同一日再 save の冪等性、期間フィルタ、未存在時の空返却を検証（httpfs/moto 不要）。
- [x] 3. **Dockerfile に httpfs 事前同梱**: `apps/batch/Dockerfile` のビルド段で `INSTALL httpfs`（実行時 DL を排除）。collect/notify 共有イメージのため 1 箇所。
- [x] 4. **settings + composition root 差し替え**: `CollectSettings`/`NotifySettings` から `sheets_sa_param` を除去し `data_location` を追加。`handler_collect.py`/`handler_notify.py` の `build_use_case` を `DuckDbAssetRepository` 構築へ差し替え（`ssm.get_secure_json(sheets_sa)` 取得を撤去）。`uv run pytest` でハンドラテスト緑を確認。
- [x] 5. **infra（CDK）更新**: `IdashBatchStack` にデータバケット（versioning / lifecycle で noncurrent 失効 / `RemovalPolicy.RETAIN` / 自動命名）を新設。collect に `grantReadWrite`・notify に `grantRead`。両 Lambda に `DATA_LOCATION` env 付与、`sheetsSaParam` の import/grant を除去。`pnpm --filter @idash/infra run test:update` でスナップショット更新し差分を確認。
- [x] 6. **移行スクリプト（CSV → Parquet 変換のみ）**: `scripts/csv_to_parquet.py`（使い捨て）。ユーザーが所定位置へ配置した CSV を DuckDB で読み、`DuckDbAssetRepository` のスキーマ（`base_date DATE` / `name VARCHAR` / 金額 3 列 `BIGINT`）に揃えてローカル parquet を生成。Sheets/gspread/SSM/S3 には触れない（エクスポートとアップロードはユーザー手作業）。CSV の列順・ヘッダ・型の前提と実行手順を docstring/README に明記し、変換後に行数・スキーマを目視検証。本番コードパスには載せない。
- [x] 7. **ドキュメント更新**: ADR-0005（データストアを DuckDB+S3 単一 Parquet へ。文脈に単一ファイル/read-modify-write/credential_chain/base_date 冪等 upsert/versioning/Sheets をやめた理由）。`CONTEXT.md` の `AssetRepository`「具象は Google Spreadsheet」記述を更新。`PROJECT_PLAN.md` のデータストア表・アーキ図を更新。

## 未確定事項・リスク

- **移行・デプロイ運用（手動手順）**: ① ユーザーが Sheets を CSV エクスポートし所定位置へ配置 → ② スクリプトで parquet 変換・目視検証 → ③ ユーザーが `DATA_LOCATION` へ `aws s3 cp` 等でアップロード → ④ デプロイ。この順序を守らないと初回 notify がスカスカ。手順を ADR / README に明記する。
- **CSV エクスポートのフォーマット差異**: Google Sheets の CSV 出力（区切り・引用符・日付/数値の表記、ヘッダ行有無）が変換スクリプトの前提と食い違うと取り込みが壊れる。スクリプト側で列順・型を明示し、変換後に行数・スキーマを検証する。
- **DuckDB バージョンの httpfs 互換**: 事前同梱した拡張バイナリと実行時 DuckDB のバージョン整合が必要。同一イメージ内で `uv.lock` の `duckdb` を使って `INSTALL`→実行時 `LOAD` するため、ビルド時点では同一バージョンで揃う（`pyproject.toml` の依存と Dockerfile の INSTALL は同じ venv を共有）。lock 更新時はイメージ再ビルドで追従する点に留意。
- **`COPY TO` の同一パス read-while-write**: ✅ **実装済み・回避済み**。既存を TEMP テーブルへ materialize してから `COPY TO` する（`duckdb_store.py`）。
- **Lambda の `/tmp` 容量**: 既定 512 MB。本件のデータ規模では十分だがスピル先として一応認識。
- **SSM `sheets-sa` の今後**: カットオーバー後は collect/notify とも参照しなくなる（移行スクリプトも Sheets/SSM に触れない方針）。パラメータ実体（手動作成）の扱い（残置/削除）は別途判断。

## 参照リンク

- Issue: https://github.com/d-kama/idash/issues/23
- 既存具象: `packages/infrastructure/src/infrastructure/sheets.py`（`SheetsAssetRepository`）
- ポート: `packages/domain/src/domain/asset.py`（`AssetRepository`）
- 配線: `apps/batch/src/batch/handler_collect.py` / `handler_notify.py`
- infra: `infra/lib/batch-stack.ts`（`IdashBatchStack`）
- 既存 ADR: `docs/adr/0002`〜`0004`（命名・記法の参考）
- glossary: `CONTEXT.md`（`AssetRepository` / `PortfolioAsset` / `Money`）
