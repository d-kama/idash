# データ収集バッチ 具象レイヤ実装（common + infrastructure + apps/batch DI）

## 基本情報

| 項目 | 内容 |
|------|------|
| チケット | issue-8（GitHub issue #8「アセット収集バッチ の実装」の具象層スライス） |
| ブランチ | feature/batch-collect-infra |
| 開始日 | 2026-06-18 |
| 目標完了日 | TBD |
| 最終更新 | 2026-06-19 |

---

## 要件サマリー

### 背景・目的

PR #9（issue-8）でデータ収集バッチの **抽象層（`domain` + `application`）** が完了済み。本タスクはその続きとして **Phase 3 の具象層**（`common` / `infrastructure` の各具象 / `apps/batch` の DI 結線）を実装する。

機能要件・モデルの正は Notion「確定拠出年金_v2」。実セレクタは旧 `scraping_nrk`（ユーザー提供）を参照し、その他の旧コードは参考に留めて本リポジトリの設計（クリーンアーキ・ADR-0002/0003）を優先する。

到達ラインは **「全具象＋DI のコードを書き、決定的にテストできる範囲（moto / fake / fixture）＋ `task check` / `synth` green」** まで。Selenium 実サイト検証・Dockerfile 実ビルド・CDK コンテナ差替・実デプロイは**ライブ依存のため後続フェーズ（本プラン フェーズ4）に明示分離**する。

### 受入条件

- [x] `common`: SSM SecureString 取得（`GetParameter WithDecryption` + モジュールスコープキャッシュ）/ os.environ ベース settings / stdlib logging + JSON フォーマッタ。追加依存は増やさない（boto3 のみ維持）
- [x] `infrastructure`: `SystemClock`（JST aware）/ `SheetsAssetRepository`（gspread・円整数保存）/ `S3ErrorPageStore`（boto3・None でもマーカー）/ `SeleniumScraper`（ADR-0002 ライフサイクル + 過渡ステップ含む）を実装し、各ポートを満たす
- [x] 抽出は `extract_portfolio(html, base_date) -> PortfolioAsset` の純粋関数（BeautifulSoup）に分離し fixture HTML で決定的にテスト
- [x] `apps/batch/handler_collect.py`（composition root）が SSM→config→具象構築→`CollectionUseCase.execute(url, credentials)` を結線
- [x] 決定的テストがグリーン（common SSM/settings/logging・各具象・handler・抽出・lifecycle 順序）— 計 51 passed
- [x] `task check`（ruff / Biome / ty / tsc / pytest+cov / infra-vitest）すべてグリーン + `task synth` green
- [x] `docs/adr/0003`（Selenium + 版ピン Chrome）を反映（本セッションで作成済み）

### スコープ

- **対象**:
  - `packages/common`（`settings.py` / `ssm.py` / `logging.py`）+ tests
  - `packages/infrastructure`（`clock.py` / `sheets.py` / `error_store.py` / `scraper.py`）+ tests + fixture HTML
  - `apps/batch/src/batch/handler_collect.py` + test
  - `packages/infrastructure/pyproject.toml`（`selenium` / `gspread` / `beautifulsoup4` / `lxml` 追加）、`pyproject.toml`（dev に `moto`、`--cov` に infrastructure/common 追加）、`uv.lock` 再生成
- **対象外（後続フェーズ4＝ライブ依存）**:
  - `apps/batch/Dockerfile`（版ピン chromium+chromedriver 同梱）
  - `IdashBatchStack` の collect コンテナ Lambda 差替・エラーページ S3 バケット追加・snapshot 更新
  - Selenium 実サイト検証（実セレクタ最終確定 / birthdate フォーマット確定）
  - 実デプロイ＆動作確認
- **対象外（Phase 4 別タスク）**: 通知系（`Notifier` / 集計 / `handler_notify`）、`AssetRepository` の read 系、`schemas`、`bff`

---

## コードベース調査結果

