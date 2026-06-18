# データ収集バッチ 抽象レイヤ実装（domain + application / 抽象テストまで）

## 基本情報

| 項目 | 内容 |
|------|------|
| チケット | issue-8 |
| ブランチ | feature/batch-collect-domain |
| 開始日 | 2026-06-17 |
| 目標完了日 | TBD |
| 最終更新 | 2026-06-18 |

---

## 要件サマリー

### 背景・目的
`PROJECT_PLAN.md` の **Phase 3（データ収集バッチ）** のうち、**抽象レイヤ（`domain` + `application`）とその抽象テスト**を実装する。機能要件・モデル設計サンプルは Notion ページ「確定拠出年金_v2」を正とする（設計サンプルは不完全な箇所があり、グリルで補完済み）。

本タスクは PROJECT_PLAN の Phase 3 定義（具象・Dockerfile・deploy 含む）から**意図的に絞り込んだ**もの。具象クラス実装・デプロイは後続フェーズへ分離し、ここでは**抽象レベルでのテスト・動作確認まで**を到達ラインとする。通知処理は実装しないが、共有ドメインの設計で手戻りが出ないよう配慮する。

### 受入条件
- [x] `domain`（値オブジェクト・収集ポート・例外）が実装され、`ruff` / `ty` グリーン。**domain は依存ゼロ（pydantic 不使用）を維持**
- [x] `application` の `CollectionInputBoundary` + `CollectionUseCase`（**save ステップ込み**）を実装
- [x] 抽象テストが **成功系 / 失敗系 / エッジ（content=None）/ login 失敗 / ライフサイクル順序**を網羅しグリーン
- [x] `Credentials` が `repr` / `str` / f-string でマスクされることをテストで保証
- [x] `task check`（ruff / Biome / ty / tsc / pytest / infra-vitest）がすべてグリーン
- [x] `CONTEXT.md` / `docs/adr/0002` が合意内容を反映（本セッションで作成済み）

### スコープ
- **対象**: `packages/domain`（`asset.py` / `collection.py`）、`packages/application`（`collection.py`）、両パッケージの `tests/`、`pyproject.toml` の pytest `--cov` 追加（レポートのみ）
- **対象外**:
  - `infrastructure` 具象（Google Sheets / Selenium・Playwright / S3 エラーストア / 通知クライアント）
  - `apps/batch/handler_collect.py` の具象 DI 結線、`Dockerfile`、`DockerImageFunction` 差替、CDK snapshot 更新、実 deploy
  - `schemas`（Pydantic DTO。収集は HTTP/JSON 境界を持たないため）
  - **通知系**（`Notifier` / `Notification` / 集計サービス `summarize`）= Phase 4
  - `AssetRepository` の read 系（`find_by_date` / `find_by_date_range`）= Phase 4（Protocol への追加は後方互換）

---

## コードベース調査結果

### 現状（Phase 0/1/2 完了済み・本タスクの起点）
- `packages/{domain,application,schemas,infrastructure,common}` と `apps/{batch,bff}` の骨格・内部依存配線は完了。**全 `src/*/__init__.py` は空スタブ**で実装なし。
- 依存配線（確認済み）: `domain`=依存ゼロ / `application`→`domain`+`schemas` / `infrastructure`→`domain`+`common` / `batch`→`application`+`infrastructure`+`common`。
- `infra` は `IdashBatchStack`（collect プレースホルダ Lambda）まで実装済み（issue-2）。本タスクでは infra に触れない。
- `CONTEXT.md` / `CONTEXT-MAP.md` は未存在 → 本セッションでルート `CONTEXT.md` を新規作成。
- pytest 設定: `--import-mode=importlib` / `testpaths=["packages","apps"]`。`--cov` は未設定（コメントで「実コード投入後に追加」と予告済み）。

### 参照・影響範囲ファイル
| ファイルパス | 役割 | 影響内容 |
|-------------|------|----------|
| Notion「確定拠出年金_v2」 | 機能要件・モデル設計サンプル | **実装の正**（不完全箇所はグリルで補完） |
| `PROJECT_PLAN.md` §2.3.1/§2.3.2/§12.8/§12.9 | 層配置・依存方向・コードスケルトン | 根拠。ただし §12.9 命名（`PensionRepositoryPort` 等）は「最小の仮置き」のため Notion v2 命名で上書き |
| `packages/domain/pyproject.toml` | domain 依存定義 | 変更なし（`dependencies=[]` を維持） |
| `packages/application/pyproject.toml` | application 依存定義 | 変更なし（`domain`+`schemas` 既配線） |
| `pyproject.toml` `[tool.pytest.ini_options]` | pytest 設定 | `addopts` に `--cov=domain --cov=application`（レポートのみ・fail-under なし）を追加 |
| `scripts/pytest.sh` | exit 5 吸収ラッパ | 変更なし（実テスト投入で exit 5 は発生しなくなる） |

