---
status: proposed
---

# DuckDB の S3 経路の統合テストに AWS Emulator を使う（opt-in 層）

`DuckDbAssetRepository` の `s3://` 経路（httpfs / aws 拡張 + `credential_chain`）はこれまでテストがなかった。
DuckDB の httpfs は C++ 実装で boto3 を経由しないため、moto のインプロセスモックでは原理的に検証できない。
この経路を **AWS Emulator** の S3 に向けた統合テストで検証する。テストは **opt-in**（専用マーカーと専用タスクで
明示したときだけ実行）とし、通常の `task test` / `task check` / CI には含めない。boto3 を使う具象
（`S3ErrorPageStore` / `common.ssm`）の単体テストは moto のまま残す。

試用の性格が強いため status は proposed とし、実際に運用して価値を確かめたら accepted に上げる。

## Considered Options

- **MinIO** — S3 互換に特化しており、HTTP で動かせるので DuckDB からも扱いやすい。ただし AWS 本家の API
  モデルから作られたものではなく、SSM などほかのサービスへ広げる余地がない。今回は AWS 公式エミュレータの
  試用も目的に含むため採用しない。
- **LocalStack** — 多サービスに対応するが、AWS 公式ではなく、機能によっては有償版が必要になる。採用しない。
- **moto サーバーモード** — 既存の依存で済むが、moto は boto3 向けのモックが本分で、S3 の忠実度は保証されない。
  採用しない。

## Consequences

- `DuckDbConfig` に、本番では未設定の S3 接続上書き（エンドポイント・URL スタイル・CA 証明書）が加わる。
  未設定のときの挙動は従来と同一。
- エミュレータには公式イメージがないため、Dockerfile をリポジトリで持ち、rpm のバージョンを固定する。
  エミュレータは頻繁に更新されるので、版上げは手動で行う。
- エミュレータは状態を永続化せずリセット機能もないため、テストはユニークなバケット（またはキー）で互いを分離する。