### 直接作成対象ファイル
| ファイルパス | 役割 | 状態 |
|-------------|------|------|
| `docs/adr/0003-selenium-pinned-chrome-on-lambda.md` | Selenium + 版ピン Chrome の ADR | ✅ 作成済み |
| `packages/common/src/common/settings.py` | os.environ ベースの設定（param ARN / env_name / bucket 名 等） | ✅ |
| `packages/common/src/common/ssm.py` | SSM SecureString 取得（WithDecryption・キャッシュ・JSON parse） | ✅ |
| `packages/common/src/common/logging.py` | stdlib logging + JSON フォーマッタ + `get_logger` | ✅ |
| `packages/infrastructure/src/infrastructure/clock.py` | `SystemClock`（JST aware） | ✅ |
| `packages/infrastructure/src/infrastructure/sheets.py` | `SheetsAssetRepository`（gspread）+ `SheetsConfig` | ✅ |
| `packages/infrastructure/src/infrastructure/error_store.py` | `S3ErrorPageStore`（boto3 s3） | ✅ |
| `packages/infrastructure/src/infrastructure/scraper.py` | `SeleniumScraper` / `_SeleniumScraperSession` / `ScraperConfig` / driver factory / `extract_portfolio` | ✅ |
| `apps/batch/src/batch/handler_collect.py` | composition root（DI 結線・`build_use_case`/`handler`） | ✅ |
| `packages/common/tests/test_*.py` | SSM(moto) / settings / logging | ✅ |
| `packages/infrastructure/tests/test_*.py` | clock / sheets / error_store / scraper(抽出+lifecycle) | ✅ |
| `packages/infrastructure/tests/fixtures/asset_page.html` | 抽出テスト用 fixture（提供セレクタ準拠） | ✅ |
| `apps/batch/tests/test_handler_collect.py` | handler の DI 結線（fake で粗粒度確認） | ✅ |

### 参照・影響範囲ファイル
| ファイルパス | 役割 | 影響内容 |
|-------------|------|----------|
| `packages/domain/src/domain/asset.py` | 値オブジェクト・`AssetRepository` ポート | 実装の契約（変更しない） |
| `packages/domain/src/domain/collection.py` | `Scraper`/`ScraperSession`/`ErrorPageStore`/`Clock`/`Credentials`/`ScraperError`/`ErrorPage` | 実装の契約（変更しない） |
| `packages/application/src/application/collection.py` | `CollectionUseCase` | handler で DI して呼ぶ（変更しない） |
| `packages/infrastructure/pyproject.toml` | infrastructure 依存 | `selenium` / `gspread` / `beautifulsoup4` / `lxml` 追加 |
| `pyproject.toml` | dev 依存 / pytest cov | `moto` 追加、`--cov=infrastructure --cov=common` 追加 |
| `apps/batch/pyproject.toml` | batch 依存 | 既配線（application/infrastructure/common）。変更不要見込み |
| `infra/lib/batch-stack.ts` | CDK collect Lambda | **後続フェーズ4**（コンテナ化・S3・env） |
| `infra/test/batch-stack.test.ts(.snap)` | Vitest snapshot | **後続フェーズ4**（`run test:update`） |

### 類似実装の参考箇所
| 参考 | 参考内容 |
|------|----------|
| `packages/application/tests/conftest.py` | Fake/InMemory fixture パターン（具象テストの観測スタイル） |
| Notion「確定拠出年金_v2」サンプル実装 | `@contextmanager` Scraper の open→login→yield→finally(logout→close) 構造 |
| 旧 `scraping_nrk`（ユーザー提供） | **実セレクタ・行/セル対応の正**（下記「抽出マッピング」） |
| `umihico/docker-selenium-lambda` | driver オプション・版ピン同梱（後続 Dockerfile） |

---

## 設計（グリル合意）

### 設定の流れ（composition root 集中）
`handler_collect`（composition root）が `common` 経由で 2 つの SSM SecureString を読み、config を組み立てて各具象へ注入。具象はプレーン config を受け取るだけで SSM を知らない（本質的に AWS/ブラウザに触れる `S3ErrorPageStore`/`SeleniumScraper` を除く）。

- `source-login`（SecureString JSON）= `{user_id, password, birthdate, start_url, user_agent}`
- `sheets-sa`（SecureString JSON）= `{credentials(SA JSON), spreadsheet_id, sheet_name}`
- env: `ENV_NAME` / `SHEETS_SA_PARAM_ARN` / `SOURCE_LOGIN_PARAM_ARN`（既存）/ `ERROR_PAGE_BUCKET`（後続 CDK で付与）

### common
- `ssm.get_secure_json(name) -> dict`: `boto3 ssm.get_parameter(Name, WithDecryption=True)` → `json.loads`。モジュールスコープでキャッシュ（コールドスタート時のみ取得）
- `settings`: `os.environ` ベース。pydantic 不使用
- `logging`: stdlib `logging` + 軽量 JSON フォーマッタ + `get_logger(name)`。追加依存なし