### 直接作成対象ファイル
| ファイルパス | 役割 | 状態 |
|-------------|------|------|
| `CONTEXT.md` | ドメイン用語集 | ✅ 作成済み |
| `docs/adr/0002-scraper-context-manager-port.md` | Scraper CM 方式の ADR | ✅ 作成済み |
| `packages/domain/src/domain/asset.py` | Money / ProductAsset / AssetTotal / PortfolioAsset / AssetRepository | ⬜ |
| `packages/domain/src/domain/collection.py` | Credentials / Scraper / ScraperSession / ScraperError / ErrorPage / ErrorPageStore / Clock | ⬜ |
| `packages/domain/tests/test_money.py` | Money 単体 | ⬜ |
| `packages/domain/tests/test_portfolio_asset.py` | total() 合算 | ⬜ |
| `packages/domain/tests/test_error_page.py` | captured() の純粋性 | ⬜ |
| `packages/domain/tests/test_credentials.py` | マスク検証 | ⬜ |
| `packages/application/src/application/collection.py` | CollectionInputBoundary + CollectionUseCase | ⬜ |
| `packages/application/tests/conftest.py` | Fake fixture（FakeScraper / InMemoryAssetRepository / InMemoryErrorPageStore / FixedClock） | ⬜ |
| `packages/application/tests/test_collection_use_case.py` | ユースケース検証 | ⬜ |

---

## 設計（グリル合意）

### モジュールレイアウト（サブドメイン別。ADR 化はしないが PROJECT_PLAN §12.9 の `models.py`/`ports.py` を上書き）
```
packages/domain/src/domain/
├── __init__.py     # 空（広域 re-export しない。import は明示的サブモジュール参照）
├── asset.py        # 共有アセットコア
└── collection.py   # 収集サブドメイン

packages/application/src/application/
├── __init__.py
└── collection.py   # CollectionInputBoundary + CollectionUseCase
```

### domain/asset.py（すべて stdlib `@dataclass(frozen=True)`）
- `Money(yen: int)`: `parse(text)`（`¥1,234,567`/`-80,000円`/`△80,000`/`▲...` を解釈、不可なら `ValueError`、会計表記 △/▲ は負）、`__add__`/`__sub__`、`is_positive`/`is_negative`、`format()`/`signed()`
- `ProductAsset(name: str, contribution: Money, profit_loss: Money, valuation: Money)`
- `AssetTotal(contribution: Money, profit_loss: Money, valuation: Money)`
- `PortfolioAsset(base_date: date, products: list[ProductAsset])` + `total() -> AssetTotal`（各商品3項目を Money 加算で合算）
- `AssetRepository(Protocol)`: **`save(asset: PortfolioAsset) -> None` のみ**（read 系は Phase 4）

### domain/collection.py
- `Credentials(user_id: str, password: str, birthdate: date)`: **マスク `__repr__`**（`Credentials(user_id=***, password=***, birthdate=***)`、`__str__` はフォールバック）。pydantic 不使用
- `ScraperSession(Protocol)`: `scrape() -> PortfolioAsset`
- `Scraper(Protocol)`: `session(url: str, credentials: Credentials) -> AbstractContextManager[ScraperSession]`（CM 方式 = ADR-0002）
- `ScraperError(Exception)`: `__init__(message, *, content: str | None = None)`、`self.content`（失敗時点のページ。取れなければ None）
- `ErrorPage(url: str, captured_at: datetime, content: str | None)` + `captured(url, content, at)`（時計を呼ばず `at` を受け取る）
- `ErrorPageStore(Protocol)`: `save(page: ErrorPage) -> None`
- `Clock(Protocol)`: `now() -> datetime`（ErrorPage 時刻専用）

