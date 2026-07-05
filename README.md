# idash

[![CI/CD](https://github.com/d-kama/idash/actions/workflows/cicd.yml/badge.svg)](https://github.com/d-kama/idash/actions/workflows/cicd.yml)
[![last commit](https://img.shields.io/github/last-commit/d-kama/idash)](https://github.com/d-kama/idash/commits/main)

[![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Biome](https://img.shields.io/badge/lint%2Fformat-Biome-60a5fa?logo=biome&logoColor=white)](https://biomejs.dev/)
[![code size](https://img.shields.io/github/languages/code-size/d-kama/idash)](https://github.com/d-kama/idash)
[![languages](https://img.shields.io/github/languages/count/d-kama/idash)](https://github.com/d-kama/idash)

iDeCo（個人型確定拠出年金）の運用状況を把握・管理するためのアプリ。
データを定期収集して蓄積し、Web 上で可視化＋サマリ通知する。個人利用・学習用。

Python（batch / bff / 共有ライブラリ）と TypeScript（frontend / infra）が混在する
polyglot モノレポ。Python 側は uv ワークスペース、TypeScript 側は pnpm ワークスペースで管理する。

詳細な設計・実装計画は [`PROJECT_PLAN.md`](./PROJECT_PLAN.md) を参照。

## ディレクトリ構成

```
idash/
├── packages/        # Python 共有ライブラリ（uv member）
│   ├── domain/          # エンティティ / ドメインサービス / ポート
│   ├── application/     # ユースケース（orchestration）
│   ├── schemas/         # Pydantic スキーマ
│   ├── infrastructure/  # ポートの具象実装（DuckDB+S3 / 外部サイト / 通知）
│   └── common/          # 設定 / Parameter Store / ロギング
├── apps/
│   ├── batch/       # データ収集 / サマリ通知 Lambda（uv member）
│   ├── bff/         # FastAPI + Mangum（uv member）
│   └── frontend/    # React / Vite（pnpm member）
└── infra/           # AWS CDK（TypeScript, pnpm member）
```

## 前提ツール

ツールのバージョンは [mise](https://mise.jdx.dev/) で固定している（`mise.toml`）。
mise を導入後、リポジトリルートで以下を実行すると python / node / uv / pnpm / task が揃う。

```bash
mise install
```

## セットアップ

```bash
mise install   # ツール（python/node/uv/pnpm/task）を導入
task setup     # 依存解決（uv sync && pnpm install）
```

## タスク一覧

[go-task](https://taskfile.dev/)（`Taskfile.yml`）で横断タスクを管理する。

| タスク | 内容 |
|--------|------|
| `task setup` | 依存解決（`uv sync` + `pnpm install`） |
| `task lint` | Lint（静的解析のみ・書き換えなし。Python: ruff / TS: Biome） |
| `task format` | フォーマット自動修正（書き込み・ローカル整形。Python: ruff format / TS: Biome） |
| `task typecheck` | 型チェック（Python: ty / TS: tsc） |
| `task test` | テスト（pytest + infra Vitest スナップショット） |
| `task synth` | CDK synth（build-front 依存。CloudFormation テンプレート生成。AWS 認証不要） |
| `task check` | lint + フォーマット検証 + typecheck + test を一括実行（CI と同じ検証） |
| `task gen-types` | Pydantic → OpenAPI → TS 型を生成（生成物は非コミット。frontend が import） |
| `task build-front` | フロントエンドをビルド（gen-types 依存。IdashFrontendStack の dist 元） |
| `task bff` | BFF をローカル起動（uvicorn。既定でローカル Parquet `data/assets.parquet` を read） |
| `task front` | フロントエンドをローカル起動（vite dev。`/api` を `task bff` へプロキシ） |
| `task deploy` | CDK デプロイ（build-front 依存。要 AWS 認証） |

> `task setup` 直後は生成型（`schema.d.ts`）が無いため frontend の IDE 型エラーが出る。
> `task gen-types`（または `task typecheck`）を一度実行すると解消する。

## infra（AWS CDK）

`infra/` は AWS CDK（TypeScript）。3 スタック構成:

- **`IdashBatchStack`** — データ収集（collect）とサマリ通知（notify）の 2 Lambda。**Lambda は
  コンテナイメージ**（`DockerImageFunction`、版ピン chrome を同梱した `apps/batch/Dockerfile`）で
  collect / notify は同一イメージを `cmd` 違いで共有する。収集は平日 JST 09:00、通知は週次・日曜
  JST 09:00（EventBridge Scheduler）。エラーページ証跡 S3 と失敗検知 Alarm→SNS を併設（ADR-0004）。
- **`IdashBffStack`** — 可視化 API（`GET /api/visualization`）。FastAPI + Mangum の chrome なし
  コンテナ Lambda を HTTP API（API Gateway v2）で公開。データストア S3 は read のみ。
- **`IdashFrontendStack`** — CloudFront を唯一の入口とする配信（ADR-0006）。非公開 S3（OAC）+
  `/api/*` を BFF へパススルー。**Basic 認証（CloudFront Function + KVS）** と **Geo 制限(JP)**、
  **origin-verify** で API Gateway 直叩きを遮断する。

Docker イメージはリポジトリルートを build context にビルドする。スタックは Batch → Bff →
Frontend の順にプロパティ渡しで配線する（`infra/bin/app.ts`）。

```bash
# 構成確認（CloudFormation テンプレート生成。AWS 認証不要）
task synth
# または
pnpm --filter @idash/infra exec cdk synth

# スナップショットテスト
pnpm --filter @idash/infra test
```

### デプロイ手順

> SSM SecureString は CDK では作成しない（CFn は SecureString 非対応）。デプロイ前に
> AWS コンソール / CLI で事前作成しておくこと（`sheets-sa` は ADR-0005 で不要）:
>
> - `/idash/<env>/source-login` — 収集ログイン情報（collect）
> - `/idash/<env>/notify-line` — LINE 通知（notify）
> - `/idash/<env>/origin-verify` — **CloudFront 経由限定化の共有シークレット（BFF）**。
>   後述の CloudFront KVS `origin-verify` と**同一値**を投入する（ADR-0006）。
>
> ```bash
> # 例: origin-verify（推測困難なランダム値。KVS にも同じ値を入れる）
> aws ssm put-parameter --type SecureString \
>   --name /idash/dev/origin-verify --value "$(openssl rand -hex 32)"
> ```

```bash
# 1) 再認証（有効な AWS 認証情報を用意）
aws login   # またはプロファイルを利用

# 2) 初回のみ CDK ブートストラップ（ap-northeast-1）
pnpm --filter @idash/infra exec cdk bootstrap aws://<ACCOUNT_ID>/ap-northeast-1

# 3) デプロイ（フロント dist ビルド → 全スタック）
task deploy
# または: pnpm --filter @idash/infra exec cdk deploy --all --require-approval never
```

#### デプロイ後: ダッシュボードのアクセス制御（CloudFront KVS・IaC 外・手動）

`IdashFrontendStack` は CloudFront Function + `KeyValueStore` を作るが、**秘密値は投入しない**
（public repo 制約。ADR-0006）。デプロイ後すみやかに KVS へ 2 キーを投入する（投入前は全 401/403
＝ダッシュボードが開けないだけで、データ流出方向のリスクはない）。

```bash
# KVS の ARN と現在の ETag を取得（put には ETag 必須）
KVS_ARN=$(aws cloudfront list-key-value-stores \
  --query "KeyValueStoreList.Items[?contains(Name, 'AuthKeyValueStore')].ARN" --output text)
ETAG=$(aws cloudfront-keyvaluestore describe-key-value-store --kvs-arn "$KVS_ARN" --query ETag --output text)

# 1) basic-auth: `Basic <base64(user:pass)>` 全体
aws cloudfront-keyvaluestore put-key --kvs-arn "$KVS_ARN" --if-match "$ETAG" \
  --key basic-auth --value "Basic $(printf 'user:pass' | base64)"

# 2) origin-verify: SSM /idash/<env>/origin-verify と同一値（ETag は put ごとに変わる点に注意）
ETAG=$(aws cloudfront-keyvaluestore describe-key-value-store --kvs-arn "$KVS_ARN" --query ETag --output text)
aws cloudfront-keyvaluestore put-key --kvs-arn "$KVS_ARN" --if-match "$ETAG" \
  --key origin-verify --value "<SSM origin-verify と同じ値>"
```

- **秘密ローテーション順は KVS → SSM**。先に SSM を変えると正規経路（CloudFront が旧値を注入）が
  一時的に 403 になる。
- 確認: CloudFront ドメイン（`aws cloudfront list-distributions` 等）を開き Basic 認証 → ダッシュボード
  表示。あわせて **API Gateway 直 URL への直叩きが 403**（origin-verify 欠落）になることを確認する。

#### デプロイ後: バッチ失敗通知の Email サブスク（IaC 外・手動）

バッチ失敗は CloudWatch Alarm（Lambda `Errors`）→ SNS Topic で検知する（ADR-0004）。
**Email サブスクは個人アドレスを IaC に残さないため CDK では作成しない。** 初回デプロイ後に手動で追加し、
届く確認メールのリンクから承認する（承認するまで通知は飛ばない）。

```bash
# Topic ARN を取得（Console > SNS でも可）
aws sns list-topics --query "Topics[?contains(TopicArn, 'BatchAlertTopic')].TopicArn" --output text

# Email サブスクを追加 → 届いた確認メールを承認
aws sns subscribe \
  --topic-arn <TOPIC_ARN> \
  --protocol email \
  --notification-endpoint <YOUR_EMAIL_ADDRESS>
```
