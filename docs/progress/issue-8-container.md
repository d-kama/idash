# データ収集バッチ コンテナ化・デプロイ準備（Dockerfile + CDK + 後始末整理 + ローカルランナー）

## 基本情報

| 項目 | 内容 |
|------|------|
| チケット | issue-8（GitHub issue #8「アセット収集バッチ の実装」の第3スライス＝コンテナ化・デプロイ準備） |
| ブランチ | feature/batch-collect-container |
| 開始日 | 2026-06-20 |
| 目標完了日 | TBD |
| 最終更新 | 2026-06-20 |

---

## 要件サマリー

### 背景・目的

PR #9（抽象層: `domain` + `application`）・PR #10（具象層: `common` / `infrastructure` / `apps/batch` DI）でデータ収集バッチの**決定的に検証できる範囲**は完了済み。本タスクはその続きで、`PROJECT_PLAN.md` Phase 3 のうち **issue-8-concrete「フェーズ4: ライブ依存」の前段（コードとして書けて `task check` / `task synth` / snapshot で検証可能な部分）**を仕上げる。

到達ラインは PR#9/#10 と同じ「**決定的に検証できる範囲まで green**」。すなわち **Dockerfile（4.1）・CDK コンテナ化＋S3＋env（4.2）・先送りコード整理（C1/C2）・ローカル検証ランナー**を実装し、`task check` / `task synth` / Vitest snapshot を green にする。**実サイト検証（4.3）と実デプロイ（4.4）はライブ依存（実サイト・実認証情報・AWS 認証）のためユーザー手元の後続作業**として明示分離する。

### 受入条件

- [ ] `apps/batch/Dockerfile` を新規作成（`public.ecr.aws/lambda/python:3.13` ベース、CfT 版ピン `chrome-headless-shell`＋`chromedriver` を `/opt/chrome/chrome`・`/opt/chromedriver/chromedriver` へ同梱、chrome 依存共有ライブラリ導入、`uv sync --package batch --no-dev --frozen`、CMD=collect）
- [ ] ルート `.dockerignore` を新規作成（build context を batch 関連に絞り、イメージ軽量化＋snapshot の image asset ハッシュ揺れを限定）
- [ ] `IdashBatchStack`: collect を `DockerImageFunction.fromImageAsset`（cmd=collect / memory 2048 / timeout 10分）へ差替。エラーページ S3 バケット新設（BLOCK_ALL / lifecycle 30日 / DESTROY、**autoDeleteObjects なし**）＋`grantWrite`＋env `ERROR_PAGE_BUCKET`
- [ ] Vitest snapshot を `run test:update` で更新（プレースホルダ ZipFile → image asset ＋ S3 バケットを反映）
- [ ] C1: `extract_portfolio` に「欠落要素を明示する `ValueError`」境界チェックを追加し fixture で決定的にテスト
- [ ] C2: `_default_chrome_factory` の tmpdir を driver `quit()` 時に rmtree 解放。ラップ部を fake driver で単体テスト
- [ ] `scripts/run_collect_local.py`（ローカル検証ランナー）を追加（`selenium/standalone-chrome` へ `webdriver.Remote` 接続するファクトリ注入、ローカル JSON 認証、`--dry-run` で print リポジトリ）。本番コードは不変。決定的テスト対象外（ruff は通す）
- [ ] `task check`（ruff / Biome / ty / tsc / pytest+cov / infra-vitest）＋ `task synth` がすべて green
- [ ] （Docker が使えれば）ローカル `docker build` でスモーク確認

### スコープ

- **対象**:
  - `apps/batch/Dockerfile`（新規）
  - ルート `.dockerignore`（新規）
  - `infra/lib/batch-stack.ts`（collect コンテナ化・S3・env）＋ `infra/test/__snapshots__/*.snap`（更新）
  - `packages/infrastructure/src/infrastructure/scraper.py`（C1: extract_portfolio 境界チェック / C2: tmpdir 解放）＋ tests + fixtures
  - `scripts/run_collect_local.py`（新規・ローカル検証用）