### infrastructure/clock.py
- `SystemClock`: `now() -> datetime` = `datetime.now(ZoneInfo("Asia/Tokyo"))`（JST aware）

### infrastructure/sheets.py
- `SheetsConfig(spreadsheet_id, sheet_name, credentials: dict)`
- `SheetsAssetRepository(config)`: `save(asset)` で `asset.products` を行展開し `worksheet.append_rows`。1 行 = `[base_date.isoformat(), name, contribution.yen, profit_loss.yen, valuation.yen]`（**金額は円整数を数値で保存**）
- 認証は `gspread.service_account_from_dict(credentials)`。ヘッダ行は既存前提（append のみ、シート初期化はしない）

### infrastructure/error_store.py
- `S3ErrorPageStore(bucket, *, s3_client=None)`: `save(page)` で `bucket` にアップロード
- key スキーム: `collect/{captured_at:%Y/%m/%dT%H%M%S}.html`（JST）
- `content` が `None` でも**必ずオブジェクトを書く**（マーカー本文）。`url` / `captured_at` を S3 オブジェクトメタデータに付与
- ContentType: 本文ありは `text/html`、マーカーは `text/plain`

### infrastructure/scraper.py（ADR-0002 / ADR-0003）
- `ScraperConfig(user_agent, chrome_binary_location, chrome_driver_path, implicit_wait=10, select_transferring_plan=True)`
- `SeleniumScraper(config, *, driver_factory=_default_chrome_factory)`: `session(url, credentials)` を `@contextmanager` で実装
  - `__enter__` 相当: `driver = driver_factory(config)` → `driver.get(url)` → ログイン入力（`name=userId/password/birthDate` → `#btnLogin` submit）→ 成功判定（「ログアウト」リンク存在、無ければ login 失敗で例外）→ **過渡ステップ** `_select_transferring_out_plan`（「転出処理中」プラン選択） → 失敗時はその場で `driver.quit()` して再送出
  - `yield _SeleniumScraperSession(driver, config)`
  - `finally`: `logout`（握り潰し）→ 必ず `driver.quit()`
- `_SeleniumScraperSession.scrape()`:
  - `#mainMenu01` クリック → `.total` 出現で読み込み確認 → `html = driver.page_source`
  - `return extract_portfolio(html, base_date=今日(JST))`
  - 失敗時は `raise ScraperError(msg, content=driver.page_source)`（取得自体が失敗したら content=None、主例外は隠さない）
- `extract_portfolio(html, base_date) -> PortfolioAsset`（**純粋関数 / BeautifulSoup**）: 下記マッピングで `ProductAsset` を組み立て `PortfolioAsset` を返す。`Money.parse` で金額解釈

#### 抽出マッピング（旧 scraping_nrk・「正」）
- 商品コンテナ: `#prodInfo .infoDetailUnit_02.pc_mb30`、商品名: `.infoHdWrap00`（strip）
- 拠出金額累計（contribution）: 商品 tbody の `tr[2]` の最終 `td`
- 評価損益（profit_loss）: `tr[5]` の最終 `td`
- 資産評価額（valuation）: `tr[2]` の `td[2]`
- ログイン: `name=userId/password/birthDate` 入力 → `#btnLogin` submit → 成功判定「ログアウト」リンク
- 過渡ステップ: `table.inputTable tbody tr` を走査し `td[data-lang='jp']` に「転出処理中」を含む行の radio をクリック → `#btnSubmit`
- 資産ページ遷移: `#mainMenu01` クリック → `.total` 待機

### apps/batch/handler_collect.py
- `event/context` 受領 → `common` で env 読取 → SSM 2 本を JSON 取得 → config 構築 → `SeleniumScraper` / `SheetsAssetRepository` / `S3ErrorPageStore` / `SystemClock` を構築 → `CollectionUseCase` に DI → `Credentials` と `start_url` を組み立て `execute(url, credentials)` を呼ぶ
- 成功時は最小 dict（`{"status":"ok","base_date":...,"products":N}`）をログ＆返却。例外は**捕捉せず再送出**して Lambda を失敗扱いにする（Notion 要件「例外をスローして終了」）

