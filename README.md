# idash

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
│   ├── infrastructure/  # ポートの具象実装（Sheets / 外部サイト / 通知）
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
| `task lint` | Lint（Python: ruff / TS: Biome） |
| `task format` | フォーマット（Python: ruff format / TS: Biome） |
| `task typecheck` | 型チェック（Python: ty / TS: tsc） |
| `task test` | テスト（pytest + infra Vitest スナップショット） |
| `task synth` | CDK synth（CloudFormation テンプレート生成。AWS 認証不要） |
| `task check` | lint + typecheck + test を一括実行 |

> gen-types / build-front / deploy などの将来タスクは後続フェーズで有効化する
> （`Taskfile.yml` にコメントで雛形を残置）。

## infra（AWS CDK）

`infra/` は AWS CDK（TypeScript）。現状は `IdashBatchStack`（データ収集 Lambda）の
最小実装。Lambda はプレースホルダ（Phase 3 でコンテナ化予定）。

```bash
# 構成確認（CloudFormation テンプレート生成。AWS 認証不要）
task synth
# または
pnpm --filter @idash/infra exec cdk synth

# スナップショットテスト
pnpm --filter @idash/infra test
```

### デプロイ手順

> SSM SecureString（`/idash/<env>/sheets-sa`・`/idash/<env>/source-login`）は
> CDK では作成しない。デプロイ前に AWS コンソール / CLI で事前作成しておくこと。

```bash
# 1) 再認証（有効な AWS 認証情報を用意）
aws login   # またはプロファイルを利用

# 2) 初回のみ CDK ブートストラップ（ap-northeast-1）
pnpm --filter @idash/infra exec cdk bootstrap aws://<ACCOUNT_ID>/ap-northeast-1

# 3) デプロイ
pnpm --filter @idash/infra exec cdk deploy --require-approval never
```