- **対象外（ライブ依存＝ユーザー手元の後続）**:
  - 4.3 Selenium 実サイト検証（実セレクタ最終確定 / birthdate フォーム入力フォーマット確定）
  - 4.4 実デプロイ＆動作確認（GitHub Actions の deploy ジョブ経由＝push:main / workflow_dispatch、OIDC）
- **対象外（別タスク）**: 通知系（`Notifier` / 集計 / `handler_notify`）、`AssetRepository` の read 系、`schemas`、`bff`
- **依存変更**: pyproject / uv.lock の変更は**不要見込み**（新規 deps なし）。新規 ADR / CONTEXT.md 追記も不要（ADR-0002/0003 の範囲内、新ドメイン語彙なし）

---

## コードベース調査結果

### 直接修正・作成対象ファイル
| ファイルパス | 役割 | 修正内容 |
|-------------|------|----------|
| `apps/batch/Dockerfile` | collect コンテナイメージ | **新規**。python:3.13 + CfT 版ピン chrome 同梱 + uv workspace 解決 |
| `.dockerignore` | build context 絞り込み | **新規**。node_modules / .git / infra / apps/frontend / docs / .venv / __pycache__ 等を除外 |
| `infra/lib/batch-stack.ts` | CDK collect Lambda | collect を DockerImageFunction 化、S3 バケット新設、env `ERROR_PAGE_BUCKET`、memory 2048/timeout 10分 |
| `infra/test/__snapshots__/batch-stack.test.ts.snap` | Vitest snapshot | `run test:update` で更新（ZipFile → image asset + S3） |
| `packages/infrastructure/src/infrastructure/scraper.py` | Scraper 具象 / 抽出 | C1: extract_portfolio 境界チェック / C2: tmpdir 解放ラップ |
| `packages/infrastructure/tests/test_scraper.py`（既存） | scraper テスト | C1 境界 fixture / C2 cleanup の追加テスト |
| `packages/infrastructure/tests/fixtures/*.html` | 抽出 fixture | C1 用に行欠落 HTML を追加 |
| `scripts/run_collect_local.py` | ローカル検証ランナー | **新規**。standalone-chrome Remote 注入 / ローカル JSON / --dry-run |

### 参照・影響範囲ファイル
| ファイルパス | 役割 | 影響内容 |
|-------------|------|----------|
| `apps/batch/src/batch/handler_collect.py` | composition root | 変更なし。chrome 既定パス `/opt/chrome/chrome`・`/opt/chromedriver/chromedriver` と Dockerfile 配置を一致させる根拠 |
| `packages/common/src/common/settings.py` | `CollectSettings` | 変更なし。`ERROR_PAGE_BUCKET` が**必須 env**（`_require`）→ CDK で付与必須 |
| `packages/infrastructure/src/infrastructure/error_store.py` | `S3ErrorPageStore` | 変更なし。`grantWrite` のみで足りる（PutObject のみ） |
| `docs/adr/0003-selenium-pinned-chrome-on-lambda.md` | Selenium 版ピン ADR | 本タスクの根拠。CfT 直引きで自前ピンする具体手段は実装時にコメントで明記 |
| `PROJECT_PLAN.md` §12.2/§12.6 | batch-stack / Dockerfile スケルトン | 出発点（python 版は 3.13 へ更新、context=repo ルート踏襲） |
| `.github/workflows/cicd.yml` | CI/CD | 変更なし。deploy ジョブ（`cdk deploy --all`）が**4.4 で chrome イメージを実ビルド**する経路 |

### 既存コード構造（本タスクの起点）
```
infra/lib/batch-stack.ts        // collect = lambda.Function(Code.fromInline プレースホルダ) / memory 1024 / 5分
packages/infrastructure/src/infrastructure/
├── scraper.py                  // SeleniumScraper(driver_factory 注入可) / _default_chrome_factory(tmpdir 未解放) / extract_portfolio(境界チェックなし)
├── sheets.py / error_store.py / clock.py
apps/batch/src/batch/handler_collect.py  // SSM→config→具象 DI→CollectionUseCase.execute（chrome パスは env 上書き可・既定 /opt/...）
```

