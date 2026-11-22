# タスクランナーを go-task から Just へ移行する 実装計画

## 概要
横断タスクの実行基盤を go-task（`Taskfile.yml`）から Just（`justfile`）へ置き換える。YAML と Go テンプレートの
二重の書式をやめ、シェルに近い書き方とレシピ引数でタスクを読み書きしやすくするのが目的。移行前に得失を整理し、
判断を ADR に残す。

## 要件
- **R1**: `mise install` で just が導入され、`just --list` で全レシピが説明付きで一覧できる。
- **R2**: 現行の全タスク（setup / setup:ci / lint / format / gen-types / typecheck / test / emulator:up /
  emulator:down / test:emulator / build-front / synth / bff / front / deploy / check）と同じ処理・同じ依存順・
  同じ終了コードの振る舞いを just のレシピで実行できる。
- **R3**: `test:emulator` 相当のレシピは、起動やテストが失敗してもエミュレータを必ず停止し、元の終了コードを返す。
- **R4**: CI（check / deploy ジョブ）、composite action、devcontainer が just で動き、go-task に依存しない。
- **R5**: リポジトリから go-task への依存（`Taskfile.yml`、`mise.toml` の `task`、ドキュメント・コメント中の
  `task xxx`）がなくなる。ただし過去の決定記録（既存 ADR・PROJECT_PLAN の完了済みチェックリスト・過去の計画書）は
  当時の記録として書き換えない。
- **R6**: go-task から Just へ移行するメリット・デメリットと判断理由が ADR に記録されている。

## メリット・デメリットの整理（移行判断の材料）

このリポジトリの Taskfile が実際に使っている機能に照らして評価する。

### メリット
- **書式が 1 つで済む**: 現行は YAML の中に Go テンプレート（`{{.PORT}}`）とシェルが混ざり、`desc` にコロンを
  含めるとクォートが要るなど、YAML 側の都合に気を遣う。just はシェルに近い 1 書式で、変数展開も `{{PORT}}` だけ。
- **レシピ引数が素直に書ける**: `task bff` の `DATA_LOCATION` は env + テンプレートの `default` で表現している。
  just ならレシピ引数のデフォルト値（`bff data_location="data/assets.parquet"`）で書け、`just --list` にも出る。
- **複数行スクリプトを自然に書ける**: `emulator:up` の待機ループや `test:emulator` の終了コード保持は、YAML の
  ブロック文字列に埋め込んでいる。just は shebang / `[script]` レシピで `set -euo pipefail` 付きの普通の
  シェルスクリプトとして書ける。
- **一覧と確認がしやすい**: 既定レシピを `just --list` にでき、`--dry-run` / `--show` で実行内容を事前に確認できる。

### デメリット・リスク
- **タスク名にコロンを使えない**: `setup:ci` / `emulator:up` / `emulator:down` / `test:emulator` は改名が要る
  （ケバブケースにする。`mod` による名前空間化は 4 個のために導入するほどではない）。CI・ドキュメント・手癖の
  更新コストがかかる。
- **依存の並列実行が既定ではない**: go-task の `deps` は並列、just の依存は直列。現行は各タスクの依存が 1 個
  だけなので実害はない。
- **ファイル差分による実行スキップ（`sources` / `generates`）がない**: 現行の Taskfile は使っていないので影響なし。
  将来 gen-types などを差分ビルドにしたくなったら自前で書く必要がある。
- **トップレベルのバッククォート変数は毎回評価される**: `RPM_ARCH` / `USER_OPT` をトップレベル変数にすると、
  関係ないレシピの実行時にもシェルが走る。レシピ内で計算して回避する。
- **レシピ本体の `#` 行はシェルへ渡され、エコーされる**: 現行のように行ごとに意図コメントを書くと出力が汚れる。
  `set ignore-comments := true` を使う。
- **サブタスク呼び出しの書き方が変わる**: `check` 内の `task: typecheck` は、just では依存として宣言する。
  依存は 1 回の実行内で重複実行されないので、`check` → `typecheck` → `gen-types` の流れは保てる。

