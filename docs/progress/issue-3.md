# CI/CD 基盤（GitHub Actions：CI 検証 + main 自動/手動 deploy）

## 基本情報

| 項目 | 内容 |
|------|------|
| チケット | issue-3 |
| ブランチ | feature/cicd-github-actions |
| 開始日 | 2026-06-15 |
| 目標完了日 | TBD |
| 最終更新 | 2026-06-15 |

---

## 要件サマリー

### 背景・目的
`PROJECT_PLAN.md` Phase 2 の CI/CD を実装する。単一の GitHub Actions ワークフローで
**CI（PR 検証）と CD（`main` 自動 deploy ＋ 手動 deploy）** を束ね、デプロイ可能なパイプラインを
早期に疎通検証する。現状の deploy 対象は `IdashBatchStack`（プレースホルダ Lambda）のみだが、
`fromSecureStringParameterAttributes` は名前インポートで synth/deploy 時に値解決しないため、
SSM 未作成でも安全に deploy できる。

### 受入条件
- [ ] PR で `check`（lint/typecheck/test/synth）が走り、グリーンでマージ可能になる
- [ ] `main` への push と `workflow_dispatch` で `deploy` が走り、OIDC ロールを assume して
      `cdk deploy --all` が実行される
- [ ] ツールチェーンは `jdx/mise-action`（`mise.toml` 単一ソース）で導入される
- [ ] 依存は frozen install（`task setup:ci`）で、古い lockfile を CI で検知して落とす
- [ ] uv / pnpm のキャッシュが効く
- [ ] ローカルで `task setup:ci` / `task check` / `task synth` がグリーン（CI コマンドの妥当性確認）

### スコープ
- **対象**: `.github/workflows/cicd.yml`（check + deploy）、共用 composite action
  `.github/actions/setup`、`Taskfile.yml` の `setup:ci` 追加、ADR 0001、計画書 Phase 2 反映
- **対象外**: パスフィルタによるジョブ分割（YAGNI / Phase 3・6 で再検討）、Docker ビルドキャッシュ
  （Dockerfile が出る Phase 3 から）、AWS Budgets（**不採用**）、stg/prod 環境分離、ブランチ保護設定
  （GitHub リポジトリ設定側・任意）

---

## コードベース調査結果

### 現状（Phase 1 完了済み・本タスクの起点）
- `.github/` 無し（CI 未整備）。
- `Taskfile.yml` に `setup` / `lint` / `format` / `typecheck` / `test` / `synth` / `check` が整備済み。
  CI はこれらを呼ぶだけでよい。
- ツール版は `mise.toml` が単一ソース（python 3.13 / node 24 / uv・pnpm・task = latest）。
  lint/typecheck のツール（ruff/ty/pytest=uv.lock、Biome/tsc=pnpm-lock）は lockfile で版固定済み。
- リポジトリ: GitHub `d-kama/idash`。AWS 認証は OIDC ロール準備済み・`cdk bootstrap` 済み・
  ロール ARN は repo Variable に保管済み（AWS 側リソースは作成不要）。

### 直接作成・変更対象ファイル
| ファイルパス | 役割 |
|-------------|------|
| `.github/workflows/cicd.yml` | CI/CD ワークフロー（check + deploy） |
| `.github/actions/setup/action.yml` | mise + frozen install + uv/pnpm キャッシュ（共用 composite） |
| `Taskfile.yml` | `setup:ci`（frozen install）追加 |
| `docs/adr/0001-cicd-github-oidc.md` | 認証モデルの ADR |
| `PROJECT_PLAN.md` | Phase 2 を grill 結果で更新・Budgets 不採用に統一 |

---

## 詳細タスク一覧

### フェーズ1: 設計（grill 完了）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 1.1 | スコープ確定（CI+CD / Budgets 不採用 / OIDC ロール準備済み） | ✅ | grill-with-docs |
| 1.2 | CD トリガ確定（main 自動 + workflow_dispatch） | ✅ | trust 条件 = ref main |
| 1.3 | パスフィルタ見送り・mise-action・frozen・キャッシュ確定 | ✅ | |

### フェーズ2: 実装
| # | タスク | 状態 | 対象 |
|---|--------|------|------|
| 2.1 | `Taskfile.yml` に `setup:ci` 追加 | ✅ | `Taskfile.yml` |
| 2.2 | 共用 composite action 作成 | ✅ | `.github/actions/setup/action.yml` |
| 2.3 | `cicd.yml`（check + deploy）作成 | ✅ | `.github/workflows/cicd.yml` |
| 2.4 | ADR 0001 作成 | ✅ | `docs/adr/0001-cicd-github-oidc.md` |
| 2.5 | 計画書 Phase 2 反映・Budgets 不採用統一 | ✅ | `PROJECT_PLAN.md` |

