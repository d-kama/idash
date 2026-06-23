# サマリ通知バッチ 抽象レイヤ実装（domain summarize/Notification/read ポート + application NotifySummary / 抽象テストまで）

## 基本情報

| 項目 | 内容 |
|------|------|
| チケット | issue-16 |
| ブランチ | feature/batch-notify-domain |
| 開始日 | 2026-06-21 |
| 目標完了日 | TBD |
| 最終更新 | 2026-06-21 |

---

## 要件サマリー

### 背景・目的
`PROJECT_PLAN.md` の **Phase 4（サマリ通知バッチ）** のうち、**抽象レイヤ（`domain` + `application`）とその抽象テスト**を実装する。収集バッチ（issue-8 系）が Sheets へ蓄積した `PortfolioAsset` を、直近 N 日ぶん読み取り → 集計（`summarize`）→ 整形（`render_summary`）→ 通知（`Notifier`）する経路の純粋部分を確立する。

収集の抽象レイヤ実装（issue-8.md）の前例に倣い、Phase 4 を縦切りで分割した**スコープ A（ドメイン〜抽象）**。具象（Sheets read 具象 / 通知チャネル具象）・`handler_notify`・CDK・deploy は後続タスク（concrete / container）へ分離する。issue-8 で Phase 4 へ申し送られた「`AssetRepository` read 系」「通知系 `Notifier` / `Notification` / `summarize`」をここで実装する。

### 受入条件
- [x] `domain` に `summarize` / `Summary` / `render_summary` / `Notification` / `Notifier` を実装し、`ruff` / `ty` グリーン。**domain は依存ゼロ（pydantic 不使用）を維持**
- [x] `AssetRepository` に `find_by_date_range(from_date, to_date)` を**後方互換で追加**（既存 `save` は不変）
- [x] `Clock` を共有ポート `domain/clock.py` へ昇格し、既存 import（collection / scraper / application.collection）を付け替えても収集側テストがグリーン
- [x] `application` の `NotifySummaryInputBoundary` + `NotifySummaryUseCase`（窓計算・skip 判定込み）を実装
- [x] 抽象テストが **集計（複数日 / 単一日）・整形（本文スナップショット）・窓境界・0件 skip・損益率ゼロ拠出ガード**を網羅しグリーン
- [x] `task check`（ruff / Biome / ty / tsc / pytest / infra-vitest）がすべてグリーン
- [x] `CONTEXT.md` が通知語彙（`Summary` / `Notification` / `Notifier`）を反映（本セッションで更新済み）

### スコープ
- **対象**:
  - `packages/domain`: `notification.py`（新規）、`clock.py`（新規＝昇格）、`asset.py`（`find_by_date_range` 追加）、`collection.py`（`Clock` を `domain.clock` から import に変更）
  - `packages/infrastructure`: `scraper.py`（`Clock` の import 元を `domain.clock` へ付替のみ。ロジック不変）
  - `packages/application`: `notification.py`（新規）、`collection.py`（`Clock` import 元の付替のみ）
  - 上記の `tests/`（domain `test_notification.py`、application `conftest.py` 拡張 + `test_notification_use_case.py`）
- **対象外（後続タスク）**:
  - `infrastructure` 具象: Sheets の `find_by_date_range` 実装（行→基準日グループ化で `PortfolioAsset` 再構成）、通知チャネル具象（`Notifier` の実体）
  - `apps/batch/handler_notify.py`（composition root・DI 結線）、N の既定値・指定方法（env / event）
  - `Dockerfile` / `DockerImageFunction`（notify 関数）/ CDK（notify Lambda・スケジュール・`grantRead`）/ snapshot 更新 / 実 deploy
  - 通知スケジュール（JST）、通知チャネルの選定（メール / Slack / LINE）と認証情報管理
  - `schemas`（Pydantic DTO。通知は HTTP/JSON 境界を持たないため不要）
  - `find_by_date`（単日取得。今回の消費者なし＝YAGNI。必要時に後方互換追加）

---

## コードベース調査結果

