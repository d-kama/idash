# idash

iDeCo（個人型確定拠出年金）の運用状況を収集・蓄積し、可視化とサマリ通知を行うシステム。
本ファイルはドメイン用語集（ユビキタス言語）であり、実装詳細は持たない。

## Language

### 資産（Asset）

**ProductAsset**:
単一の投資商品（ファンド）について、ある基準日時点の拠出金額累計・評価損益・資産評価額を表す値オブジェクト。
_Avoid_: Product, Fund, Asset（単独では曖昧）

**PortfolioAsset**:
ある基準日（`base_date`）時点の全 ProductAsset の集合。ポートフォリオ全体としての合計（AssetTotal）を算出できる。
_Avoid_: Pension, PensionRecord, Portfolio（単独）

**AssetTotal**:
PortfolioAsset を構成する全 ProductAsset を合算した、ポートフォリオ全体の拠出金額累計・評価損益・資産評価額。

**Money**:
日本円の金額を円単位の整数で表す値オブジェクト。Web 取得文字列のパース、加減算、表示書式を担う。
_Avoid_: Amount, Yen

### 収集（Collection）

**Scraper** / **ScraperSession**:
外部 DC 年金サイトへ接続・ログインし、ScraperSession を通じて PortfolioAsset を取得するポート。ScraperSession はログイン済みの取得コンテキスト。
_Avoid_: SourceSite, Fetcher

**Credentials**:
外部 DC 年金サイトへのログインに必要な認証情報。実行時に Parameter Store から供給される。

**AssetRepository**:
PortfolioAsset を永続化するポート（保存・日付/期間での取得）。具象は Google Spreadsheet。
_Avoid_: PensionRepository

**ErrorPage** / **ErrorPageStore**:
スクレイピング失敗時点で捕捉したエラーページ（HTML 等の証跡）と、その保存先ポート。
