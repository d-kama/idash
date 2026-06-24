# サマリ通知バッチ 具象＋コンテナ実装（infrastructure 具象 / handler_notify / CDK notify ＋ collect 平日化 ＋ ローカルランナー）

## 基本情報

| 項目 | 内容 |
|------|------|
| チケット | issue-16-concrete（notification スレッド。issue-16-domain の続き＝具象＋コンテナスライス） |
| ブランチ | feature/batch-notify-concrete |
| 開始日 | 2026-06-24 |
| 目標完了日 | TBD |
| 最終更新 | 2026-06-24 |

---

## 要件サマリー

### 背景・目的

`PROJECT_PLAN.md` **Phase 4（サマリ通知バッチ）** のうち、抽象層（`domain` + `application` + 抽象テスト）は **issue-16-domain（PR #17）で完了・main マージ済み**。本タスクはその続きで、**具象（concrete）＋コンテナ（container）を1タスクに統合**して実装する。

収集バッチ（issue-8）は abstract / concrete / container の3スライスに分けたが、notify は **新規の重依存（Chrome/Selenium）が無く、収集イメージを `cmd` 違いで再利用するだけ**なので concrete と container を分ける必要がない（CDK 差分も小さく `synth`/snapshot で決定的検証できる）。

到達ラインは collect の concrete/container と同じ **「決定的に検証できる範囲（fake/mock/moto/snapshot）＋ `task check` / `task synth` green」**。実 deploy・実 LINE 送信検証・LINE 公式アカウント準備はライブ依存のため**ユーザー手元の後続作業**として明示分離する。

### 受入条件

- [ ] `infrastructure`: `SheetsAssetRepository.find_by_date_range` を実装（`NotImplementedError` スタブを置換）。`get_all_values` → col1 を `date.fromisoformat` で解釈しパース不能行（ヘッダ/空行）はスキップ → 閉区間 `[from, to]` フィルタ → 金額3列を `Money(int(cell))` で復元（save の生整数と round-trip）→ base_date でグループ化し `PortfolioAsset` 再構成 → **基準日昇順**で返す（0件可）
- [ ] `infrastructure`: `LineNotifier`（`notifier.py` 新規）。LINE Messaging API **push**（`/v2/bot/message/push`）へ `subject\n\nbody` を1通の text メッセージで送信。stdlib `urllib.request` で Bearer 付き POST、非2xx は `HTTPError` 伝播。`transport` シーム注入でテスト可能。**新規依存ゼロ**（pyproject/uv.lock 不変）
- [ ] `common`: `NotifySettings`（`env_name` / `sheets_sa_param` / `notify_line_param` / `notify_days`）。`notify_days` は env 欠落時 7 既定
- [ ] `apps/batch`: `handler_notify.py`（composition root）。env + SSM 2本（`sheets-sa` read 用・`notify-line`）→ `SheetsAssetRepository`/`LineNotifier`/`SystemClock` を `NotifySummaryUseCase` に DI。`days = event.get("days") or settings.notify_days`（event 優先）。戻り値は最小 dict（`{"status":"ok"|"skipped","days":N,...}`）、例外は捕捉せず再送出
- [ ] `apps/batch/Dockerfile`: ヘッダコメントを「batch アプリ共有イメージ（collect + notify。CDK が cmd を関数ごとに上書き）」に更新（位置・既定 CMD は不変）
- [ ] `infra`: notify Lambda を `IdashBatchStack` に追加（同一イメージ `cmd=batch.handler_notify.handler` / memory 512 / timeout 1分 / 予約同時実行 1 / 専用 LogGroup 7日 DESTROY / `grantRead`（sheets-sa + notify-line）/ env 4本 / Schedule 日曜 09:00 JST）。**collect の Schedule を平日のみ `MON-FRI` に変更**。snapshot を `run test:update` で更新
- [ ] `scripts/run_notify_local.py`: ローカル検証ランナー（`--days` / `--send`（実 LINE 送信）/ 既定 dry-run（print）/ ローカル JSON 認証）。本番コード不変・決定的テスト対象外（ruff/ty のみ通す）
- [ ] doc: `PROJECT_PLAN.md` / `CLAUDE.md` の「収集は日次 JST 09:00」を「平日のみ（Mon–Fri）JST 09:00」へ更新。Phase 4 の該当 TODO を消し込み
- [ ] 決定的テスト green（sheets read / LineNotifier / NotifySettings / handler_notify）
- [ ] `task check`（ruff / Biome / ty / tsc / pytest+cov / infra-vitest）＋ `task synth` がすべて green