### 判断
メリットは日々の読み書きのしやすさで、デメリットの多くは現行が使っていない機能か回避策が明確なもの。実質的な
コストはタスク名の改名と参照箇所の更新に限られるため、移行する。なお mise 自身のタスク機能（mise tasks）も
候補になるが、ツール版管理とタスク定義が 1 ファイルに密結合する点を避け、専用ランナーである just を選ぶ。

### タスク名の対応
| go-task | just |
|---|---|
| `setup:ci` | `setup-ci` |
| `emulator:up` | `emulator-up` |
| `emulator:down` | `emulator-down` |
| `test:emulator` | `test-emulator` |
| 上記以外 | 同名 |

## フェーズ一覧
| # | フェーズ | 対応要件 | 想定変更量 |
|---|---|---|---|
| 1 | justfile を Taskfile と並存させて等価性を確かめる | R1, R2, R3 | ~180 行 |
| 2 | 参照を just へ切り替え、go-task を撤去する | R4, R5, R6 | ~250 行（うち機械的な置換 ~150 行、スナップショット更新を含む可能性あり） |

フェーズ 1 で justfile 単体の正しさを確かめ、Taskfile を残したまま比較できる状態にする。CI やドキュメントの切替は
justfile が正しく動くことを前提にするため、フェーズ 2 に分ける。

## Phase 1: justfile を Taskfile と並存させて等価性を確かめる
### Goal
`just <レシピ>` で現行の全タスクと同じ処理を実行でき、`just check` / `just synth` が `task check` / `task synth`
と同じ結果になる。CI はまだ go-task のまま動く。

### TaskList
- [x] `mise.toml` に `just` を追加する。版は固定し、固定理由（`[script]` などの利用機能が版に依存する）をコメントに残す。
- [x] ルートに `justfile` を作る。
  - [x] `set ignore-comments := true`（必要なら `set shell` / `set positional-arguments` も）を設定し、既定レシピを `just --list` にする。
  - [x] 各タスクの `desc` をレシピ直上の doc コメントへ移す。Taskfile の意図コメント（なぜその順序・オプションか）も残す。
  - [x] setup / setup-ci / lint / format / gen-types / typecheck / test / build-front / synth / front / deploy / check を移す。依存（typecheck・build-front → gen-types、synth・deploy → build-front、check → typecheck・test）を宣言する。
  - [x] bff: `DATA_LOCATION` をデフォルト値付きのレシピ引数にし、`ENV_NAME=local` と合わせて export する。環境変数 `DATA_LOCATION` での上書きも従来どおり効くようにする。
  - [x] emulator-up: `RPM_ARCH` / `USER_OPT` をレシピ内で計算する shebang（または `[script]`）レシピにする。health 待機ループもそのまま移す。
  - [x] emulator-down を移す。
  - [x] test-emulator: `set -u` 下で終了コードを保持し、失敗時も `emulator-down` を必ず実行するスクリプトレシピにする。
- [x] `task --list` と `just --list` を突き合わせ、移し漏れがないことを確かめる。

### Verification
- [x] `mise install` 後に `just --version` が固定した版を返す。
- [x] `just`（引数なし）で全 16 レシピが説明付きで一覧される。
- [x] `just check` と `just synth` が成功する（`task check` / `task synth` と同じく緑）。
- [x] `just --dry-run check` の実行順が lint → format 検証 → biome ci → gen-types → typecheck → test になっている。
- [x] `just test-emulator` が成功し、終了後に `docker ps` に `idash-aws-emulator` が残っていない。
- [x] Docker を止めた状態で `just test-emulator` が非 0 で終わり、`emulator-down` が実行されている。
- [x] `just bff` が `data/assets.parquet` を既定に起動し、`just bff other.parquet` と `DATA_LOCATION=other.parquet just bff` で上書きできる（起動ログまたは `--dry-run` で確認）。
- [x] `just setup-ci` が frozen install で成功する。

