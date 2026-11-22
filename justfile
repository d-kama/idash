# 横断タスクを just に集約する。個別言語ツールを直接叩く必要は基本ない。

# レシピ本体の `#` 行をシェルへ渡さない。渡すと意図コメントがコマンドとしてエコーされ、実行ログに混ざる。
set ignore-comments

# AWS Emulator の公開ポート。scripts/emulator.env.sh の接続先と揃える。
emulator_port := "9297"
emulator_container := "idash-aws-emulator"

[private]
default:
    @{{ just_executable() }} --list --unsorted

# 依存解決（Python uv + TS pnpm）
setup:
    uv sync
    pnpm install

# CI 用の依存解決（frozen install。古い lockfile を検知して落とす）
setup-ci:
    uv sync --frozen
    pnpm install --frozen-lockfile

# Lint（Python: ruff / TS: Biome）
lint:
    uv run ruff check .
    pnpm exec biome lint .

# フォーマット自動修正（書き込み・ローカル整形。Python: ruff format / TS: Biome）
format:
    uv run ruff format .
    pnpm exec biome format --write .

# Pydantic → OpenAPI → TS 型を生成（生成物は非コミット。frontend が import）
gen-types:
    # export_openapi は bff.main を import して app.openapi() を出力するだけ（DB/env 不要）。
    uv run python -m bff.export_openapi > apps/frontend/openapi.json
    # --filter で frontend ディレクトリ基準に実行（openapi.json / 出力先とも相対）。
    pnpm --filter @idash/frontend exec openapi-typescript openapi.json -o src/api/generated/schema.d.ts

# 型チェック（Python: ty / TS: tsc）
typecheck: gen-types
    # frontend の tsc は生成型（schema.d.ts）に依存するため先に生成する（非コミットのため
    # クリーン環境でも通す）。Python 側の ty は生成型に依存しないが、まとめて gen-types 後に走らせる。
    uv run ty check
    pnpm -r run typecheck

# テスト（pytest + infra/frontend Vitest）
test:
    uv run pytest
    pnpm --filter @idash/infra test
    pnpm --filter @idash/frontend test

# AWS Emulator をビルドして起動（127.0.0.1 のみ公開。health が ok になるまで待つ）
[script("bash")]
emulator-up:
    set -euo pipefail
    # rpm は arch 別。Apple Silicon の `uname -m` は arm64 なので aarch64 へ読み替える。
    case "$(uname -m)" in arm64|aarch64) rpm_arch=aarch64 ;; *) rpm_arch=x86_64 ;; esac
    # Linux はマウント先がホストの uid 所有のため、イメージ既定の uid 1000 では書き込めない場合がある
    # （公式ドキュメントも Linux では --user 指定を求める）。macOS（colima）は uid を読み替えるので不要。
    user_opt=()
    if [ "$(uname -s)" = Linux ]; then user_opt=(--user "$(id -u):$(id -g)"); fi
    docker build -t aws-emulator --build-arg RPM_ARCH="$rpm_arch" tools/aws-emulator
    # 共有ディレクトリを先に作らないと、Linux では Docker が root 所有で作り SDK が読めなくなる。
    mkdir -p "$HOME/.aws/emulator"
    # 前回の残骸（同名コンテナ）があれば消す。
    docker rm -f {{ emulator_container }} >/dev/null 2>&1 || true
    # 2g 固定（swap なし）。超過すると 137 で落ち、状態も失われる。ポートは必ず 127.0.0.1 に限定する。
    docker run -d --rm --name {{ emulator_container }} ${user_opt[@]+"${user_opt[@]}"} \
      --memory=2g --memory-swap=2g \
      -p 127.0.0.1:{{ emulator_port }}:{{ emulator_port }} \
      -e HOME="$HOME" -v "$HOME/.aws/emulator:$HOME/.aws/emulator" \
      aws-emulator -p {{ emulator_port }}
    for _ in $(seq 30); do
      if curl -sf --cacert "$HOME/.aws/emulator/{{ emulator_port }}/ca.pem" \
          https://127.0.0.1:{{ emulator_port }}/__admin/health; then
        echo
        exit 0
      fi
      sleep 1
    done
    echo "emulator が 30 秒以内に ready にならなかった" >&2
    docker logs {{ emulator_container }} >&2 || true
    exit 1

# AWS Emulator を停止（--rm 付きなのでコンテナも消える）
emulator-down:
    docker rm -f {{ emulator_container }} >/dev/null 2>&1 || true

# S3 統合テスト（AWS Emulator を起動して pytest -m emulator → 停止。要 colima / Docker）
[script("bash")]
test-emulator:
    # up が途中で失敗しても、テストが失敗しても down を必ず実行し、元の終了コードを返す。
    # そのため -e は付けない（付けると失敗時点で抜けて down が走らない）。
    rc=0
    {{ just_executable() }} emulator-up && {
      . scripts/emulator.env.sh
      uv run pytest -m emulator --no-cov
    } || rc=$?
    {{ just_executable() }} emulator-down
    exit $rc

# フロントエンドをビルド（生成型で tsc + vite build。IdashFrontendStack の dist 元）
build-front: gen-types
    pnpm --filter @idash/frontend run build

# CDK synth（CloudFormation テンプレート生成。AWS 認証不要）
synth: build-front
    # IdashFrontendStack の Source.asset('apps/frontend/dist') が synth 時に dist を要求する。
    pnpm --filter @idash/infra exec cdk synth

# /api/visualization を http://localhost:8000 で提供する。
[doc("BFF をローカル起動（uvicorn。既定は data/assets.parquet。引数か DATA_LOCATION で上書き）")]
bff data_location=env("DATA_LOCATION", "data/assets.parquet"):
    ENV_NAME=local DATA_LOCATION={{ quote(data_location) }} uv run uvicorn bff.main:app --reload --port 8000

# フロントエンドをローカル起動（vite dev。/api は just bff へプロキシ）
front:
    pnpm --filter @idash/frontend exec vite

# CDK デプロイ（要 AWS 認証。build-front 後に全スタックを配備）
deploy: build-front
    pnpm --filter @idash/infra exec cdk deploy --all --require-approval never

# CI と同じ検証（書き換えなし）: lint + フォーマット検証 + typecheck + test
check: && typecheck test
    # `&&` 以降は本体の後に走る依存。静的検証を先に済ませ、重い型生成・テストは後に回す。
    # Python: Lint
    uv run ruff check .
    # Python: フォーマット検証
    uv run ruff format --check .
    # TS: Lint + フォーマット + import 整列 を一括検証（CI 専用コマンド）
    pnpm exec biome ci .