### スコープ

- **対象**:
  - `packages/infrastructure/src/infrastructure/sheets.py`（read 実装）/ `notifier.py`（新規）+ tests
  - `packages/common/src/common/settings.py`（`NotifySettings` 追加）+ test
  - `apps/batch/src/batch/handler_notify.py`（新規）+ test
  - `apps/batch/Dockerfile`（コメントのみ）
  - `infra/lib/batch-stack.ts`（notify Lambda 追加・collect 平日化）+ `infra/test/__snapshots__/*.snap`（更新）
  - `scripts/run_notify_local.py`（新規）
  - `PROJECT_PLAN.md` / `CLAUDE.md`（収集スケジュール記述・Phase 4 TODO）
- **対象外（ライブ依存＝ユーザー手元の後続）**:
  - 実 deploy（GitHub Actions deploy ジョブ経由＝push:main / workflow_dispatch、OIDC）
  - 実 LINE 送信検証（実トークン・実 userId）
  - LINE 公式アカウント作成・チャネルアクセストークン取得・Bot 友だち追加・userId 取得
  - SSM `/idash/<env>/notify-line`（SecureString）の実値作成（AWS 側で手動作成）
- **対象外（別タスク／別フェーズ）**: `bff`（Phase 5）、`schemas`、`frontend`（Phase 6）、収集側ロジックの変更（スケジュール cron 以外）

---

## コードベース調査結果

### 直接修正・作成対象ファイル
| ファイルパス | 役割 | 修正内容 |
|-------------|------|----------|
| `packages/infrastructure/src/infrastructure/sheets.py` | AssetRepository 具象（gspread） | `find_by_date_range` を実装（現状 L69-71 が `NotImplementedError`）。read 経路追加・`save` 不変 |
| `packages/infrastructure/src/infrastructure/notifier.py` | Notifier 具象（LINE） | **新規**。`LineConfig` + `LineNotifier`（push / urllib / transport seam） |
| `packages/common/src/common/settings.py` | env 設定 | `NotifySettings` を追加（`CollectSettings` と同様 `_require` ベース、`notify_days` 既定7） |
| `apps/batch/src/batch/handler_notify.py` | notify composition root | **新規**。`handler_collect.py` の DI パターンを踏襲 |
| `apps/batch/Dockerfile` | batch 共有イメージ | ヘッダコメント更新のみ（collect+notify 供用を明記） |
| `infra/lib/batch-stack.ts` | CDK batch | notify Lambda + 日曜 09:00 Schedule 追加、notify-line SSM import + grantRead、collect を `MON-FRI` 化 |
| `infra/test/__snapshots__/batch-stack.test.ts.snap` | Vitest snapshot | `run test:update`（notify fn + schedule + collect weekDay 反映） |
| `scripts/run_notify_local.py` | ローカル検証ランナー | **新規**。`run_collect_local.py` と対をなす |
| `PROJECT_PLAN.md` / `CLAUDE.md` | ドキュメント | 収集スケジュール「日次」→「平日のみ」、Phase 4 TODO 消し込み |

