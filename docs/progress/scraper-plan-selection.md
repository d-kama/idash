# scraper: プラン選択を「1行目のプラン」選択に変更する

- **short-topic**: `scraper-plan-selection`
- **作業ブランチ**: `fix/scraper-plan-selection`
- **ステータス**: 完了

## 目的・背景

`SeleniumScraper` はログイン後の**プラン選択画面**で、異動状況セルに「転出処理中」を含む行の
ラジオを選んで「決定」する過渡ステップ（`_select_transferring_out_plan`）を持っている
（`packages/infrastructure/src/infrastructure/scraper.py:225`、issue-8 の決定事項）。

転出処理が**完了**したため、現在の画面には「転出処理中」の行が存在しない。

| 行 | プランコース | 異動状況 | transIn / transOut |
| --- | --- | --- | --- |
| 1行目 | スリムコース | （空欄） | 03 / 00 ← 収集対象 |
| 2行目 | 標準コース | 転出済 | 00 / 03 |

その結果、現行コードはループを一巡しても該当行が無く、ラジオも `#btnSubmit` も押さずに
**黙って返る**。プラン選択画面のまま資産ページへ遷移できず、収集が失敗する（あるいは
意図しないページを収集する）状態になっている。

プラン選択画面自体は移行完了後も残るため、ステップは廃止せず、**テーブル1行目のプランを
選ぶ**という単純な方針へ変更する（1行目は既定で `checked` かつ収集対象のスリムコース）。
異動状況テキストへの依存を捨てることで、文言変更に対しても壊れにくくなる。

## スコープ

### 対象（やること）

- `_select_transferring_out_plan` を **1行目のプランを選ぶ**実装に置き換える
  （`table.inputTable tbody` 内の最初の `input[name='checkedPlanIdx']` をクリック → `#btnSubmit`）。
  メソッド名も実態に合わせて `_select_plan` に改名する。
- **実行場所を `SeleniumScraper._open_and_login`（セッション確立）から
  `_SeleniumScraperSession.scrape()` の冒頭へ移す**。プラン選択はログインの一部ではなく
  資産ページへ至る画面遷移の一部、という整理（→「決定事項」）。
- `ScraperConfig.select_transferring_plan` → **`select_plan`** にリネームし、
  「移行期間中のみ」「移行完了後に削除する」旨の TODO コメントを外す（既定 `True` は維持）。
- 要素が見つからない場合は `ScraperError`（失敗時点のページを `content` に添付）を送出して
  **収集を失敗させる**（`session()` の `finally` で logout → close される）。
- `packages/infrastructure/tests/test_scraper.py` の FakeWebDriver / プラン選択テストを
  新仕様に合わせて更新する。
- **`scripts/run_collect_local.py` で実サイトに対する動作確認**（`--dry-run`）を行い、
  1行目（スリムコース）が選択されて資産ページまで到達し、抽出結果が妥当であることを確認する。
- 本ファイル（`docs/progress/scraper-plan-selection.md`）に検証結果と決定を記録する。

### 対象外（やらないこと）

- プラン選択ステップの廃止（画面は残るためフラグごと残す）。
- `extract_portfolio` の抽出マッピング変更、資産ページ側のセレクタ見直し。
- プラン選択画面の HTML fixture 追加や、Selenium を実際に起動する統合テスト
  （既存方針どおり FakeWebDriver で契約のみ検証する）。
- infra（CDK）・環境変数・SSM パラメータの変更（`select_plan` は既定値のまま、
  `handler_collect.py` からは指定しない）。CDK スナップショットは Docker イメージの
  ダイジェスト差分のみ追随更新する。
- 過去の progress ファイル（`issue-8-concrete.md` 等）の記述更新。当時の記録として残す。
- `CollectionUseCase` がセッション確立時（ログイン・プラン選択）の失敗もエラーページ保存
  対象に含める改修（既知の穴。→「未確定事項・リスク」）。

## 実装ステップ