### フェーズ3: テスト（検証）
| # | タスク | 状態 | 観点 |
|---|--------|------|------|
| 3.1 | `task setup:ci` グリーン | ✅ | frozen install OK（uv: Audited 9 / pnpm: Lockfile up to date） |
| 3.2 | `task check` グリーン | ✅ | ruff/Biome/ty/tsc/pytest(exit5→0)/infra vitest すべて exit 0 |
| 3.3 | `task synth` グリーン | ✅ | `Idash-dev-Batch` テンプレ生成（bootstrap hnb659fds 参照確認） |
| 3.4 | ワークフロー YAML 構文確認 | ✅ | pyyaml で parse OK、jobs=check/deploy 認識 |

### フェーズ4: レビュー・完了
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 4.1 | セルフレビュー | ⬜ | 受入条件チェック |
| 4.2 | PR 作成 | ⬜ | ユーザー指示があれば |
| 4.3 | 実 deploy 疎通（main マージ後 or 手動 dispatch） | ⬜ | ユーザー実施 |

### ステータス凡例
- ⬜ 未着手 / 🔄 進行中 / ✅ 完了 / ⏸️ 保留 / ❌ キャンセル

---

## メモ・課題

### 未解決・確認事項
| # | 課題 | 優先度 | 担当 |
|---|------|--------|------|
| 1 | repo Variable の実名（暫定 `AWS_DEPLOY_ROLE_ARN`）。違えば `cicd.yml` の 1 語を差替 | 中 | ユーザー確認 |
| 2 | 実 deploy 疎通は `main` マージ後の自動 run または手動 dispatch で確認（GH Actions 上で実行） | 中 | ユーザー |
| 3 | ブランチ保護（`check` を必須ステータスに）は GitHub リポジトリ設定側。任意 | 低 | ユーザー |

### 決定事項（grill）
| 決定事項 |
|----------|
| CI + CD 両方。Budgets 不採用。OIDC ロールは準備済み（AWS 側作成不要） |
| CD = `main` push 自動 ＋ `workflow_dispatch` 手動。env=dev 単一・region ap-northeast-1 |
| 単一 `cicd.yml`：`check`（全トリガ）＋ `deploy`（`needs: check` / PR 以外） |
| パスフィルタ分割は見送り（YAGNI / Phase 3・6 で再検討） |
| ツール導入は `jdx/mise-action`（`mise.toml` 単一ソース） |
| **pnpm は 10.30.3 に固定**（当初 latest だったが CI で pnpm 11.6.0 を引き込み、build script 承認機構の差異で frozen install が壊れたため。grill の「ツール版 latest 維持」を pnpm に限り見直し）。build script 承認は `pnpm-workspace.yaml` の `onlyBuiltDependencies: [esbuild]` |
| 再現性は `setup:ci`（`uv sync --frozen` / `pnpm install --frozen-lockfile`）のみ |
| uv（`~/.cache/uv`）+ pnpm store キャッシュを有効化 |
| 認証は GitHub OIDC（長期キー不使用）→ ADR 0001 |
| **PR レビュー対応（CodeRabbit）**: ①deploy の `if` に `github.ref == 'refs/heads/main'` を追加（非 main dispatch をクリーン skip）②`actions/checkout` に `persist-credentials: false` ③全外部 Action を SHA pin（現メジャー v4/v4/v4/v2）＋ `.github/dependabot.yml`（github-actions 週次）で陳腐化防止。メジャー更新は Dependabot の個別 PR で実施。④日付指摘は JST のため対応不要（CodeRabbit 撤回済み） |

---

## 作業再開ガイド

### 現在の状態
- 実装（フェーズ2）完了。検証（フェーズ3）と PR はこれから。
- ブランチ `feature/cicd-github-actions`。コミットはユーザー指示待ち。

### 次のアクション
1. `task setup:ci` / `task check` / `task synth` をローカルで流して妥当性確認
2. ユーザーに repo Variable の実名を確認（暫定 `AWS_DEPLOY_ROLE_ARN`）
3. PR 作成 → マージ後の自動 deploy（または手動 dispatch）で疎通確認
