# データストアを DuckDB + S3 単一 Parquet とする

`AssetRepository`（PortfolioAsset の永続化ポート）の具象を、Google Spreadsheet（gspread）から
**DuckDB + S3 上の単一 Parquet ファイル**へ置き換える。収集（write）と通知/可視化（read）は引き続き
このデータストアを介してのみ疎結合に連携する。`SheetsAssetRepository` はコードとして残すが、配線からは外す。

## Context

- Sheets は API レート/レイテンシ・型の欠如（全セル文字列で read 時に再パースが必要）・
  クエリ性の弱さがあり、可視化（Phase 5/6）に向けてデータストアとして手狭。
- iDeCo 個人データは規模が小さい（平日 1 回 × 商品 5〜10 件 ≒ 年 2,500 行、10 年でも 2.5 万行＝
  Parquet で数百 KB）。並行書き込みは収集 Lambda の `reservedConcurrency=1` で構造的に発生しない。

## Decision

- **形式は単一 Parquet（分割なし）**。列は `base_date DATE` / `name VARCHAR` /
  `contribution`・`profit_loss`・`valuation BIGINT`（円整数）/ `seq INTEGER`（同一基準日内の商品保存順）。
  型を保持して exact round-trip し、read 時の再パースを廃する。
- **書き込みは read-modify-write**。Parquet はイミュータブルで行の in-place 更新ができないため、
  既存を読み・当該 `base_date` の行を除外し・新行と結合した全件を書き戻す
  （= **base_date 単位の冪等 upsert**。同一日再実行はその日を置換するだけで重複しない）。
- **認証は DuckDB 推奨の `CREATE SECRET (TYPE s3, PROVIDER credential_chain)`**。AWS 標準認証チェーン
  経由で Lambda 実行ロールを使い、静的キーをコード/SSM に持たない。
- **httpfs / aws 拡張はコンテナイメージへビルド時に事前 INSTALL** し、実行時は固定
  `extension_directory` から `LOAD` のみ（外部 DL・コールドスタート遅延・障害点を排除）。
- **S3 バケットは versioning 有効・noncurrent は 90 日失効・`RemovalPolicy.RETAIN`**。単一ファイル
  上書きの欠損/誤書きを旧バージョンで巻き戻せるようにし、再取得不可能な唯一のデータをスタック削除から守る。

## Considered Options

- **パーティション分割 / table format（Iceberg・Delta）** — MERGE による差分更新や追記が可能だが、
  内部的に「複数 Parquet + メタデータ層」を要し、本件が避けたい運用複雑性を持ち込む。データ規模が
  小さく差分更新の利得が無いため不採用（単一ファイルなら read も 1 GET で済み S3 リクエストも最小）。
- **CSV** — 人間可読だが S3 では追記不可（Parquet と同じ read-modify-write）で利得が無く、型が全て
  文字列になり再パースの脆さが残る。不採用。
- **DuckDB ネイティブ DB ファイル（.duckdb）** — UPSERT は可能だが S3 へ直接 write できず
  「/tmp へ DL→更新→アップロード」と結局フルファイルの read-modify-write。issue の Parquet 指定にも反する。不採用。

## Consequences

- 既存データは一回限りの移行で引き継ぐ。役割分担は ① ユーザーが Sheets を CSV エクスポート →
  ② `scripts/csv_to_parquet.py` がローカル Parquet へ変換 → ③ ユーザーが `DATA_LOCATION` へアップロード。
  スクリプトはテスト済みの `DuckDbAssetRepository.save()` を再利用し、本番 read 経路とスキーマを一致させる。
- **デプロイ手順は順序が重要**: 「移行 Parquet を配置 → デプロイ」を守らないと初回の通知が
  空になる（通知は直近 N 日を集計するため）。さらに移行 Parquet 配置前に collect が走ると、
  `save()` は未存在を検知してその日の行だけで新規 Parquet を作る（過去データ無しで開始）。
  破壊的な上書きにはならないが過去分が欠けるため、必ず移行配置を先に済ませる。
- collect は `DATA_LOCATION` バケットへ read/write（glob の LIST 含む）、notify は read のみを実行ロールに付与。
- `SHEETS_SA_PARAM_ARN` env と grant は両 Lambda から除去（SSM パラメータ実体は手動管理のため AWS 側には残る）。
- メモリは肥大時に備え `memory_limit` + `temp_directory='/tmp'` を設定しスピル可能にするが、
  この規模では数 MB に収まりメモリは律速にならない。
