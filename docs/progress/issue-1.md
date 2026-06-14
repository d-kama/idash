# idash モノレポ初期構築（Phase 0: リポジトリ初期化）

## 基本情報

| 項目 | 内容 |
|------|------|
| チケット | issue-1 |
| ブランチ | chore/monorepo-bootstrap |
| 開始日 | 2026-06-14 |
| 目標完了日 | TBD |
| 最終更新 | 2026-06-14 |

---

## 要件サマリー

### 背景・目的
`PROJECT_PLAN.md` の **Phase 0: リポジトリ初期化** を実施する。idash は iDeCo 運用状況の把握・管理アプリで、Python（batch / bff / 共有ライブラリ）と TypeScript（frontend / infra）が混在する polyglot モノレポ。本タスクでは **モノレポ管理に必要なパッケージ・ワークスペースの準備まで**を行い、ビジネスロジック（ハンドラ中身・FastAPI ルーター・CDK スタック・ドメインモデル等）は実装しない。uv ワークスペース（Python）と pnpm ワークスペース（TypeScript）を並置し、各メンバーが解決可能な土台を作る。

### 受入条件
- [ ] `uv sync` が通り、`packages/*`（domain/application/schemas/infrastructure/common）と `apps/batch`・`apps/bff` の内部依存（`workspace = true`）が解決される
- [ ] `pnpm install` が通り、`apps/frontend` と `infra` が pnpm メンバーとして解決される
- [ ] `task setup` / `task lint` / `task format` / `task typecheck` / `task test` / `task check` が（空パッケージの状態で）エラーなく実行できる
- [ ] ルート `mise.toml` で `python/node/uv/pnpm/task` のバージョンが固定されている
- [ ] `README.md`（日本語・最小構成）と `.gitignore`（標準セット）が整備され、`uv.lock` / `pnpm-lock.yaml` がコミットされている

### スコープ
- **対象**: ディレクトリ骨格、uv/pnpm ワークスペース定義、各 `pyproject.toml` / `package.json` 雛形、内部依存配線、lint/format/型チェック/テスト基盤、Taskfile、mise.toml、README/.gitignore、lockfile 生成
- **対象外**: ビジネスロジック全般（ドメインモデル、ユースケース実装、ハンドラ中身、FastAPI ルーター、CDK スタック実装、React コンポーネント）、Dockerfile（Phase 6）、CI/CD（Phase 7）、機能固有の外部ライブラリ（gspread / Playwright / 通知SDK）

---

## コードベース調査結果

### 現状（グリーンフィールド）
- `.git`（初期化済み）、`PROJECT_PLAN.md`（実装計画の正本）、`README.md`（空）のみ存在。
- ツール導入済み: uv 0.10.0 / pnpm 10.30.3 / node v24.13.0 / python 3.13.13。**go-task は未インストール**（mise 経由で導入する）。
- ローカル python 既定は 3.13.13（mise グローバル設定）。

### 関連ファイル一覧

#### 参照（仕様の正本）
| ファイルパス | 役割 | 影響内容 |
|-------------|------|----------|
| `PROJECT_PLAN.md` | 実装計画の正本（セクション3=ディレクトリ構成、6=Taskfile、付録=初期化コマンド） | Phase 0 の構成・命名・ワークスペース割当の根拠 |

#### 新規作成対象（主要）
| ファイルパス | 役割 |
|-------------|------|
| `pyproject.toml`（ルート） | uv ワークスペース定義・dev group・ruff/ty/pytest 設定集約（仮想ルート） |
| `pnpm-workspace.yaml` / `package.json`（ルート） | pnpm ワークスペース定義・Biome/tsc 等の devDeps |
| `mise.toml` | ツール版固定（python/node/uv/pnpm/task） |
| `Taskfile.yml` | 横断タスク（動くタスクのみ実装、将来タスクはコメント残置） |
| `biome.json` / `tsconfig.base.json` | TS lint+format / 共有 tsconfig |
| `packages/*/pyproject.toml` + `src/<pkg>/__init__.py` | Python 共有ライブラリ雛形 |
| `apps/{batch,bff}/pyproject.toml` + `src/<app>/__init__.py` | Python アプリ雛形 |
| `apps/frontend/` / `infra/` | pnpm メンバー最小スタブ（package.json + 設定のみ） |

