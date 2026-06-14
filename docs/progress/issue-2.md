# データ収集バッチ infra 最小実装（IdashBatchStack / collect・synth＋snapshot まで）

## 基本情報

| 項目 | 内容 |
|------|------|
| チケット | issue-2 |
| ブランチ | feature/batch-collect-infra |
| 開始日 | 2026-06-14 |
| 目標完了日 | TBD |
| 最終更新 | 2026-06-14 |

---

## 要件サマリー

### 背景・目的
`PROJECT_PLAN.md` の **`IdashBatchStack`（データ収集 Lambda 側）** を、infra（AWS CDK / TypeScript）として最小実装する。アプリ・パッケージ側（batch ハンドラ等）の実装は行わず、**infra に必要な最低限**のみ。目的は早期に **`cdk synth` がグリーン（＝デプロイ可能）＋ snapshot テストが通る**土台を確認すること。実 deploy はユーザーが再認証後に自分で行う。

### 受入条件
- [ ] `pnpm install` が通る（infra devDeps: `vitest` / `tsx` / `@types/node` 追加後）
- [ ] `task synth`（`cdk synth`）がグリーンで CloudFormation テンプレートが生成される（AWS 認証不要）
- [ ] `pnpm --filter @idash/infra test`（Vitest）でスナップショットが生成され、テストがパスする
- [ ] `task check`（ruff / Biome / ty / tsc / pytest / infra-vitest）がすべてグリーン
- [ ] 実 deploy 手順（`aws login` → `cdk bootstrap` → `cdk deploy`）が README / 作業再開ガイドに記載されている

### スコープ
- **対象**: `IdashBatchStack` の **collect（データ収集）Lambda 側のみ**。プレースホルダ Lambda（`Code.fromInline`）＋ EventBridge Scheduler ＋ 予約同時実行 ＋ SSM 読取権限 ＋ LogGroup ＋ 環境変数、`bin/app.ts` 結線、Vitest スナップショットテスト、タスク/スクリプト統合
- **対象外**: batch アプリ実装（handler_collect 等）、Dockerfile（Phase 3）、notify（サマリ通知）Lambda、bff/frontend スタック、実 deploy の実行、Budgets/コスト監視、CI/CD

---

## コードベース調査結果

### 現状（Phase 0 完了済み・本タスクの起点）
- `infra/` は最小スタブ: `package.json`（aws-cdk-lib/constructs/aws-cdk/typescript）、`cdk.json`（`npx ts-node --prefer-ts-exts bin/app.ts` ← **ts-node 未導入**）、`tsconfig.json`（base 継承・include `["bin","lib"]`）、`scripts/typecheck.mjs`、`bin/.gitkeep`・`lib/.gitkeep`（空）。
- 環境: Docker 起動中 / **AWS 認証はセッション切れ（実 deploy 不可）** / CDK CLI 2.1106.1 が npx 利用可。

### 参照・影響範囲ファイル
| ファイルパス | 役割 | 影響内容 |
|-------------|------|----------|
| `PROJECT_PLAN.md` §2.3.1 / §5 / §11 / §12.2 / §12.4 | IdashBatchStack の意図・コスト暴発対策・コードスケルトン | 実装の根拠（ただし Lambda はコンテナ→プレースホルダへ暫定変更） |
| `infra/cdk.json` | CDK アプリ実行コマンド | `ts-node` → `tsx` へ変更 |
| `infra/tsconfig.json` | infra 型チェック設定 | include に `test` 追加 |
| `infra/scripts/typecheck.mjs` | .ts 不在時 tsc スキップ | `.ts` 追加後は通常 `tsc --noEmit` が実走 |
| `infra/package.json` | infra 依存・scripts | devDeps と scripts（synth/diff/deploy/test）追加 |
| `Taskfile.yml` | 横断タスク | `test` に infra vitest 追加・`synth` 新設 |
| `tsconfig.base.json` | 共有 tsconfig | 変更なし（参照のみ） |

### 直接作成対象ファイル
| ファイルパス | 役割 |
|-------------|------|
| `infra/lib/batch-stack.ts` | `IdashBatchStack`（collect のみ） |
| `infra/bin/app.ts` | App + IdashBatchStack 結線 |
| `infra/test/batch-stack.test.ts` | Vitest スナップショットテスト |
| `infra/test/__snapshots__/*` | スナップショット（自動生成・コミット対象） |
| `infra/vitest.config.ts` | Vitest 最小設定（environment: node） |

---

## 詳細タスク一覧

### フェーズ1: 準備・設計確認（グリル完了）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 1.1 | 要件グリル・合意形成（スコープ・到達ライン確定） | ✅ | DoD=synth グリーン＋snapshot＝デプロイ可能 |
| 1.2 | Lambda コードソース方針確定 | ✅ | プレースホルダ zip（Code.fromInline）。Phase 3 でコンテナ差替 |
| 1.3 | ツール/構成確定（Vitest/tsx、構成物、SSM ARN 方針） | ✅ | SSM: import→grantRead→env に ARN |

