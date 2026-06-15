# idash — iDeCo 運用状況 把握・管理アプリ 実装計画

> 本ドキュメントは Claude Code での実装引き継ぎ用。
> **確定事項**（アーキテクチャ・技術選定・構成方針）と **未決定事項（TODO）**（各機能の詳細仕様）を分けて記載する。
> TODO は実装着手時に都度確定していく前提。

---

## 1. プロジェクト概要

**プロジェクト名: idash**（iDeCo ＋ dashboard）

**目的**: iDeCo（個人型確定拠出年金）の運用状況の把握・管理を効率的にする。データを定期収集して蓄積し、Web 上で可視化＋サマリ通知することで、運用状況を一望できる状態を作る。個人利用・学習用を兼ねる。

- **バッチ**: 以下の2機能で構成
  - **データ収集バッチ**: 外部の確定拠出年金サイトへ接続してデータを収集し、リポジトリ（Google Spreadsheet）へ書き込む
  - **サマリ通知バッチ**: リポジトリから直近 N 日の収集データを取得・集計し、通知する
- **可視化 Web アプリ**: フロントエンド（React）＋ BFF（FastAPI）で構成
- **モノレポ**で管理（Python と TypeScript が混在する polyglot 構成）

---

## 2. 確定事項（Decided）

### 2.1 アーキテクチャ方針

- モノレポ管理パターンは **「アプリ + 共有ライブラリ」型**（`apps/*` と `packages/*` を分離）
- Python 側は **uv ワークスペース**、TypeScript 側は **pnpm ワークスペース** を並置
- 言語境界を明確化:
  - **Python** = `batch` / `bff` / 共有ライブラリ（`packages/*`）
  - **TypeScript** = `frontend` / `infra`（CDK）

### 2.1.1 開発ツールチェーン（Phase 0 で確定）

| 領域 | ツール | 補足 |
|---|---|---|
| Python ランタイム | **3.13**（`requires-python = ">=3.13"`） | Lambda 3.13 ベースイメージと一致 |
| Python パッケージ/WS | **uv**（ワークスペース）、ビルドバックエンド **uv_build** | 仮想ルート＋単一 `uv.lock` |
| Python lint/format | **ruff**（1ツールで lint+format） | black 不使用 |
| Python 型チェック | **ty**（Astral 製） | 不調時は mypy へ退避可 |
| Python テスト | **pytest ＋ pytest-cov** | dev dependency-group |
| TS パッケージ/WS | **pnpm**（ワークスペース） | members: `apps/frontend`, `infra` |
| TS lint/format | **Biome**（`biome.json`） | eslint/prettier 不使用 |
| TS 型チェック | **tsc**（`tsconfig.base.json` 継承） | - |
| infra テスト | **Vitest**（スナップショット） | `aws-cdk-lib/assertions` を使用 |
| CDK アプリ実行 | **tsx**（`cdk.json` の `app`） | ts-node 不使用 |
| タスクランナー | **go-task**（`Taskfile.yml`） | mise で版管理 |
| ツール版固定 | **mise**（`mise.toml`） | python/node/uv/pnpm/task を pin |

- パッケージ命名: import 名は接頭辞なし（`domain` 等）、配布名は `idash-*`、src レイアウト。
- 内部依存は `[tool.uv.sources]` の `workspace = true` で配線（依存方向は §4 のグラフに準拠）。

### 2.2 技術スタック

| コンポーネント | 技術 | AWS リソース |
|---|---|---|
| データ収集バッチ | Python | EventBridge Scheduler + Lambda |
| サマリ通知バッチ | Python | EventBridge Scheduler + Lambda |
| BFF | Python / FastAPI（+ Mangum） | API Gateway (HTTP API) + Lambda |
| フロントエンド | React / Vite / TypeScript | S3 + CloudFront |
| IaC | AWS CDK（**TypeScript**） | - |
| データストア | Google Spreadsheet | - |
| 認証情報管理 | - | SSM Parameter Store（SecureString / 標準パラメータ） |

### 2.3 主要な設計判断

- **Lambda パッケージング**: モノレポのワークスペース依存（`packages/*`）を確実に解決するため、**コンテナイメージ Lambda** を採用。Docker ビルドコンテキストは**モノレポのルート**とする。
  - 補足: BFF はユーザー対面のためコールドスタートが問題になれば、将来 zip + Lambda レイヤー化へ部分移行する余地を残す。batch は非同期のため考慮不要。
- **型の共有（polyglot 境界）**: **Pydantic スキーマを single source of truth** とし、`Pydantic → OpenAPI → TypeScript 型` の一方向で伝播。
  - フロントは生成された TS 型を import するだけ。Python コードには直接依存しない。
- **CORS 回避**: **単一 CloudFront ディストリビューション**でフロント（S3）と BFF（API GW）を束ねて**同一オリジン化**。
  - デフォルトオリジン = S3、ビヘイビア `/api/*` = API Gateway。
  - フロントは `fetch('/api/...')` と書け、CORS 設定不要。
- **EventBridge**: 旧 Rules ではなく **EventBridge Scheduler** を採用（タイムゾーン指定可能。日次収集は JST 指定が必須要件）。
- **依存方向ルール**（崩れ防止）:
  - `domain` は他に依存しない純粋なモデル
  - `apps/*`（batch/bff）は `packages/*` に依存してよいが、**apps 同士は依存させない**
  - frontend は BFF の HTTP 契約（生成型）経由でのみ接続

### 2.3.1 バッチ構成（2機能）

データ収集バッチとサマリ通知バッチは**役割・実行頻度・依存先が異なる**ため、**Lambda 関数を2つに分ける**。

- **パッケージング方針**: `apps/batch` は**1アプリ（1コンテナイメージ）**のまま、**ハンドラを2つ**用意（`handler_collect.py` / `handler_notify.py`）。CDK 側で**同一イメージから2つの Lambda 関数**を作り、`cmd`（ハンドラ）と**スケジュールを個別指定**する。
  - 利点: 共有ライブラリ・ビルド・依存解決を二重化せず、関数ごとに cron・メモリ・タイムアウト・権限を分離できる。
- **データ収集バッチ**
  - 外部の確定拠出年金サイトへ接続 → データ収集 → リポジトリ（Sheets）へ**書き込み**
  - 外部サイトはログイン必須・公開 API 非提供の可能性が高く、**スクレイピング/ヘッドレスブラウザ**が必要になる想定（**TODO**）。コンテナ Lambda なので重い依存（例: Playwright）も同梱しやすい。
  - 外部サイトのログイン認証情報は **Parameter Store の SecureString** に保管（Sheets サービスアカウントとは別パラメータ）。