### 参照・影響範囲ファイル
| ファイルパス | 役割 | 影響内容 |
|-------------|------|----------|
| `packages/domain/src/domain/notification.py` | `Summary`/`summarize`/`Notification`/`render_summary`/`Notifier` | 契約（変更しない）。`render_summary` 文言は現状維持 |
| `packages/application/src/application/notification.py` | `NotifySummaryUseCase`（窓計算・skip・send） | handler で DI して呼ぶ（変更しない） |
| `packages/domain/src/domain/asset.py` L113-123 | `AssetRepository.find_by_date_range` 契約 | 閉区間・基準日昇順・歯抜け許容の契約を満たす実装 |
| `packages/infrastructure/src/infrastructure/sheets.py` L56-67 | `save`（行展開フォーマット） | read は save の列順 `[base_date, name, contribution.yen, profit_loss.yen, valuation.yen]` と round-trip させる |
| `packages/application/tests/conftest.py` L79-101 | `InMemoryAssetRepository` / `RecordingNotifier` | read/notify の期待挙動の参照（フィルタ＋昇順、send 記録） |

### 類似実装の参考箇所
| 参考ファイル | 行番号 | 参考内容 |
|-------------|--------|----------|
| `apps/batch/src/batch/handler_collect.py` | L40-91 | composition root（`build_use_case` factory seam + `handler`）。SSM→config→具象→UseCase→execute |
| `apps/batch/tests/test_handler_collect.py` | L61-119 | fake UseCase を factory seam に注入＋moto 下で実 wiring 検証 |
| `packages/infrastructure/src/infrastructure/sheets.py` | L48-67 | worksheet キャッシュ（コールドスタート時のみ認証）/ `client_factory` 注入パターン |
| `packages/common/src/common/settings.py` | L22-44 | `CollectSettings.from_env`（`_require` ベース dataclass） |
| `scripts/run_collect_local.py` | 全体 | ローカルランナーの構造（本番 build_use_case と対・seam 注入・dry-run / 実行モード） |
| `infra/lib/batch-stack.ts` | L75-110 | DockerImageFunction / LogGroup / grantRead / Schedule のパターン（notify はこれを複製＋cmd 違い） |

### 既存コード構造（notify 経路）
```
packages/domain/src/domain/
├── asset.py          # Money/ProductAsset/AssetTotal/PortfolioAsset/AssetRepository(find_by_date_range 契約)
├── clock.py          # Clock(Protocol)
└── notification.py   # Summary/summarize/Notification/render_summary/Notifier(Protocol)  ← 抽象完了済

packages/application/src/application/
└── notification.py   # NotifySummaryUseCase（窓計算・0件skip・send）  ← 抽象完了済

packages/infrastructure/src/infrastructure/
├── sheets.py         # SheetsAssetRepository（save 実装済 / find_by_date_range は本タスクで実装）
├── notifier.py       # ★新規: LineNotifier
└── clock.py          # SystemClock（再利用）

apps/batch/src/batch/
├── handler_collect.py  # 参照（DI パターンの手本）
└── handler_notify.py   # ★新規
```

---

## 設計（グリル合意）

### パッケージング: 同一コンテナを `cmd` 違いで再利用（PROJECT_PLAN §2.3.1 準拠）
- notify は収集イメージ（`apps/batch/Dockerfile`）を `cmd=["batch.handler_notify.handler"]` で再利用。**新規 Dockerfile・新規依存・新規イメージビルドは不要**。
- `cmd` は CDK の `DockerImageCode.fromImageAsset` の override（Lambda ImageConfig.Command）であり image asset 自体のフィンガープリントには影響しない＝**同一イメージを1回ビルドし2関数が参照**（collect/notify）。
- notify 経路は `infrastructure.scraper`（selenium import）を import しない（`sheets` + 新規 `notifier` のみ）。重イメージのコールドスタートは週次バッチのため実害なし。

