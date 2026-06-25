# バッチ失敗は CloudWatch Alarm（Lambda `Errors`）→ SNS → Email で検知・通知する

collect / notify の 2 バッチ Lambda は「例外は再送出して Lambda 失敗扱いにし、検知に委ねる」設計だが、
検知・通知の仕組みが未実装で失敗（例外 / タイムアウト / OOM / 起動失敗）に気づけない。
**CloudWatch Alarm を Lambda の `Errors` メトリクスに張り（collect / notify 各 1 個）、SNS Topic 経由で
Email 通知する**。SNS の Email サブスクは個人のアドレスを IaC に載せないため CDK では作成せず、Topic 作成後に
手動追加・承認する（SSM SecureString を手動作成する既存パターンと同じ思想）。あわせて Scheduler の
`retryAttempts=0`（即失敗・即通知）とする。アプリ（Python）は無改修。

## Considered Options

- **CloudWatch Alarm on Lambda `Errors` → SNS → Email（採用）** — アプリ層を汚さず、例外だけでなく
  timeout / OOM / 起動失敗も Lambda の `Errors` として一律に拾える。低頻度バッチに合わせ `treatMissingData=
  notBreaching`・`evaluationPeriods=1`・`Sum ≥ 1`、OK（復旧）通知は付けない。collect / notify で**別アラーム 2 個**
  にし、どちらが落ちたか即わかるようにする。
- **アプリ内で例外を捕捉して直接通知（SNS publish / LINE 等）** — timeout / OOM / 起動失敗（ハンドラに到達しない
  失敗）を取りこぼす。通知のために application/infrastructure 層へ責務が漏れるため不採用。
- **Lambda Destinations（onFailure）** — 非同期呼び出し前提で構成が増える一方、検知粒度は Alarm と大差なく、
  timeout/OOM も結局メトリクス側で見たほうが素直なため不採用。
- **Email サブスクも CDK で作成** — アドレス（個人情報）がテンプレート/リポジトリに残る。SecureString を IaC 外で
  手動作成する既存方針と不整合のため不採用。

## Consequences

- `IdashBatchStack` に SNS Topic（自動命名）と CloudWatch Alarm 2 個を追加し、各アラームのアクションに
  Topic を配線する。物理名は付けない（[ADR の無し]＝CDK 自動命名方針）。
- **デプロイ後手順（IaC 外）**: 出力された Topic ARN に対し Email サブスクを手動追加し、届く確認メールで承認する。
  手順は `README.md` のデプロイ節に記載する。サブスク未承認の間は通知が飛ばない点に注意。
- Scheduler ターゲットを `retryAttempts=0` にし、失敗を即アラーム化する。リトライしないため**冪等性方針は引き続き
  未検討**（`PROJECT_PLAN.md` §インフラ・運用）。リトライを将来入れる場合は冪等性とセットで再検討する。
- **スコープ外（将来検討）**: Scheduler が Lambda を呼べない失敗（権限欠如 / 同時実行枯渇 throttle）や Scheduler の
  無音失敗は `Errors` に出ない。必要時に DLQ / `Invocations` 欠損アラームを追加検討する。
- Vitest スナップショット（`pnpm --filter @idash/infra run test:update`）が増分で壊れるため更新する。