### 類似実装の参考箇所
| 参考 | 参考内容 |
|------|----------|
| `PROJECT_PLAN.md` §12.6 | Dockerfile スケルトン（uv workspace 解決の COPY 手順）。python 版のみ 3.13 へ更新 |
| `PROJECT_PLAN.md` §12.2 | batch-stack（DockerImageCode.fromImageAsset / context=repo ルート / cmd 上書き） |
| `umihico/docker-selenium-lambda` | driver オプション・版ピン同梱パターン（ADR-0003）。本タスクは CfT 直引きで自前ピン |
| `packages/infrastructure/src/infrastructure/scraper.py` の `driver_factory` seam | ローカルランナーが `webdriver.Remote`(standalone-chrome) を注入する接続点（本番不変） |
| `infra/test/batch-stack.test.ts` | `Template.fromStack` → toMatchSnapshot の既存作法 |

---

## 設計（グリル合意）

### スコープ境界（最重要）
- 本タスク = **コードとして書けて `task check`/`task synth`/snapshot で検証できる範囲**（4.1 / 4.2 / C1 / C2 / ローカルランナー）。
- 4.3（実サイト検証）はユーザーが**ローカルで `selenium/standalone-chrome` を使い**実施。4.4（実デプロイ）は**GitHub Actions の deploy ジョブ**（push:main / workflow_dispatch、OIDC）で実施。chrome イメージの**初回実ビルドは 4.4 の deploy 内**で走る（CI check では走らない）。

### Dockerfile（4.1）
- ベース `public.ecr.aws/lambda/python:3.13`。マルチステージで CfT 版ピン `chrome-headless-shell`＋一致 `chromedriver` をダウンロードし `/opt/chrome/chrome`・`/opt/chromedriver/chromedriver` に配置（handler 既定パスに一致させ env 上書き不要に）。chrome が要求する共有ライブラリ（nss / nspr / atk / at-spi2 / cups-libs / libdrm / mesa-libgbm / libxkbcommon / libX* / alsa-lib / pango 等）を `dnf` で導入。
- 依存解決は `COPY pyproject.toml uv.lock` → `COPY packages/` `COPY apps/batch/` → `uv sync --package batch --no-dev --frozen`（selenium/gspread/bs4/lxml は batch→infrastructure のワークスペース依存で入る）。CMD 既定 = `batch.handler_collect.handler`。
- CfT のピン版は実装時に直近 stable を選定し、4.3/4.4 で調整可とコメント明記。

### CDK（4.2）
- collect: `DockerImageFunction` ＋ `DockerImageCode.fromImageAsset(repoRoot, { file: 'apps/batch/Dockerfile', cmd: ['batch.handler_collect.handler'] })`、`memorySize: 2048` / `timeout: Duration.minutes(10)`。`reservedConcurrentExecutions: 1` / 明示 LogGroup(7日 DESTROY) / スケジュール JST 09:00 は据置。`runtime`/`handler` プロパティは除去（イメージ側が決める）。
- エラーページ S3: `BlockPublicAccess.BLOCK_ALL` / `lifecycleRules: [{ expiration: Duration.days(30) }]` / `removalPolicy: DESTROY`。**`autoDeleteObjects` は付けない**（snapshot を綺麗に保つ。destroy 時は手動でバケットを空にする運用）。`bucket.grantWrite(collectFn)`、env `ERROR_PAGE_BUCKET: bucket.bucketName`。
- ルート `.dockerignore` で build context を絞り、image asset の content ハッシュ揺れを「batch 関連ソース変更時のみ」に限定。
- snapshot は `pnpm --filter @idash/infra run test:update` で更新。以後 batch 関連変更時に意図的更新。

### ローカルランナー（4.3 支援）
- `scripts/run_collect_local.py`（`uv run python scripts/run_collect_local.py`）。SSM をバイパスし `.gitignore` 済みローカル JSON から認証情報・`start_url`・`user_agent` を読む。`webdriver.Remote(command_executor=<--remote-url 既定 http://localhost:4444>, options=...)` を返す**スクリプト内定義の Remote ファクトリ**を `SeleniumScraper` に注入（本番 `infrastructure` の表面を広げない）。`--dry-run` で `AssetRepository` を print 専用 fake に差替（実 Sheets を汚さずセレクタ確認）、`--write` で実 Sheets。
- 起動手順は doc に `docker run -p 4444:4444 -p 7900:7900 selenium/standalone-chrome:<pinned>` を記載（compose は作らない）。noVNC（:7900）で headed ブラウザを目視可能。
- 実サイト・実コンテナ依存のため**決定的テスト対象外**（coverage/test に含めない。ruff は通す）。

