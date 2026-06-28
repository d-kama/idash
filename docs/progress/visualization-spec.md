# 可視化項目の仕様確定（Phase 5/6 前段）

- **short-topic**: `visualization-spec`
- **ステータス**: 仕様確定（コード実装は Phase 5/6 で着手・本ドキュメントは前提合意の記録）

## 目的・背景

Phase 5（BFF）/ Phase 6（フロントエンド）の実装着手前提として、`PROJECT_PLAN.md` の未決
TODO（L407「BFF エンドポイント一覧・レスポンススキーマ」・L408「フロントの画面構成・可視化
内容（指標・グラフ種別・期間軸）」）のうち、**可視化内容（テーブル / グラフ / ウィジェット）と
期間軸**をユーザー合意のうえで確定する。本ドキュメントは決定事項の記録であり、コードは含まない。

### 手元のデータと再利用できる資産

データストアの Parquet は **基準日 × 商品** 粒度で `contribution`（拠出累計）/ `profit_loss`
（評価損益）/ `valuation`（評価額）の3金額（円整数）を持つ
（`packages/infrastructure/src/infrastructure/duckdb_store.py`）。重要な恒等式
**評価額 = 拠出累計 + 評価損益** が成り立つ。集計・整形ロジックは既存ドメインをほぼ再利用できる:

- `PortfolioAsset.total()` → `AssetTotal`（全商品合算） … `packages/domain/src/domain/asset.py`
- `summarize()` → 損益率・期間変化（前回比） … `packages/domain/src/domain/notification.py`
- `Money.format()` / `Money.signed()`（`+¥` 付き表示） … 表示整形に流用

## 確定した可視化仕様

### 1. 最新ポートフォリオ・ウィジェット — ヒーロー＋構成バー

- 評価額を主役の大きな数字で表示し、横に前回比デルタ（`Money.signed()` 相当、含み益=緑 /
  元本割れ=赤の色分け）。
- その下に水平の積み上げバー: **土台=拠出累計**、その上に**評価損益**を重ね、「元本に対して今
  いくら／元本割れか」を直感表示。損益率（%）を併記。
- データ源は最新基準日の `AssetTotal` ＋ 前回基準日との差分（`summarize` 相当のロジックを再利用）。

```
       資産評価額
     ¥2,480,000   ( 前回比 +¥12,000 )
  ████████████████████░░░░
  └─ 拠出 ¥2,300,000 ─┘└ 損益 +¥180,000 (+7.83%) ─┘
```

### 2. テーブル — 商品毎の日別推移（指標トグルで切替）

- 行 = 基準日、列 = 商品。1つの指標（評価額 / 評価損益 / 拠出累計）をトグルで切替表示し、横幅の
  肥大を回避。
- 最終行または別カラムに合計（`AssetTotal` の該当指標）。
- 金額表示は `Money.format()` / 損益指標時は `Money.signed()` 相当。

### 3. グラフ — 折れ線（期間セレクタあり）

- **商品毎の折れ線**: 各商品の選択指標（既定=評価額）を multi-series で時系列表示。
- **ポートフォリオ全体の折れ線**: 評価額の折れ線に**拠出累計のライン**を重ね、両者の差分
  （=評価損益）が面で読めるようにする。
- 共通の**期間セレクタ**（1M / 3M / 6M / 1Y / 全期間）で表示範囲を切替。

## BFF が返すべきデータ形（後続フェーズの指針）

上記を満たすため、`GetVisualizationData` ユースケース / `schemas` DTO は概ね次を供給する想定
（本ドキュメントでは確定まで踏み込まず方針のみ記録）:

- **時系列（series）**: 基準日ごとに
  `[{ base_date, products: [{ name, contribution, profit_loss, valuation }], total: { … } }]`。
  テーブル・両折れ線・期間セレクタすべてをこの1系列から描画できる。
- **最新サマリ（latest summary）**: `summarize()` 出力相当（`latest_total` / `profit_rate` /
  前回比 `valuation_change`・`profit_change`）。ヒーロー＋構成バー用。
- 期間フィルタは BFF 側クエリ（`from`/`to` or `range`）で `AssetRepository.find_by_date_range`
  に委譲する余地あり。データ量が小さい（年 ~2,500 行）ため、初期は全期間返却＋フロント側
  フィルタでも可。

## 確定していない（後続フェーズで詰める）残課題

- チャートライブラリ選定（Recharts / Nivo 等）と UI ライブラリ — Phase 6 実装着手時。
- BFF のエンドポイント分割（単一 `/visualization` か、series / summary の分割か）と Parquet
  直読み vs JSON キャッシュ層（`PROJECT_PLAN.md` §9）。
- 認証・認可の要否（`PROJECT_PLAN.md` L409）。