- **サマリ通知バッチ**
  - リポジトリから**直近 N 日**の収集データを**読み取り** → **集計** → **通知**
  - データ収集バッチには依存せず、リポジトリ（Sheets）を介してのみ連携（疎結合）。
  - 通知チャネル（メール / Slack / LINE 等）は**未決定（TODO）**。
  - `N`（集計対象日数）はパラメータ化し、環境変数 or イベントペイロードで渡す（**TODO: 既定値・指定方法**）。
- **コンポーネント配置（確定。詳細はセクション 2.3.2 参照）**
  - ユースケース（収集/通知の手続き）… `packages/application`
  - 集計ロジック … `domain` のドメインサービス（ユースケースから委譲）
  - 外部サイト接続クライアント / 通知クライアント … `infrastructure`（`domain` のポートを実装する具象）

### 2.3.2 アプリケーション層（ユースケース）

ユースケース（業務手続きの組み立て）は `domain`（純粋なモデル）にも `apps`（アダプタ）にも属さない**第3の層**として、専用パッケージ **`packages/application`** に置く（採用案: A）。

- **責務**: orchestration 専任。「ポートからの取得 → ドメインサービス呼び出し → ポートへの出力」の手続きのみを持つ。
- **依存（許可）**: `domain`（エンティティ / ドメインサービス / **ポート＝interface**）と `schemas`（入出力 DTO）**のみ**。
- **依存（禁止）**: フレームワーク・ランタイム（**Lambda / boto3 / FastAPI / Mangum**）、および具象実装（Sheets / 外部サイト接続 / 通知の実体）。
  - これらは `apps`（アダプタ）側で**注入（DI）**する。専用パッケージにすることで「ユースケースに boto3/Mangum を import できない」を**パッケージ境界で物理的に強制**するのが A 採用の主目的。
- **ポートの配置**: リポジトリ/外部サイト/通知のインターフェース（ポート）は **`domain`** に置く。具象は `infrastructure` が `domain` のポートを実装する形となり、既存の「`infrastructure` → `domain`」依存方向と整合する。
- **集計の置き場所**: 集計（純粋な業務計算）は**ユースケースではなく `domain` のドメインサービス**に置く。ユースケースは「取得→集計呼び出し→通知」の手続きだけに保ち、集計ルールは I/O 無しでテスト可能にする。

#### ユースケースと app の対応（1:1）

| ユースケース | パッケージ | 呼び出し元 app | 概要 |
|---|---|---|---|
| `CollectPensionData` | `application` | batch（collect handler） | 外部サイトポート(read) + 年金リポジトリポート(write) を orchestration |
| `NotifySummary` | `application` | batch（notify handler） | リポジトリポート(直近N日 read) → 集計（ドメインサービス）→ 通知ポート(send) |
| `GetVisualizationData` | `application` | bff（FastAPI router） | リポジトリポート(read) → `schemas` の DTO へ整形 |

> 補足: ユースケースは app と 1:1 で app 間共有はないが、共有目的ではなく**フレームワーク非依存を構造で強制**する目的で専用パッケージ化している。

#### `infrastructure` パッケージの位置づけ（補足）

`infrastructure` は Sheets だけでなく外部サイトクライアント・通知の具象も内包するため、実態は「外部システムとのアダプタ全般＝**インフラ層**」。Phase 0 で `repository` から `infrastructure` へ改称済み。当面は広めに使い、肥大化したらサブモジュールへ分割する（**TODO: 分割要否は実装後に判断**）。

### 2.4 Google Spreadsheet 利用方針

- **書き込みは batch（データ収集）のみに限定**（Sheets はトランザクション非対応のため並行書き込みを避ける）
- 認証用サービスアカウント JSON は**バンドルせず Parameter Store の SecureString** に保管。Lambda のモジュールスコープでキャッシュ取得（コールドスタート時のみ）
- Sheets API はレート制限あり・レイテンシが大きいため、BFF が毎リクエストで直接読むのは避ける方針
  - **TODO（2.4 関連）**: 配信用キャッシュ層の採否を決定（後述）

### 2.5 機密情報管理方針（コスト最適化）

個人利用・学習用のためコストを抑える方針。機密情報は **SSM Parameter Store の SecureString（標準パラメータ）** で管理する（Secrets Manager は不採用）。

- **採用理由（コスト）**: 標準パラメータは**保管・取得とも無料**。Secrets Manager はパラメータあたり月額＋API 課金が発生するため、本プロジェクトでは Parameter Store を選択。
- **暗号化キー**: SecureString の復号は **AWS 管理キー `aws/ssm` を使用（追加料金なし）**。カスタム KMS キーは月額が発生するため**使わない**。
- **パラメータの用途別分離**（命名規約は実装時確定、例: `/idash/<env>/...`）:
  - ① Sheets サービスアカウント
  - ② 外部DC年金サイトのログイン情報
  - ③ 通知チャネルの認証情報（チャネル確定後）
- **割り切り事項**: Parameter Store には**自動ローテーション機能がない**（手動更新で運用。今回の機密は手動更新で足りる想定）。
- **取得方法**: Lambda から SSM `GetParameter`（`WithDecryption=true`）で取得し、モジュールスコープでキャッシュ。`common` に取得ユーティリティを集約。
- **IAM**: 各 Lambda には必要なパラメータへの `ssm:GetParameter(s)` を最小権限で付与（CDK の `grantRead` が生成）。暗号化キーは **AWS 管理キー `aws/ssm`** のためキーポリシーがアカウントへ復号を許可しており、**明示の `kms:Decrypt` 付与は不要**。
- **CDK での参照（確定）**: SecureString は CDK/CloudFormation では作成しない（作成済みを運用）。CDK は `ssm.StringParameter.fromSecureStringParameterAttributes` で**パラメータ名からインポート**し、`grantRead` で IAM 付与。Lambda には取得したリソースの **ARN（`parameterArn`）** を環境変数で渡す（例: `SHEETS_SA_PARAM_ARN` / `SOURCE_LOGIN_PARAM_ARN`）。実行時はその ARN を `GetParameter` の `Name` に使用。
- **TODO**:
  - 標準パラメータは1値**4KB 上限**。Google サービスアカウント JSON が超える場合の対処（Advanced は有料のため、値分割 / S3保管+鍵のみ Parameter Store 等の回避策を検討）。
  - パラメータ命名規約と環境（dev/stg/prod）プレフィックスの確定。

---

## 3. ディレクトリ構成（確定）