### C1（extract_portfolio 境界チェック）
- `rows[2]` / `rows[5]` / `cells_tr2[2]` 等の直接アクセスを検査し、不足時に**「どの要素/行が足りないか」を明示した `ValueError`** を送出。`scrape()` 側で `ScraperError(content=page_source)` に包まれるためエラーページは従来どおり捕捉される。fixture（行欠落 HTML）で決定的にテスト。

### C2（tmpdir 解放）
- `_default_chrome_factory` の `tempfile.mkdtemp()` を driver `quit()` 時に `shutil.rmtree(..., ignore_errors=True)` で解放するようラップ。後始末は tmp dir を作る factory 内に閉じ込め、汎用 `_safe_quit` は不変。ラップ部を小さな純粋ヘルパに切り出し、fake driver で「quit 後に cleanup が呼ばれる」ことを単体テスト（live 不要）。

---

## 詳細タスク一覧

### フェーズ1: 準備・設計確認（グリル完了）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 1.1 | 要件グリル・合意形成（grill-with-docs） | ✅ | スコープ境界・Dockerfile・CDK・ローカルランナー・C1/C2 を確定 |
| 1.2 | 4.3/4.4 の実行経路確認（ローカル standalone-chrome / GitHub Actions deploy） | ✅ | cicd.yml deploy = push:main / workflow_dispatch（OIDC） |
| 1.3 | DockerImageAsset と synth/snapshot の関係確認 | ✅ | synth は context ハッシュのみ・Docker ビルドは deploy 時。CI は Docker 不要で green 維持 |

### フェーズ2: 実装
| # | タスク | 状態 | 対象ファイル | 実装詳細 |
|---|--------|------|-------------|----------|
| 2.1 | `apps/batch/Dockerfile` 作成 | ✅ | `apps/batch/Dockerfile` | python:3.13 + CfT 版ピン chrome 同梱 + dnf 共有ライブラリ + uv sync --package batch --no-dev --frozen |
| 2.2 | ルート `.dockerignore` 作成 | ✅ | `.dockerignore` | node_modules/.git/infra/apps/frontend/docs/.venv/__pycache__ 等を除外 |
| 2.3 | C1: extract_portfolio 境界チェック | ✅ | `packages/infrastructure/src/infrastructure/scraper.py` | 行/セル不足を明示 ValueError で送出 |
| 2.4 | C2: tmpdir 解放ラップ | ✅ | `packages/infrastructure/src/infrastructure/scraper.py` | quit() 時に rmtree。ラップを testable ヘルパへ |
| 2.5 | `IdashBatchStack` collect コンテナ化 | ✅ | `infra/lib/batch-stack.ts` | DockerImageFunction.fromImageAsset(cmd=collect, memory 2048/10分) |
| 2.6 | `IdashBatchStack` エラーページ S3 + env | ✅ | `infra/lib/batch-stack.ts` | BLOCK_ALL / lifecycle 30日 / DESTROY（autoDeleteObjects なし）/ grantWrite / env ERROR_PAGE_BUCKET |
| 2.7 | ローカルランナー作成 | ✅ | `scripts/run_collect_local.py` | standalone-chrome Remote 注入 / ローカル JSON / --dry-run / --write |