### infrastructure/sheets.py（read 実装）
- `find_by_date_range(from_date, to_date)`:
  - `worksheet.get_all_values()` で全行取得。各行 col1 を `date.fromisoformat` で解釈、**失敗した行（ヘッダ "base_date" / 空行）はスキップ**（ヘッダ有無に頑健）。
  - 基準日が閉区間 `[from_date, to_date]` の行のみ採用。金額3列は `Money(int(cell))`（save が `ValueInputOption.raw` で生整数を保存しているため exact round-trip）。
  - 同一 base_date の行を `ProductAsset` にして1つの `PortfolioAsset` に集約。**base_date 昇順**の `list[PortfolioAsset]` を返す（区間内 0件もあり得る）。
  - 既存 `SheetsConfig` / worksheet キャッシュ（`_worksheet_handle`）を再利用。`save` は不変。

### infrastructure/notifier.py（新規・LINE push）
```python
@dataclass(frozen=True)
class LineConfig:
    channel_access_token: str
    to: str  # 送信先 userId（push）
    api_url: str = "https://api.line.me/v2/bot/message/push"

class LineNotifier:  # Notifier ポートを構造的に満たす
    def __init__(self, config: LineConfig, *, transport: Transport = _default_transport) -> None: ...
    def send(self, notification: Notification) -> None:
        text = f"{notification.subject}\n\n{notification.body}"
        payload = {"to": self._config.to, "messages": [{"type": "text", "text": text}]}
        # urllib.request で POST。header: Authorization: Bearer {token}, Content-Type: application/json
        # 非2xx は HTTPError が伝播（Lambda 失敗＝検知に委ねる）
```
- `Transport = Callable[[str, bytes, Mapping[str, str]], None]`（url, body, headers）。既定実装は `urllib.request.urlopen`、テストは記録用 fake を注入（ネットワーク非依存）。
- LINE text メッセージ上限 5000 文字。`render_summary` の body は十分小さい。
- LINE Notify 終了（2025-03-31）に伴い Messaging API push を採用した旨をコードコメントに残す。

### common/settings.py（NotifySettings 追加）
```python
@dataclass(frozen=True)
class NotifySettings:
    env_name: str
    sheets_sa_param: str       # SHEETS_SA_PARAM_ARN（read 用に再利用）
    notify_line_param: str     # NOTIFY_LINE_PARAM_ARN
    notify_days: int           # NOTIFY_DAYS（欠落時 7）
```
- collect は `source-login` / `error_page_bucket` を要するが notify は不要（Sheets read + LINE のみ）。`common` の `_require` を共有。

### apps/batch/handler_notify.py（composition root）
- `handler_collect` と同形。`build_use_case` factory seam を持ち、`handler(event, context, *, use_case_factory=build_use_case)`。
- SSM `sheets-sa`（read 用 config）＋ `notify-line`（token/to）を取得 → `SheetsAssetRepository`/`LineNotifier`/`SystemClock` を `NotifySummaryUseCase` に DI。
- `days = (event or {}).get("days") or settings.notify_days`（event 優先・既定 env=7）。
- `execute(days)` の戻り（`Notification | None`）を最小 dict に整形してログ＆返却：
  - 送信時: `{"status":"ok","days":N,"period_from":...,"latest_date":...}`（Summary 由来の最古/最新を含めるなら use case 戻りを `Notification` のみから判別できないため、必要なら use case 側は現状維持で handler は `{"status":"ok","days":N,"subject":notification.subject}` 程度に留める）
  - skip 時（None）: `{"status":"skipped","days":N}`
- 例外は捕捉せず再送出（Lambda 失敗扱い）。