```
idash/
├── apps/
│   ├── batch/                  # Python: EventBridge + Lambda（2機能を1アプリに同梱）
│   │   ├── src/batch/
│   │   │   ├── handler_collect.py   # データ収集バッチのエントリ
│   │   │   └── handler_notify.py    # サマリ通知バッチのエントリ
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   ├── bff/                    # Python: API GW + Lambda (FastAPI + Mangum)
│   │   ├── src/bff/
│   │   │   ├── main.py
│   │   │   └── export_openapi.py
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── frontend/               # React / Vite / TS → S3
│       ├── src/
│       │   └── api/generated/  # OpenAPI から自動生成（編集禁止）
│       ├── package.json
│       └── vite.config.ts
├── packages/                   # Python 共有ライブラリ
│   ├── domain/                 # エンティティ / 集計=ドメインサービス / リポジトリ・ポート(interface)。他に依存しない
│   ├── application/            # ★ ユースケース(orchestration)。domain と schemas にのみ依存
│   ├── schemas/                # Pydantic スキーマ（API/バッチ I/O 共通）
│   ├── infrastructure/         # インフラ層: domain のポートを実装（Google Sheets / 外部サイト接続 / 通知の具象）
│   └── common/                 # 設定 / Parameter Store取得 / ロギング / ユーティリティ
├── infra/                      # AWS CDK (TypeScript) → pnpm member
│   ├── bin/app.ts
│   ├── lib/
│   │   ├── frontend-stack.ts
│   │   ├── bff-stack.ts
│   │   └── batch-stack.ts
│   ├── test/                   # Vitest スナップショットテスト（__snapshots__ 同梱）
│   ├── vitest.config.ts
│   ├── cdk.json                # app = npx tsx bin/app.ts
│   ├── package.json
│   └── tsconfig.json
├── pyproject.toml              # uv workspace 定義（仮想ルート / ruff・ty・pytest 設定集約）
├── pnpm-workspace.yaml         # pnpm workspace 定義
├── package.json                # pnpm ルート（Biome / typescript devDeps）
├── uv.lock
├── pnpm-lock.yaml
├── mise.toml                   # ツール版固定（python/node/uv/pnpm/task）
├── biome.json                  # TS lint + format
├── tsconfig.base.json          # TS 共有設定
├── scripts/                    # 横断スクリプト（pytest.sh 等）
├── Taskfile.yml                # 横断タスク（go-task）
├── docs/progress/              # 進捗管理ファイル（issue 単位）
└── PROJECT_PLAN.md             # 本ドキュメント
```

> 注: `packages/repository` は Phase 0 で **`packages/infrastructure`** へ改称済み（import 名 `infrastructure` / 配布名 `idash-infrastructure`）。

### ワークスペースのメンバー割り当て

- **uv workspace**: `apps/batch`, `apps/bff`, `packages/*`（`infra` は含めない）
- **pnpm workspace**: `apps/frontend`, `infra`

---

## 4. 依存・データフロー（確定）

### モジュール依存方向

```
                     domain（entities / domainサービス / ポート=interface）
                    ▲   ▲                        ▲
        implements │   │ depends                │ depends
                   │   │                        │
      infrastructure   application ──────────────┘
      （ポートの具象）  （ユースケース: orchestration / schemas にも依存）
                   ▲        ▲
        DI で具象注入│        │ ユースケース呼び出し
                   │        │
                 apps（batch / bff: 薄いアダプタ）   frontend ←（生成型）← bff
```

- `domain` は他に依存しない（`common` のユーティリティ利用は許容範囲で判断）。
- `application` は `domain`（ポート/ドメインサービス）と `schemas` のみに依存。フレームワーク・具象には依存しない。
- `infrastructure` は `domain` のポートを実装する具象（Sheets / 外部サイト / 通知）。
- `apps` は具象を `application` のユースケースへ DI し、ユースケースを呼ぶだけの薄いアダプタ。**apps 同士は依存させない**。
- frontend は bff の HTTP 契約（生成型）経由でのみ接続。

### 実行時データフロー

```
[EventBridge Scheduler]──cron(JST)──▶[Lambda: データ収集]──収集──▶ 外部DC年金サイト
                                            │
                                          write
                                            ▼
                                  [Google Spreadsheet]
                                            │
                                          read（直近N日）
                                            ▼
[EventBridge Scheduler]──cron(JST)──▶[Lambda: サマリ通知]──集計──▶ 通知チャネル(未定)

                       （可視化系）
[CloudFront]──/──▶[S3: React]        [Lambda: bff(FastAPI)]──read──▶[Google Spreadsheet]
     └────/api/*──────────▶[API Gateway]──────┘
```

- 2つのバッチは **Sheets を介してのみ連携**（直接呼び出さない疎結合）。
- スケジュールは機能ごとに独立（収集と通知で頻度・時刻が異なる想定）。

---

## 5. CDK スタック構成（確定）

| スタック | 内容 |
|---|---|
| **IdashFrontendStack** | S3（OAC・非公開）+ CloudFront + Vite ビルド成果物デプロイ + SPA フォールバック（403/404 → index.html） |
| **IdashBffStack** | HTTP API + Lambda（コンテナ）+ Parameter Store 読取権限（`ssm:GetParameter` + `aws/ssm` の `kms:Decrypt`） |
| **IdashBatchStack** | EventBridge Scheduler ×2 + Lambda（コンテナ）×2 + Parameter Store 読取権限（`ssm:GetParameter` + `aws/ssm` の `kms:Decrypt`）。同一イメージから `cmd` 違いで2関数（収集/通知）を生成し、スケジュール・メモリ・タイムアウト・権限を個別設定。収集は外部サイト認証情報、通知は通知チャネル認証情報の読取権限を付与 |

- スタック間の値受け渡し（例: API GW ドメイン → IdashFrontendStack）は `bin/app.ts` で**プロパティ渡し**にする（クロススタック参照より明示的）。
- **デプロイ順序**: `型生成 → フロントビルド → cdk deploy`（BucketDeployment がフロントの `dist` を必要とするため）。

---

## 6. 横断タスク（Taskfile）

> 「いま動くタスク」のみ実装し、各アプリ実装が入る後続フェーズで将来タスクを有効化する方針（将来タスクはコメント据置）。

実装済み（Phase 0 + Phase 1 で順次追加）:

```yaml
version: '3'
tasks:
  setup:      # 依存解決
    cmds: [uv sync, pnpm install]
  lint:       # Python: ruff / TS: Biome
    cmds: [uv run ruff check ., pnpm exec biome lint .]
  format:     # Python: ruff format / TS: Biome
    cmds: [uv run ruff format ., pnpm exec biome format --write .]
  typecheck:  # Python: ty / TS: tsc（各パッケージの typecheck script）
    cmds: [uv run ty check, pnpm -r run typecheck]
  test:       # pytest（exit 5 は成功扱い）＋ infra Vitest（Phase 1〜）
    cmds: [sh scripts/pytest.sh, pnpm --filter @idash/infra test]
  synth:      # CDK synth（認証不要・デプロイ可能検証。Phase 1〜）
    cmds: [pnpm --filter @idash/infra exec cdk synth]
  check:      # lint + typecheck + test を一括
    cmds: [{task: lint}, {task: typecheck}, {task: test}]
```

将来タスク（コメント据置 → 後続フェーズで有効化）: `gen-types`（Pydantic→OpenAPI→TS, Phase 5/6）/ `build-front`（Phase 6）/ フル `deploy`（`--all`, Phase 6）/ `batch`・`bff`・`front`（各ローカル実行）。