### テスト方針
- `common`: SSM（`moto @mock_aws`）/ settings（env）/ logging（JSON 出力検証）
- `SystemClock`: tzinfo が Asia/Tokyo
- `SheetsAssetRepository`: gspread クライアント/worksheet を mock し `append_rows` 引数（円整数・行構造）を観測
- `S3ErrorPageStore`: `moto` で content あり→本文+メタデータ / content=None→マーカー+メタデータ / key スキーム
- `SeleniumScraper`: `extract_portfolio` を fixture HTML で検証（複数商品・△/▲ 負値・¥/カンマ）。lifecycle 順序（open→login→[plan]→scrape→logout→close、login 失敗→close）を `FakeWebDriver` で検証（ADR-0002 が infra 具象の責務と明記）
- `handler_collect`: fake を注入し DI 結線が `execute` を呼ぶことを粗粒度で確認
- `--cov` はレポートのみ（閾値なし）

---

## 詳細タスク一覧

### フェーズ1: 準備・設計確認（グリル完了）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 1.1 | 要件グリル・合意形成（grill-with-docs） | ✅ | スコープ・設定フロー・各具象契約・テスト方針を確定 |
| 1.2 | 旧 scraping_nrk セレクタの v2 マッピング確認 | ✅ | 抽出マッピング（上記）に反映 |
| 1.3 | Selenium + 版ピン Chrome の意思決定記録 | ✅ | `docs/adr/0003` 作成 |

### フェーズ2: 実装
| # | タスク | 状態 | 対象ファイル |
|---|--------|------|-------------|
| 2.1 | common: settings / ssm / logging | ✅ | `packages/common/src/common/*` |
| 2.2 | infrastructure: SystemClock | ✅ | `clock.py` |
| 2.3 | infrastructure: SheetsAssetRepository | ✅ | `sheets.py` |
| 2.4 | infrastructure: S3ErrorPageStore | ✅ | `error_store.py` |
| 2.5 | infrastructure: SeleniumScraper + extract_portfolio | ✅ | `scraper.py` |
| 2.6 | apps/batch: handler_collect（DI） | ✅ | `handler_collect.py` |
| 2.7 | 依存配線（selenium/gspread/bs4/lxml・dev moto・cov 追加・uv.lock 再生成） | ✅ | `pyproject.toml` × 2, `uv.lock` |

### フェーズ3: テスト（検証）
| # | タスク | 状態 | 対象 |
|---|--------|------|------|
| 3.1 | common テスト（SSM moto / settings / logging） | ✅ | `packages/common/tests/` |
| 3.2 | SystemClock テスト | ✅ | `packages/infrastructure/tests/` |
| 3.3 | SheetsAssetRepository テスト（gspread mock） | ✅ | `packages/infrastructure/tests/` |
| 3.4 | S3ErrorPageStore テスト（moto・None・key） | ✅ | `packages/infrastructure/tests/` |
| 3.5 | SeleniumScraper テスト（fixture 抽出 + lifecycle） | ✅ | `packages/infrastructure/tests/` + `fixtures/asset_page.html` |
| 3.6 | handler_collect テスト（fake DI） | ✅ | `apps/batch/tests/` |
| 3.7 | `task check` グリーン | ✅ | ruff / Biome / ty / tsc / pytest+cov / infra-vitest（51 passed・cov 94%）+ `task synth` green |

### フェーズ4: ライブ依存（後続・ユーザー環境が必要）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 4.1 | `apps/batch/Dockerfile`（版ピン chromium+chromedriver 同梱） | ⬜ | umihico パターン / ADR-0003 |
| 4.2 | `IdashBatchStack`: collect を DockerImageFunction 化 + エラーページ S3（DESTROY+30日）+ `grantWrite` + env `ERROR_PAGE_BUCKET` + memory 2048/timeout 10分 | ⬜ | snapshot を `run test:update` |
| 4.3 | Selenium 実サイト検証（実セレクタ最終確定 / birthdate フォーマット） | ⬜ | 実サイト＋認証情報が必要 |
| 4.4 | 実デプロイ＆動作確認 | ⬜ | ユーザー実施 |

### フェーズ5: レビュー・完了
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 5.1 | セルフレビュー（受入条件チェック） | ⬜ | |
| 5.2 | PR 作成 | ⬜ | ユーザー指示があれば |
| 5.3 | コードレビュー対応 | ⬜ | |
| 5.4 | マージ・完了 | ⬜ | |

### ステータス凡例
- ⬜ 未着手 / 🔄 進行中 / ✅ 完了 / ⏸️ 保留 / ❌ キャンセル

---

## 総合進捗

| 項目 | 完了 | 総数 | 進捗率 |
|------|------|------|--------|
| 設計（フェーズ1） | 3 | 3 | 100% |
| 実装（フェーズ2） | 7 | 7 | 100% |
| 検証（フェーズ3） | 7 | 7 | 100% |
| **本タスク到達ライン（フェーズ2+3）** | **14** | **14** | **100%** |

