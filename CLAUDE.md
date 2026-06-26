# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

idash は iDeCo（個人型確定拠出年金）の運用状況を定期収集・蓄積し、可視化＋サマリ通知する個人利用/学習用システム。Python（batch / bff / 共有ライブラリ）と TypeScript（frontend / infra）が混在する **polyglot モノレポ**で、Python 側は **uv ワークスペース**、TypeScript 側は **pnpm ワークスペース**を並置している。

実装は段階的に進行中。Phase 0（初期化）/ 1（infra 足場）/ 2（CI/CD）/ 4（サマリ通知バッチ）が完了済み（**通知=LINE push は実デプロイ＆動作確認まで完了**）。Phase 3（データ収集バッチ）はコードレベル完了で実デプロイ＆動作確認のみ残（収集=Selenium スクレイピング・コンテナ Lambda 化済み）。Phase 5（BFF）/ 6（フロントエンド）は未着手で、**`packages/schemas` と `apps/bff` の `src` は現状ほぼ空スタブ**（schemas は Phase 5 で本格利用）。設計の全体像は `PROJECT_PLAN.md`、進行中作業は `docs/progress/issue-*.md` を参照。

## ツールチェーン

バージョンは **mise**（`mise.toml`）で固定する。`pnpm` は **10.30.3 にピン留め**してあり、安易に上げない（v11 系は build script 承認機構が変わり frozen install が壊れる）。

```bash
mise install   # python / node / uv / pnpm / task を導入
task setup     # 依存解決（uv sync && pnpm install）
```

## よく使うコマンド

横断タスクは **go-task**（`Taskfile.yml`）に集約。個別言語ツールを直接叩く必要は基本ない。

```bash
task check       # lint + フォーマット検証 + typecheck + test を一括（CI と同じ検証）
task lint        # ruff check + biome lint（静的解析のみ・書き換えなし）
task format      # ruff format + biome format --write（ローカル整形・書き込み）
task typecheck   # ty check（Python）+ tsc（TS, pnpm -r run typecheck）
task test        # pytest + infra Vitest
task synth       # CDK synth（CloudFormation 生成、AWS 認証不要）
```

### 単体テスト実行

```bash
# Python（pytest）— 直接実行する場合
uv run pytest packages/domain/tests/test_money.py
uv run pytest packages/application/tests/test_collection_use_case.py::test_success

# infra（Vitest スナップショット）
pnpm --filter @idash/infra test
pnpm --filter @idash/infra run test:update   # スナップショット更新（-u）
```

`task test` はワークスペース全体（`testpaths = ["packages", "apps"]`）を `uv run pytest` で一括収集・実行し、続けて infra の Vitest（スナップショット）を走らせる。

## アーキテクチャ

### ワークスペースの二重構造

- **uv（Python）** members: `packages/*` + `apps/batch` + `apps/bff`（`pyproject.toml` のルートは配布物でない仮想ルート）
- **pnpm（TypeScript）** members: `apps/frontend` + `infra`（`pnpm-workspace.yaml`）

import 名は接頭辞なし（`domain`, `application` …）、配布名は `idash-*`、src レイアウト。各 Python パッケージの `[tool.uv.build-backend]` で `module-name` を指定している。内部依存は `[tool.uv.sources]` の `workspace = true` で配線する。

### クリーンアーキテクチャの層と依存方向（厳守）

```
domain（entities / domainサービス / ポート=interface、依存ゼロ）
  ▲ implements          ▲ depends
infrastructure        application（+ schemas に依存）
（ポートの具象）            ▲
  ▲ DI で注入             │ ユースケース呼び出し
  apps（batch / bff: 薄いアダプタ）   frontend ←(生成型)← bff
```