### 確定パッケージ構成
```
idash/
├── packages/{domain, application, schemas, infrastructure, common}  # uv member（src レイアウト）
├── apps/{batch, bff}                                                # uv member（src レイアウト）
├── apps/frontend                                                    # pnpm member（最小スタブ）
└── infra                                                            # pnpm member（最小スタブ）
```

---

## 詳細タスク一覧

### フェーズ1: 準備・設計確認（グリル完了）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 1.1 | 要件グリル・合意形成（DoD・スコープ確定） | ✅ | DoD=B（uv sync/pnpm install が通る状態）|
| 1.2 | ツールチェーン選定 | ✅ | Python: uv/ruff/ty、TS: pnpm/Biome/tsc、go-task+mise |
| 1.3 | パッケージ命名・内部依存グラフ確定 | ✅ | 配布名 `idash-*`／import 名は接頭辞なし／`repository`→`infrastructure` |

### フェーズ2: 実装（ファイル作成）
| # | タスク | 状態 | 対象ファイル | 実装詳細 |
|---|--------|------|-------------|----------|
| 2.1 | ルート `pyproject.toml` 作成 | ✅ | `pyproject.toml` | 仮想ルート（build-system なし）。`[tool.uv.workspace] members = ["packages/*", "apps/batch", "apps/bff"]`、`[dependency-groups] dev = ["ruff","ty","pytest","pytest-cov"]`、`[tool.ruff]`/`[tool.ty]`/`[tool.pytest.ini_options]` 集約 |
| 2.2 | `packages/*` の雛形作成（5件） | ✅ | `packages/{domain,application,schemas,infrastructure,common}/pyproject.toml`, `src/<pkg>/__init__.py` | 配布名 `idash-*`、`build-backend = "uv_build"`、src レイアウト、空 `__init__.py` |
| 2.3 | `apps/{batch,bff}` の雛形作成 | ✅ | `apps/{batch,bff}/pyproject.toml`, `src/<app>/__init__.py` | 同上。bff は fastapi/mangum 宣言 |
| 2.4 | 内部依存の配線 | ✅ | 各 `pyproject.toml` | `dependencies` + `[tool.uv.sources] {name = {workspace = true}}`。application→domain,schemas / infrastructure→domain,common / batch→application,infrastructure,common / bff→application,infrastructure,schemas,common |
| 2.5 | 外部依存（フレームワークのみ）宣言 | ✅ | `schemas`(pydantic) / `common`(boto3) / `bff`(fastapi,mangum) | 機能ライブラリ（gspread/Playwright/通知SDK）は先送り |
| 2.6 | pnpm ワークスペース定義 | ✅ | `pnpm-workspace.yaml`, ルート `package.json` | members: `apps/frontend`, `infra`。ルートに `@biomejs/biome`・`typescript` を devDeps |
| 2.7 | `apps/frontend` 最小スタブ | ✅ | `apps/frontend/{package.json,tsconfig.json,vite.config.ts}` | react/react-dom/vite/@vitejs/plugin-react を宣言。React 実体・index.html は置かない |
| 2.8 | `infra` 最小スタブ | ✅ | `infra/{package.json,tsconfig.json,cdk.json}` | aws-cdk-lib/constructs/aws-cdk を宣言。`bin`/`lib` は空（.gitkeep）。空ソース時の tsc TS18003 回避に `scripts/typecheck.mjs` を追加 |
| 2.9 | TS 共通設定 | ✅ | `biome.json`, `tsconfig.base.json` | ルート集約。frontend(DOM)/infra(node) が extend |
| 2.10 | `mise.toml` 作成 | ✅ | `mise.toml` | `python=3.13`, `node=24`, `uv`, `npm:pnpm`, `task` を pin（pnpm は aqua backend のアセット名不一致を避け npm backend に） |
| 2.11 | `Taskfile.yml` 作成 | ✅ | `Taskfile.yml` | setup/lint/format/typecheck/test/check を実装。test は exit code 5 を成功扱い。gen-types/build-front/deploy 等はコメント残置 |
| 2.12 | `.gitignore` / `README.md` 整備 | ✅ | `.gitignore`, `README.md` | 標準 ignore セット（lockfile は除外しない）。README は日本語・最小（概要+mise+task setup+タスク一覧）|

