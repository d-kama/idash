# Issue #20: バッチ失敗時の Email 通知

## 背景 / 目的

collect / notify の 2 バッチ Lambda は「例外は再送出して Lambda 失敗扱いにし、検知に委ねる」設計だが、検知・通知の仕組みが未実装で、失敗（例外 / タイムアウト / OOM / 起動失敗）に気づけない。`PROJECT_PLAN.md:417`（監視・アラート方針=未検討）を埋める。

## スコープ

- [x] `IdashBatchStack` に SNS Topic（自動命名）を追加
- [x] collect / notify それぞれに CloudWatch Alarm（Lambda `Errors` ≥ 1）を追加し SNS をアクションに配線
- [x] Scheduler ターゲットの `retryAttempts=0`（即失敗・即通知 ／ CDK の prop 名は `retryAttempts`）
- [x] Vitest スナップショット更新（`pnpm --filter @idash/infra run test:update`）
- [x] デプロイ後手順: Topic への Email サブスク手動追加 + 確認承認（IaC 外・`README.md` デプロイ節に記載）
- アプリ（Python）は無改修

## 設計（グリル合意）

ADR-0004 に確定。要点:

- **検知**: CloudWatch Alarm on Lambda `Errors`（Sum ≥ 1, `evaluationPeriods=1`, `treatMissingData=notBreaching`）。collect / notify で**別アラーム 2個**。OK（復旧）通知は付けない。
- **通知先**: SNS Topic を CDK で自動命名作成。**Email サブスクは CDK で作らず手動追加・承認**（SSM SecureString 手動作成の既存パターンと同じ思想。アドレスをリポジトリ/テンプレートに残さない）。
- **即失敗・即通知**: Scheduler `maximumRetryAttempts=0`。
- **層**: アプリ無改修、`IdashBatchStack` 追記のみ。
- **スコープ外（将来検討）**: Scheduler が Lambda を呼べない失敗（権限欠如 / 同時実行枯渇 throttle）、Scheduler 無音失敗。必要時に DLQ / Invocations 欠損アラームを追加検討。

## 決定事項

| 日付 | 決定 | 補足 |
|---|---|---|
| 2026-06-25 | 検知=CloudWatch Alarm on `Errors`、通知先=SNS→Email | アプリ層を汚さず timeout/OOM/起動失敗も拾える（ADR-0004） |
| 2026-06-25 | アラームは collect/notify 別 2個・`notBreaching`・OK通知なし | 低頻度バッチで missing data 誤発報を避ける |
| 2026-06-25 | Email サブスクは Topic 作成後に手動追加 | 個人情報を IaC に載せない既存パターンに整合 |
| 2026-06-25 | Scheduler `maximumRetryAttempts=0` | 即失敗・即通知。冪等性方針（PROJECT_PLAN:418）は未検討のまま |

## メモ / 残課題

- 冪等性方針は引き続き未検討（`PROJECT_PLAN.md:418`）。
- Email サブスクの手動手順は `README.md` のデプロイ節（デプロイ後手順）に集約した。
- Scheduler の即失敗化は CDK `LambdaInvoke` の `retryAttempts`（合成後 `MaximumRetryAttempts`）で表現。

## 作業ログ

- 2026-06-25 ADR-0004 作成。`IdashBatchStack` に SNS Topic（自動命名）+ CloudWatch Alarm 2 個
  （collect/notify の Lambda `Errors`・`Sum≥1`・`notBreaching`・OK通知なし）を追加し SNS をアクション配線。
  collect/notify 両スケジュールに `retryAttempts: 0`。README にデプロイ後の Email サブスク手順を追記。
  typecheck / Vitest スナップショット更新 / synth 通過。