> implement スキルがステップごとに実装・レビューを回す。各ステップは
> 独立してテスト・レビューできる粒度に分割し、完了したら `[x]` にする。

- [x] 1. `ScraperConfig.select_transferring_plan` を `select_plan` にリネームし、コメントを
      「プラン選択画面で1行目のプランを選ぶステップ」に更新する。`_open_and_login` の参照
      （`scraper.py:210`）も追随させ、`task typecheck` で参照漏れが無いことを確認する。
- [x] 2. `_select_transferring_out_plan` を `_select_plan` に置き換える。実装は
      「`table.inputTable tbody input[name='checkedPlanIdx']` を `find_element` で1件取得 →
      `click()` → `#btnSubmit` を `click()`」のみ。`find_elements` によるテキスト走査と
      「転出処理中」判定・祖先 tr 辿りは削除し、なぜ1行目固定でよいか（1行目が収集対象の
      スリムコース、2行目は転出済）をコメントに残す。失敗時は握り潰さず `ScraperError` に
      包んで送出する（Selenium 例外を上位層へ漏らさない）。証跡ページは載せない。
      - レビュー反映: 当初 `input[type='radio']` だったセレクタを `name='checkedPlanIdx'` に
        変更（別画面が挟まったときに無関係な選択肢を押す事故を防ぐ）。
- [x] 3. `test_scraper.py` を更新する。
      - `FakeWebDriver._plan_cells`（異動状況セル列）と `find_elements` のプラン分岐を削除し、
        `find_element` が `name='checkedPlanIdx'` で引かれたときに `plan-radio` を記録する
        要素を返す形へ（＝汎用の `inputTable` だけで引かないことを fake 側で担保する）。
      - `has_plan=False` を「プラン選択画面が出ない（ラジオが無い）」ケースとして扱い、
        `ScraperError`（`content` 付き）が送出され `logout` → `close` される後始末契約を確認する。
      - **テストケースの棚卸し**（ユーザー合意）: lifecycle は後始末契約の観点で5本に整理する。
        - 正常系（`test_normal_completion_logs_out_then_closes`）に plan 選択を畳み、
          `login → plan-radio → plan → logout → close` を**部分列**で検証する
          （完全一致の順序アサートは PR#10 の決定どおり避け、ステップ追加で壊さない）。
        - 削除: `test_plan_selection_clicks_plan_radio_then_submits`（正常系に統合）、
          `test_plan_selection_skipped_when_disabled`（`select_plan` の2行分岐のため）、
          `TestExtractPortfolio::test_sets_base_date`（`test_maps_each_product` の
          `PortfolioAsset` 全体比較に含まれ重複）。
        - 残す: 正常系 / ログイン確立前の失敗 / 確立後・yield 前の失敗（プラン選択）/
          yield 後の失敗（scrape、`ScraperError.content` の証跡契約）/ quit 失敗が主例外を
          隠さないこと（ADR-0002・PR#10 の決定を守る唯一のテスト）。
      - `task test` がグリーンであることを確認する。
- [x] 4. **実サイトでの動作確認**（`scripts/run_collect_local.py`）。別ターミナルで
      `docker run --rm -p 4444:4444 -p 7900:7900 selenium/standalone-chrome:4.27.0` を起動し、
      `uv run python scripts/run_collect_local.py --dry-run` を実行する。
      - noVNC（http://localhost:7900, password=secret）でプラン選択画面が1行目（スリムコース）
        で「決定」され、資産ページへ遷移することを目視する。
      - 標準出力の `[dry-run]` 行で商品ごとの `contribution` / `valuation` / `profit_loss` が
        妥当であること（＝転出済の標準コースではなくスリムコース側の資産であること）を確認する。
      - 失敗した場合は `./errorpages/collect-*.html` を開いて実 DOM を確認し、
        ステップ2のセレクタ（`table.inputTable` の一意性など）を調整して再実行する。
      - 確認できた内容（実行日・選択された行・抽出結果の要約）を本ファイルに追記する。
      - 注: `run_collect_local.py` の composition root は `ScraperConfig` に `select_plan` を
        渡さない（既定 `True`）ため、リネームによるスクリプト側の変更は不要。ステップ1で
        参照漏れが無いことだけ確認する。