実 deploy（認証後・参考）:

```bash
aws login
pnpm --filter @idash/infra exec cdk bootstrap aws://<ACCOUNT_ID>/ap-northeast-1   # 初回のみ
pnpm --filter @idash/infra exec cdk deploy --require-approval never
```

---

## 7. 実装計画（フェーズ別）

> フェーズは「**インフラの足場 → CI/CD → 機能ごとに実装〜デプロイ**」の順で進める（機能は縦切り。各機能はデプロイ可能な状態まで一気通貫で仕上げる）。各フェーズ内の詳細 TODO は着手時に確定する。

### Phase 0: リポジトリ初期化（✅ 完了 / issue-1）
- [x] モノレポのディレクトリ骨格、uv/pnpm ワークスペース、各 `pyproject.toml` / `package.json` 雛形、内部依存配線
- [x] ツールチェーン導入（ruff / ty / pytest・pytest-cov、Biome / tsc、go-task、mise、uv_build）… §2.1.1
- [x] `Taskfile.yml` / `.gitignore` / README / lockfile

### Phase 1: インフラ動作確認（infra の足場）（✅ 完了 / issue-2）
> アプリ・パッケージ実装は行わず、**infra に必要な最低限**で `cdk synth` グリーン＋ snapshot テストが通る土台を確認する。
- [x] infra のテスト/実行系を導入（**Vitest** スナップショット、**tsx**、`@types/node`）
- [x] `IdashBatchStack`（**collect のみ**）を実装: プレースホルダ Lambda（`Code.fromInline`）/ 予約同時実行=1 / timeout 5分 / memory 1024 / 明示 LogGroup(7日) / EventBridge Scheduler（JST 09:00）/ SSM `fromSecureStringParameterAttributes` インポート＋`grantRead`＋環境変数に ARN
- [x] `bin/app.ts`（batch のみ結線、env-agnostic account / region ap-northeast-1）
- [x] スナップショットテスト、`task synth` / `task check` グリーン
- [x] 実 deploy 手順を文書化（実 deploy はユーザー実施 / README に記載）
- [x] EventBridge Scheduler L2/L1 の判定 → **解決**: aws-cdk-lib 2.259.0 で L2 `Schedule` が stable のため **L2 採用**（L1 フォールバック不要）
- [ ] **残 TODO（後続で解消）**: Lambda はプレースホルダ（Phase 3 でコンテナ化＝`DockerImageFunction` へ差替・snapshot 撮り直し）、notify は Phase 4、実 deploy はユーザー再認証後に実施

### Phase 2: CI/CD（GitHub Actions）（grill 済み / issue-3）
> 単一ワークフロー `cicd.yml` で **CI（PR 検証）と CD（main 自動 deploy ＋ 手動）** を束ねる。デプロイ対象は当面 `IdashBatchStack`（プレースホルダ）のみだが、パイプラインを早期に疎通検証する。
- [ ] `.github/workflows/cicd.yml`: トリガ = `pull_request` / `push`(main) / `workflow_dispatch`
- [ ] `check` ジョブ: `jdx/mise-action`（`mise.toml` を単一ソース）→ `task setup:ci`（frozen install）→ `task check` → `task synth`。`~/.cache/uv`（uv.lock keyed）＋ pnpm store（pnpm-lock keyed）をキャッシュ。`concurrency` で PR の進行中 run をキャンセル
- [ ] `deploy` ジョブ: `needs: check`、`if` = push(main) または `workflow_dispatch`。`permissions: id-token: write`。`aws-actions/configure-aws-credentials`（role = `vars.AWS_DEPLOY_ROLE_ARN` / region ap-northeast-1）→ `cdk deploy --all --require-approval never`。deploy の `concurrency` は**非キャンセル**（CloudFormation 中断回避）
- [ ] `Taskfile.yml`: `setup:ci` を追加（`uv sync --frozen` / `pnpm install --frozen-lockfile`）。ツール版は `mise.toml` 管理（uv/node/task は緩め、**pnpm は 10.30.3 に固定**＝latest が CI で pnpm 11 を引き込み build script 承認機構が壊れたため）。build script 承認は `pnpm-workspace.yaml` の `onlyBuiltDependencies`（esbuild）
- [ ] **確定事項**: AWS 認証は **GitHub OIDC（長期キー不使用）**。準備済み OIDC ロールが **CDK bootstrap ロールを `sts:AssumeRole`** する標準形。bootstrap 済み・ロール ARN は **repo Variable に保管済み**（AWS 側リソースは作成不要）
- [ ] **見送り（後続で解消 / 不採用）**:
  - パスフィルタによるジョブ分割は **YAGNI**（重い build が入る Phase 3/6 で再検討）
  - Docker ビルドキャッシュ（ルート context）は Dockerfile が出る **Phase 3** から
  - AWS Budgets / Cost Anomaly Detection は**不採用**（本プロジェクトでは入れない）

### Phase 3: データ収集バッチ 実装〜デプロイ
> 関連 `packages`（collect 経路）＋ `apps/batch` collect ＋ Dockerfile ＋ コンテナ Lambda 化 ＋ デプロイまで。
- [ ] `domain`: DC年金ドメインモデル・ポート（リポジトリ/外部サイト interface）… **TODO: モデル項目・シグネチャ**
- [ ] `schemas`: 収集 I/O の Pydantic スキーマ … **TODO: 項目**
- [ ] `infrastructure`: `domain` ポートの具象（Google Sheets: gspread 等、外部サイトクライアント）… **TODO: シート構造・接続方式**
- [ ] `common`: 設定ローダ / Parameter Store（SecureString）取得 / ロギング基盤
- [ ] `application`: `CollectPensionData` ユースケース（domain・schemas のみ依存、フレームワーク非依存）
- [ ] `apps/batch/handler_collect.py`（薄いアダプタ。具象を DI して呼ぶ）
- [ ] `apps/batch/Dockerfile`（uv workspace 解決込み。ルートを context に `COPY packages/`、`uv sync --package batch --no-dev --frozen`）
- [ ] `IdashBatchStack` の collect Lambda を **プレースホルダ → `DockerImageFunction.fromImageAsset` へ差替**（必要なら memory 2048 へ）。snapshot 更新
- [ ] 収集スケジュール最終確定（JST）/ Lambda 上限15分の評価（超過時 Step Functions 検討）
- [ ] 実デプロイ＆動作確認
- [ ] **TODO: 対象サイト・収集項目・収集ロジック / 認証情報・多要素認証の有無 / 利用規約・自動アクセス可否**