### フェーズ3: テスト（検証）
| # | タスク | 状態 | 対象 | テスト観点 |
|---|--------|------|------|-----------|
| 3.1 | `uv sync` 成功・内部依存解決確認 | ✅ | ルート | `uv tree` で `idash-*` 7件が workspace 解決（内部依存グラフ一致）を確認 |
| 3.2 | `pnpm install` 成功確認 | ✅ | ルート | `@idash/frontend`・`@idash/infra` が member 解決を確認 |
| 3.3 | `task check` 疎通 | ✅ | 全体 | ruff/Biome lint・ty・tsc（frontend/infra）・pytest が空パッケージで完了。exit 0 |
| 3.4 | lockfile 生成・コミット確認 | ✅ | `uv.lock`, `pnpm-lock.yaml` | 生成済み・`git check-ignore` で非除外を確認 |

### フェーズ4: レビュー・完了
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 4.1 | セルフレビュー | ⬜ | 受入条件チェック |
| 4.2 | PR作成 | ⬜ | ユーザー指示があれば |
| 4.3 | コードレビュー対応 | ⬜ | |
| 4.4 | マージ・完了 | ⬜ | |

### ステータス凡例
- ⬜ 未着手 / 🔄 進行中 / ✅ 完了 / ⏸️ 保留 / ❌ キャンセル

---

## 総合進捗

| 項目 | 完了 | 総数 | 進捗率 |
|------|------|------|--------|
| 実装タスク（フェーズ1+2） | 15 | 15 | 100% |
| 検証タスク（フェーズ3） | 4 | 4 | 100% |
| **総合** | **19** | **19** | **100%** |

---

## 作業ログ

### 2026-06-14
#### 実施内容
- [x] 要件グリル・合意形成（plan-then-build / grill-with-docs）
- [x] 詳細設計兼進捗管理表作成
- [x] フェーズ2 実装（2.1〜2.12）: ルート仮想 pyproject / packages 5件・apps 2件の雛形・内部依存配線・外部依存宣言（pydantic/boto3/fastapi/mangum）/ pnpm workspace・frontend/infra スタブ / biome.json・tsconfig.base.json / mise.toml / Taskfile.yml / .gitignore・README.md
- [x] フェーズ3 検証（3.1〜3.4）: `uv sync`・`uv tree`（idash-* 7件 workspace 解決）/ `pnpm install`（frontend・infra member 解決）/ `task check` 疎通（ruff・biome・ty・tsc・pytest, exit 0）/ lockfile 生成・非除外確認

#### 進捗サマリー
- **完了タスク**: 19/19（フェーズ1〜3 完了）
- **進行中タスク**: 0
- **ブロッカー**: なし

#### 実装メモ（仕様への補足。設計は不変更）
- pytest はテスト 0 件時 exit code 5 を返すため `scripts/pytest.sh` で 5 を成功扱いに吸収（`task test`/`task check` が誤検知しないように）。
- infra は bin/lib を空（.gitkeep）で保つ決定のため、.ts 0 件時の tsc TS18003 を `infra/scripts/typecheck.mjs` で回避（ソース追加後は通常どおり tsc 実行）。
- mise の pnpm は aqua backend が linux-x64 アセット名不一致で失敗したため `npm:pnpm` backend に変更（python/node/uv/task/pnpm すべて `mise install` で導入可能）。
- Biome 設定は CLI 2.5.0 に合わせ schema 2.5.0・`rules.preset = "recommended"` へ（`biome migrate` 準拠）。