- [x] 5. 本ファイルに検証結果・レビュー対応を追記し、ステータスを「完了」にする。
      過去の progress ファイル（`issue-8-concrete.md` 等）は**当時の記録として修正しない**。
- [x] 6. `task check` を通し、`git-workflow` スキルで `fix/scraper-plan-selection` から
      コミット・PR を作成する。

## 決定事項

| 日付 | 決定 | 決めた人 |
| --- | --- | --- |
| 2026-08-14 | 「転出処理中」の行を探す実装をやめ、プラン選択テーブルの**1行目**（`input[name='checkedPlanIdx']` の最初の1件）を選ぶ | ユーザー |
| 2026-08-14 | `select_transferring_plan` → `select_plan` にリネームし、フラグ自体は残す（プラン選択画面は移行後も残るため） | ユーザー |
| 2026-08-14 | プラン選択失敗時のページ保存は不要（当時は保存経路が無かったため）→ **session 側へ移して保存可能になったので撤回し、`content` に失敗時点のページを載せる** | ユーザー |
| 2026-08-14 | プラン選択を `SeleniumScraper._open_and_login`（セッション確立）から `_SeleniumScraperSession.scrape()` へ移す。ログインの一部ではなく資産ページへ至る画面遷移の一部として扱う | ユーザー |
| 2026-08-14 | lifecycle テストは後始末契約の観点で整理（正常系にプラン選択を畳む・`select_plan=False` と `base_date` の重複テストを削除） | ユーザー |

### プラン選択を session 側へ移したことの影響

- `_open_and_login` は「開く → 入力 → ログイン成功判定」だけになり、確立後・yield 前に失敗する
  ステップが無くなった。そのため同メソッドの `except BaseException: logout → raise` は削除した
  （ログイン失敗時は従来どおり logout せず close のみ）。
- プラン選択の失敗は `with` の内側（`scrape()`）で起きるようになったため、`CollectionUseCase` の
  `except ScraperError` に捕捉され `ErrorPageStore.save` が呼ばれる。これにより失敗時点の
  HTML が証跡として残せるようになったので、`_select_plan` は `scrape()` と同じく
  `content=_safe_page_source(...)` を添える（実検証で保存を確認済み → 検証結果）。
- `scrape()` は1セッションにつき1回呼ぶ前提になった（2回目はプラン選択画面が無く失敗する）。
  現状の唯一の呼び出し元 `CollectionUseCase.execute` は1回しか呼ばない。

## 検証結果（2026-08-14）

`scripts/run_collect_local.py --dry-run`（standalone-chrome 4.27.0 / Remote WebDriver）で実サイト検証。

- プラン選択画面を1行目で「決定」し、資産ページまで到達して抽出まで成功（**連続2回とも成功**）。
  セレクタを `input[name='checkedPlanIdx']` に絞った後、さらに `scrape()` へ移した後にも
  それぞれ2回ずつ実行し、いずれも同じ結果で成功した。
- 抽出結果（`--dry-run` 出力、base_date=2026-08-14 / products=2）:
  - ｅＭＡＸＩＳ Ｓｌｉｍ 先進国債券インデックス（除く日本）: contribution=1,983 / valuation=1,949 / profit_loss=-34
  - ｅＭＡＸＩＳ Ｓｌｉｍ 米国株式（Ｓ＆Ｐ５００）: contribution=2,358,262 / valuation=2,396,061 / profit_loss=37,799
  - いずれも eMAXIS Slim シリーズ＝**スリムコース（1行目）側の資産**であることを確認（転出済の標準コースではない）。