### フェーズ2: 実装
| # | タスク | 状態 | 対象ファイル | 実装詳細 |
|---|--------|------|-------------|----------|
| 2.1 | infra devDeps 追加 | ✅ | `infra/package.json` | `vitest`/`tsx`/`@types/node` を devDeps に。scripts に `synth`/`diff`/`deploy`/`test`("vitest run")/`test:update`("vitest run -u") 追加。`pnpm install` 成功 |
| 2.2 | CDK アプリ実行器を tsx へ | ✅ | `infra/cdk.json` | `app` を `npx tsx bin/app.ts` に変更 |
| 2.3 | `IdashBatchStack`（collect）実装 | ✅ | `infra/lib/batch-stack.ts` | プレースホルダ Lambda（`Code.fromInline`/`Runtime.PYTHON_3_13`/memory 1024/timeout `Duration.minutes(5)`/`reservedConcurrentExecutions=1`）。明示 `LogGroup`（`ONE_WEEK`＋`RemovalPolicy.DESTROY`）。SSM: `fromSecureStringParameterAttributes`（`version` 省略）→`grantRead`→env に `parameterArn`。env: `ENV_NAME`/`SHEETS_SA_PARAM_ARN`/`SOURCE_LOGIN_PARAM_ARN`。**L2 `Schedule`**（`aws-cdk-lib/aws-scheduler`）cron JST 09:00（`Asia/Tokyo`）で collect 起動。aws-cdk-lib 2.259.0 で L2 stable のため L1 フォールバック不要 |
| 2.4 | `bin/app.ts` 結線 | ✅ | `infra/bin/app.ts` | `IdashBatchStack` のみ。envName=context `env`?? 'dev'、stack id `Idash-${envName}-Batch`、`env={region:'ap-northeast-1'}`。`bin/.gitkeep`・`lib/.gitkeep` 削除済 |
| 2.5 | TS テスト設定 | ✅ | `infra/tsconfig.json`, `infra/vitest.config.ts` | tsconfig include に `test` 追加。vitest.config（environment node）。テストは明示 import |
| 2.6 | スナップショットテスト | ✅ | `infra/test/batch-stack.test.ts` | 固定 envName 'dev'・region ap-northeast-1→`toMatchSnapshot()`。**snapshot のみ** |
| 2.7 | タスク/スクリプト統合 | ✅ | `Taskfile.yml` | `test` に infra vitest 追加。`synth` 新設。フル deploy はコメント据置 |
| 2.8 | deploy 手順を文書化 | ✅ | `README.md` | infra/CDK セクション追加（synth/test/bootstrap/deploy 手順・SSM 事前作成の注意） |

### フェーズ3: テスト（検証）
| # | タスク | 状態 | 対象 | 観点 |
|---|--------|------|------|------|
| 3.1 | `pnpm install` 成功 | ✅ | ルート | vitest/tsx/@types/node 解決（+41 packages） |
| 3.2 | `task synth` グリーン | ✅ | infra | 認証不要でテンプレ生成。Lambda(python3.13/Mem1024/Timeout300/Reserved1)・LogGroup(Retention7)・Scheduler(Asia/Tokyo, cron(0 9 * * ? *), FlexibleTimeWindow OFF)・SSM 読取 IAM・env ARN を確認。L2 Schedule 採用・`version` 省略可を確認 |
| 3.3 | スナップショット生成＋パス | ✅ | infra | `vitest run` で snap 生成→再実行パス。`Code.fromInline` でアセットハッシュ無し→決定的 |
| 3.4 | `task check` グリーン | ✅ | 全体 | ruff/Biome(14 files)/ty/tsc(front+infra)/pytest(exit5 吸収)/infra-vitest すべて exit 0 |

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
| 実装タスク（フェーズ1+2） | 11 | 11 | 100% |
| 検証タスク（フェーズ3） | 4 | 4 | 100% |
| **総合** | **15** | **15** | **100%** |

---

## 作業ログ

### 2026-06-14
#### 実施内容
- [x] 要件グリル・合意形成（plan-then-build / grill-with-docs）
- [x] 詳細設計兼進捗管理表作成
- [x] フェーズ2 実装完了（2.1〜2.8）: `IdashBatchStack`（collect プレースホルダ）一式
  - branch `feature/batch-collect-infra` 作成（base main）。コミット未実施（ユーザー指示待ち）
  - aws-cdk-lib **2.259.0** で L2 `Schedule`/`ScheduleExpression`/`TimeZone.ASIA_TOKYO` が stable → L2 採用（L1 フォールバック不要）
  - `fromSecureStringParameterAttributes` の `version` は任意（`@default 最新版`）→ 省略
- [x] フェーズ3 検証完了（3.1〜3.4）: `pnpm install` / `task synth` / vitest snapshot / `task check` すべてグリーン

#### 進捗サマリー
- **完了タスク**: 15/15（フェーズ1〜3 完了。残はフェーズ4 レビュー/PR＝ユーザー指示待ち）
- **進行中タスク**: 0
- **ブロッカー**: なし