※ フェーズ4（ライブ依存）はユーザー環境が必要なため後続。フェーズ5 はユーザー指示待ち。

---

## 作業ログ

### 2026-06-18
#### 実施内容
- [x] 要件グリル・合意形成（grill-with-docs）。スコープ・設定フロー・各具象契約・抽出マッピング・テスト方針を確定
- [x] `docs/adr/0003-selenium-pinned-chrome-on-lambda.md` 作成
- [x] 本進捗ファイル（issue-8-concrete）作成

#### 進捗サマリー
- **完了**: フェーズ1（設計）3/3
- **進行中**: なし（フェーズ2 実装は未着手）
- **ブロッカー**: なし

### 2026-06-19
#### 実施内容（フェーズ2 実装 + フェーズ3 検証を TDD で）
- [x] ブランチを main に ff 同期（PR #9 の抽象層を取り込み）。`feature/batch-collect-infra` は旧基点だったため
- [x] 2.7 依存配線: `infrastructure` に selenium/gspread/beautifulsoup4/lxml、dev に moto を追加、`--cov` に infrastructure/common/batch を追加、`uv sync` で `uv.lock` 再生成
- [x] 2.1/3.1 common: `settings`（os.environ）/ `ssm.get_secure_json`（moto・キャッシュ）/ `logging`（JSON フォーマッタ・冪等 get_logger）
- [x] 2.2/3.2 `SystemClock`（JST aware）
- [x] 2.3/3.3 `SheetsAssetRepository`（gspread client_factory 注入・円整数 append_rows）
- [x] 2.4/3.4 `S3ErrorPageStore`（moto・content None でもマーカー・url/captured_at メタデータ・key スキーム）
- [x] 2.5/3.5 `extract_portfolio`（fixture HTML・△負値）+ `SeleniumScraper` lifecycle（FakeWebDriver で open→login→[plan]→scrape→logout→close、login 失敗→close、抽出失敗→ScraperError(content)）
- [x] 2.6/3.6 `handler_collect`（composition root）: env→SSM2本→`build_use_case`→`execute`。`use_case_factory` を seam に fake DI 検証 + 実 wiring（Credentials/birthdate/start_url）を moto 下で検証
- [x] 3.7 `task check` 全グリーン（ruff/Biome/ty/tsc/pytest 51 passed・cov 94%/infra-vitest）+ `task synth` green

#### 進捗サマリー
- **完了**: フェーズ2（実装）7/7、フェーズ3（検証）7/7 = 本タスク到達ライン 14/14
- **進行中**: なし
- **ブロッカー**: なし。残りはライブ依存のフェーズ4（Dockerfile / CDK コンテナ化 / 実検証 / デプロイ）

---

## メモ・課題

### 未解決課題（ライブ検証フェーズで確定）
| # | 課題 | 優先度 | 対応 |
|---|------|--------|------|
| 1 | 実セレクタの最終確認（fixture は提供セレクタ準拠で作成。実 HTML との差異） | 中 | フェーズ4.3 |
| 2 | birthdate のフォーム入力フォーマット（`%Y%m%d` 等） | 中 | フェーズ4.3 |
| 3 | chromium / chromedriver の具体ピン版（umihico リリースに合わせる） | 中 | フェーズ4.1 |
| 4 | `start_url` 実値（SSM `source-login` に格納） | 低 | フェーズ4.4 |
| 5 | `_default_chrome_factory` の `--user-data-dir`（`tempfile.mkdtemp()`）を driver 終了時に解放（warm `/tmp` 圧迫対策）。live 専用・未テストのためコンテナ化検証と併せて実装（PR#10 CodeRabbit 指摘） | 中 | フェーズ4.1 |