- 補足: 一連の検証の**初回のみ**ログイン成功判定（「ログアウト」リンク）に失敗した。直後の
  手動ダンプではログイン後ページ（＝プラン選択画面）に「ログアウト」リンクが存在し検出もでき、
  以降 4 回の実行では再現しなかった。standalone-chrome 起動直後のコールドスタート由来と判断し、
  本変更とは無関係として扱う（再発したら実 Lambda 側のログで再確認する）。

### 追加検証（プラン選択を scrape() へ移した後）

- 正常系: `--dry-run` を2回実行し、いずれも移動前と同じ結果（上記の2商品）で成功。
- 失敗系: セレクタを一時的に壊して（`checkedPlanIdxBROKEN`）実行し、`ErrorPageStore`
  （ローカルでは `_LocalFileErrorPageStore`）に**プラン選択画面の HTML が保存されること**を確認。
  保存ファイルに `checkedPlanIdx` ×2 / `スリムコース` / `標準コース` / `転出済` を確認（11,600 byte）。

### 検証中に判明した既存の挙動（本変更の対象外）

プラン選択画面から `_logout_quietly` の「ログアウト」クリックが**効かない**（当該画面の
`onclick="return formSubmitCheck();"` が submit を止めていると推測）。その結果サーバ側
セッションが残り、次回ログインが「現在、同じユーザーIDで利用されています…(990003)」で
弾かれる（→ `_is_logged_in` が False になり `ログインに失敗しました` になる）。
サーバ側セッションのタイムアウトを待てば回復する。

- プラン選択が失敗した回の後始末で起きるため、**失敗が次回実行にも1回波及**する可能性がある。
- 本変更以前（プラン選択が `_open_and_login` にあった頃）も同じ経路で logout していたため、
  新たに生じた問題ではない。
- 対処するなら「ログアウトを待つ / 別画面へ遷移してからログアウトする」等の改修が要る。

## 未確定事項・リスク

- 1行目のラジオが既定で `checked` のため、クリックせず `#btnSubmit` だけでも通る可能性が
  高いが、明示クリックは冪等なので安全側に倒している。
- **1行目＝収集対象という前提**は実サイト検証（上記）で確認済み。プラン構成が再び変わったら
  （例: 新プランへの再移行）1行目固定の前提が崩れるため、この計画に立ち返る。
- **将来プラン選択画面が消えた場合**は `ScraperError` で収集が失敗する（合意済みの挙動）。
  その時点で `select_plan=False`（＝コード変更＋再デプロイ）か、ステップごと削除する。
  env/SSM からは切り替えられない（切替は稀な想定のため配線していない）。
- **ログイン／プラン選択の失敗ではエラーページが S3 に残らない**（既知の穴）。
  `CollectionUseCase.execute` はセッション確立後の `scrape()` 失敗のみ `ErrorPageStore` に保存し、
  `with` の `__enter__`（＝ログイン・プラン選択）で送出された `ScraperError` は捕捉しない
  （issue-8 での明示的な決定）。
  **決定（2026-08-14・ユーザー）**: プラン選択失敗時のページ保存は不要とし、ログに出る例外
  メッセージ（`プラン選択に失敗しました: <Selenium のメッセージ>`）で足りるものとする。
  よって `_select_plan` は `ScraperError` に `content` を載せない。application 層で確立時失敗も
  証跡保存する改修は行わない。

## 参照リンク

- `packages/infrastructure/src/infrastructure/scraper.py`（`ScraperConfig` / `_select_plan`）
- `packages/infrastructure/tests/test_scraper.py`（`TestSessionLifecycle`）
- `scripts/run_collect_local.py`（実サイト検証ランナー。冒頭 docstring に前提と使い方）
- `docs/progress/issue-8-concrete.md`（当時の設計合意・決定事項。過渡ステップの経緯。本変更では更新しない）
- `docs/adr/0002-*.md`（Scraper はコンテキストマネージャ方式のセッション。後始末契約）
- `CONTEXT.md`（`Scraper` / `PortfolioAsset` の語彙）