### Phase 4: サマリ通知バッチ 実装〜デプロイ
> Sheets を介してのみ collect と連携（疎結合）。
- [ ] `domain`: 集計ドメインサービス（I/O 無しでテスト可能）… **TODO: 集計ルール**
- [ ] `domain`/`schemas`: 通知ポート・サマリ DTO
- [ ] `infrastructure`: 通知クライアント具象（チャネル確定後）… **TODO: メール/Slack/LINE 等**
- [ ] `application`: `NotifySummary` ユースケース（直近 N 日 read → 集計 → 通知 send）
- [ ] `apps/batch/handler_notify.py`（薄いアダプタ）。同一イメージから2 Lambda 関数（cmd 違い）を CDK で生成
- [ ] `IdashBatchStack` に notify Lambda ＋ 通知スケジュール（JST）＋ 通知認証情報の `grantRead`
- [ ] 実デプロイ＆動作確認
- [ ] **TODO: 通知チャネルと認証情報管理 / 集計内容・サマリ項目 / N の既定値・指定方法 / 通知頻度・時刻**

### Phase 5: BFF 実装〜デプロイ
- [ ] `application`: `GetVisualizationData` ユースケース、`schemas`: API レスポンス DTO
- [ ] `apps/bff`: FastAPI + Mangum（`handler = Mangum(app)`）、ルーターは薄いアダプタ＋DI、`export_openapi.py`
- [ ] `apps/bff/Dockerfile`、`IdashBffStack`（HTTP API + コンテナ Lambda + SSM 読取 + 予約同時実行=3 + スロットリング）
- [ ] 型生成パイプライン（Pydantic → OpenAPI → TS、`gen-types` タスク有効化）
- [ ] 実デプロイ＆動作確認
- [ ] **TODO: エンドポイント/レスポンス仕様 / Sheets 直読み or キャッシュ層（§9）**

### Phase 6: フロントエンド 実装〜デプロイ
- [ ] `apps/frontend`: Vite + React + TS 本実装、生成型 import（`api/generated`）、API クライアント（`fetch('/api/...')`）
- [ ] `IdashFrontendStack`（S3 + CloudFront 同一オリジン化 + SPA フォールバック + Geo 制限(JP) + CloudFront Functions IP 制限）
- [ ] `bin/app.ts` でスタック間プロパティ受け渡し（API GW ドメイン → Frontend）、デプロイ順序（型生成 → フロントビルド → `cdk deploy`）
- [ ] **TODO: 画面構成・可視化内容 / 許可IPの確定（IP変動時は秘密トークン方式）/ 環境分離(dev/stg/prod) / 独自ドメイン・ACM**

### 横断（全フェーズ共通の確定事項）
- **Lambda は VPC に入れない**（NAT Gateway 課金回避。§10）。
- CloudWatch Logs は保持期間を設定（7〜14日目安、コスト抑制）。
- コスト暴発対策（§11）は該当スタックの実装時に組み込む（予約同時実行＝Phase 1/3/4/5、API スロットリング＝Phase 5、Geo/IP 制限＝Phase 6）。Budgets は不採用（§11）。

---

## 8. 未決定事項（TODO）一覧（横断）

実装着手前〜途中で確定が必要な事項を集約。

### ドメイン・データ
- [ ] DC年金ドメインモデルの項目（口座 / 拠出記録 / 運用商品マスタ / 残高 など）
- [ ] Google Spreadsheet のシート設計（テーブル構造・カラム・キー）
- [ ] データ収集元（対象 DC年金サイト）と収集項目・収集ロジック
- [ ] 外部サイトの接続方式（公開API有無 / スクレイピング / ヘッドレスブラウザ）
- [ ] 外部サイトのログイン認証情報の管理方式・多要素認証等の有無
- [ ] 外部サイトの利用規約・自動アクセス可否の確認
- [ ] サマリ通知の集計内容・サマリ項目
- [ ] 通知チャネル（メール/Slack/LINE 等）と認証情報管理
- [ ] 集計対象日数 N の既定値・指定方法
- [ ] 収集頻度・通知頻度・各スケジュール時刻（JST）
- [ ] 共有コンポーネントの packages 配置（外部サイトクライアント / 集計ロジック / 通知クライアント）

### アプリ仕様
- [ ] BFF が公開するエンドポイント一覧とレスポンススキーマ
- [ ] フロントの画面構成・可視化内容（指標、グラフ種別、期間軸など）
- [ ] 認証・認可の要否（アプリ利用者のログイン有無）… **未検討**

### インフラ・運用
- [ ] 環境分離（dev/stg/prod）と命名・アカウント戦略
- [ ] 独自ドメイン / ACM 証明書の利用有無
- [x] ~~Python ランタイムバージョン~~ → **3.13 に確定**（Phase 0）
- [ ] 配信用キャッシュ層（S3-JSON）の採否（セクション 9）
- [ ] アクセス制御の確定（セクション11）: 許可IPの確定、IP変動時の秘密トークン方式への切替要否
- [x] ~~Budgets / Cost Anomaly Detection を CDK 化するか手動設定か~~ → **不採用に決定**（Phase 2 / §11）
- [ ] CI/CD 基盤（GitHub Actions 想定）の詳細
- [ ] 監視・アラート（CloudWatch Logs / メトリクス / 失敗通知）方針 … **未検討**
- [ ] バッチ失敗時のリトライ / 冪等性の方針 … **未検討**

### バージョン確認が必要な箇所（着手時に最新を確認）
- [ ] CDK `aws-scheduler` / `aws-scheduler-targets` の `timeZone` 指定の正確な API 形
- [ ] CDK の Lambda 関連モジュール、Lambda ランタイム最新状況
- [ ] `openapi-typescript` の最新利用方法

---

## 9. 要検討事項: Sheets 直読み vs 配信用キャッシュ

Google Sheets API はレート制限・レイテンシ（数百ms〜秒）があり、BFF が毎リクエストで直接読むとスロットリングと体感遅延を招く懸念がある。以下の選択肢から決定する（**TODO**）。

- **案A（最小構成）**: BFF のモジュールスコープに短い TTL のメモリキャッシュを置き、Sheets を直読み
- **案B（推奨・拡張）**: batch が Sheets 書き込みと同時に**可視化用の整形済み JSON を S3 に出力**。BFF（またはフロント）はそれを読む
  - Sheets = 「人が確認・編集できるマスタ」、S3-JSON = 「配信用キャッシュ」と役割分担
  - 既存の S3 + CloudFront を流用でき追加コストが小さい

> 初期は案A で立ち上げ、負荷・体感に応じて案B へ拡張する判断も可。

---

## 10. コスト概算（2026年6月時点・要再確認）

> 金額は変動しうるため目安。リージョンは東京（ap-northeast-1）想定。

### 前提（利用頻度）

| 処理 | 頻度 | 月間回数 |
|---|---|---|
| データ収集バッチ | 日次1回 | 約30回 |
| サマリ通知バッチ | 週1回 | 約4〜5回 |
| ダッシュボード確認 | 週1回 | 約4〜5回（1回で API 数リクエスト） |