### 現状（issue-8 系完了済み・本タスクの起点）
- 収集バッチの abstract / concrete / container が完了し main にマージ済み。`domain` / `application` / `infrastructure` / `common` / `apps/batch`（collect）が実装済み。
- 既存 `domain/asset.py`: `Money`（parse/四則/format/signed）/ `ProductAsset` / `AssetTotal` / `PortfolioAsset.total()` / `AssetRepository`（**現状 `save` のみ**）。**集計は既存の `total()` を再利用可能**。
- 既存 `domain/collection.py`: `Clock(Protocol)` が「ErrorPage 時刻専用」の位置づけでここに定義されている。
- 既存 `infrastructure/clock.py`: `SystemClock`（JST aware）。Protocol を import せず**構造的に充足**（昇格しても無変更で両ポートを満たす）。
- 既存 `application/collection.py`: `CollectionInputBoundary` + `CollectionUseCase`。**DI でポート具象を受けるパターンの参照実装**。
- pytest 設定（issue-8）: `--import-mode=importlib` / `testpaths=["packages","apps"]` / `--cov=domain --cov=application`（レポートのみ・閾値なし）。**新規ファイルは既存 cov 対象配下のため pyproject 変更不要**。

### 参照・影響範囲ファイル
| ファイルパス | 役割 | 影響内容 |
|-------------|------|----------|
| `packages/domain/src/domain/asset.py` | アセットコア | `AssetRepository` に `find_by_date_range` を追加（既存に変更なし） |
| `packages/domain/src/domain/collection.py` | 収集サブドメイン | `Clock` 定義を `domain/clock.py` へ移設。本ファイルからは削除 |
| `packages/infrastructure/src/infrastructure/scraper.py` L30 | Selenium 具象 | `from domain.collection import Clock, ...` → `Clock` を `domain.clock` から import に分離 |
| `packages/application/src/application/collection.py` L13 | 収集ユースケース | `Clock` の import 元を `domain.clock` へ変更 |
| `packages/application/tests/conftest.py` | 収集テストの Fake | `InMemoryAssetRepository` に `find_by_date_range` を追加、`RecordingNotifier` を追加（`FixedClock` は再利用） |
| `pyproject.toml` `[tool.pytest.ini_options]` | pytest 設定 | 変更なし（cov 対象 `domain`/`application` に新規ファイルが含まれる） |
| `CONTEXT.md` | ドメイン用語集 | ✅ `Summary`/`Notification`/`Notifier` を追加済み（本セッション） |

### 類似実装の参考箇所
| 参考ファイル | 行番号 | 参考内容 |
|-------------|--------|----------|
| `packages/application/src/application/collection.py` | L22-53 | InputBoundary(Protocol) + UseCase の構成、DI での具象受け取り、薄い orchestration |
| `packages/application/tests/conftest.py` | L78-120 | `InMemoryAssetRepository` / `FixedClock` の Fake パターン（拡張のベース） |
| `packages/domain/src/domain/asset.py` | L85-119 | `PortfolioAsset.total()`（集計の既存実装。`summarize` から再利用）/ `AssetRepository`（read 系追加先） |

---

## 設計（グリル合意）

### モジュールレイアウト（サブドメイン別。issue-8 の方針を踏襲）
```
packages/domain/src/domain/
├── asset.py         # 既存。AssetRepository に find_by_date_range を後方互換追加
├── clock.py         # 新規（昇格）。Clock(Protocol) を collection.py から移設
├── collection.py    # 既存。Clock 定義を削除し import 不要化（本ファイルは Clock を内部で使わない）
└── notification.py  # 新規。通知サブドメイン

packages/application/src/application/
├── collection.py    # 既存。Clock の import 元を domain.clock へ
└── notification.py  # 新規。NotifySummaryInputBoundary + NotifySummaryUseCase
```

### domain/clock.py（昇格）
```python
from typing import Protocol
from datetime import datetime

class Clock(Protocol):
    """現在時刻を供給する汎用の技術ポート（収集・通知・将来の BFF が共有）。"""
    def now(self) -> datetime: ...
```
- `domain/collection.py` から `Clock` 定義を削除。`infrastructure/scraper.py` と `application/collection.py` は `from domain.clock import Clock` へ付替。
- `SystemClock`（`infrastructure/clock.py`）は構造的実装のため無変更で満たす。

