# Scraper ポートはコンテキストマネージャ方式のセッションを返す

データ収集の外部サイト接続ポート `Scraper` は、単純な `scrape(url, credentials) -> PortfolioAsset` ではなく、
`session(url, credentials) -> AbstractContextManager[ScraperSession]` を返し、`with` ブロック内で
`ScraperSession.scrape()` を呼ぶ設計とする。ログイン後のログアウト・ブラウザクローズという**後始末を
`with` で確実化**し、ユースケースを「セッションを開いて scrape するだけ」に保つため。

## Considered Options

- **単純メソッド `scrape(url, credentials)`** — 呼び出しは簡潔だが、ログイン状態の後始末（logout / close）を
  ユースケースか具象が手続き的に抱えることになり、失敗経路での解放漏れが起きやすい。不採用。
- **コンテキストマネージャ方式のセッション（採用）** — `__enter__` 相当で open→login、`__exit__` 相当で
  logout（失敗は握り潰して主例外を隠さない）→必ず close。後始末を構造で保証する。

## Consequences

- 具象（Selenium 等）および抽象テストの Fake が守るべき本質は**後始末の契約**であり、各操作の網羅的な
  発生順そのものではない。具体的には (1) 正常終了・scrape 失敗のいずれでも `logout → close` の順で後始末する、
  (2) ログイン**確立前**の失敗（ログアウトリンク未検出＝サーバ側セッション無し）は `logout` を呼ばず
  `close` のみ。一方ログイン**確立後**の失敗（確立後の過渡ステップ＝プラン選択などで失敗）は
  サーバ側セッションが残るため `logout → close` で後始末する（残存セッションでの再ログイン不能を防ぐ）、
  (3) 後始末（logout / close）の失敗は握り潰して主例外を隠さない、の3点。`open→login→scrape` は
  通常フローの説明であって、テストで全ステップの順序を逐一アサートする必要はない（後始末契約に焦点を当てる）。
- ユースケースはセッション本体内で `scrape()` のみを呼び、失敗時に `ScraperError.content`（捕捉済みページ）から
  `ErrorPage` を組んで保存する。