### application/collection.py
```python
class CollectionInputBoundary(Protocol):
    def execute(self, url: str, credentials: Credentials) -> PortfolioAsset: ...

class CollectionUseCase(CollectionInputBoundary):
    def __init__(self, scraper, repository, error_store, clock) -> None: ...
    def execute(self, url, credentials) -> PortfolioAsset:
        with self._scraper.session(url, credentials) as session:
            try:
                asset = session.scrape()
            except ScraperError as e:
                self._error_store.save(
                    ErrorPage.captured(url=url, content=e.content, at=self._clock.now())
                )
                raise
        self._repository.save(asset)   # with を抜けて保存
        return asset
```
- `base_date` は Scraper（scrape の戻り値）が設定。ユースケースは触らない
- エラーページ捕捉は `scrape()` の `ScraperError` に限定（login/session 失敗・save 失敗は捕捉せず送出）

### テスト方針
- `domain`: 純粋単体（Money 各表記・total 合算・captured 純粋性・Credentials マスク）
- `application`: `conftest.py` の Fake fixture で `CollectionUseCase` を検証
  - 成功系: `scrape` → `repository.save` 呼出 → 戻り値一致 + outcome によらず後始末（session close）
  - 失敗系: `ScraperError` → `error_store.save(ErrorPage(...))` → 再送出 → `repository.save` 未呼出
  - エッジ: `content=None` でも ErrorPage 保存
  - login 失敗: 伝播のみ（error page も save も無し）
  - ※ `open→login→scrape→logout→close` の**細かな順序は具象アダプタ（ADR-0002）の契約**であり application の関心事ではない。application テストでは検証せず、後続フェーズの infrastructure 具象 Scraper テストで担保する（application は粗粒度の close のみ確認）
- `--cov` はレポートのみ（閾値なし）

---

## 詳細タスク一覧

### フェーズ1: 準備・設計確認（グリル完了）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 1.1 | 要件グリル・合意形成（grill-with-docs） | ✅ | スコープ・モデル・ポート契約・テスト方針を確定 |
| 1.2 | 語彙確定（Notion v2 を正・ポート接尾辞なし） | ✅ | `CONTEXT.md` 作成 |
| 1.3 | Scraper CM 方式の意思決定記録 | ✅ | `docs/adr/0002` 作成 |

### フェーズ2: 実装
| # | タスク | 状態 | 対象ファイル |
|---|--------|------|-------------|
| 2.1 | `domain/asset.py` | ✅ | Money / ProductAsset / AssetTotal / PortfolioAsset / AssetRepository(save) |
| 2.2 | `domain/collection.py` | ✅ | Credentials(マスク) / Scraper / ScraperSession / ScraperError(content) / ErrorPage / ErrorPageStore / Clock |
| 2.3 | `application/collection.py` | ✅ | CollectionInputBoundary + CollectionUseCase（save 込み） |
| 2.4 | pytest `--cov` 設定 | ✅ | `pyproject.toml`（レポートのみ・閾値なし） |
| 2.5 | ワークスペースメンバーの dev 依存配線（計画外・必須） | ✅ | `pyproject.toml` dev group + `[tool.uv.sources]` + `uv.lock` 再生成（下記「決定事項」参照） |

### フェーズ3: テスト（検証）
| # | タスク | 状態 | 対象 |
|---|--------|------|------|
| 3.1 | domain 単体テスト | ✅ | test_money(17) / test_portfolio_asset(2) / test_error_page(2) / test_credentials(5) |
| 3.2 | application ユースケーステスト | ✅ | conftest（Fake）+ test_collection_use_case（成功/失敗/エッジ/login失敗）= 4。細かなライフサイクル順序は application の関心外として削除（infra へ移管） |
| 3.3 | `task check` グリーン | ✅ | ruff / Biome / ty / tsc / pytest(+cov, 30 passed/cov 100%) / infra-vitest すべて緑 |

### フェーズ4: レビュー・完了
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 4.1 | セルフレビュー | ⬜ | 受入条件チェック |
| 4.2 | PR 作成 | ⬜ | ユーザー指示があれば |
| 4.3 | コードレビュー対応 | ⬜ | |
| 4.4 | マージ・完了 | ⬜ | |

### ステータス凡例
- ⬜ 未着手 / 🔄 進行中 / ✅ 完了 / ⏸️ 保留 / ❌ キャンセル

---

## 総合進捗

| 項目 | 完了 | 総数 | 進捗率 |
|------|------|------|--------|
| 設計（フェーズ1） | 3 | 3 | 100% |
| 実装（フェーズ2） | 5 | 5 | 100% |
| 検証（フェーズ3） | 3 | 3 | 100% |
| **総合（実装・検証）** | **11** | **11** | **100%** |

※ フェーズ4（PR / レビュー / マージ）はユーザー指示待ち。

---

## 作業ログ