### infra/lib/batch-stack.ts（notify 追加・collect 平日化）
- collect の `DailyCollect` schedule に `weekDay: 'MON-FRI'` を追加（時刻 09:00 JST 不変）。
- notify-line SSM を `fromSecureStringParameterAttributes` でインポート。
- notify Lambda: 同一 `DockerImageCode.fromImageAsset(repoRoot, { file: 'apps/batch/Dockerfile', cmd: ['batch.handler_notify.handler'], ignoreMode: IgnoreMode.DOCKER })`、memory 512、timeout `Duration.minutes(1)`、`reservedConcurrentExecutions: 1`、専用 LogGroup（`ONE_WEEK` / DESTROY）、env（`ENV_NAME` / `SHEETS_SA_PARAM_ARN` / `NOTIFY_LINE_PARAM_ARN` / `NOTIFY_DAYS`）。
- `grantRead`: sheets-sa（read）+ notify-line。エラーページ S3 は notify では付与しない。
- `WeeklyNotify` Schedule: `cron({ minute:'0', hour:'9', weekDay:'SUN', timeZone: TimeZone.ASIA_TOKYO })`。
- `functionName` / `logGroupName` は付けない（CDK 自動命名。infra-resource-naming 方針）。
- snapshot を `pnpm --filter @idash/infra run test:update` で更新。

### scripts/run_notify_local.py（ローカルランナー）
- `run_collect_local.py` と対。本番 `handler_notify.build_use_case`（SSM→Sheets/LINE）に対し、ローカル JSON 認証で `SheetsAssetRepository`（実 read）/ `LineNotifier`（`--send` 時のみ実送信、既定は print transport）/ `SystemClock` を組み、`NotifySummaryUseCase.execute(days)` を実行。
- `--days N`（既定 env 相当 7）/ `--send`（実 LINE 送信）/ 既定 dry-run（transport を print fake に差替）。本番コード不変・公開面非拡張。決定的テスト対象外（ruff/ty のみ）。

### テスト方針
- `infrastructure/sheets.py`: gspread worksheet を mock し `get_all_values` の戻りから、(a) ヘッダ/空行スキップ、(b) 閉区間フィルタ（境界含む／範囲外除外）、(c) `Money(int)` round-trip（負の profit_loss 含む）、(d) 同一 base_date 複数商品の集約、(e) base_date 昇順、(f) 0件 を検証。`save`→`find_by_date_range` の round-trip も可能なら確認。
- `infrastructure/notifier.py`: fake transport を注入し、POST url=push エンドポイント / `Authorization: Bearer {token}` / `Content-Type: application/json` / body JSON（`to`、`messages[0].type=="text"`、text==`subject\n\nbody`）を検証。非2xx 時に例外伝播することを fake transport で確認。
- `common/settings.py`: `NotifySettings.from_env`（必須欠落で KeyError、`NOTIFY_DAYS` 欠落で既定7、指定時 int 解釈）。
- `apps/batch/handler_notify.py`: factory seam に fake UseCase を注入し、(a) days 解決（event 優先 / env 既定）、(b) 戻り dict（ok / skipped）、(c) 例外再送出 を確認。moto 下で `build_use_case` の実 wiring（SSM 2本→config）も確認。
- infra Vitest snapshot: notify fn + schedule + collect weekDay 反映を `run test:update`。
- `--cov` は既存（infrastructure/common/batch）に含まれるため pyproject 変更不要。

---

## 詳細タスク一覧

### フェーズ1: 準備・設計確認（グリル完了）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 1.1 | 要件グリル・合意形成（grill-with-docs） | ✅ | スコープ統合・パッケージング A・LINE push・スケジュール・N・SSM 名・collect 平日化を確定 |
| 1.2 | 進捗ファイル作成 | ✅ | 本ファイル |

> ADR は作成しない（チャネルは `Notifier` ポート背後で差替可能＝覆すコスト小。issue-16 同様シンプル優先）。CONTEXT.md も変更不要（`Notifier` はチャネル非依存、LINE はインフラ詳細）。