Lambda 起動は合計でも月40回前後、API も月数十リクエスト。無料枠を大きく下回る。

### サービス別概算

| サービス | 月額 | 備考 |
|---|---|---|
| Lambda（収集/通知/BFF） | **$0** | 無料枠（100万req + 40万GB-秒）内。ヘッドレスブラウザで2GB×30秒×30回でも無料枠の0.5%程度 |
| API Gateway (HTTP API) | **$0** | 月数十reqのみ。無料枠終了後でも $0.001 未満 |
| S3 | **〜$0** | 静的数MB + 数十req。数セント未満 |
| CloudFront | **$0** | 無料枠（1TB/月 + 1,000万req）内 |
| EventBridge Scheduler | **$0** | 月35回程度 |
| Parameter Store（SecureString 標準） | **$0** | 保管・取得・`aws/ssm`復号すべて無料 |
| CloudWatch Logs | **$0〜0.1** | 低頻度。保持期間7〜14日設定推奨 |
| **ECR（コンテナイメージ保管）** | **$0.06〜0.25** | $0.10/GB・月。bff/batch の2イメージ計0.6〜1.5GB。**唯一の実費** |

### 合計

**約 $0.1〜0.6 / 月（≒ 月15〜90円程度）**。実費はほぼ ECR 保管料のみ。

### 想定外課金の注意点

- **NAT Gateway を発生させない**: Lambda を VPC に入れると NAT Gateway が約 **$32/月**＋通信量で跳ねる。**本構成は Lambda を VPC に入れない**（Sheets も外部サイトもインターネット経由のため VPC 不要）。← 最重要
- **無料枠の期間制限**: CloudFront/API Gateway の一部無料枠は最初の12ヶ月。13ヶ月目以降に少額（月数セント）発生の可能性。
- **CloudWatch Logs 無限保持**: 塵積もり防止に保持期間を設定。
- **KMS カスタムキー不使用**: 作ると $1/月/キー。`aws/ssm` 管理キー利用で回避済み。

---

## 11. コスト暴発対策（単独利用前提・確定方針）

利用者は1名のみ。**WAF は不採用**（固定費回避）とし、**無料で実現できる範囲**で「大量アクセスでも料金が跳ねない」設計を構造で担保する。考え方は ①入口を絞る ②ハードキャップで止める ③即検知する の3層。

### 採用する対策（確定）

1. **Lambda 予約同時実行（reserved concurrency）** ← 課金の物理上限。最重要
   - 例: BFF=3、収集=1、通知=1。何リクエスト来てもこの数しか同時起動せず、Lambda 課金の上限が確定する。無料。
2. **API Gateway スロットリング** ← 無料
   - rate / burst を小さく設定（例: rate=5req/s, burst=10）。一人利用には十分で、攻撃時もここで頭打ち。
3. **CloudFront Geo 制限＝日本のみ** ← 無料
   - ディストリビューション設定で日本以外を全ブロック。海外ボットの大半を入口で遮断。
4. **IP 制限** ← 無料
   - **CloudFront Functions** で送信元IP（`CloudFront-Viewer-Address`）を判定し、許可IP以外を拒否。
   - **前提・TODO**: 自宅/モバイルの固定的なIPがあること。IP が頻繁に変動する環境では運用しづらいため、その場合は「CloudFront Functions による秘密トークン検査」へ切替可能な含みを残す。
### 不採用（確定）

- **AWS WAF**: レートベースルールは強力だが固定費（ルール月額＋リクエスト課金）が発生するため**使わない**。上記1〜4の無料セットで代替し、必要を感じた時点で再検討する。
- **AWS Budgets / Cost Anomaly Detection**: 無料だが本プロジェクトでは**入れない**（Phase 2 グリルで決定）。実費がほぼ ECR 保管料のみ（§10）で暴発経路が構造的に塞がれているため、コスト監視の追加運用を持たない。必要を感じた時点で手動設定で再検討する。

### 各対策の実装先（CDK）

| 対策 | 実装スタック / 場所 |
|---|---|
| 予約同時実行（BFF） | `IdashBffStack`（Lambda 関数プロパティ） |
| 予約同時実行（収集/通知） | `IdashBatchStack`（各 Lambda 関数プロパティ） |
| API スロットリング | `IdashBffStack`（HTTP API のステージ設定） |
| Geo 制限 | `IdashFrontendStack`（CloudFront Distribution） |
| IP 制限 | `IdashFrontendStack`（CloudFront Functions） |
| ~~Budgets / Anomaly Detection~~ | **不採用**（Phase 2 で決定。§11「不採用」参照） |

---

## 12. コードスケルトン（確定仕様反映版）

> 以下は確定仕様（idash 命名 / Parameter Store SecureString / 予約同時実行 / API スロットリング / CloudFront Geo・IP 制限 / batch 2ハンドラ / application 経由 DI）を反映した出発点。
> CDK・ライブラリは更新が速いため、着手時にバージョン確認のうえ調整すること（特に `aws-scheduler` の `TimeZone`、CloudFront Functions ランタイム）。
> 細部（IAM 最小権限の絞り込み、エラーハンドリング等）は実装時に補完する前提。

### 12.1 IdashBffStack（infra/lib/bff-stack.ts）

```typescript
import { Stack, StackProps, Duration } from 'aws-cdk-lib';
import { DockerImageFunction, DockerImageCode } from 'aws-cdk-lib/aws-lambda';
import { HttpApi } from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';
import * as path from 'path';

interface IdashBffStackProps extends StackProps {
  envName: string; // 'dev' | 'prod' など
}

export class IdashBffStack extends Stack {
  public readonly httpApiUrl: string;

  constructor(scope: Construct, id: string, props: IdashBffStackProps) {
    super(scope, id, props);
    const { envName } = props;

    // Parameter Store(SecureString)。SecureString は fromSecureStringParameterAttributes で参照
    const sheetsSaParamName = `/idash/${envName}/sheets-sa`;

    const fn = new DockerImageFunction(this, 'BffFn', {
      // ビルドコンテキストはモノレポルート（COPY packages/ のため）
      code: DockerImageCode.fromImageAsset(path.join(__dirname, '../..'), {
        file: 'apps/bff/Dockerfile',
      }),
      memorySize: 512,
      timeout: Duration.seconds(29), // HTTP API の上限に合わせる
      reservedConcurrentExecutions: 3, // ★コスト暴発対策: 同時実行ハードキャップ
      environment: {
        ENV_NAME: envName,
        SHEETS_SA_PARAM: sheetsSaParamName,
      },
    });

    // Parameter Store 読取 + aws/ssm 復号 権限（最小権限は実装時に調整）
    StringParameter.fromSecureStringParameterAttributes(this, 'SheetsSaParam', {
      parameterName: sheetsSaParamName,
    }).grantRead(fn);

    const api = new HttpApi(this, 'IdashHttpApi', {
      defaultIntegration: new HttpLambdaIntegration('BffInteg', fn),
    });

    // ★コスト暴発対策: スロットリング（既定ステージ）
    const stage = api.defaultStage!.node.defaultChild as any;
    stage.defaultRouteSettings = {
      throttlingRateLimit: 5,
      throttlingBurstLimit: 10,
    };

    this.httpApiUrl = api.apiEndpoint;
  }
}
```