## Phase 2: 参照を just へ切り替え、go-task を撤去する
### Goal
CI・devcontainer・ドキュメントが just だけで成り立ち、リポジトリから go-task への依存がなくなっている。判断が
ADR-0008 に記録されている。

### TaskList
- [x] CI を切り替える: `.github/workflows/cicd.yml` の `task check` / `task synth` / `task deploy`、`.github/actions/setup/action.yml` の `task setup:ci` と説明文。
- [x] `.devcontainer/setup.sh` の `CI=true task setup` を just に替える。
- [x] `Taskfile.yml` を削除し、`mise.toml` から `task` を外す。
- [x] ドキュメントを更新する: `README.md`（前提ツール・セットアップ・タスク一覧）、`CLAUDE.md`（ツールチェーン・よく使うコマンド・CI/CD）、`PROJECT_PLAN.md`（技術選定表・ディレクトリ構成・§6 横断タスク）。完了済みチェックリストと既存 ADR・過去の計画書は書き換えない。
- [x] コード・設定中のコメントを更新する: `.gitignore`、`pyproject.toml`、`scripts/emulator.env.sh`、`tools/aws-emulator/Dockerfile`、`infra/lib/frontend-stack.ts`、`apps/bff/src/bff/{main,export_openapi}.py`、`packages/common/src/common/settings.py`、`packages/infrastructure/tests/integration/test_duckdb_store_s3.py`（skip 理由の文言を含む）、`apps/frontend/{vite.config.ts,src/api/types.ts}`。
- [x] `packages/` / `apps/` 配下のコメント変更でコンテナイメージのハッシュが変わるため、`pnpm --filter @idash/infra test` を確かめ、差分がイメージハッシュだけなら `run test:update` で更新する。
- [x] `docs/adr/0008-task-runner-just.md` を書く。上記「メリット・デメリットの整理」を Considered Options（go-task 継続 / mise tasks / Make）と Consequences の形にまとめる。

### Verification
- [x] `git grep -nE '\btask (setup|check|lint|format|typecheck|test|synth|deploy|bff|front|gen-types|build-front|emulator)|Taskfile|go-task'` の結果が、既存 ADR・PROJECT_PLAN の完了済み項目・過去の計画書・ADR-0008 だけになっている。
- [x] `mise.toml` に `task` がなく、`Taskfile.yml` が存在しない。
- [x] `just check` と `just synth` が成功する（infra スナップショット更新後も緑）。
- [ ] PR の CI（check ジョブ）が just で緑になる。deploy ジョブはマージ後の main push で成功を確かめる。（未 push のため未確認）
- [x] `docs/adr/0008-task-runner-just.md` にメリット・デメリットと判断理由が書かれている。

## 発見事項
- just 1.59.0 に固定した（mise の最新）。`[script("bash")]` は 1.59.0 で unstable 指定なしに使える。
- doc コメントとして `just --list` に出るのはレシピ直前の 1 行だけだった。複数行の意図コメントをレシピ上に置くと
  最終行が説明に出てしまうため、意図コメントはレシピ本体へ移した（`set ignore-comments` で実行時は無視される）。
  `bff` は引数がある分 `--list` の表示が崩れるので `[doc(...)]` で説明を明示した。
- `just --fmt` の正規形に合わせ、`set ignore-comments := true` は `set ignore-comments` と書いた。
- `check` は本体の後に走る依存（`check: && typecheck test`）にして、Taskfile と同じ「静的検証 → gen-types →
  typecheck → test」の順を保った（`just --dry-run check` で確認）。
- `test-emulator` の失敗パスは、Docker を止める代わりに `DOCKER_HOST` を存在しないソケットに向けて確かめた。
  `emulator-up` が失敗しても `emulator-down` が走り、終了コード 1 で終わった。
- コメント変更で batch / bff のイメージハッシュが変わり、infra スナップショットはその 3 行だけが変わった。
- README のレシピ表には、従来どおりエミュレータ系（emulator-up / emulator-down / test-emulator）を載せていない。
- 手元で `just` を使うには、`mise install` 後にシェルの mise activate を再読込する必要がある（PATH に載るため）。