### 2026-06-17
#### 実施内容
- [x] 要件グリル・合意形成（grill-with-docs）。スコープ絞り込み・モデル補完・ポート契約・マスク方式・レイアウト・テスト方針を確定
- [x] `CONTEXT.md`（ドメイン用語集）作成
- [x] `docs/adr/0002-scraper-context-manager-port.md` 作成
- [x] 本進捗ファイル（issue-8）作成

#### 進捗サマリー
- **完了**: フェーズ1（設計）3/3
- **進行中**: なし（フェーズ2 実装は未着手）
- **ブロッカー**: なし

### 2026-06-18
#### 実施内容（TDD: red→green の縦スライス）
- [x] `domain/asset.py` 実装（Money: parse/四則/is_positive/negative/format/signed、ProductAsset / AssetTotal / PortfolioAsset.total() / AssetRepository(save)）
- [x] `domain/collection.py` 実装（Credentials マスク `__repr__` / ErrorPage.captured(純粋) / ScraperError(content) / Scraper / ScraperSession / ErrorPageStore / Clock）
- [x] `application/collection.py` 実装（CollectionInputBoundary + CollectionUseCase。成功系を先行実装→失敗系テストで except ブランチを駆動）
- [x] テスト: domain 単体 26 件 + application ユースケース 4 件 = 計 30 件グリーン、カバレッジ 100%
- [x] `conftest.py` に application が観測する範囲だけの Fake（FakeScraper/_FakeSession/InMemory*/FixedClock）+ fixture
- [x] **レビュー指摘反映**: 細かなライフサイクル順序アサート（`open→login→…→close`）は application の関心外（具象の契約）として削除。粗粒度の close 確認のみ残す。順序検証は infra 具象 Scraper テストへ移管
- [x] pytest `--cov=domain --cov=application --cov-report=term-missing`（閾値なし）を addopts に追加
- [x] **（計画外・必須）** ワークスペースメンバーを root の dev 依存に配線（`uv sync` がメンバーを prune する問題の解消）。`uv.lock` 再生成、frozen install 検証済み
- [x] `task check` 全項目グリーン（ruff / Biome / ty / tsc / pytest+cov / infra-vitest）

#### 進捗サマリー
- **完了**: フェーズ2（実装）5/5・フェーズ3（検証）3/3。受入条件すべて充足
- **進行中**: なし
- **ブロッカー**: なし
- **次のアクション**: フェーズ4（コミット / PR）はユーザー指示待ち。未コミット

---

## メモ・課題

### 未解決課題（後続フェーズ）
| # | 課題 | 優先度 | 期限 | 担当 |
|---|------|--------|------|------|
| 1 | `AssetRepository` の read 系（`find_by_date` / `find_by_date_range`）追加。Notion の `find_by_date_range(from, to)` は `from` が予約語のため `from_date`/`to_date` 等へ改名 | 中 | Phase 4 | 実装者 |
| 2 | 通知系 `Notifier` / `Notification` / 集計サービス `summarize` の設計・実装 | 中 | Phase 4 | 実装者 |
| 3 | `Credentials` の正確なログイン要素は対象サイト確定時に再確認（現状 birthdate 含む前提） | 低 | 具象フェーズ | 実装者 |
| 4 | `infrastructure` 具象（Sheets / Selenium）・Dockerfile・コンテナ Lambda 差替・deploy | 中 | 後続 | 実装者 |
| 5 | ADR-0002 の完全なライフサイクル契約（`open→login→scrape→logout→close`、login 失敗時その場で close、logout 失敗は主例外を隠さない）の検証は **infra 具象 Scraper のテスト**で実施する（application テストからは移管済み） | 中 | 具象フェーズ | 実装者 |