### 12.2 IdashBatchStack（infra/lib/batch-stack.ts）

同一イメージから収集/通知の2関数を `cmd` 違いで生成し、スケジュールを個別に設定。

> **Phase 1（issue-2）での差分**（下記は Phase 3/4 完了時の最終形。現フェーズの権威ある仕様は `docs/progress/issue-2.md`）:
> - Lambda は **プレースホルダ zip**（`lambda.Function` + `Code.fromInline` / `Runtime.PYTHON_3_13`）。`DockerImageFunction` への差替は **Phase 3**。
> - 実装は **collect のみ**（notify は Phase 4）。collect は memory **1024** / timeout **5分** / 予約同時実行 **1**。
> - 収集スケジュールは **JST 09:00**。
> - SSM は `fromSecureStringParameterAttributes` でインポート→`grantRead`→環境変数に **ARN**（`SHEETS_SA_PARAM_ARN` 等）。`kms:Decrypt` の明示付与は不要（`aws/ssm`）。
> - 明示 `LogGroup`（保持 **7日** + `RemovalPolicy.DESTROY`）。

```typescript
import { Stack, StackProps, Duration } from 'aws-cdk-lib';
import {
  DockerImageFunction, DockerImageCode, IFunction,
} from 'aws-cdk-lib/aws-lambda';
import { Schedule, ScheduleExpression, TimeZone } from 'aws-cdk-lib/aws-scheduler';
import { LambdaInvoke } from 'aws-cdk-lib/aws-scheduler-targets';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';
import * as path from 'path';

interface IdashBatchStackProps extends StackProps {
  envName: string;
}

export class IdashBatchStack extends Stack {
  constructor(scope: Construct, id: string, props: IdashBatchStackProps) {
    super(scope, id, props);
    const { envName } = props;

    const root = path.join(__dirname, '../..');
    const sheetsSaParamName = `/idash/${envName}/sheets-sa`;
    const sourceLoginParamName = `/idash/${envName}/source-login`;
    const notifyParamName = `/idash/${envName}/notify-credential`;

    // 共通: 同一イメージ・cmd違いの関数を作るヘルパ
    const makeFn = (name: string, cmd: string[], memory: number): IFunction =>
      new DockerImageFunction(this, name, {
        code: DockerImageCode.fromImageAsset(root, {
          file: 'apps/batch/Dockerfile',
          cmd, // ハンドラを関数ごとに上書き
        }),
        memorySize: memory,
        timeout: Duration.minutes(10),
        reservedConcurrentExecutions: 1, // ★同時実行ハードキャップ
        environment: { ENV_NAME: envName },
      });

    // データ収集（外部サイト接続。ヘッドレスブラウザ利用ならメモリ多め）
    const collectFn = makeFn('CollectFn', ['batch.handler_collect.handler'], 2048);
    StringParameter.fromSecureStringParameterAttributes(this, 'SheetsSaForCollect', {
      parameterName: sheetsSaParamName,
    }).grantRead(collectFn);
    StringParameter.fromSecureStringParameterAttributes(this, 'SourceLogin', {
      parameterName: sourceLoginParamName,
    }).grantRead(collectFn);

    // サマリ通知
    const notifyFn = makeFn('NotifyFn', ['batch.handler_notify.handler'], 512);
    StringParameter.fromSecureStringParameterAttributes(this, 'SheetsSaForNotify', {
      parameterName: sheetsSaParamName,
    }).grantRead(notifyFn);
    StringParameter.fromSecureStringParameterAttributes(this, 'NotifyCredential', {
      parameterName: notifyParamName,
    }).grantRead(notifyFn);

    // 収集: 日次（JST 06:00）
    new Schedule(this, 'DailyCollect', {
      schedule: ScheduleExpression.cron({
        minute: '0', hour: '6', timeZone: TimeZone.ASIA_TOKYO,
      }),
      target: new LambdaInvoke(collectFn, {}),
    });

    // 通知: 週次（JST 月曜 08:00）
    new Schedule(this, 'WeeklyNotify', {
      schedule: ScheduleExpression.cron({
        minute: '0', hour: '8', weekDay: 'MON', timeZone: TimeZone.ASIA_TOKYO,
      }),
      target: new LambdaInvoke(notifyFn, {}),
    });
  }
}
```

### 12.3 IdashFrontendStack（infra/lib/frontend-stack.ts）

Geo 制限（日本のみ）と CloudFront Functions による IP 制限を内包。

```typescript
import { Stack, StackProps } from 'aws-cdk-lib';
import { Bucket, BlockPublicAccess } from 'aws-cdk-lib/aws-s3';
import {
  Distribution, GeoRestriction, Function as CfFunction,
  FunctionCode, FunctionEventType,
} from 'aws-cdk-lib/aws-cloudfront';
import { S3BucketOrigin, HttpOrigin } from 'aws-cdk-lib/aws-cloudfront-origins';
import { BucketDeployment, Source } from 'aws-cdk-lib/aws-s3-deployment';
import { Construct } from 'constructs';

interface IdashFrontendStackProps extends StackProps {
  apiDomain: string;      // BFF の API GW ドメイン（https:// を除いたホスト名）
  allowedIps: string[];   // 許可IP（CIDR ではなく完全一致の例。実装時に方式確定）
}

export class IdashFrontendStack extends Stack {
  constructor(scope: Construct, id: string, props: IdashFrontendStackProps) {
    super(scope, id, props);
    const { apiDomain, allowedIps } = props;

    const bucket = new Bucket(this, 'SiteBucket', {
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
    });

    // ★IP制限: CloudFront Functions（viewer request）。event.viewer.ip で送信元IP判定
    const ipAllowlistFn = new CfFunction(this, 'IpAllowlistFn', {
      code: FunctionCode.fromInline(`
