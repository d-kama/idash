# AWS Emulator による DuckDB S3 経路の統合テスト 実装計画

- PRD: [prd.md](./prd.md)

## フェーズ一覧
| # | フェーズ | 対応要件 | 想定変更量 |
|---|---|---|---|
| 1 | エミュレータの起動基盤と DuckDB 接続スパイク | R1（起動・停止部分）, 非機能要件 | ~100 行 |
| 2 | S3 接続上書きと統合テスト | R1, R2, R3, R4, R5, R6 | ~250 行 |

Phase 1 で、DuckDB がエミュレータの自己署名 CA 越しに S3 へ届くかを確かめる。Phase 2 の設定項目と後退策は
この結果で決まるので、Phase 1 を独立させて先に確かめる。

## Phase 1: エミュレータの起動基盤と DuckDB 接続スパイク
### Goal
`task emulator:up` / `task emulator:down` でエミュレータを起動・停止できる。DuckDB からエミュレータの S3 へ
Parquet を読み書きするのに必要な設定が分かっている。

### TaskList
- [x] AWS Emulator の Dockerfile を `tools/aws-emulator/Dockerfile` に置く。中身は公式ドキュメントのもので、
      rpm はバージョンを固定する。バージョンは GitHub releases で確かめ、固定理由をコメントに残す。
- [x] Taskfile に `emulator:up` / `emulator:down` を追加する。
  - up: イメージをビルドし、`127.0.0.1:9297` にだけ公開してコンテナを起動する。`--memory=2g` を付ける。
    `/__admin/health` が 200 を返すまで待つ。
  - down: コンテナを停止する。
- [x] 接続用の環境変数をまとめる仕組みを用意する（例: `scripts/` 配下の env ファイル）。
  - `AWS_ENDPOINT_URL` / `AWS_SHARED_CREDENTIALS_FILE` / `AWS_CONFIG_FILE` / `AWS_CA_BUNDLE` などを設定する。
  - 実際の AWS 認証情報（`AWS_ACCESS_KEY_ID` / `AWS_PROFILE` など）は unset する。
- [x] スパイク: 使い捨てのスクリプトで次を確かめ、結果を「Phase 1 の結果」節に書く。スクリプトは scratchpad に置き、
      コミットしない。
  - boto3 でバケットを作れる
  - DuckDB 1.5.4 の `CREATE SECRET (TYPE s3, PROVIDER credential_chain, ENDPOINT ..., URL_STYLE 'path')` で
    エミュレータの資格情報ファイルが読まれる
  - httpfs の `ca_cert_file` などで自己署名 CA を信頼させ、Parquet の COPY / read_parquet / glob が通る
  - region の扱い（エミュレータは us-east-1 を推奨）
  - 通らなかった場合: テストに限り証明書の検証を無効にする方法で通るか

### Verification
- [x] `task emulator:up` のあと、`curl --cacert ~/.aws/emulator/9297/ca.pem https://127.0.0.1:9297/__admin/health`
      が `ok` を返す。
- [x] 環境変数を読み込んだ状態で `aws sts get-caller-identity` を実行すると、Account が `000000000000` になる。
- [x] `task emulator:down` のあと、コンテナが残っていない（`docker ps` に出ない）。
- [x] DuckDB からエミュレータの S3 へ Parquet を書いて読み戻せた。その設定項目（エンドポイント・URL スタイル・
      CA・region）を「Phase 1 の結果」節に書いてある。
- [x] `task check` が従来どおり通る。

### Phase 1 の結果
検証環境: DuckDB 1.5.4 / エミュレータ v1.0.564（Apple Silicon・colima・aarch64 rpm）。

**起動基盤**
- rpm の版固定 URL は `LTS/aws-emulator-<version>-1-<arch>.rpm`。`<version>` は `1.0.564`（3 区切り）。
  `versions.json` には `1.0.564.1` と載るが、4 区切りを URL に入れると 403 になる。
- `task emulator:up` / `emulator:down` と `scripts/emulator.env.sh`（`source` して使う）を追加した。

**DuckDB → エミュレータ S3 に必要な設定（Phase 2 で `DuckDbConfig` に足すもの）**
- `s3_endpoint`（`127.0.0.1:9297`、スキームなし）と `s3_url_style`（`path`）: **必須**。
  `credential_chain` は `AWS_ENDPOINT_URL` を読まず、省くと endpoint が `s3.amazonaws.com` になり実 AWS 宛てになる。
  資格情報（key_id / secret / session_token）と region（`AWS_REGION`）は `AWS_SHARED_CREDENTIALS_FILE` /
  `AWS_CONFIG_FILE` から読まれた。
- `ca_cert_file`（`~/.aws/emulator/9297/ca.pem`）: **必須**。`AWS_CA_BUNDLE` は DuckDB に効かない。未設定だと PUT が
  `SSL peer certificate ... was not OK` で失敗する。接続時に `SET ca_cert_file = '...'` で渡すと、COPY / read_parquet / glob / 同一キー上書きが通った。
  `SET enable_server_cert_verification=false` は効かなかった（後退策にならない）。