### フェーズ3: テスト（検証）
| # | タスク | 状態 | 対象 | テスト観点 |
|---|--------|------|------|-----------|
| 3.1 | C1 境界チェックテスト | ✅ | `packages/infrastructure/tests/` + fixtures | 行/セル欠落 HTML で ValueError と欠落要素メッセージ |
| 3.2 | C2 cleanup テスト | ✅ | `packages/infrastructure/tests/` | fake driver で quit 後に tmpdir 解放が呼ばれる |
| 3.3 | Vitest snapshot 更新 | ✅ | `infra/test/__snapshots__/` | `run test:update`。image asset + S3 + env を反映、差分が意図どおりか目視（ZipFile→ImageUri / S3 BLOCK_ALL+lifecycle30+Delete / autoDelete なし / grantWrite / env） |
| 3.4 | `task check` + `task synth` green | ✅ | 横断 | ruff / Biome / ty / tsc / pytest+cov(55 passed) / infra-vitest / synth すべて green |
| 3.5 | （任意）ローカル `docker build` スモーク | ✅ | `apps/batch/Dockerfile` | Docker 利用可。`docker build -f apps/batch/Dockerfile .` 成功。chrome/chromedriver が `/opt/chrome/chrome`・`/opt/chromedriver/chromedriver` に配置（CfT 131.0.6778.108）、`batch.handler_collect.handler`・`infrastructure.scraper` の import 成功を確認 |

### フェーズ4: レビュー・完了
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 4.1 | セルフレビュー | ⬜ | 受入条件チェック |
| 4.2 | PR 作成 | ⬜ | ユーザー指示があれば |
| 4.3 | コードレビュー対応 | ⬜ | |
| 4.4 | マージ・完了 | ⬜ | |

### フェーズ5: ライブ依存（後続・ユーザー手元）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 5.1 | 4.3 実サイト検証（ローカル standalone-chrome） | ⬜ | 実セレクタの最終確認。`scripts/run_collect_local.py --dry-run` で調整 |
| 5.2 | 4.4 実デプロイ＆動作確認 | ⬜ | GitHub Actions deploy（push:main / workflow_dispatch）。SSM `source-login` に start_url/user_agent 追加が前提 |

### ステータス凡例
- ⬜ 未着手 / 🔄 進行中 / ✅ 完了 / ⏸️ 保留 / ❌ キャンセル

---

## 総合進捗

| 項目 | 完了 | 総数 | 進捗率 |
|------|------|------|--------|
| 設計（フェーズ1） | 3 | 3 | 100% |
| 実装（フェーズ2） | 7 | 7 | 100% |
| 検証（フェーズ3） | 5 | 5 | 100% |
| **本タスク到達ライン（フェーズ2+3）** | **12** | **12** | **100%** |

※ フェーズ4 はユーザー指示待ち。フェーズ5（ライブ依存）はユーザー手元の後続。

---

## 作業ログ

### 2026-06-20
#### 実施内容
- [x] 要件グリル・合意形成（grill-with-docs）。スコープ境界・Dockerfile・CDK・ローカルランナー・C1/C2 を確定
- [x] 4.3（ローカル standalone-chrome）/ 4.4（GitHub Actions deploy）の実行経路を確認
- [x] DockerImageAsset が synth/snapshot で Docker ビルドを起こさないことを確認（CI は Docker 不要で green 維持）
- [x] 本進捗ファイル（issue-8-container）作成

#### 進捗サマリー
- **完了**: フェーズ1（設計）3/3
- **進行中**: なし（フェーズ2 実装は未着手）
- **ブロッカー**: なし

#### 実装セッション（フェーズ2+3）
- [x] 2.1 `apps/batch/Dockerfile`: マルチステージ（CfT 131.0.6778.108 の chrome-headless-shell + chromedriver を `/opt/chrome/chrome`・`/opt/chromedriver/chromedriver` に同梱）+ dnf 共有ライブラリ + `uv sync --no-dev --frozen`
- [x] 2.2 ルート `.dockerignore`: build context を `pyproject.toml`/`uv.lock`/`packages/`/`apps/batch/` 周辺に限定
- [x] 2.3 C1: `extract_portfolio` に `_require_row`/`_require_cells` 境界チェック（商品名・行・必要セル数を明示した ValueError）
- [x] 2.4 C2: `_quit_cleans_up` ヘルパで quit 後に tmpdir を rmtree（`_default_chrome_factory` に適用、汎用 `_safe_quit` は不変）
- [x] 2.5/2.6 `IdashBatchStack`: collect を `DockerImageFunction.fromImageAsset`（cmd=collect / memory 2048 / 10分）化、エラーページ S3（BLOCK_ALL / lifecycle 30日 / DESTROY、**autoDeleteObjects なし**）+ `grantWrite` + env `ERROR_PAGE_BUCKET`
- [x] 2.7 `scripts/run_collect_local.py`: standalone-chrome へ `webdriver.Remote` 注入する script 内ファクトリ、ローカル JSON 認証、`--dry-run`（print fake repo）/`--write`。`*.local.json` を `.gitignore`/`.dockerignore` に追加
- [x] 3.1 C1 テスト + 行欠落/セル欠落 fixture（2 件）。3.2 C2 cleanup テスト（fake driver、正常 quit / quit 失敗時も cleanup）
- [x] 3.3 Vitest snapshot を `run test:update` で更新（ZipFile→ImageUri / S3 BLOCK_ALL+lifecycle30+Delete / Custom::S3AutoDeleteObjects なし / s3:PutObject / env）。差分を目視確認
- [x] 3.4 `task check`（pytest 55 passed）+ `task synth` すべて green
- [x] 3.5 ローカル `docker build` 成功。chrome 配置・version・handler/infra import を image 内で確認