### フェーズ2: 実装
| # | タスク | 状態 | 対象ファイル | 実装詳細 |
|---|--------|------|-------------|----------|
| 2.1 | Sheets read 実装 | ✅ | `infrastructure/sheets.py` | `find_by_date_range`（get_all_values→date 解釈/ヘッダ空行 skip→閉区間→Money(int)→base_date 集約→昇順） |
| 2.2 | LINE 通知具象 | ✅ | `infrastructure/notifier.py`（新規） | `LineConfig` + `LineNotifier`（push / urllib / transport seam / 非2xx 伝播） |
| 2.3 | NotifySettings | ✅ | `common/settings.py` | env_name/sheets_sa_param/notify_line_param/notify_days（既定7） |
| 2.4 | handler_notify（DI） | ✅ | `apps/batch/.../handler_notify.py`（新規） | env+SSM2本→具象構築→UseCase.execute(days)。event 優先 days・最小 dict・例外再送出 |
| 2.5 | Dockerfile コメント更新 | ✅ | `apps/batch/Dockerfile` | 「batch 共有イメージ（collect+notify）」明記（位置・CMD 不変） |
| 2.6 | CDK notify + collect 平日化 | ✅ | `infra/lib/batch-stack.ts` | notify fn（同一イメージ cmd 違い/512/1分/予約1/LogGroup/grantRead×2/env4/日曜09:00）＋ collect を MON-FRI 化 |
| 2.7 | ローカルランナー | ✅ | `scripts/run_notify_local.py`（新規） | --days/--send/dry-run。本番コード不変 |
| 2.8 | ドキュメント更新 | ✅ | `PROJECT_PLAN.md` / `CLAUDE.md` | 収集「日次」→「平日のみ」、Phase 4 TODO 消し込み |

### フェーズ3: テスト（検証）
| # | タスク | 状態 | 対象 | テスト観点 |
|---|--------|------|------|-----------|
| 3.1 | Sheets read テスト | ✅ | `infrastructure/tests/` | ヘッダ/空行 skip・閉区間境界・Money round-trip（負値）・複数商品集約・昇順・0件 |
| 3.2 | LineNotifier テスト | ✅ | `infrastructure/tests/` | url/Bearer/Content-Type/body JSON（to/messages/text）・非2xx 伝播 |
| 3.3 | NotifySettings テスト | ✅ | `common/tests/` | 必須欠落 KeyError・NOTIFY_DAYS 既定7・int 解釈 |
| 3.4 | handler_notify テスト | ✅ | `apps/batch/tests/` | days 解決（event 優先/env）・戻り dict（ok/skipped）・例外再送出・moto wiring |
| 3.5 | snapshot 更新 | ✅ | `infra/test/__snapshots__/` | notify fn + schedule + collect weekDay |
| 3.6 | `task check` / `task synth` green | ✅ | 全体 | ruff/Biome/ty/tsc/pytest+cov/infra-vitest + synth |

### フェーズ4: レビュー・完了
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 4.1 | セルフレビュー | ⬜ | 受入条件チェック |
| 4.2 | PR 作成 | ⬜ | ユーザー指示があれば |
| 4.3 | コードレビュー対応 | ⬜ | |
| 4.4 | マージ・完了 | ⬜ | |

### フェーズ5: ライブ依存（後続・ユーザー環境が必要）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 5.1 | LINE 公式アカウント作成・トークン取得・Bot 友だち追加・userId 取得 | ⬜ | ユーザー実施 |
| 5.2 | SSM `/idash/<env>/notify-line`（SecureString JSON `{channel_access_token, to}`）作成 | ⬜ | AWS 側で手動作成 |
| 5.3 | `run_notify_local.py --send` で実 LINE 送信検証 | ⬜ | 実トークン・実 userId が必要 |
| 5.4 | 実デプロイ＆動作確認 | ⬜ | GitHub Actions deploy 経由・ユーザー実施 |

### ステータス凡例
- ⬜ 未着手 / 🔄 進行中 / ✅ 完了 / ⏸️ 保留 / ❌ キャンセル

---

## 総合進捗

| 項目 | 完了 | 総数 | 進捗率 |
|------|------|------|--------|
| 設計（フェーズ1） | 2 | 2 | 100% |
| 実装（フェーズ2） | 8 | 8 | 100% |
| 検証（フェーズ3） | 6 | 6 | 100% |
| **本タスク到達ライン（フェーズ2+3）** | **14** | **14** | **100%** |

