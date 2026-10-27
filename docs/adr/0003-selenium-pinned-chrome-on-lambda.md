# データ収集は Selenium ＋ 版ピン chromium/chromedriver を Lambda コンテナに同梱する

外部 DC 年金サイト（NRK 系）の収集は公開 API が無く、`requests` + セッション/クッキー方式では取得できなかったため、
ヘッドレスブラウザ自動化（**Selenium**）を採用する。実行基盤は Lambda コンテナイメージとし、**バージョンを一致させた
chromium headless-shell ＋ chromedriver をイメージに同梱（版ピン留め）**する。旧実装で頻発した版不整合起因の
`InvalidSessionId` / `NoSuchElement` を構造的に避けるのが目的（umihico/docker-selenium-lambda パターン）。

## Considered Options

- **Selenium ＋ 版ピン chromium/chromedriver 同梱（採用）** — 旧実装のセレクタ・ナビゲーション知見をそのまま移植でき、
  版を明示ピンすることで再現性を確保。コンテナ Lambda なので重いブラウザ依存も同梱できる。イメージは肥大化する。
- **OS パッケージ（dnf/yum）で chromium 導入** — 手軽だが版がディストリ更新に追従して不整合が再発しうる。不採用。
- **Playwright へ移行** — ブラウザ版管理は楽だが、旧資産（セレクタ・抽出ロジック）の移植メリットを捨て、イメージも肥大化。
  既存知見の活用と段階移行を優先して不採用（将来再評価の余地は残す）。

## Consequences

- 具象 `SeleniumScraper` は driver 生成をファクトリ注入にし、テストでは `FakeWebDriver` に差し替える。版ピンの実体は
  Dockerfile（後続フェーズ）に置き、`chrome_binary_location` / `chrome_driver_path` は設定で渡す。
- 抽出は selenium のナビゲーション（メニュー遷移・待機）と、`page_source` → `PortfolioAsset` への純粋関数
  （BeautifulSoup）に分離し、後者を fixture HTML で決定的にテストする。実セレクタの最終確定とログインフォームの
  birthdate 入力フォーマットは、実サイトを用いるライブ検証フェーズで詰める。

## CA の失効・不信頼への追従

- Linux の Chrome は独自の **Chrome Root Store** を使うため、OS の `/etc/pki` の
  ブロックリストは Chrome に効かない。OS 側の対策は Python・OS 向けとして維持する。
- 採用している headless-shell は component updater を持たず、毎回新規の `user-data-dir`
  で起動する。CRLSet や Root Store の配信更新は受け取れないため、CA の失効・不信頼は
  **対応を組み込んだバイナリへの版上げ・再ビルド・再デプロイ**で反映する。
- eMudhra 対応（[#47](https://github.com/d-kama/idash/issues/47)）は
  `da63b94c`（侵害された中間 CA の SPKI 遮断）と `8793082f`（Root Store v43）の
  **両方を含む CfT Stable** を選定する。main の commit position や公開予定日だけで判断せず、
  対象 Stable タグでの取り込み（バックポートの場合はマージ CL）を確認する。
  linux64 の headless-shell と chromedriver が同一版で提供されることも確認する。

### 手動 TLS 検証（CI 対象外）

リポジトリルートで `task verify:chrome-tls` を実行する。Docker と外部ネットワークが必要。
本番の batch イメージをビルドし、`_default_chrome_factory` の起動オプションと新規プロファイルを
そのまま使う。検証先は公開テストホストのみで、SSM や年金サイトの認証情報は使わない。

- `dv-g3b-emudhra.we-have-a-problem.com`（emSign 経路）と
  `dv-g3b-aaa-emudhra.we-have-a-problem.com`（AAA 相互署名経路）は証明書エラーで遮断されること。
- 陽性対照 `letsencrypt.org` は HTTPS で開くこと。
- Selenium の `net::ERR_CERT_*` を証明書拒否と判定する。headless-shell は空の
  `chrome-error://` ページを例外なしで返す場合があるため、その場合は CDP の
  `Page.navigate` で再検証し、`errorText` が `net::ERR_CERT_*` であることを確認する。
  エラーページであることだけでは成功としない。DNS 失敗・タイムアウト・一般的な接続エラーは
  遮断成功とはせず、判定不能として非ゼロ終了する。各ホストの結果と Chrome の版を出力し、
  全条件を満たした場合だけ 0 終了する。

旧版の判定確認や候補版の検証では Docker の build 引数を渡せる（Dockerfile のピンは変わらない）。
131 で対象ホストが開く場合は検証の **失敗（非ゼロ終了）** が期待値であり、安全確認ではない。

```bash
task verify:chrome-tls -- --build-arg CFT_VERSION=131.0.6778.108
task verify:chrome-tls -- --build-arg CFT_VERSION=<candidate-version>
```

ローカルに同一版のバイナリを配置済みなら、コンテナをビルドせず検証スクリプトを直接実行できる。

```bash
CHROME_BINARY_LOCATION=/path/to/chrome-headless-shell \
CHROME_DRIVER_PATH=/path/to/chromedriver \
uv run python apps/batch/scripts/verify_chrome_distrust.py
```

版上げ時は実行イメージ内の `ldd /opt/chrome/chrome` に `not found` が無いことを確認し、
必要なら dnf の共有ライブラリ依存を追加する。infra のスナップショットは
`pnpm --filter @idash/infra run test:update` で更新する。
**両経路の拒否・陽性対照の成功、`task check`、デプロイ後の収集 Lambda 手動実行成功**が
揃うまで、停止中の収集バッチの自動実行を再開しない。