#### 実装中の発見（要記録）
- **Dockerfile の `uv sync` パッケージ名修正**: PROJECT_PLAN §12.6 スケルトンの `--package batch` は誤り（`batch` は import モジュール名、配布パッケージ名は `idash-batch`）。docker build スモークで `error: Could not find root package 'batch'` を検知し `--package idash-batch` に修正。設計合意の意図（batch app を同期）は不変で、スケルトンの誤りを実ビルドで是正したもの。
- **ty の method 代入抑止**: `driver.quit` 差し替えは mypy 記法 `# type: ignore` ではなく ty 記法 `# ty: ignore[invalid-assignment]` が必要（注入点に限定）。

#### 進捗サマリー（実装セッション終了時点）
- **完了**: フェーズ2（実装）7/7、フェーズ3（検証）5/5。本タスク到達ライン 12/12（100%）
- **green ゲート**: `task check` + `task synth` + Vitest snapshot + ローカル docker build すべて green
- **ブロッカー**: なし
- **次**: フェーズ4（セルフレビュー / PR）はユーザー指示待ち。フェーズ5（4.3 実サイト検証・4.4 実デプロイ）はユーザー手元の後続

#### 追加対応セッション（ローカルランナーの use case 経由化・snapshot 安定化）
- [x] `scripts/run_collect_local.py` を **`CollectionUseCase.execute` 経由の composition root** に作り直し。本番 `handler_collect` と対称（実行元＝Lambda/ローカルで「設定源・driver・repository・error store」のアダプタだけ差し替わり、use case 実行は同一）。直前版は session/scrape/save を手書き再現し application をバイパスしていたため是正
- [x] `_LocalFileErrorPageStore` を追加（本番 `S3ErrorPageStore` のローカル代替）。失敗時のページを `./errorpages/` へ書き出し、セレクタ調整時に実 HTML を開いて DOM 確認できるようにした。`errorpages/` を `.gitignore` に追加（個人情報を含み得るため）
- [x] 動作確認用テンプレート `collect.local.json`（gitignore 済み）を作成
- [x] **snapshot 安定化**: `DockerImageCode.fromImageAsset` に `ignoreMode: IgnoreMode.DOCKER` を明示。これがないと `.dockerignore` が asset フィンガープリントに効かず、build context 外の dev ファイル（`scripts/` や `*.local.json`）の変更でも image asset ハッシュが揺れて Vitest snapshot が壊れる事象を確認・是正。`scripts/` を意図的に変更しても snapshot が落ちないことを実証済み
- [x] `task check` / `task synth` / Vitest snapshot 再び green（ruff / ty も通過）

---

## メモ・課題

