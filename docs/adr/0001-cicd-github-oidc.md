# CI/CD は GitHub Actions、AWS 認証は GitHub OIDC（長期キー不使用）

idash の CI/CD は GitHub Actions の単一ワークフロー（`.github/workflows/cicd.yml`）で構成し、
AWS への deploy は GitHub OIDC が発行する短命トークンで準備済み IAM ロールを assume して行う。
**静的アクセスキーは発行・保管しない（GitHub Secrets にも置かない）。** 当該ロールは CDK の
bootstrap ロール（`cdk-hnb659fds-*`）を `sts:AssumeRole` する標準形で最小権限に保つ。
CD は `main` への push（自動）と `workflow_dispatch`（手動）で起動し、対象環境は dev 単一。

## Considered Options

- **静的 IAM アクセスキーを GitHub Secrets に保管** — 鍵の漏洩リスクとローテーション負債を恒常的に
  抱えるため不採用。
- **GitHub OIDC で短命トークン（採用）** — 鍵を持たず、ロールの trust 条件でリポジトリ/ブランチを
  限定できる。`ref:refs/heads/main` に絞り、push・手動いずれも同一条件で assume 可能。

## Consequences

- ロール ARN は機密ではないため、repo **Variable**（`AWS_DEPLOY_ROLE_ARN`）で参照する（Secret にしない）。
- OIDC provider / IAM ロール / `cdk bootstrap` は **AWS 側で事前準備済み**（本リポジトリの IaC 管理外）。
  再作成・移行時は手動対応が必要。
- 将来 stg/prod を分ける場合は、環境ごとにロール（または trust 条件）を分け、ワークフローの
  `aws-region` / stack 選択を環境化する。
