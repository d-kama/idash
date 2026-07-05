# ダッシュボードのアクセス制御を CloudFront Basic 認証 + Geo 制限 + origin-verify とする

可視化ダッシュボード（Phase 6）のアクセス制御を、**CloudFront を唯一の入口**とし、
CloudFront Functions による Basic 認証 + Geo 制限(JP) で保護する。オリジン（S3 / API Gateway）へ
の直接アクセスは、S3 は OAC、API Gateway は **origin-verify 共有シークレット**で塞ぎ、
その検証は **BFF Lambda 内（FastAPI 依存）で行う（Lambda Authorizer は使わない）**。

本 ADR は方式決定の記録。実装は Phase 6（`docs/progress/issue-27.md` step 11/12）で行う。

## Context

- 対象は個人利用・低頻度・**read-only** の iDeCo 残高可視化。書き込み経路はなく、データ機微度も低い
  が、資産履歴を返すため無制限公開は避けたい。
- リポジトリは **public**。認証情報・シークレットをコード/テンプレートに埋め込めない。
- 3 つの制約が方式を縛る:
  1. **public repo** — 秘密値をコードに置けない。
  2. **CloudFormation は SecureString を作成不可** — SSM SecureString / CloudFront KVS の値は
     CDK では作らず、AWS 側で手動投入する（既存の `source-login` / `notify-line` と同じ運用）。
  3. **`task synth` は AWS 認証不要を維持** — synth 時に秘密を読みに行かない。
- 脅威は ① 素の URL への到達（casual access）② 国外からのアクセス ③ **API Gateway 既定
  エンドポイントへの直叩きで CloudFront の認証を迂回される**こと。
- HTTP API（API Gateway v2）は REST API のような resource policy / request-parameter validation を
  持たず、ゲートウェイ単体でのヘッダ照合はできない（WAF は追加コスト）。

## Decision

- **CloudFront を唯一の入口**にする。default behavior = S3（**OAC** で CloudFront 限定）、
  `/api/*` behavior = API Gateway（HttpOrigin）。
- **Basic 認証** — `cloudfront.Function`（runtime JS 2.0）+ `KeyValueStore`。**両 behavior** の
  viewer-request に適用し、KVS の期待値（`Basic <base64(user:pass)>`）と `Authorization` を照合、
  不一致は 401。
- **Geo 制限** — CloudFront の allowlist(JP)。
- **origin-verify（CloudFront 経由限定化）** — `/api/*` の CloudFront Function が Basic 認証通過後、
  KVS の別キー `origin-verify` の秘密値を `x-origin-verify` ヘッダへ**上書き注入**（クライアント偽装値を
  無効化）。**BFF Lambda（FastAPI 依存）が SSM SecureString `/idash/<env>/origin-verify` の期待値と
  照合し、不一致/欠落は 403**。CloudFront を迂回した API Gateway 直叩きは秘密値を知らず弾かれる。
- **origin-verify の検証は BFF Lambda 内で行い、Lambda Authorizer は使わない**（根拠は Considered
  Options）。
- **秘密の置き場** — CloudFront 側 = KVS（`basic-auth` / `origin-verify` の 2 キー）、BFF 側 = SSM
  SecureString（`origin-verify`）。いずれも AWS 側で手動投入する。

## Considered Options

- **origin-verify の検証を Lambda Authorizer で行う** — 統合前に弾ける利点はあるが不採用。
  ① 別 Lambda（成果物・IAM ロール・CDK 配線・コールドスタート）が増え、コンテナ BFF の前段で
  コールドスタートが二重化する。② 秘密読取（SSM）を Authorizer 側にも作る必要があり一元性を失う。
  ③ 背後は**単一 Lambda（BFF）**のため「検証の一元化による重複排除」の利得がない。④ 検証は定数の
  共有シークレット照合で役割が軽く（本来の認証は CloudFront Basic 認証側）、`apps/bff`（薄いアダプタ層）
  で FastAPI 依存として数行で済む。「拒否時に BFF を起動させない」利得はあるが、ステージの
  スロットリング（rate 20 / burst 40）+ 予約同時実行 3 で流量は既に上限化されており実効差は小さい。
- **既定エンドポイント無効化（`disableExecuteApiEndpoint`）** — 独自ドメイン + ACM が前提（無効化
  すると到達経路が独自ドメインのみになる）で本件のスコープ外。かつ単体では CloudFront 経由限定に
  ならない（公開 DNS の独自ドメインは直接到達可能）ため不採用。
- **IP 制限（allowlist）** — 家庭/モバイル回線は IP 変動が激しく運用が破綻するため不採用。
- **Cognito / OAuth 等の本格認証** — 個人利用の read-only ダッシュボードに対して過剰。
- **CORS** — ブラウザ側の**レスポンス読取制御**であり、サーバへの到達制御にはならない
  （curl / サーバ間は CORS を無視するため直叩きに無力）。origin-verify の代替にならない。加えて
  フロントと API は同一 CloudFront ドメイン = 同一オリジンで、自前フロントからのアクセスに CORS は
  不要。
- **SPA フォールバック（403/404 → index.html）** — ルーティングなしの 1 ページで不要なうえ、
  カスタムエラーレスポンスがディストリビューション全体に効き `/api/*` のエラー応答まで書き換える
  副作用があるため入れない（関連決定）。

## Consequences

- KVS に 2 キー（`basic-auth` / `origin-verify`）、SSM に `origin-verify` を**手動投入**する。
  投入前はダッシュボードが開けないだけで、データ流出方向のリスクはない。手順は README に明記する。
- **秘密ローテーション順は KVS → SSM**。先に SSM を変えると、正規経路（CloudFront が旧値を注入）が
  一時的に 403 になるため、CloudFront 側（KVS）を先に更新する。
- BFF 実行ロールに当該 SSM パラメータの `ssm:GetParameter` を付与する（aws/ssm マネージドキーのため
  `kms:Decrypt` の明示付与は不要）。BFF は `common.ssm` でコールドスタート時に取得・キャッシュする。
- `/api/*` と default の**両 behavior に Function を付け漏らす**と認証が素通しになるため、CDK の
  スナップショットテストで両 behavior の `FunctionAssociations` を検証する。
- **Phase 5 完了〜Phase 6 完了の間**は CloudFront 未経由・素の API Gateway（認証なし）で、自動命名の
  推測困難 URL（obscurity）のみで保護する。origin-verify は Phase 6 で入るため、この期間は短く保つ。
- origin-verify の拒否は BFF Lambda の起動を伴うが、スロットリング + 予約同時実行で上限化されている。
- S3 は OAC、API Gateway は origin-verify という**非対称だが目的（CloudFront 経由限定）は共通**の構成に
  なる。独自ドメイン・ACM を増やさずに CloudFront 一本化を達成する。