### 未解決課題（ライブ検証フェーズ＝後続）
| # | 課題 | 優先度 | 対応 |
|---|------|--------|------|
| 1 | 実セレクタの最終確認（fixture は提供セレクタ準拠） | 中 | 5.1（ローカル standalone-chrome） |
| 2 | birthdate のフォーム入力フォーマット（`%Y%m%d`） | ✅ | 2026-06-21 確定（暫定解除・TODO 削除）。5.1 で再確認不要 |
| 3 | CfT の chrome-headless-shell / chromedriver の具体ピン版 | 中 | 2.1 で直近 stable 選定 → 5.1/5.2 で調整 |
| 4 | `start_url` 実値（SSM `source-login` に格納） | 低 | 5.2 |
| 5 | SSM `source-login` JSON に `start_url` / `user_agent` を追加（4.4 前提） | 中 | 5.2 前にユーザーが SSM 更新 |

### 決定事項
| 日付 | 決定事項 | 決定者 |
|------|----------|--------|
| 2026-06-20 | スコープ境界: 4.1/4.2/C1/C2/ローカルランナーを実装し task check/synth/snapshot まで green。4.3（実サイト検証）・4.4（実デプロイ）はユーザー手元の後続 | ユーザー |
| 2026-06-20 | 4.3 実サイト検証はローカルで `selenium/standalone-chrome` を使う。`SeleniumScraper` の driver_factory seam に `webdriver.Remote` ファクトリを注入（本番コード不変）。noVNC で headed 目視 | ユーザー |
| 2026-06-20 | ローカルランナー `scripts/run_collect_local.py` を本タスクに含める。SSM バイパス・ローカル JSON 認証・`--dry-run` print リポジトリ。Remote ファクトリはスクリプト内定義（infrastructure の表面を広げない）。決定的テスト対象外 | ユーザー |
| 2026-06-20 | 4.4 実デプロイは GitHub Actions deploy（push:main / workflow_dispatch、OIDC）。chrome イメージの初回実ビルドは deploy 内。ローカル `aws login` + cdk deploy は参考フォールバック | ユーザー |
| 2026-06-20 | Dockerfile: base `public.ecr.aws/lambda/python:3.13`、CfT 版ピン chrome-headless-shell+chromedriver を `/opt/chrome/chrome`・`/opt/chromedriver/chromedriver` に同梱（handler 既定パスに一致）、dnf で共有ライブラリ、uv sync --package batch --no-dev --frozen。具体ピン版は CfT 直引きの自前ピン | ユーザー |
| 2026-06-20 | ローカル `docker build` スモークは Docker が使えれば実施、不可ならスキップ（実ビルド検証は 4.4 deploy に委ねる） | ユーザー |
| 2026-06-20 | CDK: collect を DockerImageFunction.fromImageAsset（cmd=collect / memory 2048 / timeout 10分）へ差替。スケジュール JST 09:00・予約同時実行 1・LogGroup は据置 | ユーザー |
| 2026-06-20 | エラーページ S3: BLOCK_ALL / lifecycle 30日 / removalPolicy DESTROY。**autoDeleteObjects は付けない**（snapshot を綺麗に保つ。destroy 時は手動でバケットを空にする） | ユーザー |
| 2026-06-20 | ルート `.dockerignore` を新設し build context を絞る（イメージ軽量化＋snapshot の image asset ハッシュ揺れを batch 関連変更時に限定） | ユーザー |
| 2026-06-20 | C1: extract_portfolio に欠落要素を明示する ValueError 境界チェックを入れる（4.3 のセレクタ調整を楽にするため。暫定セレクタでも有用） | ユーザー |
| 2026-06-20 | C2: _default_chrome_factory の tmpdir を quit() 時に rmtree 解放。ラップを testable ヘルパへ切り出し fake で検証 | ユーザー |
| 2026-06-20 | 新規 ADR / CONTEXT.md 追記は不要（ADR-0002/0003 の範囲内、新ドメイン語彙なし）。pyproject / uv.lock 変更も不要見込み | ユーザー |
| 2026-06-20 | ローカルランナーは「5.1 のための導入」だが**恒久のローカル保守ツール**として残す（位置づけ A）。対象が外部サイトでセレクタが先方都合で変わり得るため、破損時の調査・デプロイ前スモークに継続して使う | ユーザー |
| 2026-06-20 | `run_collect_local.py` を本番 `handler_collect` と対称の **`CollectionUseCase` 経由 composition root** に作り直す。実行元（Lambda/ローカル）でアダプタ群だけ差し替わり、use case 実行は同一。失敗ページは `_LocalFileErrorPageStore` でローカル保存（S3 の代替）。本番コードは不変（driver_factory seam 経由） | ユーザー |
| 2026-06-20 | **（実装中の是正）** `.dockerignore` だけでは CDK の image asset フィンガープリントに効かず、dev ファイル変更で snapshot が揺れた。`fromImageAsset` に `ignoreMode: IgnoreMode.DOCKER` を明示して `.dockerignore` をハッシュ計算にも効かせ、churn を batch 関連の build context 変更のみに限定（グリル合意の実現）。`scripts/` 変更で snapshot が落ちないことを実証 | 実装者 |
| 2026-06-21 | **C1 撤回**: `extract_portfolio` の `_require_row`/`_require_cells` 境界チェックを削除（該当テスト・fixture 共）。行・セル不足（構造ずれ）は IndexError として `scrape()` に伝播し `ScraperError(content=page_source)` に包まれる経路は同一。差はメッセージ粒度のみで、失敗ページ HTML は常に保存されるため実益小（差が小さければシンプル優先） | ユーザー |
| 2026-06-21 | **C2 簡素化**: `_quit_cleans_up`（quit 後の tmpdir 掃除ラッパ）と `TestQuitCleansUp` を削除。`tempfile.mkdtemp()` での user-data-dir 作成は残すが終了後の削除はしない（あえてのリーク）。収集は日次1回・毎回コールドスタート、`reservedConcurrentExecutions=1` でウォーム環境は最大1個、プロファイル数十MB に対し /tmp は既定 512MB、アイドル実行環境は破棄されるため /tmp 蓄積リスクは実質ゼロ。リーク防止の便益に対し `driver.quit` の monkeypatch + ty 抑止のコストが見合わない（差が小さければシンプル優先）。あえてのリークである旨を `_default_chrome_factory` にコメントで明記し再実装を防ぐ | ユーザー |
| 2026-06-21 | **birthdate フォーマット確定**: `_format_birthdate` の入力フォーマットを `%Y%m%d` で確定（暫定を解除）し TODO を削除。未解決課題 #2 を解消（5.1 でのフォーマット確定タスクは不要に） | ユーザー |