- **`domain` は何にも依存しない純粋層**。pydantic すら入れない（値オブジェクトは stdlib `@dataclass(frozen=True)`、ポートは `Protocol`）。
- **`application`** は `domain` と `schemas` のみに依存。フレームワーク（FastAPI / Mangum / boto3 / Lambda）や具象実装は import 禁止 — これを**パッケージ境界で物理的に強制**するために専用パッケージ化している。
- **`infrastructure`** が `domain` のポートを実装する具象（Google Sheets / 外部サイトスクレイピング / 通知）。`domain` + `common` に依存。
- **`apps/{batch,bff}`** は具象を `application` のユースケースへ DI して呼ぶだけの薄いアダプタ。**apps 同士は依存させない**。
- **`common`** は config / Parameter Store / logging（boto3 に依存）。
- frontend は bff の HTTP 契約経由でのみ接続。型は **Pydantic → OpenAPI → TS 型** の一方向伝播（single source of truth は Pydantic スキーマ。生成タスクは後続フェーズで有効化）。

ツール設定（ruff / ty / pytest）は**ルート `pyproject.toml` に集約**し、各メンバーパッケージは設定を持たない。

### 実行時データフロー

2つのバッチ（データ収集 / サマリ通知）は **Google Spreadsheet を介してのみ連携**する疎結合（互いを直接呼ばない）。収集は外部 DC 年金サイトをスクレイピングして Sheets へ write、通知は Sheets から直近 N 日を read → 集計 → 通知。bff（FastAPI + Mangum）は Sheets を read して可視化データを返す。スケジュールは EventBridge Scheduler（JST 指定可）。

### infra（AWS CDK / TypeScript）

`infra/` は CDK。`IdashBatchStack` に収集（collect）と通知（notify）の2 Lambda。**Lambda はコンテナイメージ**（`DockerImageFunction`、版ピン chrome を同梱した `apps/batch/Dockerfile` を build context = リポジトリルートでビルド）で、collect / notify は**同一イメージを `cmd` 違いで共有**する。失敗時のエラーページ証跡を保存する S3（`ErrorPageBucket`）を併設（collect のみ書き込み）。リージョンは `ap-northeast-1`、収集は平日のみ（Mon–Fri）JST 09:00、通知は週次・日曜 JST 09:00。

- スタックのエントリは `infra/bin/app.ts`、`--context env=<name>`（既定 `dev`）でスタック名・SSM パラメータ名を切替。
- **SSM SecureString（`/idash/<env>/sheets-sa`・`/idash/<env>/source-login`）は CDK では作成しない**（CloudFormation が SecureString 非対応）。デプロイ前に AWS 側で手動作成し、名前でインポートする。
- 変更時は `pnpm --filter @idash/infra test`（Vitest スナップショット）が壊れる。意図した差分なら `run test:update` で更新する。
- **物理名は付けず CDK 自動命名に寄せる**（Lambda `functionName` / Logs `logGroupName` 等を固定しない）。固定名のリソースが置換を伴う変更（例: Lambda の PackageType を Zip⇄Image）を受けると新旧で名前衝突し `custom-named resource requires replacing` で deploy が詰まるため。参照はオブジェクト/ARN 経由で配線する。例外は永続データを持ち名前安定性が要るリソース（S3 等）のみ。

## CI/CD

`.github/workflows/cicd.yml` の単一ワークフロー。全トリガで `task check` + `task synth` を走らせ、deploy は **`main` への push と `workflow_dispatch`（どちらも main ref のみ）**で実行。AWS 認証は **GitHub OIDC の短命トークン**で、静的キーは持たない（ADR-0001）。ロール ARN は repo Variable `AWS_DEPLOY_ROLE_ARN`。OIDC provider / IAM ロール / `cdk bootstrap` は AWS 側で事前準備済み（本リポジトリの IaC 管理外）。

## プロジェクトのドキュメント運用

- **`CONTEXT.md`** — ドメイン用語集（ユビキタス言語）。`ProductAsset` / `PortfolioAsset` / `Money` / `Scraper` / `AssetRepository` などの語彙と _Avoid_（使わない曖昧語）を定義。ドメインのコード/会話はこの語彙に従う。
- **`docs/adr/*.md`** — アーキテクチャ決定記録（例: 0001 CI/CD OIDC、0002 Scraper をコンテキストマネージャ方式のセッションとする）。
- **`docs/progress/issue-*.md`** — issue 単位の進捗・設計合意・決定事項。**作業再開時はまず該当ファイルの「設計（グリル合意）」「決定事項」を確認**してから着手する。
- **`PROJECT_PLAN.md`** — フェーズ別の実装計画と確定/未決事項の全体像。
