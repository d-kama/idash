# 可視化: BFF（Phase 5）+ フロントエンド（Phase 6）設計・実装計画

- **short-topic**: `visualization`
- **作業ブランチ**: フェーズ毎に分割（Phase 5: `feature/bff` → Phase 6: `feature/frontend`）
- **ステータス**: 計画中（基本設計 grilling 合意済み・詳細設計済み・実装未着手）
- **Issue**: [#27 可視化](https://github.com/d-kama/idash/issues/27)
- **前提ドキュメント**: `docs/progress/visualization-spec.md`（表示項目レベルの仕様は確定済み）

## 目的・背景

Issue #27「可視化」を実現する。表示項目（ヒーロー＋構成バー / 商品別テーブル / 折れ線グラフ2種）
は `visualization-spec.md` で確定済み。本ドキュメントは grilling で確定した基本設計と、
それを実装へ落とす詳細設計・実装ステップの記録。実装は Phase 5（BFF）→ Phase 6（フロント
エンド）の順に、フェーズ毎のブランチ / PR で進める。

### issue 記載「期間: 日 / 週 / 月 / 年」の解釈（確定）

**表示範囲セレクタ（1M / 3M / 6M / 1Y / 全期間）**の意味で確定（visualization-spec.md の解釈を
追認）。粒度リサンプリングは行わない（平日日次・年 ~250 基準日と少量で全点描画可能）。

## 主要な設計判断（grilling 合意）

| 論点 | 決定 |
|---|---|
| スコープ | BFF + フロントエンドの両方を基本設計済み。実装は Phase 5 → 6 の順 |
| API 構成 | **単一エンドポイント `GET /api/visualization`**。`summary`（ヒーロー用）と `series`（テーブル・グラフ用）を1レスポンスで返す |
| 期間フィルタ | **BFF は常に全期間を返し、フロントがメモリ内フィルタ**。クエリパラメータなし。肥大化したら `?range=` を後付け可能 |
| キャッシュ層 | **なし（Parquet 直読み）**。キャッシュ層の根拠は旧 Sheets 時代のレート制限懸念（ADR-0005 で歴史扱い）であり不要 |
| アクセス制御 | **CloudFront Functions による Basic 認証**＋ Geo 制限(JP) 併用。IP 制限は IP 変動で脆いため不採用、Cognito は過剰 |
| 認証情報の置き場 | **CloudFront KeyValueStore**（repo が public のためコード埋め込み不可）。CDK は Function + KVS を作るだけ、値は AWS 側で手動投入（SSM SecureString と同じ運用パターン）。`task synth` は AWS 認証不要のまま |
| CloudFront 経由限定化 | **origin-verify 共有シークレット**で API GW 直叩きを遮断（obscurity のみに依存しない）。CF Function（viewer-request）が Basic 認証通過後に KVS から秘密値を読み `x-origin-verify` ヘッダを**クライアント値を上書きして**注入、BFF が SSM SecureString の期待値と照合し不一致/欠落は 403。CloudFront を迂回した API GW 直接アクセスは秘密値を知らず弾かれる。秘密は CF 側=KVS / BFF 側=SSM に手動投入（`disableExecuteApiEndpoint` は独自ドメイン前提のため不採用） |
| チャート / CSS | **Recharts** + **Tailwind CSS**。シングルページ（ヒーロー → 折れ線2種 → テーブル）、ルーティングなし |
| 環境 / ドメイン | 単一環境のまま（`--context env` の仕組みだけ維持）。CloudFront 既定ドメイン（独自ドメイン・ACM 見送り） |
| 商品の入れ替え | 表示期間内に登場する**全商品の和集合**を列/系列にし、データがない基準日は**空欄（折れ線は途切れ）**。BFF はあるがまま返すだけ |
| テーブル表示 | **期間セレクタに連動**（グラフと同一期間）・**基準日降順**・縦スクロール。ページネーションなし |
| 空データ | 0件: **200 で `summary: null` / `series: []`**、フロントは「データ未収集」の空状態表示。1件: 前回比 ±¥0（`summarize` 既存仕様） |
| 金額整形 | DTO は**円整数・生比率**、表示整形（`¥`・`+`符号・`%`）は**フロント側**（`Intl.NumberFormat("ja-JP")`） |
| 型生成 | Pydantic → OpenAPI → TS の一方向。TS 生成は **openapi-typescript**（型のみ・ランタイム依存なし） |
| 決定記録 | アクセス制御方式は **ADR-0006** を起こす（Basic 認証＋origin-verify による CloudFront 経由限定化。public repo 制約・CFn SecureString 非対応・synth 認証不要の3制約が背景） |

## 詳細設計

### API 契約

```text
GET /api/visualization
200 OK
{
  "summary": {                      // データ0件なら null
    "base_date": "2026-07-03",
    "total": { "contribution": 2300000, "profit_loss": 180000, "valuation": 2480000 },
    "profit_rate": 0.0783,          // 生比率（表示整形はフロント）
    "valuation_change": 12000,      // 前回基準日比（直近2基準日を summarize に渡す）
    "profit_change": 9000
  },
  "series": [                       // 基準日昇順・全期間
    { "base_date": "2026-07-03",
      "products": [ { "name": "商品A", "contribution": ..., "profit_loss": ..., "valuation": ... } ],
      "total": { "contribution": ..., "profit_loss": ..., "valuation": ... } }
  ]
}
```

金額はすべて円整数（`Money.yen`）。恒等式 `valuation = contribution + profit_loss` が成立。

### ドメイン: ポート拡張（`find_all`）

`AssetRepository` に **`find_all() -> Sequence[PortfolioAsset]`（基準日昇順・全期間）** を追加する。
`find_by_date_range(date.min, date.max)` の流用は「全期間」という意図が型に現れず、番兵値が
クエリへ漏れるため不採用。`DuckDbAssetRepository` は既存 read 経路から WHERE を外すだけで実装
できる（未存在 glob 判定も共通化）。

### schemas（Pydantic DTO — Phase 5 で本格利用開始）

`packages/schemas/src/schemas/visualization.py`:

```python
class AssetAmounts(BaseModel):        # 3金額の組（total / product 共通の基底）
    contribution: int
    profit_loss: int
    valuation: int

class ProductSnapshot(AssetAmounts):  # + name: str
class SeriesPoint(BaseModel):         # base_date: date / products: list[ProductSnapshot] / total: AssetAmounts
class VisualizationSummary(BaseModel):# base_date / total / profit_rate: float / valuation_change: int / profit_change: int
class VisualizationResponse(BaseModel): # summary: VisualizationSummary | None / series: list[SeriesPoint]
```

domain → DTO の詰め替えは **application 層**が担う（application は domain + schemas に依存可）。
schemas は domain を import しない（OpenAPI の single source of truth として純粋に保つ）。

### application: `GetVisualizationDataUseCase`

`packages/application/src/application/visualization.py`:

```python
class GetVisualizationDataInputBoundary(Protocol):
    def execute(self) -> VisualizationResponse: ...

class GetVisualizationDataUseCase(GetVisualizationDataInputBoundary):
    def __init__(self, repository: AssetRepository) -> None: ...
    def execute(self) -> VisualizationResponse:
        # find_all() → 0件なら summary=None/series=[] を即返す
        # summary は直近2基準日（1件しかなければ1件）を summarize() に渡して前回比を得る
        # series は PortfolioAsset → SeriesPoint へ詰め替え（total は asset.total() を使用）
```

Clock 不要（「今日」に依存しない。最新=データ内の最新基準日）。集計は既存 `summarize()` /
`PortfolioAsset.total()` を再利用し、application は orchestration と詰め替えのみ。

### apps/bff（FastAPI + Mangum）

- `src/bff/main.py` — FastAPI app。`GET /api/visualization`（`response_model=VisualizationResponse`）。
  CloudFront が `/api/*` をパススルーするためルートパスに `/api` 接頭辞を含める。
  `handler = Mangum(app)`。
- DI は FastAPI の `Depends(get_use_case)`。`get_use_case` はモジュールスコープで
  `DuckDbAssetRepository` を構築・キャッシュ（コールドスタート時1回。batch handler と同じく
  `memory_limit` / `temp_directory=/tmp` / `extension_directory=/opt/duckdb-extensions`）。
  テストは `app.dependency_overrides` でフェイク注入。
- `src/bff/export_openapi.py` — `json.dumps(app.openapi())` を stdout へ（`gen-types` タスクが使用）。
- `common.settings` に **`BffSettings`**（`env_name` / `data_location` ＋ Phase 6 で
  `origin_verify_param`）を追加（既存 `NotifySettings` と同形式）。データストアは実行ロール認証で
  SSM 不要だが、**CloudFront 経由限定化（origin-verify）で SSM SecureString を1つ使う**。
- **origin-verify 検証（Phase 6・B 採用）**: `main.py` は `x-origin-verify` ヘッダを SSM の期待値
  （`/idash/<env>/origin-verify`、`common.ssm` でコールドスタート時に取得・キャッシュ）と照合し、
  不一致/欠落なら 403。CloudFront Function が正規リクエストにのみ本ヘッダを注入するため、API GW を
  直叩きした相手は弾かれる。FastAPI の依存（`Depends`）で実装し、テストはヘッダ有無で 200/403 を確認。
  IdashBffStack は `ORIGIN_VERIFY_PARAM_ARN` を env で渡し、SSM param に `grantRead` する。
- `apps/bff/Dockerfile` — batch 版から chrome 部分を除いた縮小版:
  `public.ecr.aws/lambda/python:3.13` / uv 0.10.0 ピン / `uv sync --package idash-bff --no-dev
  --frozen --no-editable` / DuckDB httpfs+aws 拡張の事前 INSTALL / `CMD ["bff.main.handler"]`。
  ※ `idash-infrastructure` 依存で selenium 等も venv に入るが、起動経路で import しない
  （notify と同じ扱い。イメージ肥大は許容）。

### 型生成パイプライン（Taskfile `gen-types` 有効化）

```text
uv run python -m bff.export_openapi > openapi.json（一時ファイル）
pnpm --filter @idash/frontend exec openapi-typescript openapi.json -o src/api/generated/schema.d.ts
```

- **生成物（`schema.d.ts` / `openapi.json`）はコミットしない（gitignore）**。Pydantic を単一の
  真実源に保ち、生成物の鮮度ドリフトを構造的に排除する。
- `typecheck`（frontend 分）と `build-front` は `gen-types` に依存させる。`task setup` 後の初回
  IDE エラーは `task gen-types` 実行で解消（README に記載）。

### フロントエンド（apps/frontend）

- 依存追加: `recharts` / `tailwindcss` + `@tailwindcss/vite`（v4 系）/ dev: `openapi-typescript`,
  `vitest`。`build`（`tsc && vite build`）・`test` スクリプト追加。
- `vite.config.ts` に dev proxy（`/api` → `http://localhost:8000`、`task bff` のローカル uvicorn）
  を追加しローカル結合確認を可能にする。
- 構成（1ページ）:
  - `src/api/client.ts` — `fetch('/api/visualization')` + 生成型
  - `src/lib/` — 純粋ロジック: `filterByRange`（期間セレクタ）/ `productUnion`（和集合列）/
    `formatYen`・`formatSigned`・`formatPercent`（`Intl.NumberFormat("ja-JP")`）→ **vitest 対象**
  - `src/components/` — `Hero`（評価額＋前回比＋構成バー）/ `PortfolioChart`（評価額×拠出累計の
    重ね描き: Recharts `ComposedChart` の Area+Line、欠測は `connectNulls=false`）/
    `ProductsChart`（商品毎 multi-series Line）/ `AssetsTable`（降順・指標トグル）/
    `PeriodSelector` / `MetricToggle` / `EmptyState`
  - 状態: `App` が1フェッチ + `period` / `metric` の useState のみ。状態管理ライブラリ不要。

### infra（CDK）

**`IdashBffStack`**（`infra/lib/bff-stack.ts`）:

- props: `envName` / `dataBucket: IBucket` / `dataLocation: string`（`IdashBatchStack` が
  `dataBucket` / `dataLocation` を public プロパティで公開し、`bin/app.ts` がプロパティ渡し）。
- `DockerImageFunction`（`apps/bff/Dockerfile`、build context = リポジトリルート、
  `ignoreMode: DOCKER`）。memory 512 / timeout 29s（API GW 上限未満）/
  `reservedConcurrentExecutions: 3` / LogGroup 明示作成（1週間保持・自動命名）。
  env: `ENV_NAME` / `DATA_LOCATION`。`dataBucket.grantRead(fn)`。
- HTTP API（`aws-apigatewayv2` + `HttpLambdaIntegration`）。デフォルトステージに
  スロットリング（rate/burst 低め、コスト暴発対策）。
- 公開プロパティで API エンドポイントのドメインを `IdashFrontendStack` へ渡す。

**`IdashFrontendStack`**（`infra/lib/frontend-stack.ts`）:

- サイトバケット（非公開・enforceSSL・自動命名）+ CloudFront Distribution:
  - default behavior = S3（**OAC**、`S3BucketOrigin.withOriginAccessControl`）
  - `/api/*` behavior = HttpOrigin（API GW ドメイン）、`CACHING_DISABLED`、
    `ALL_VIEWER_EXCEPT_HOST_HEADER`
  - **Geo 制限 allowlist(JP)**
  - **SPA フォールバック（403/404→index.html）は入れない**: ルーティングなしの1ページで不要な
    うえ、カスタムエラーレスポンスはディストリビューション全体に効き `/api/*` のエラー応答まで
    書き換える副作用があるため（PROJECT_PLAN の既定方針からの変更 → ドキュメント更新で反映）
- **Basic 認証**: `cloudfront.Function`（runtime **JS 2.0**、コードは
  `infra/lib/functions/basic-auth.js`）+ `KeyValueStore` 関連付け。**両 behavior** の
  viewer-request に適用。関数は KVS のキー（例 `basic-auth`）から期待値
  （`Basic <base64(user:pass)>` 全体）を取得し、`Authorization` ヘッダと不一致なら
  401 + `WWW-Authenticate: Basic` を返す。KVS への値投入は手動
  （`aws cloudfront-keyvaluestore put-key`。ETag 指定が要る点含め README に手順明記）。
- **origin-verify 注入（`/api/*` behavior のみ・B 採用）**: 同 Function は Basic 認証通過後、KVS の
  別キー（例 `origin-verify`）から秘密値を読み `request.headers['x-origin-verify']` に**セット
  （既存値を上書き）**して origin（API GW）へ転送する。`ALL_VIEWER_EXCEPT_HOST_HEADER` で転送される
  が、Function が最後に上書きするためクライアント偽装値は無効化される。BFF が SSM の期待値と照合して
  直叩きを弾く（→ 詳細設計「apps/bff」）。KVS には Basic 認証値と origin-verify 値の2キーを手動投入
  する（README に両方明記）。
- `BucketDeployment` で `apps/frontend/dist` を配備。
- **synth の前提**: `Source.asset('apps/frontend/dist')` は synth 時に dist の存在が必要。
  Taskfile で `synth` を `build-front` に依存させる。Vitest スナップショットは asset ハッシュが
  フロントのビルド内容で揺れるため、**スナップショット前にハッシュを正規化**（プレースホルダ
  置換）する（実装時に cdk-development スキルの規約に従い方式確定）。

**`bin/app.ts`**: `Idash-${env}-Batch` → `Idash-${env}-Bff` → `Idash-${env}-Frontend` の順に
インスタンス化し、プロパティ渡しで配線（クロススタック参照より明示的、既定方針どおり）。

### Taskfile / CI

- 有効化・追加: `gen-types` / `build-front`（deps: gen-types）/ `bff`（ローカル uvicorn）/
  `front`（vite dev）。`synth` に deps: `build-front` を追加。`deploy` は
  `gen-types → build-front → cdk deploy --all` へ拡張。
- `task test` に frontend vitest（`pnpm --filter @idash/frontend test`）を追加。
- biome の lint/format 対象に `apps/frontend` が含まれることを確認（除外されていれば追加）。
- CI（`cicd.yml`）は `task check` + `task synth` / `task deploy` の呼び出し構造のまま変更最小。

## スコープ

### 対象（やること）

- `AssetRepository.find_all` ポート追加と `DuckDbAssetRepository` 実装
- `schemas` 可視化 DTO / `application` `GetVisualizationDataUseCase` / `apps/bff`（FastAPI +
  Mangum + Dockerfile）と各テスト
- `IdashBffStack` / `IdashFrontendStack` 新設、`bin/app.ts` 配線、スナップショットテスト
- 型生成パイプライン（`gen-types`）の有効化と frontend の本実装（Recharts + Tailwind）
- Basic 認証（CloudFront Functions + KVS）・Geo 制限(JP)
- **origin-verify による CloudFront 経由限定化**（CF Function のヘッダ注入 + BFF の SSM 照合・403）
- ドキュメント（ADR-0006 / PROJECT_PLAN.md 更新 / README に KVS・SSM 投入とデプロイ手順）

### 対象外（やらないこと）

- 独自ドメイン・ACM / 環境の複数化（単一環境のまま）
- BFF レスポンスのキャッシュ層・期間クエリパラメータ（必要になったら後付け）
- 粒度リサンプリング（日/週/月/年への集約）・ページネーション
- Cognito 等の本格認証 / CONTEXT.md の用語追加（新ドメイン概念なし）
- 収集・通知バッチ側の変更（`find_all` 追加以外、既存経路には触れない）

## 実装ステップ

> implement スキルがステップごとに実装・レビューを回す。各ステップは
> 独立してテスト・レビューできる粒度に分割し、完了したら `[x]` にする。

### Phase 5: BFF（`feature/bff`）

- [x] 1. **ポート拡張**: `domain.asset.AssetRepository` に `find_all()` を追加し、
       `DuckDbAssetRepository` に実装（既存 read 経路の WHERE なし版・基準日昇順）。
       既存テストのフェイク（application/batch の conftest）にも `find_all` を足す。
       ローカル parquet での round-trip テスト追加。`task check` 緑。
- [x] 2. **schemas DTO**: `schemas/visualization.py` に `AssetAmounts` / `ProductSnapshot` /
       `SeriesPoint` / `VisualizationSummary` / `VisualizationResponse` を定義。
       シリアライズ（date の ISO 化・None summary）の単体テスト。
- [x] 3. **ユースケース**: `application/visualization.py` に `GetVisualizationDataUseCase`。
       フェイクリポジトリで 0件（summary=None/series=[]）/ 1件（前回比±0）/ 複数件
       （直近2基準日の前回比・series 昇順・商品欠測日の素通し）をテスト。
- [x] 4. **bff アプリ**: `bff/main.py`（FastAPI + `Depends` DI + Mangum）/
       `bff/export_openapi.py` / `common.settings.BffSettings`。TestClient +
       `dependency_overrides` で 200 応答・JSON 形・空データ応答をテスト。
       `task bff`（ローカル uvicorn）タスク有効化。
- [x] 5. **bff Dockerfile**: chrome なし縮小版（uv sync --package idash-bff + DuckDB 拡張
       事前 INSTALL + `CMD ["bff.main.handler"]`）。ローカル `docker build` で成功確認。
       - **dockerignore 方式（確定）**: CDK の image asset フィンガープリントは build context
         直下の `.dockerignore` **のみ**読む（`<Dockerfile>.dockerignore` は無視）。よって共有
         root `.dockerignore` で apps/batch・apps/bff の両方を許可し、各 image asset の
         `exclude`（batch→`apps/bff` / bff→`apps/batch`）でハッシュを相互分離する。これで
         片方の**ソース**変更が他方のイメージハッシュを揺らさない（`.dockerignore` 自体の
         編集時は両ハッシュが1回だけ変わる＝context 定義の変更として正当）。
- [x] 6. **IdashBffStack**: `IdashBatchStack` に `dataBucket` / `dataLocation` の public
       プロパティを追加 → `bff-stack.ts` 新設（HTTP API + コンテナ Lambda + grantRead +
       スロットリング + 予約同時実行 3）→ `bin/app.ts` 配線。スナップショットテスト追加
       （`pnpm --filter @idash/infra run test:update`）。`task synth` 緑。
- [ ] 7. **Phase 5 実デプロイ・動作確認**: main マージ → CI deploy 後、API GW 直 URL に
       curl して `/api/visualization` の実データ応答を確認（この時点では CloudFront 未経由・
       Basic 認証なしの素の API GW。URL 非公開のまま Phase 6 へ）。

### Phase 6: フロントエンド（`feature/frontend`）

- [x] 8. **型生成有効化**: frontend に devDeps（openapi-typescript / vitest）+ `build`・`test`
       スクリプト追加、Taskfile `gen-types` 有効化、生成物を gitignore。
       `task gen-types` → frontend `typecheck` が生成型で通ることを確認。
- [x] 9. **フロント純粋ロジック**: `src/lib/`（filterByRange / productUnion / formatYen 等）を
       vitest で TDD。`task test` に frontend vitest を組み込み。
- [ ] 10. **フロント UI**: Tailwind + Recharts 導入、`App` + 各コンポーネント（Hero /
        PortfolioChart / ProductsChart / AssetsTable / PeriodSelector / MetricToggle /
        EmptyState）。vite dev proxy + `task bff` でローカル結合確認（空データ状態含む）。
- [ ] 11. **IdashFrontendStack**: `basic-auth.js`（JS 2.0 + KVS）+ `KeyValueStore` +
        Distribution（S3 OAC / `/api/*` behavior / Geo JP / 両 behavior に Function）+
        BucketDeployment。**`/api/*` の Function は Basic 認証通過後に KVS の `origin-verify` 値を
        `x-origin-verify` ヘッダへ上書き注入**（→ step 12 の BFF 検証と対）。`bin/app.ts` 配線、
        Taskfile `build-front`・`synth` deps 更新、スナップショット（asset ハッシュ正規化）。
        `task check` + `task synth` 緑。
- [ ] 12. **origin-verify（CloudFront 経由限定化・B 採用）**: `bff.main` に `x-origin-verify` を
        SSM SecureString（`/idash/<env>/origin-verify`、`common.ssm` でキャッシュ）と照合する依存を
        追加し、不一致/欠落は 403。`BffSettings` に `origin_verify_param` を追加、`IdashBffStack` は
        `ORIGIN_VERIFY_PARAM_ARN` を env で渡し当該 SSM param に `grantRead`。TestClient でヘッダ
        有無の 200/403、settings、スナップショット差分を確認。`task check` + `task synth` 緑。
- [ ] 13. **ドキュメント**: ADR-0006（ダッシュボードのアクセス制御 = CF Functions Basic 認証 + KVS
        ＋ origin-verify による CloudFront 経由限定化。**origin-verify の検証は BFF Lambda 内で行い
        Lambda Authorizer は不採用**の判断と根拠含む。背景3制約と代替案比較）— **初版は
        `docs/adr/0006-dashboard-access-control.md` に先行作成済み、実装確定後に最終化** / PROJECT_PLAN.md
        の Phase 5/6 TODO 解消・SPA フォールバック方針の更新 / README に KVS（basic-auth・
        origin-verify の2キー）と SSM（origin-verify）の手動投入手順とデプロイ順序。
- [ ] 14. **Phase 6 実デプロイ・E2E 確認**: KVS（2キー）・SSM へ秘密投入 → `task deploy`（--all）→
        CloudFront URL で Basic 認証 → ダッシュボード表示・期間セレクタ・指標トグル・実データ描画を
        確認。あわせて **API GW 直 URL への直叩きが 403**（origin-verify 欠落）になることを確認。
        issue #27 クローズ。

## 未確定事項・リスク

- **BFF コールドスタート**: コンテナ Lambda + DuckDB 初期化で初回応答数秒の可能性。個人利用の
  低頻度アクセスではほぼ毎回コールドスタート。許容し、問題なら zip + レイヤー化へ移行余地
  （PROJECT_PLAN 既定方針）。
- **infra スナップショットの揺れ**: フロント dist / bff イメージの asset ハッシュがソース変更で
  揺れる。正規化（プレースホルダ置換）の具体方式は実装時に cdk-development スキルの規約で確定。
- **`/api/*` への Basic 認証適用**: 両 behavior に Function を付け漏らすと API が素通しになる。
  スナップショットテストで両 behavior の FunctionAssociations を確認する。
- **KVS 値未投入時は全 401/403**: デプロイ手順書に「デプロイ後すみやかに KVS へ投入」を明記
  （投入前にダッシュボードは開けないだけで、データ流出方向のリスクはない）。
- **Recharts の欠測描画**: 商品入れ替え時の線の途切れは `connectNulls=false` で実現できる想定。
  実装時に確認。
- **openapi-typescript / Tailwind のバージョン**: pnpm 10.30.3 ピンの build script 承認機構と
  干渉しないか `task setup` で確認（CLAUDE.md の pnpm 注意事項）。
- **Phase 5 完了〜Phase 6 完了の間、API GW 直 URL が認証なしで存在**: 自動命名の推測困難 URL
  のみで保護（obscurity）。期間を短くする。**恒久対応は B（origin-verify で CloudFront 経由限定化）
  を Phase 6 step 12 で実装確定**（この期間だけは obscurity のまま）。
- **origin-verify の付け漏らし/取り違え**: `/api/*` Function のヘッダ注入と BFF の照合が揃わないと、
  全 403（サービス不能）か、逆に検証が実質無効化される。KVS と SSM へ**同一の秘密値**を投入する運用
  を README に明記し、Phase 6 step 14 で「CloudFront 経由=200 / API GW 直叩き=403」を両方確認する。
  秘密ローテーション時は KVS→SSM の順で反映（先に SSM を変えると正規経路が一時 403）。

## 参照リンク

- Issue: https://github.com/d-kama/idash/issues/27
- 表示項目仕様: `docs/progress/visualization-spec.md`
- ドメイン: `packages/domain/src/domain/asset.py`（`AssetRepository` / `PortfolioAsset`）/
  `notification.py`（`summarize`）
- 既存パターン: `apps/batch/src/batch/handler_notify.py`（composition root / DuckDB 設定値）/
  `apps/batch/Dockerfile`（uv sync + DuckDB 拡張同梱）/ `infra/lib/batch-stack.ts`（自動命名・
  LogGroup・アラーム方針）
- ADR: 0005（DuckDB + S3 単一 Parquet）/ 0001（CI/CD OIDC）
- 全体計画: `PROJECT_PLAN.md` Phase 5 / Phase 6・§2.3.1（1アプリ=1イメージ）