---

## 作業再開ガイド

### 現在の状態
- **最終作業**: フェーズ2（実装）+ フェーズ3（検証）完了。本タスク到達ライン 12/12。`feature/batch-collect-container` 上で `task check` / `task synth` / Vitest snapshot / ローカル docker build すべて green。コミットは未作成（ユーザー指示待ち）。
- **次のアクション**: フェーズ4（セルフレビュー / PR）はユーザー指示待ち。フェーズ5（4.3 実サイト検証・4.4 実デプロイ）はユーザー手元の後続。
- **実装メモ**: Dockerfile の `uv sync` は `--package idash-batch`（PROJECT_PLAN §12.6 スケルトンの `--package batch` は配布名と不一致のため是正）。`driver.quit` 差し替えの抑止は ty 記法 `# ty: ignore[invalid-assignment]`。

### 再開時の確認事項
1. 本ファイルの「設計（グリル合意）」「決定事項」を厳守。特に**スコープ境界（4.3/4.4 は対象外）**と **autoDeleteObjects を付けない**点。
2. `domain` / `application` / 本番 `infrastructure` の契約（公開シグネチャ）は変更しない。ローカルランナーは driver_factory seam 経由で本番コードを不変に保つ。
3. Dockerfile の chrome 配置は handler 既定パス（`/opt/chrome/chrome`・`/opt/chromedriver/chromedriver`）に一致させる。
4. CDK 変更後は `pnpm --filter @idash/infra run test:update` で snapshot を更新し、差分（image asset + S3 + env）が意図どおりかを目視確認。
5. `ERROR_PAGE_BUCKET` は `CollectSettings` の必須 env。CDK で必ず付与する（未設定だと handler が KeyError）。

### コンテキスト復元用コマンド
```bash
# ブランチ作成（base は main）
git switch -c feature/batch-collect-container

# 設計確認
cat docs/progress/issue-8-container.md docs/adr/0003-selenium-pinned-chrome-on-lambda.md

# 検証
task check && task synth
```