- SECRET は `CREATE SECRET (TYPE s3, PROVIDER credential_chain, ENDPOINT '127.0.0.1:9297', URL_STYLE 'path')`。
  未設定のときは従来と同じ `CREATE SECRET (TYPE s3, PROVIDER credential_chain)`。
- region は `us-east-1` に統一する。静的キー + `ap-northeast-1` で試すと 403（署名の region 不一致）。
  `AWS_REGION` は env ファイルで設定済みなので、`DuckDbConfig` に region は足さない。
- 拡張は `SET extension_directory` した固定ディレクトリへ INSTALL すれば、LOAD のみの経路と同じ動きになる。

**Phase 2 への申し送り: `_exists` が S3 で未存在を検出できない**
- ワイルドカードなしの S3 パスに対する `glob('s3://b/missing.parquet')` は、未存在でもそのパス自身を 1 件返す。
  `_exists` が True になり、`read_parquet` が HTTP 404 で例外になる。ワイルドカード付き（`nope*.parquet`）は 0 件で正しい。
- したがって R2 の「未存在のとき空」と、初回 save（既存なし）は S3 で失敗する。本番でも初回の collect が同じ原因で
  落ちる可能性が高い。Phase 2 の統合テストが最初に落とすので、`_exists` の修正（例: 404 の `HTTPException` を未存在と扱う）を
  Phase 2 の TaskList に加える。
- 単体テストはローカルパスのみのため、これまで検出されなかった。

## Phase 2: S3 接続上書きと統合テスト
### Goal
`task test:emulator` の 1 コマンドで、エミュレータの起動から `DuckDbAssetRepository` の S3 統合テスト（R2 の 3 点）、
停止までが通る。通常の `task test` / `task check` は従来と変わらない。

### TaskList
- [ ] `DuckDbConfig` に S3 接続上書きのフィールドを追加する（`packages/infrastructure/src/infrastructure/duckdb_store.py`）。
  - 候補は `s3_endpoint` / `s3_url_style` / `ca_cert_file` で、どれも既定は None。実際に足すのは Phase 1 で必要と
    分かったものだけにする。
  - `_connect` は、設定されたときだけ `CREATE SECRET` にオプションを付ける。未設定なら従来と同じ SQL を使う。
  - 「本番では使わず、統合テスト用である」ことを docstring に書く。
- [x] `_exists` が S3 の未存在を検出できない問題を直す（Phase 1 の結果を参照）。Phase 1 のレビュー時に前倒しで修正済み。
      S3 は `read_parquet(...) LIMIT 0` を試し、`HTTPException` の 404 を未存在と判定する（`_exists_s3`）。
      エミュレータで、修正前は初回 save が 404 で落ち、修正後は空 / 初回 save / round-trip / upsert が通ることを確認した。
      統合テスト（下記）で回帰を防ぐ。
- [ ] 単体テストを追加する。上書きを設定しないとき、S3 用 SECRET の SQL が従来と同じになることを確かめる（R5）。
      SQL の組み立てを純粋関数に切り出すと、S3 なしで検証できる。
- [ ] pytest に `emulator` マーカーを登録する（ルートの `pyproject.toml`）。通常の実行では `-m "not emulator"`
      で除外する（R3）。
- [ ] 統合テストを `packages/infrastructure/tests/integration/test_duckdb_store_s3.py` などに追加する。
  - 接続情報の環境変数がなければ、モジュールごと skip する（R4）。
  - fixture でテストごとにユニークなバケットを boto3 で作り、location を `s3://<bucket>/assets.parquet` にする（R6）。
  - httpfs / aws 拡張は、ローカルの固定ディレクトリへ fixture で INSTALL する。初回だけネットワークが必要。
    そのディレクトリを `extension_directory` に渡す。本番が前提とする LOAD だけの経路と揃えるため。
  - 既存の `infrastructure/tests/conftest.py` は、AWS のダミー認証情報を autouse で入れている。これが
    エミュレータの資格情報を上書きしないように、統合テスト側で打ち消す。
  - 対象は R2 の 3 ケース: round-trip（負の損益を含む）、未存在のとき空、同じ基準日の冪等 upsert。
- [ ] Taskfile に `test:emulator` を追加する。手順は `emulator:up`、環境変数の読み込み、`uv run pytest -m emulator`、
      `emulator:down` の順。テストが失敗しても down は必ず実行する（R1）。
- [ ] CLAUDE.md の「よく使うコマンド」に `task test:emulator` と前提（colima / Docker の起動）を追記する。

### Verification
- [ ] colima を起動した状態で `task test:emulator` を実行すると、統合テスト 3 件が pass し、終了後にコンテナが残っていない。
- [ ] テストを 1 件わざと失敗させても、`task test:emulator` のあとにコンテナが残っていない。
- [ ] `task test:emulator` を続けて 2 回実行しても、2 回とも pass する（R6）。
- [ ] エミュレータを起動せずに `uv run pytest -m emulator` を実行すると、統合テストが skip になる（R4）。
- [ ] `task check` が通り、統合テストが収集・実行されていない（出力に emulator のテストが出ない）（R3）。
- [ ] 上書き未設定のときの SQL 単体テストが通る（R5）。既存の `test_duckdb_store.py` も変更なしで通る。