※ フェーズ5（ライブ依存）はユーザー環境が必要なため後続。フェーズ4 はユーザー指示待ち。

---

## 作業ログ

### 2026-06-24
#### 実施内容
- [x] 要件グリル・合意形成（grill-with-docs）。スコープ統合・パッケージング A・LINE push・スケジュール・N・SSM 名・collect 平日化・各具象契約・テスト方針を確定
- [x] 本進捗ファイル（issue-16-concrete）作成
- [x] `feature/batch-notify-concrete` を main から作成
- [x] フェーズ2（実装）2.1〜2.8 完了:
  - 2.1 `sheets.find_by_date_range`（get_all_values→date 解釈/ヘッダ空行 skip→閉区間→`Money(int)` round-trip→base_date 集約→昇順）
  - 2.2 `infrastructure/notifier.py`（`LineConfig` + `LineNotifier`。push / stdlib urllib / transport seam / 非2xx 伝播。新規依存ゼロ）
  - 2.3 `common.NotifySettings`（`NOTIFY_DAYS` 既定7・int 解釈）
  - 2.4 `apps/batch/handler_notify.py`（env+SSM2本→具象 DI→`execute(days)`。event 優先 days・最小 dict・例外再送出）
  - 2.5 Dockerfile ヘッダを batch 共有イメージ（collect+notify）へ更新（CMD 不変）
  - 2.6 CDK notify Lambda（同一イメージ cmd 違い/512/1分/予約1/専用 LogGroup/grantRead×2/env4/日曜09:00）＋ collect を `MON-FRI` 化
  - 2.7 `scripts/run_notify_local.py`（--days/--send/dry-run print transport）
  - 2.8 `PROJECT_PLAN.md` / `CLAUDE.md` の収集スケジュール「日次」→「平日のみ」、Phase 4 TODO 消し込み
- [x] フェーズ3（検証）3.1〜3.6 完了:
  - 3.1 `test_sheets_read.py`（ヘッダ/空行 skip・閉区間境界・Money 負値 round-trip・複数商品集約・昇順・0件・save→find round-trip）
  - 3.2 `test_notifier.py`（url/Bearer/Content-Type/body JSON・例外伝播）
  - 3.3 `test_settings.py` に NotifySettings（必須欠落 KeyError・既定7・int 解釈）追加
  - 3.4 `test_handler_notify.py`（days 解決 event 優先/env・ok/skipped・例外再送出・moto wiring）
  - 3.5 infra snapshot 更新（notify fn + SUN schedule + collect MON-FRI。collect/notify は同一 image asset hash＝1ビルド）
  - 3.6 `task check`（82 passed / cov 96%）＋ `task synth` green。notify 経路は selenium-free を確認。pyproject/uv.lock 不変

#### 進捗サマリー
- **完了**: フェーズ1（設計）2/2、フェーズ2（実装）8/8、フェーズ3（検証）6/6 ＝ 本タスク到達ライン 14/14
- **進行中**: なし
- **ブロッカー**: なし
- **次のアクション**: フェーズ4（レビュー・PR）はユーザー指示待ち。フェーズ5（ライブ依存: LINE OA 準備・SSM 実値・実送信・実デプロイ）はユーザー環境

---

## メモ・課題

### 未解決課題（ライブ検証フェーズで確定）
| # | 課題 | 優先度 | 対応 |
|---|------|--------|------|
| 1 | LINE チャネルアクセストークン・userId の実値（SSM `/idash/<env>/notify-line`） | 中 | フェーズ5.1/5.2 |
| 2 | 実 LINE 送信での体裁確認（改行・文字数）。必要なら `render_summary` 文言を微調整 | 低 | フェーズ5.3 |
| 3 | Sheets の実データ列順・ヘッダ有無の最終確認（fixture は save 列順準拠で作成） | 低 | フェーズ5.4 |

