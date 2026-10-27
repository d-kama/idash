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
- eMudhra 対応（[#47](https://github.com/d-kama/idash/issues/47)）では
  侵害された中間 CA 鍵の SPKI 遮断を含む CfT Stable `156.0.8078.73` を採用する。
  `da63b94c` のバックポート
  [`3d1980a8`](https://github.com/chromium/chromium/commit/3d1980a8550c3cf594059ed3a974310b3a325c36)
  が対象タグに含まれることを確認済み。これは信頼するルートにつながるチェーンも拒否する
  **組み込みの鍵のブロックリスト**であり、配信更新に依存しない。
- Root Store v43（`8793082f`）による emSign ECC Root CA - G3 の信頼解除は別の変更。
  採用版の Root Store は v40 だが、今回の侵害鍵の遮断に v43 の取り込みは必須としない。
  これは eMudhra のルート全体を不信頼にする方針への変更ではない。
- 以後の版上げも main の commit position や公開予定日だけで判断せず、対象 Stable タグでの
  修正の取り込み（バックポートの場合はマージ CL）と、linux64 の headless-shell /
  chromedriver が同一版で提供されることを確認する。
- ChromeDriver には `browserName=chrome-headless-shell` を明示する。新規プロファイルでの
  初期タブ生成に必要で、通常の `chrome` として起動すると採用版では
  `unable to discover open pages` でセッション確立に失敗する。
- 変更後の実行イメージで共有ライブラリの不足が無いこと、対象証明書の拒否と正常な HTTPS
  接続の成功を確認する。DNS 失敗・タイムアウト・一般的な接続エラーは遮断成功とはしない。
  一時的な検証スクリプトはバージョン管理せず、結果・再現手順・未確認項目を PR コメントに
  記録する。認証情報や機密ログは含めない。
- TLS 検証、`task check`、デプロイ後の収集 Lambda 手動実行成功を確認するまで、
  停止中の収集バッチの自動実行を再開しない。