function handler(event) {
  var allowed = ${JSON.stringify(allowedIps)};
  var ip = event.viewer.ip;
  if (allowed.indexOf(ip) === -1) {
    return { statusCode: 403, statusDescription: 'Forbidden' };
  }
  return event.request;
}`),
    });

    const dist = new Distribution(this, 'Dist', {
      defaultBehavior: {
        origin: S3BucketOrigin.withOriginAccessControl(bucket),
        functionAssociations: [{
          function: ipAllowlistFn,
          eventType: FunctionEventType.VIEWER_REQUEST,
        }],
      },
      additionalBehaviors: {
        '/api/*': {
          origin: new HttpOrigin(apiDomain),
          functionAssociations: [{
            function: ipAllowlistFn,
            eventType: FunctionEventType.VIEWER_REQUEST,
          }],
        },
      },
      // ★Geo制限: 日本のみ許可
      geoRestriction: GeoRestriction.allowlist('JP'),
      defaultRootObject: 'index.html',
      errorResponses: [ // SPA フォールバック
        { httpStatus: 403, responseHttpStatus: 200, responsePagePath: '/index.html' },
        { httpStatus: 404, responseHttpStatus: 200, responsePagePath: '/index.html' },
      ],
    });

    new BucketDeployment(this, 'DeploySite', {
      sources: [Source.asset('../apps/frontend/dist')], // Vite ビルド成果物
      destinationBucket: bucket,
      distribution: dist,
      distributionPaths: ['/*'],
    });
  }
}
```

> 注: IP制限は完全一致の簡易例。CIDR 範囲やIP変動への対応が必要なら、関数ロジックの拡張 or 秘密トークン方式へ切替（セクション11 の TODO）。Geo制限と IP制限はいずれも CloudFront 標準機能/Functions で**追加固定費なし**。

### 12.4 bin/app.ts（スタック結線）

```typescript
#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import { IdashBffStack } from '../lib/bff-stack';
import { IdashBatchStack } from '../lib/batch-stack';
import { IdashFrontendStack } from '../lib/frontend-stack';

const app = new App();
const envName = app.node.tryGetContext('env') ?? 'dev';
const env = { region: 'ap-northeast-1' }; // account は実行環境から

const bff = new IdashBffStack(app, `Idash-${envName}-Bff`, { env, envName });
new IdashBatchStack(app, `Idash-${envName}-Batch`, { env, envName });
new IdashFrontendStack(app, `Idash-${envName}-Frontend`, {
  env,
  apiDomain: '', // TODO: bff.httpApiUrl からホスト名抽出して渡す（実装時に結線）
  allowedIps: app.node.tryGetContext('allowedIps') ?? [],
});
```

> `apiDomain` の受け渡しは、`httpApiUrl`（`https://xxx.execute-api...`）からホスト名を取り出す必要がある。同一スタックにまとめる / SSM 経由で渡す等、実装時に方式確定（セクション5 のプロパティ渡し方針に従う）。

### 12.5 apps/bff/Dockerfile

```dockerfile
FROM public.ecr.aws/lambda/python:3.12
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
# ビルドコンテキストはモノレポルート
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/bff/ apps/bff/
RUN uv sync --package bff --no-dev --frozen
CMD ["bff.main.handler"]
```

### 12.6 apps/batch/Dockerfile

CMD は CDK 側で関数ごとに上書きするため、ここでは既定値（収集）を置く程度。

```dockerfile
FROM public.ecr.aws/lambda/python:3.12
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/batch/ apps/batch/
RUN uv sync --package batch --no-dev --frozen
# 既定（CDK で handler_collect / handler_notify に上書き）
CMD ["batch.handler_collect.handler"]
```

> ヘッドレスブラウザ（Playwright 等）を収集で使う場合、ブラウザバイナリと依存の追加が必要（イメージ肥大化。セクション 10 のコスト・Phase 3 の TODO 参照）。

### 12.7 apps/bff/src/bff/main.py（FastAPI + Mangum + ユースケース DI）

```python
from fastapi import FastAPI, Depends
from mangum import Mangum

# application: ユースケース（フレームワーク非依存）
from application.get_visualization_data import GetVisualizationData
# repository: domain ポートの具象実装
from infrastructure.sheets import SheetsPensionRepository

app = FastAPI(title="idash BFF")


def get_usecase() -> GetVisualizationData:
    # 具象をここで注入（ユースケースは FastAPI/boto3 を知らない）
    repo = SheetsPensionRepository()
    return GetVisualizationData(repo)


@app.get("/api/summary")
def get_summary(uc: GetVisualizationData = Depends(get_usecase)):
    return uc.execute()  # schemas の DTO を返す


# Lambda エントリ
handler = Mangum(app)
```

### 12.8 apps/batch のハンドラ2種（薄いアダプタ）

```python
# apps/batch/src/batch/handler_collect.py
from application.collect_pension_data import CollectPensionData
from infrastructure.sheets import SheetsPensionRepository
from infrastructure.source_site import SourceSiteClient


def handler(event, context):
    # 具象を注入してユースケースを呼ぶだけ
    uc = CollectPensionData(
        source=SourceSiteClient(),
        repo=SheetsPensionRepository(),
    )
    return uc.execute()
```

```python
# apps/batch/src/batch/handler_notify.py
from application.notify_summary import NotifySummary
from infrastructure.sheets import SheetsPensionRepository
from infrastructure.notifier import Notifier


def handler(event, context):
    days = int((event or {}).get("days", 7))  # 既定 N=7（指定方法は TODO）
    uc = NotifySummary(
        repo=SheetsPensionRepository(),
        notifier=Notifier(),
    )
    return uc.execute(days=days)
```

### 12.9 ユースケース（application）と ポート（domain）の最小形

```python
# packages/application/src/application/notify_summary.py
# フレームワーク・具象に依存しない。domain のポートと schemas のみに依存。
from domain.ports import PensionRepositoryPort, NotifierPort
from domain.summary_service import summarize  # 集計はドメインサービス


class NotifySummary:
    def __init__(self, repo: PensionRepositoryPort, notifier: NotifierPort):
        self._repo = repo
        self._notifier = notifier

    def execute(self, days: int):
        records = self._repo.fetch_recent(days)   # ポート経由 read
        summary = summarize(records)              # 集計（ドメインサービス）
        self._notifier.send(summary)              # ポート経由 send
        return {"notified": True, "days": days}
```

```python
# packages/domain/src/domain/ports.py
# ポート（インターフェース）は domain に置く。具象は repository が実装する。
from typing import Protocol, Sequence
from domain.models import PensionRecord, Summary


class PensionRepositoryPort(Protocol):
    def fetch_recent(self, days: int) -> Sequence[PensionRecord]: ...
    def save(self, records: Sequence[PensionRecord]) -> None: ...


class SourceSitePort(Protocol):
    def collect(self) -> Sequence[PensionRecord]: ...


class NotifierPort(Protocol):
    def send(self, summary: Summary) -> None: ...
```

> 上記の `models` / `summarize` / 各ポートのシグネチャは**最小の仮置き**。確定仕様（ドメイン項目・集計内容・N の指定方法）に合わせて実装時に確定する。

---

## 付録: 初期化コマンド例（参考・未確定）

```bash
# Python ワークスペース
uv init
# 各パッケージ/アプリは uv init --package で追加していく想定

# TS ワークスペース
pnpm init
# frontend: pnpm create vite apps/frontend --template react-ts
# infra:    cdk init app --language typescript （infra ディレクトリ内）
```

> 上記は方向性の例。実際のコマンド・テンプレート選定は着手時に確定する。