### 決定事項
| 日付 | 決定事項 | 決定者 |
|------|----------|--------|
| 2026-06-24 | スコープ: notification の具象＋コンテナを1タスクに統合し、`task check`/`synth`/snapshot green まで。実 deploy・実 LINE 送信検証・LINE OA 準備・SSM 実値作成はライブ依存で後続分離 | ユーザー |
| 2026-06-24 | パッケージング: A（収集コンテナを `cmd=batch.handler_notify.handler` で再利用）。新規 Dockerfile・新規依存・新規イメージビルドなし。PROJECT_PLAN「1アプリ=1イメージ」準拠 | ユーザー |
| 2026-06-24 | Dockerfile は現位（`apps/batch/Dockerfile`）維持＋ヘッダコメントを batch 共有イメージへ更新。リネーム・移動なし | ユーザー |
| 2026-06-24 | 通知チャネル: LINE Messaging API（LINE Notify は 2025-03-31 終了のため）。送信は **push（自分の userId 宛）**。SecureString JSON `{channel_access_token, to}` | ユーザー |
| 2026-06-24 | HTTP クライアントは stdlib `urllib.request`（新規依存ゼロ）。`transport` シーム注入でテスト。非2xx は伝播 | ユーザー（推奨承認） |
| 2026-06-24 | 通知スケジュール: 週次・**日曜 09:00 JST**。N（集計対象日数）= env `NOTIFY_DAYS` 既定 7 + event `days` で上書き（event 優先） | ユーザー |
| 2026-06-24 | SSM パラメータ名: `/idash/<env>/notify-line`（チャネル明示・notify スコープ） | ユーザー |
| 2026-06-24 | **collect スケジュールを平日のみ（Mon–Fri 09:00 JST）へ変更**（土日は更新されず・メンテ多いため）。現状コード/ドキュメントの「日次」記述も更新。これにより notify 日曜 09:00 の collect 競合も解消 | ユーザー |
| 2026-06-24 | ローカル検証ランナー `scripts/run_notify_local.py` を含める（collect と対称） | ユーザー |
| 2026-06-24 | Sheets read: `get_all_values`→col1 を date 解釈しヘッダ/空行 skip→閉区間→`Money(int)` round-trip→base_date 集約→昇順。save 列順と round-trip | ユーザー（推奨承認） |
| 2026-06-24 | `render_summary` 文言は現状維持（LINE text にプレーンテキストでそのまま流せる）。実送信後に必要なら微調整 | ユーザー（推奨承認） |
| 2026-06-24 | ADR 作成なし／CONTEXT.md 変更なし（チャネルはポート背後で差替可・LINE はインフラ詳細） | ユーザー |

---

## 作業再開ガイド

### 現在の状態
- **最終作業**: フェーズ1（設計）完了。実装未着手。ブランチ未作成
- **次のアクション**: `feature/batch-notify-concrete` を main から作成し、フェーズ2.1（Sheets read）から TDD で着手

### 再開時の確認事項
1. 本ファイルの「設計（グリル合意）」「決定事項」を厳守（再設計しない）
2. `domain` / `application` の契約（`notification.py` / `asset.py`）は変更しない。`render_summary` 文言も現状維持
3. `domain` 依存ゼロは無関係（具象は infrastructure）だが、**新規サードパーティ依存を増やさない**（LINE は stdlib urllib）。pyproject/uv.lock を触らない
4. notify 経路は `infrastructure.scraper`（selenium）を import しないこと（重依存を notify 起動経路へ持ち込まない）
5. CDK は物理名を付けない（自動命名）。collect の cron 変更と notify 追加で snapshot が壊れるので `run test:update`
6. 到達ラインは「決定的テスト＋ `task check`/`task synth` green」。実 deploy・実 LINE 送信はフェーズ5（ライブ依存）

### コンテキスト復元用コマンド
```bash
# ブランチ作成（base は main）
git switch -c feature/batch-notify-concrete

# 設計確認
cat docs/progress/issue-16-concrete.md docs/progress/issue-16-domain.md docs/progress/issue-8-concrete.md

# 検証
task check && task synth
```