### domain/asset.py（read 系の後方互換追加）
`AssetRepository(Protocol)` に1メソッド追加（`save` は不変）:
```python
def find_by_date_range(
    self, from_date: date, to_date: date
) -> Sequence[PortfolioAsset]: ...
```
- 契約: `from_date`〜`to_date` の**閉区間**に基準日が含まれる `PortfolioAsset` を、**基準日昇順**で返す。区間内に実在する基準日だけを返す（歯抜け許容、件数 0 もあり得る）。
- `from collections.abc import Sequence` を追加。`date` は既存 import を利用。

### domain/notification.py（新規）
すべて stdlib `@dataclass(frozen=True)` / `Protocol`。`domain.asset` の `Money` / `AssetTotal` / `PortfolioAsset` のみ参照。

```python
@dataclass(frozen=True)
class Summary:
    period_from: date        # 区間内に実在する最古基準日
    latest_date: date        # 区間内に実在する最新基準日
    latest_total: AssetTotal # 最新時点の合計（拠出累計 / 評価損益 / 資産評価額）
    profit_rate: float       # 損益率 = profit_loss.yen / contribution.yen（生比率。表示整形しない）
    valuation_change: Money  # 最新評価額 − 最古評価額
    profit_change: Money     # 最新評価損益 − 最古評価損益


def summarize(assets: Sequence[PortfolioAsset]) -> Summary:
    """1件以上の PortfolioAsset を集計して Summary を返す（0件はユースケースが手前で弾く）。"""
    # base_date 昇順を前提とせず、min/max を base_date で取って最古/最新を決める（防御的）。
    # latest_total = newest.total() / oldest_total = oldest.total()
    # profit_rate = latest_total.profit_loss.yen / latest_total.contribution.yen
    #   （contribution.yen == 0 のときは 0.0 にガード）
    # valuation_change = latest_total.valuation - oldest_total.valuation（Money.__sub__）
    # profit_change   = latest_total.profit_loss - oldest_total.profit_loss
    ...


@dataclass(frozen=True)
class Notification:
    subject: str  # チャネル非依存
    body: str     # チャネル非依存のプレーンテキスト


def render_summary(summary: Summary) -> Notification:
    """Summary を人が読むテキストへ整形する純粋関数（Money.format()/signed() を使用）。"""
    ...


class Notifier(Protocol):
    """整形済み Notification を通知チャネルへ送るポート（集計・整形は持たない）。"""
    def send(self, notification: Notification) -> None: ...
```

#### render_summary の出力（暫定確定。issue-8 の Money 表示確定と同様、消費者が後続のため微調整可）
```
subject = f"iDeCo 運用サマリ（{period_from.isoformat()}〜{latest_date.isoformat()}）"

body =
■ 最新（{latest_date} 時点）
  資産評価額: {latest_total.valuation.format()}
  評価損益: {latest_total.profit_loss.signed()}（{profit_rate * 100:+.2f}%）
  拠出累計: {latest_total.contribution.format()}
■ この期間の変化（{period_from} → {latest_date}）
  評価額: {valuation_change.signed()}
  評価損益: {profit_change.signed()}
```
- 損益率は本文側で `*100` し `+.2f%`（符号付き2桁）で表示。`Summary.profit_rate` 自体は生の比率を保持。

### application/notification.py（新規）
```python
class NotifySummaryInputBoundary(Protocol):
    def execute(self, days: int) -> Notification | None: ...

class NotifySummaryUseCase(NotifySummaryInputBoundary):
    def __init__(self, repository: AssetRepository, notifier: Notifier, clock: Clock) -> None: ...

    def execute(self, days: int) -> Notification | None:
        today = self._clock.now().date()
        from_date = today - timedelta(days=days - 1)   # 直近 N 日 = today を含む閉区間
        assets = self._repository.find_by_date_range(from_date, today)
        if not assets:
            return None                                 # 0件 = 送信せず skip
        summary = summarize(assets)
        notification = render_summary(summary)
        self._notifier.send(notification)
        return notification
```
- **戻り値**: 成功＝送った `Notification`、skip＝`None`（収集ユースケースが `PortfolioAsset` を返すのと同様、application は domain 型を返し、Lambda レスポンス整形は後続の `handler_notify` の責務）。
- **窓計算は use case が保持**（`days` → `[today-(N-1), today]`）。Clock 注入で純粋にテスト可能。「直近 N 日」の解釈を1箇所に集約し、将来 BFF が同じ集計を使うときも `summarize` を共有して計算重複を避ける。
- **集計は持たない**（`summarize` へ委譲）。orchestration（窓・fetch・skip 判定・send）のみ。