### 決定事項
| 日付 | 決定事項 | 決定者 |
|------|----------|--------|
| 2026-06-17 | スコープは Collection の抽象レイヤ（domain + application + 抽象テスト）。具象・Dockerfile・deploy・schemas・通知系は対象外 | ユーザー |
| 2026-06-17 | 通知系専用 I/F（Notifier 等）は本フェーズで着手しない。共有ドメインのみ手戻り防止に配慮 | ユーザー |
| 2026-06-17 | モデル語彙は Notion v2 を正とする（PROJECT_PLAN §12.9 命名は仮置きのため上書き） | ユーザー |
| 2026-06-17 | ポート命名は接尾辞なし（`AssetRepository` 等） | ユーザー |
| 2026-06-17 | `CollectionUseCase` に save ステップ・`repository` 依存を補完（Notion サンプルの欠落を是正）。`execute(url, credentials) -> PortfolioAsset`、save は with を抜けてから | ユーザー |
| 2026-06-17 | `CollectionInputBoundary`(Protocol) を設け、`CollectionUseCase` が実装（クリーンアーキ準拠） | ユーザー |
| 2026-06-17 | 値オブジェクトは stdlib frozen dataclass。Money は parse/四則/format/signed を同梱。AssetTotal は3項目合計のみ | ユーザー |
| 2026-06-17 | エラー証跡の項目名は `content`（`str | None`）に統一。ScraperError は domain に置く | ユーザー |
| 2026-06-17 | 対象サイトに対話的 MFA は無い前提。Credentials = user_id / password / birthdate | ユーザー |
| 2026-06-17 | Credentials はマスク `__repr__`（案A）。domain の依存ゼロ維持のため pydantic（SecretStr）不使用 | ユーザー |
| 2026-06-17 | `AssetRepository` は本フェーズ `save` のみ。read 系は Phase 4（後方互換追加） | ユーザー |
| 2026-06-17 | Scraper はコンテキストマネージャ方式のセッションを返す（ADR-0002） | ユーザー |
| 2026-06-17 | ファイルレイアウトはサブドメイン別（`domain/asset.py` + `domain/collection.py`）。保守性で有意差があるため規模に依らず採用 | ユーザー |
| 2026-06-17 | テストは pytest のみ（実行デモは作らず、ライフサイクル順序アサートで代替）。`--cov` はレポートのみ（閾値なし） | ユーザー |
| 2026-06-18 | **（計画外の必須変更）** ルート `pyproject.toml` の dev 依存グループにワークスペース全メンバーを追加し `[tool.uv.sources]` で `workspace = true` 配線、`uv.lock` 再生成。理由: プレーンな `uv sync`（`task setup`/`setup:ci`）は依存されないメンバーを prune するため、`uv run pytest`/`ty` が `domain` 等を import 解決できず受入条件「task check 緑」を満たせない。代替案（`uv run --all-packages` を各タスクへ付与）は `task check` 内で lint→typecheck→test 間に install/uninstall の thrash を起こすため不採用。frozen install で検証済み | 実装者 |
| 2026-06-18 | `Money.format()` = `¥1,234,567`/`-¥80,000`/`¥0`、`Money.signed()` = 正に明示的 `+`（`+¥…`）・ゼロは符号なし。Notion/issue-8 で出力文字列が未確定だったため日本円表示慣例で確定（消費者は Phase 4 のため手戻りリスク低） | 実装者 |
| 2026-06-18 | **（レビュー指摘・当初計画を是正）** application テストの「ライフサイクル順序 `open→login→…→close`」アサートは廃止。理由: その順序は具象アダプタの契約（ADR-0002）であり application の関心事ではない＝実装詳細への結合になる。application は「セッションを開く→scrape→後始末（close）」のみ観測し、順序検証は infra 具象 Scraper テストへ移管 | ユーザー指摘・実装者 |
| 2026-06-18 | 値オブジェクトの実行時バリデーションは**追加しない（現状維持）**。担保は (a) `ty` による静的型検出（CI で fail。誤った型の構築を実証済み）、(b) 外部不正データは境界（`Money.parse` / 後続 infra アダプタ）でパース・検証。domain は zero-dep の軽量 VO を維持し pydantic / `__post_init__` ガードは入れない | ユーザー |

---

## 作業再開ガイド

### 現在の状態
- **最終作業**: フェーズ2（実装）・フェーズ3（検証）完了。domain/application 実装 + 抽象テスト 31 件グリーン、`task check` 全緑。ブランチ `feature/batch-collect-domain` 上、**コミット未実施（ユーザー指示待ち）**
- **次のアクション**: フェーズ4（コミット / PR 作成 / レビュー）。ユーザー指示があれば着手

### 再開時の確認事項
1. 本ファイルの「設計（グリル合意）」「決定事項」を厳守
2. Notion「確定拠出年金_v2」のモデルサンプルを参照（ただし本ファイルの補完が優先）
3. `domain` は依存ゼロ（pydantic 不使用）を死守。ポートは接尾辞なし命名
4. 到達ラインは「抽象テスト・`task check` グリーン」。具象・deploy は対象外

### コンテキスト復元用コマンド
```bash
# ブランチ作成（base は main）
git switch -c feature/batch-collect-domain

# 設計確認
cat CONTEXT.md docs/adr/0002-scraper-context-manager-port.md docs/progress/issue-8.md
```
