# BFF（可視化 API）の Lambda コンテナイメージ。
#
# batch イメージ（apps/batch/Dockerfile）から chrome / selenium 起動経路を除いた縮小版。
# FastAPI + Mangum で `GET /api/visualization` を提供し、DuckDB + S3 単一 Parquet を
# 実行ロール認証で read する。CloudFront が `/api/*` を本 Lambda（API GW 経由）へ流す。
#
# ビルドコンテキストはモノレポルート（COPY packages/ + apps/bff/ のため）。共有 root の
# `.dockerignore` が apps/batch と apps/bff の両方を許可し、CDK 側の image asset `exclude`
# （bff は apps/batch を除外）でハッシュを batch と相互分離する（`<Dockerfile>.dockerignore`
# は CDK フィンガープリントで読まれないため使わない）。CDK は
# DockerImageCode.fromImageAsset(root, { file: 'apps/bff/Dockerfile' }) でビルドする。
#
# ※ idash-infrastructure 依存で selenium 等も venv に入るが、起動経路（bff.main）では
#   import しない（notify と同じ扱い。イメージ肥大は許容）。

FROM public.ecr.aws/lambda/python:3.13

# uv（依存解決ツール）を版ピンで導入（batch と同版。latest はビルド再現性を損なう）。
COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /bin/uv

# uv workspace を解決する。ルート pyproject.toml / uv.lock とワークスペースメンバー
# （packages/* + apps/bff）を COPY し、bff のみ（--no-dev / --frozen）で同期する。
# --no-editable: workspace パッケージを実体配置（Lambda で `No module named 'bff'` を防ぐ。
# 詳細は apps/batch/Dockerfile のコメント参照）。
WORKDIR /var/task
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/bff/ apps/bff/
RUN uv sync --package idash-bff --no-dev --frozen --no-editable

# DuckDB の httpfs/aws 拡張を固定ディレクトリへ事前 INSTALL する（S3 アクセスに必須）。
# 実行時は LOAD のみ（extensions.duckdb.org への外部 DL を排除）。DuckDbAssetRepository は
# BffSettings 経由で同一の extension_directory を受け取り LOAD を解決する。
RUN /var/task/.venv/bin/python -c "import duckdb; con = duckdb.connect(); con.execute(\"SET extension_directory='/opt/duckdb-extensions'\"); con.execute('INSTALL httpfs'); con.execute('INSTALL aws')"

# 同期した venv を Lambda ランタイムが import できるよう PATH / PYTHONPATH に通す。
ENV PATH="/var/task/.venv/bin:${PATH}"
ENV PYTHONPATH="/var/task/.venv/lib/python3.13/site-packages"

# Mangum ハンドラ（FastAPI app を Lambda イベントへアダプト）。
CMD ["bff.main.handler"]