### テスト方針
- **domain `test_notification.py`**:
  - `summarize`: 複数基準日（最古/最新の差分・損益率・最新合計が正しい）/ 単一基準日（`valuation_change` = `profit_change` = `Money(0)`）/ 入力順序不問（未ソート入力でも min/max を base_date で選ぶ）/ 拠出ゼロで `profit_rate == 0.0`
  - `render_summary`: subject / body の**文字列スナップショット**（チャネル無しで整形を固定）
- **application `test_notification_use_case.py`**（`conftest.py` の Fake を使用）:
  - ok 系: 窓内に資産あり → `notifier` が `render_summary` 出力の `Notification` を1回受領、戻り値が同一
  - skip 系: 窓内 0件 → `notifier.send` **未呼出**、戻り値 `None`
  - 窓境界: `today-(N-1)` 未満 / `today` 超過の基準日は除外される（`FixedClock` 基準）
  - 単一日: 窓内1件 → 送信され差分0
- **conftest 拡張**: `InMemoryAssetRepository` に `find_by_date_range`（`self.saved` を区間でフィルタし base_date 昇順で返す）を追加し、`save` 済みデータを read する形でシード。`RecordingNotifier`（受領 `Notification` を記録）を追加。`FixedClock` は再利用。

---

## 詳細タスク一覧

### フェーズ1: 準備・設計確認（グリル完了）
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 1.1 | 要件グリル・合意形成（grill-with-docs） | ✅ | スコープ・サマリ内容・read ポート・整形責務・Clock 昇格・データ不足挙動を確定 |
| 1.2 | 語彙確定（`Summary`/`Notification`/`Notifier`） | ✅ | `CONTEXT.md` 更新済み |
| 1.3 | 進捗ファイル作成 | ✅ | 本ファイル |

> ADR は作成しない（整形を domain に置く件＝覆すコスト小・`CONTEXT.md` の `Notification` 定義で意図が伝わるため。決定事項参照）。

### フェーズ2: 実装
| # | タスク | 状態 | 対象ファイル |
|---|--------|------|-------------|
| 2.1 | `Clock` 昇格 | ✅ | `domain/clock.py` 新規 + `domain/collection.py` から削除 + `infrastructure/scraper.py`・`application/collection.py` の import 付替 |
| 2.2 | `AssetRepository.find_by_date_range` 追加 | ✅ | `domain/asset.py`（後方互換・`save` 不変） |
| 2.3 | 通知サブドメイン | ✅ | `domain/notification.py`（`Summary` / `summarize` / `Notification` / `render_summary` / `Notifier`） |
| 2.4 | 通知ユースケース | ✅ | `application/notification.py`（`NotifySummaryInputBoundary` + `NotifySummaryUseCase`） |

### フェーズ3: テスト（検証）
| # | タスク | 状態 | 対象 |
|---|--------|------|------|
| 3.1 | domain 単体テスト | ✅ | `domain/tests/test_notification.py`（summarize 複数日/単一日/順序不問/ゼロ拠出、render_summary スナップショット） |
| 3.2 | application ユースケーステスト | ✅ | `application/tests/conftest.py` 拡張 + `test_notification_use_case.py`（ok / skip / 窓境界 / 単一日） |
| 3.3 | `task check` グリーン | ✅ | ruff / Biome / ty / tsc / pytest(+cov) / infra-vitest 全緑（62 passed）。収集側テストも緑維持（Clock 昇格の回帰確認済み） |

### フェーズ4: レビュー・完了
| # | タスク | 状態 | 備考 |
|---|--------|------|------|
| 4.1 | セルフレビュー | ✅ | 受入条件チェック済み（下記）。domain 依存ゼロ維持・`save` 不変・Clock 昇格回帰なし |
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
| 実装（フェーズ2） | 4 | 4 | 100% |
| 検証（フェーズ3） | 3 | 3 | 100% |
| **総合（実装・検証）** | **7** | **7** | **100%** |

---

## 作業ログ