---

## メモ・課題

### 未解決課題
| # | 課題 | 優先度 | 期限 | 担当 |
|---|------|--------|------|------|
| 1 | Phase 6 で Lambda コンテナベース `public.ecr.aws/lambda/python:3.13` の提供を確認（3.13 確定済みのため懸念は低）| 低 | Phase 6 | 実装者 |
| 2 | ty（pre-1.0）が型チェックで詰まった場合 mypy へ退避する含みを残す | 低 | 随時 | 実装者 |

### 決定事項
| 日付 | 決定事項 | 決定者 |
|------|----------|--------|
| 2026-06-14 | 完了の定義は B（`uv sync`/`pnpm install` が通り内部依存が解決される状態。ビジネスロジックは書かない） | ユーザー |
| 2026-06-14 | Python バージョンは 3.13（`requires-python = ">=3.13"`） | ユーザー |
| 2026-06-14 | Python ツールは ruff（lint+format 一本）＋ ty（型）。ty 不調時は mypy 退避可 | ユーザー |
| 2026-06-14 | パッケージ命名: import 名は接頭辞なし、配布名 `idash-*`、src レイアウト | ユーザー |
| 2026-06-14 | `repository` パッケージを `infrastructure` にリネーム | ユーザー |
| 2026-06-14 | pnpm メンバー（frontend/infra）は最小スタブ（package.json + 設定のみ、ソース実体なし） | ユーザー |
| 2026-06-14 | TS ツールは Biome（lint+format）＋ tsc（型）。`biome.json`+`tsconfig.base.json` をルート集約 | ユーザー |
| 2026-06-14 | タスクランナーは go-task、mise で管理。ルート `mise.toml` で python/node/uv/pnpm/task を pin | ユーザー |
| 2026-06-14 | テストは pytest＋pytest-cov を dev group に。実テストは書かない。TS テストは Phase 4 へ | ユーザー |
| 2026-06-14 | uv ルートは仮想ルート＋単一 `uv.lock`＋ツール設定集約。ビルドバックエンドは uv_build | ユーザー |
| 2026-06-14 | 内部依存グラフ確定（application→domain,schemas / infrastructure→domain,common / batch→application,infrastructure,common / bff→application,infrastructure,schemas,common） | ユーザー |
| 2026-06-14 | 外部依存はフレームワークのみ宣言（pydantic/boto3/fastapi/mangum）。機能ライブラリは先送り | ユーザー |
| 2026-06-14 | Taskfile は動くタスクのみ実装、将来タスクはコメント残置 | ユーザー |
| 2026-06-14 | README は日本語・最小構成、.gitignore は標準セット、lockfile はコミット対象 | ユーザー |
| 2026-06-14 | CONTEXT.md / ADR は本フェーズでは作成しない（ドメイン用語未登場・選定はいずれも可逆のため） | Claude（合意） |

---

## 作業再開ガイド

### 現在の状態
- **最終作業タスク**: 1.x 完了（グリル合意・設計確定）
- **作業中断理由**: 計画フェーズ完了。実装フェーズ（2.1）への着手待ち
- **次のアクション**: 2.1 ルート `pyproject.toml`（仮想ルート＋uv workspace 定義）の作成から開始

### 再開時の確認事項
1. `PROJECT_PLAN.md` セクション3（ディレクトリ構成）・セクション6（Taskfile 骨子）を再読
2. 本ファイルの「決定事項」を厳守（再設計しない。齟齬があれば停止して相談）
3. DoD は「`uv sync` / `pnpm install` が通る」。ビジネスロジックには踏み込まない

### コンテキスト復元用コマンド
```bash
# ブランチ切り替え（未作成なら作成）
git switch -c chore/monorepo-bootstrap

# 最新化（リモート追従後）
git pull origin chore/monorepo-bootstrap
```
