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