### 2026-06-21
#### 実施内容
- [x] 要件グリル・合意形成（grill-with-docs）。スコープ A・サマリ内容・read ポート形・整形責務分担・Clock 昇格・データ不足時挙動を確定
- [x] `CONTEXT.md` に `Summary` / `Notification` / `Notifier` を追加
- [x] 本進捗ファイル（issue-16-domain）作成

#### 進捗サマリー
- **完了**: フェーズ1（設計）3/3
- **進行中**: なし（フェーズ2 実装は未着手）
- **ブロッカー**: なし
- **次のアクション**: フェーズ2（実装）。`feature/batch-notify-domain` を main から作成して着手

#### 実装セッション（フェーズ2・3）
- `feature/batch-notify-domain` を main から作成
- 2.1 `Clock` 昇格: `domain/clock.py` 新規、`domain/collection.py` から `Clock` 削除、`infrastructure/scraper.py`・`application/collection.py` の import を `domain.clock` へ付替
- 2.2 `AssetRepository.find_by_date_range`（閉区間・基準日昇順）を後方互換追加（`save` 不変）
- 2.3 `domain/notification.py`（`Summary` / `summarize` / `Notification` / `render_summary` / `Notifier`）
- 2.4 `application/notification.py`（`NotifySummaryInputBoundary` + `NotifySummaryUseCase`）
- 3.1/3.2 抽象テスト追加（domain 5 ケース・application 4 ケース）、`conftest.py` に `find_by_date_range` / `RecordingNotifier` / `notifier` fixture を拡張
- 3.3 `task check` 全緑（pytest 62 passed・ruff/biome/ty/tsc・infra-vitest）

##### 計画外対応（スコープ内で解消）
- `AssetRepository` の Protocol 拡張により、収集側の既存具象（`infrastructure/sheets.py` の `SheetsAssetRepository`、`scripts/run_collect_local.py` の `_PrintAssetRepository`）が `find_by_date_range` 未実装で ty 不適合に。**read 系の実体は後続（concrete）タスク**のため、両者へ `NotImplementedError` を送出する最小スタブを追加して構造的に充足（`save` は不変）。Sheets read 本実装は未解決課題 #1 のまま。
- 上記スタブが collect Docker イメージのビルドコンテキスト内のため、infra Vitest スナップショットの `ImageUri` 資産ハッシュのみ変化（CFN 構造差分なし）。`pnpm --filter @idash/infra run test:update` で更新。notify Lambda の CDK 化は未着手（未解決課題 #4 のまま）。

#### 受入条件チェック（4.1）
- [x] `domain` に `summarize`/`Summary`/`render_summary`/`Notification`/`Notifier`、依存ゼロ維持（pydantic 不使用）
- [x] `AssetRepository.find_by_date_range` を後方互換追加（`save` 不変）
- [x] `Clock` を `domain/clock.py` へ昇格、import 3箇所付替、収集側テスト緑
- [x] `NotifySummaryInputBoundary` + `NotifySummaryUseCase`（窓計算・skip 判定込み）
- [x] 抽象テストが集計・整形・窓境界・0件 skip・ゼロ拠出ガードを網羅し緑
- [x] `task check` 全緑
- [x] `CONTEXT.md` 反映済み（フェーズ1）

---

## メモ・課題

### 未解決課題（後続タスク）
| # | 課題 | 優先度 | 期限 | 担当 |
|---|------|--------|------|------|
| 1 | `infrastructure` 具象: Sheets の `find_by_date_range`（行を base_date でグループ化し `PortfolioAsset` 再構成・昇順）+ 通知チャネル具象（`Notifier` 実体） | 中 | 後続（concrete） | 実装者 |
| 2 | `apps/batch/handler_notify.py`（DI 結線）+ N の既定値・指定方法（env / event）の確定 | 中 | 後続（concrete） | 実装者 |
| 3 | 通知チャネル選定（メール / Slack / LINE）と認証情報の Parameter Store 管理 | 中 | 後続（concrete） | ユーザー/実装者 |
| 4 | notify Lambda の CDK 化（同一イメージ・cmd 違い / スケジュール JST / 通知認証情報 `grantRead`）+ snapshot 更新 + 実 deploy | 中 | 後続（container） | 実装者 |
| 5 | `render_summary` の本文文言・損益率桁数は暫定確定。チャネル確定時に最終化（消費者が後続のため手戻りリスク低） | 低 | 後続 | 実装者 |