### 決定事項
| 日付 | 決定事項 | 決定者 |
|------|----------|--------|
| 2026-06-18 | スコープ: 全具象＋DI のコードを書き、検証は決定的範囲（moto/fake/fixture）＋ task check/synth green まで。ライブ依存（Selenium 実検証・Dockerfile 実ビルド・CDK 差替・実デプロイ）は後続フェーズへ分離 | ユーザー |
| 2026-06-18 | 設定の流れ: composition root（handler_collect）が common 経由で SSM を読み config を具象へ注入。具象は SSM 非依存（S3/Selenium 除く） | ユーザー |
| 2026-06-18 | SSM スキーマ: 2 パラメータに JSON 同梱（source-login / sheets-sa）。非機密も同梱し既存 ARN 環境変数配線のまま | ユーザー |
| 2026-06-18 | Sheets: gspread、商品ごと1行 append、金額は円整数（`Money.yen`）を数値保存 | ユーザー |
| 2026-06-18 | ロギング: stdlib logging + JSON フォーマッタ（common、追加依存なし） | ユーザー |
| 2026-06-18 | AWS テスト擬装: `moto` を dev 依存に追加 | ユーザー |
| 2026-06-18 | S3 None 処理: `content=None` でもマーカー必須 + url/captured_at をメタデータ | ユーザー |
| 2026-06-18 | エラーページ S3 バケット: DESTROY + 30日 lifecycle（後続 CDK） | ユーザー |
| 2026-06-18 | collect Lambda（後続）: memory 2048 / timeout 10分 | ユーザー |
| 2026-06-18 | `SystemClock`: JST aware（Asia/Tokyo） | ユーザー |
| 2026-06-18 | Dockerfile（後続）: 版ピン chromium+chromedriver 同梱（umihico パターン、ADR-0003） | ユーザー |
| 2026-06-18 | 抽出: `page_source` → BeautifulSoup 純粋関数 `extract_portfolio(html, base_date)`。`beautifulsoup4`+`lxml` 追加 | ユーザー |
| 2026-06-18 | 過渡ステップ `_select_transferring_out_plan`（「転出処理中」プラン選択）を含める（移行進行中、TODO 明記） | ユーザー |
| 2026-06-20 | PR#10 レビュー対応: `Settings`→`CollectSettings` にリネーム（collect 固有フィールドのため。notify/BFF は各自定義） | ユーザー |
| 2026-06-20 | PR#10 レビュー対応: `Any` を排し本番型を厳格化（sheets=`gspread.Client/Worksheet`、scraper=`WebDriver`、handler factory=`CollectionInputBoundary`）。テストは注入点で `cast` 回避 | ユーザー |
| 2026-06-20 | PR#10 レビュー対応: scraper の `_Clock`/`_SystemClock` 重複を排し `domain.collection.Clock` + `infrastructure.clock.SystemClock` を再利用（層内依存は可） | ユーザー |
| 2026-06-20 | PR#10 レビュー対応: `driver.quit()` を `_safe_quit` で握り潰し、後始末失敗が主例外（`ScraperError`）を上書きしないようにする（ADR-0002 整合） | ユーザー |
| 2026-06-20 | PR#10 レビュー対応: lifecycle テストを後始末契約の3シナリオ（正常 / ログイン失敗 / scrape 失敗）＋ quit 失敗時の主例外保持に整理。全順序アサートは削除 | ユーザー |
| 2026-06-20 | PR#10 レビュー対応: `tempfile.mkdtemp()` 解放（C2）と `extract_portfolio` の境界チェック（C1）はフェーズ4へ先送り（live 専用 / 暫定セレクタのため） | ユーザー |

---

## 作業再開ガイド

### 現在の状態
- **最終作業タスク**: フェーズ2+3 完了（具象＋DI のコードと決定的テスト・`task check`/`synth` green）。**次は PR か、ライブ依存のフェーズ4**
- **次のアクション**:
  - （ユーザー指示があれば）5.2 PR 作成（ブランチ `feature/batch-collect-infra`、未コミット）
  - フェーズ4（ライブ依存・ユーザー環境必要）: 4.1 Dockerfile（版ピン chromium+chromedriver）→ 4.2 `IdashBatchStack` のコンテナ化・S3 バケット・env → 4.3 実サイト検証（実セレクタ / birthdate フォーマット確定）→ 4.4 デプロイ

### 再開時の確認事項
1. 本ファイルの「設計（グリル合意）」「決定事項」を確認してから着手
2. `domain` / `application` の契約（`asset.py` / `collection.py`）は変更しない
3. フェーズ4 の TODO は実コード内にもマーカーで明示済み: `scraper.py` の `_format_birthdate`（暫定 `%Y%m%d`）/ `_select_transferring_out_plan`（移行後削除）/ `_default_chrome_factory`（版ピン）、`handler_collect.py` の chrome パス env 既定値
4. fixture `asset_page.html` は提供セレクタ準拠。実 HTML との差異は 4.3 で詰める

### コンテキスト復元用コマンド
```bash
# ブランチ切り替え（未作成なら作成）
git switch -c feature/batch-collect-infra   # 既存なら: git switch feature/batch-collect-infra

# 検証
task check
```