---

## メモ・課題

### 未解決課題
| # | 課題 | 優先度 | 期限 | 担当 |
|---|------|--------|------|------|
| 1 | ~~Scheduler L2/L1 判定~~ **解決(2026-06-14)**: aws-cdk-lib 2.259.0 で L2 `Schedule` stable → L2 採用 | - | 完了 | - |
| 2 | ~~`fromSecureStringParameterAttributes` の `version` 要否~~ **解決(2026-06-14)**: 任意（既定=最新版）→ 省略 | - | 完了 | - |
| 3 | Phase 3 でプレースホルダ Lambda を `DockerImageFunction.fromImageAsset` へ差替。必要なら memory 2048 へ。snapshot 撮り直し | 中 | Phase 3 | 実装者 |
| 4 | 実 deploy はユーザーが `aws login` 後に実施（認証セッション切れのため本タスクでは未実施） | 中 | 任意 | ユーザー |

### 決定事項
| 日付 | 決定事項 | 決定者 |
|------|----------|--------|
| 2026-06-14 | Lambda コードソースはプレースホルダ zip（`Code.fromInline`/`Runtime.PYTHON_3_13`）。Phase 3 で `DockerImageFunction` へ差替 | ユーザー |
| 2026-06-14 | 到達ラインは `cdk synth` グリーン＋snapshot＝「デプロイ可能」。実 deploy はユーザーが再認証後に実施 | ユーザー |
| 2026-06-14 | テストランナーは Vitest（**snapshot のみ**）。CDK アプリ実行は tsx（`cdk.json` 更新）。devDeps: vitest/tsx/@types/node | ユーザー |
| 2026-06-14 | スコープは `IdashBatchStack` の collect のみ。notify は TODO | ユーザー |
| 2026-06-14 | 収集 Lambda: メモリ 1024 / タイムアウト 5分 / 予約同時実行 1 | ユーザー |
| 2026-06-14 | スケジュールは EventBridge Scheduler、cron JST 09:00（Asia/Tokyo）。L2 Schedule 優先・不可なら L1 CfnSchedule | ユーザー |
| 2026-06-14 | SSM SecureString は CDK で作成しない。`fromSecureStringParameterAttributes` でパラメータ名からインポートし `grantRead`。Lambda 環境変数にはインポートしたリソースの **ARN（parameterArn）** を渡す（キー名 `SHEETS_SA_PARAM_ARN`/`SOURCE_LOGIN_PARAM_ARN`）。`aws/ssm` のため明示 kms 付与なし | ユーザー |
| 2026-06-14 | 環境変数は `ENV_NAME` / `SHEETS_SA_PARAM_ARN` / `SOURCE_LOGIN_PARAM_ARN` | ユーザー |
| 2026-06-14 | CloudWatch Logs は明示 LogGroup＋保持7日＋RemovalPolicy.DESTROY | ユーザー |
| 2026-06-14 | bin/app.ts は batch のみ結線。envName 既定 'dev'、stack id `Idash-${envName}-Batch`、region ap-northeast-1・account env-agnostic | ユーザー |
| 2026-06-14 | テストは snapshot のみ（的を絞ったアサーションは入れない） | ユーザー |
| 2026-06-14 | タスク統合: `task test` に infra vitest 追加・`task synth` 新設・フル deploy はコメント据置・実 deploy 手順は README/再開ガイド | ユーザー |
| 2026-06-14 | CONTEXT.md / ADR は本タスクでは作成しない（ドメイン用語なし・暫定措置は可逆のため） | Claude（合意） |

---

## 作業再開ガイド

### 現在の状態
- **最終作業タスク**: フェーズ2・3 完了（実装＋検証すべてグリーン）
- **作業中断理由**: 実装完了。コミット/PR はユーザー指示待ち（本タスクではコミットしない）
- **次のアクション**: フェーズ4（セルフレビュー → ユーザー指示があれば PR 作成）。実 deploy はユーザーが再認証後に実施

### 再開時の確認事項
1. `PROJECT_PLAN.md` §12.2（IdashBatchStack スケルトン）・§11（コスト暴発対策）を再読
2. 本ファイルの「決定事項」を厳守（Lambda はプレースホルダ。コンテナ化は Phase 3）
3. 到達ラインは「`cdk synth` グリーン＋snapshot」。実 deploy はユーザー実施

### 実 deploy 手順（ユーザー実施・参考）
```bash
# 1) 再認証
aws login            # またはプロファイルで有効な認証情報を用意

# 2) 初回のみ CDK ブートストラップ（ap-northeast-1）
pnpm --filter @idash/infra exec cdk bootstrap aws://<ACCOUNT_ID>/ap-northeast-1

# 3) デプロイ（batch のみ結線済み）
pnpm --filter @idash/infra exec cdk deploy --require-approval never
```

### コンテキスト復元用コマンド
```bash
# ブランチ切り替え（未作成なら作成。base は main）
git switch -c feature/batch-collect-infra

# 最新化（リモート追従後）
git pull origin feature/batch-collect-infra
```