### 決定事項
| 日付 | 決定事項 | 決定者 |
|------|----------|--------|
| 2026-06-21 | スコープは Phase 4 の抽象レイヤ（domain + application + 抽象テスト）。具象（Sheets read / 通知チャネル）・handler・CDK・deploy は後続タスク（concrete / container）へ分離 | ユーザー |
| 2026-06-21 | サマリ内容＝「最新スナップショット（`AssetTotal` ＋ 損益率）」＋「期間変化（評価額・評価損益の増減）」。商品別内訳は載せず全体に絞る（内訳は将来 BFF/可視化へ） | ユーザー |
| 2026-06-21 | read ポートは `find_by_date_range(from_date, to_date) -> Sequence[PortfolioAsset]` の1本のみ追加。`find_by_date` は消費者なしで見送り（YAGNI） | ユーザー |
| 2026-06-21 | 「直近 N 日」はカレンダー閉区間 `[today-(N-1), today]` で解釈。Clock 注入で today を取得。区間内に実在する基準日だけ集計（収集失敗・サイト非更新日の歯抜けを許容）。期間変化の最古→最新は区間内に実在する min/max 基準日で取る | ユーザー |
| 2026-06-21 | メッセージ整形は domain の純粋関数 `render_summary(summary) -> Notification{subject,body}`（チャネル非依存プレーンテキスト）に置く。`NotifierPort.send(Notification)` は整形済みを送るだけ。チャネル別整形（代替案）は重複・テスト性低下のため不採用 | ユーザー |
| 2026-06-21 | 集計（計算）は domain の `summarize` に置き、ユースケースは持たない。理由: 将来 BFF が同じ集計を使うときにユースケース間で計算が重複しないようにするため（apps/usecase は相互依存させない方針とも整合） | ユーザー |
| 2026-06-21 | 窓内0件＝通知を送らず skip（戻り値 `None`）。収集継続失敗の検知は収集 Lambda 失敗（将来の監視）の領域で、通知バッチに代替検知の責務は持たせない。窓内1件＝差分 `Money(0)` で正常送信 | ユーザー |
| 2026-06-21 | ユースケースの戻り値は domain 型（`Notification \| None`）。Lambda レスポンス整形は後続の `handler_notify` の責務 | ユーザー |
| 2026-06-21 | `Clock` を共有ポート `domain/clock.py` へ昇格（収集サブドメインからの位置づけを解消し、通知・将来 BFF と共有）。import 3箇所を機械的に付替。`SystemClock` は構造的実装のため無変更 | ユーザー |
| 2026-06-21 | ADR は作成しない（整形を domain に置く件は覆すコスト小・`CONTEXT.md` の `Notification` 定義で意図が伝わる＝シンプル優先） | ユーザー |
| 2026-06-21 | `Summary.profit_rate` は生比率（float）を保持。表示時の `*100`/桁整形は `render_summary` 側。拠出累計0のときは `profit_rate = 0.0` にガード | 実装者 |

---

## 作業再開ガイド

### 現在の状態
- **最終作業**: フェーズ2・3 完了（実装＋抽象テスト）。`task check` 全緑。ブランチ `feature/batch-notify-domain` 上。**未コミット・未 PR**
- **次のアクション**: 4.2 PR 作成（ユーザー指示があれば）。以降は後続タスク（concrete: Sheets read 実体 / 通知チャネル / handler_notify、container: notify Lambda CDK）

### 再開時の確認事項
1. 本ファイルの「設計（グリル合意）」「決定事項」を厳守（再設計しない）
2. `domain` は依存ゼロ（pydantic 不使用）を死守。ポートは接尾辞なし命名（`Notifier` / `AssetRepository`）
3. `Clock` 昇格は収集側の回帰に注意（`task check` で収集テストの緑を必ず確認）
4. 到達ラインは「抽象テスト・`task check` グリーン」。具象・handler・CDK・deploy は対象外
5. 集計＝`summarize`（domain）、整形＝`render_summary`（domain）、orchestration＝ユースケース、の責務境界を崩さない

### コンテキスト復元用コマンド
```bash
# ブランチ作成（base は main）
git switch -c feature/batch-notify-domain

# 設計確認
cat CONTEXT.md docs/progress/issue-16-domain.md docs/progress/issue-8.md
```
