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
| `task synth` | CDK synth（CloudFormation テンプレート生成。AWS 認証不要） |
| `task check` | lint + フォーマット検証 + typecheck + test を一括実行（CI と同じ検証） |

> gen-types / build-front / deploy などの将来タスクは後続フェーズで有効化する
> （`Taskfile.yml` にコメントで雛形を残置）。

## infra（AWS CDK）

`infra/` は AWS CDK（TypeScript）。`IdashBatchStack` にデータ収集（collect）と
サマリ通知（notify）の 2 Lambda を持つ。**Lambda はコンテナイメージ**
（`DockerImageFunction`、版ピン chrome を同梱した `apps/batch/Dockerfile` を
リポジトリルートを build context にビルド）で、collect / notify は同一イメージを
`cmd` 違いで共有する。収集は平日（Mon–Fri）JST 09:00、通知は週次・日曜 JST 09:00
（EventBridge Scheduler）。失敗時のエラーページ証跡を保存する S3（`ErrorPageBucket`、
collect のみ書き込み）と、失敗検知の CloudWatch Alarm（Lambda `Errors`）→ SNS Topic
を併設する（ADR-0004）。

```bash
# 構成確認（CloudFormation テンプレート生成。AWS 認証不要）
task synth
# または
pnpm --filter @idash/infra exec cdk synth

# スナップショットテスト
pnpm --filter @idash/infra test
```

### デプロイ手順

> SSM SecureString（`/idash/<env>/source-login`・`/idash/<env>/notify-line`）は
> CDK では作成しない。デプロイ前に AWS コンソール / CLI で事前作成しておくこと。
> （データストアは DuckDB + S3 Parquet へ移行済み＝ADR-0005。`sheets-sa` は不要になった。）

```bash
# 1) 再認証（有効な AWS 認証情報を用意）
aws login   # またはプロファイルを利用

# 2) 初回のみ CDK ブートストラップ（ap-northeast-1）
pnpm --filter @idash/infra exec cdk bootstrap aws://<ACCOUNT_ID>/ap-northeast-1

# 3) デプロイ
pnpm --filter @idash/infra exec cdk deploy --require-approval never
```

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
