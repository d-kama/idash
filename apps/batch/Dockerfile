# データ収集バッチ（collect）の Lambda コンテナイメージ。
#
# ADR-0003: Selenium + 版ピン chromium/chromedriver を同梱する。版不整合起因の
# InvalidSessionId / NoSuchElement を構造的に避けるため、Chrome for Testing(CfT)
# から chrome-headless-shell と一致版の chromedriver を直接ダウンロードして同梱する
# （OS パッケージの dnf には頼らず自前でピンする）。
#
# 配置先は handler_collect.py の既定パス（CHROME_BINARY_LOCATION /
# CHROME_DRIVER_PATH の既定値）に一致させ、env 上書き不要にする:
#   /opt/chrome/chrome
#   /opt/chromedriver/chromedriver
#
# ビルドコンテキストはモノレポルート（COPY packages/ のため）。CDK は
# DockerImageCode.fromImageAsset(root, { file: 'apps/batch/Dockerfile', cmd }) で
# このイメージをビルドし、関数ごとに CMD を上書きする。

# ---------------------------------------------------------------------------
# stage 1: CfT chrome-headless-shell + chromedriver をダウンロードして配置する。
# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:3.13 AS chrome

# CfT のピン版。直近 stable を選定（chrome-headless-shell と chromedriver は
# 同一ビルド番号で一致させる＝ADR-0003 の版ピン）。
# TODO(フェーズ4.3/4.4): 実サイト検証・実デプロイ時に直近 stable へ調整可。
# 版一覧: https://googlechromelabs.github.io/chrome-for-testing/
ARG CFT_VERSION=131.0.6778.108

RUN dnf install -y unzip && \
    curl -fsSL -o /tmp/chrome-headless-shell.zip \
      "https://storage.googleapis.com/chrome-for-testing-public/${CFT_VERSION}/linux64/chrome-headless-shell-linux64.zip" && \
    curl -fsSL -o /tmp/chromedriver.zip \
      "https://storage.googleapis.com/chrome-for-testing-public/${CFT_VERSION}/linux64/chromedriver-linux64.zip" && \
    unzip -q /tmp/chrome-headless-shell.zip -d /tmp && \
    unzip -q /tmp/chromedriver.zip -d /tmp && \
    mkdir -p /opt/chrome /opt/chromedriver && \
    cp /tmp/chrome-headless-shell-linux64/chrome-headless-shell /opt/chrome/chrome && \
    cp -r /tmp/chrome-headless-shell-linux64/. /opt/chrome/ && \
    cp /tmp/chromedriver-linux64/chromedriver /opt/chromedriver/chromedriver && \
    chmod +x /opt/chrome/chrome /opt/chromedriver/chromedriver && \
    rm -rf /tmp/chrome-headless-shell.zip /tmp/chromedriver.zip \
           /tmp/chrome-headless-shell-linux64 /tmp/chromedriver-linux64

# ---------------------------------------------------------------------------
# stage 2: 実行イメージ。chrome 共有ライブラリ + Python 依存 + アプリを載せる。
# ---------------------------------------------------------------------------
FROM public.ecr.aws/lambda/python:3.13

# Chrome(headless-shell) が要求する共有ライブラリ群。dnf で導入する
# （chrome バイナリそのものは CfT 版ピンを使い、共有ライブラリのみ OS から供給）。
RUN dnf install -y \
      nss \
      nss-util \
      nspr \
      atk \
      at-spi2-atk \
      at-spi2-core \
      cups-libs \
      libdrm \
      mesa-libgbm \
      libxkbcommon \
      libX11 \
      libXcomposite \
      libXdamage \
      libXext \
      libXfixes \
      libXrandr \
      libxcb \
      libxshmfence \
      alsa-lib \
      pango \
      cairo \
      expat \
      dbus-libs && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# CfT chrome / chromedriver を stage 1 から取り込む（handler 既定パスに配置）。
COPY --from=chrome /opt/chrome /opt/chrome
COPY --from=chrome /opt/chromedriver /opt/chromedriver

# uv（依存解決ツール）を導入。
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# uv workspace を解決する。ルート pyproject.toml / uv.lock とワークスペースメンバー
# （packages/* + apps/batch）を COPY し、batch のみ（--no-dev / --frozen）で同期する。
# batch → infrastructure 依存で selenium / gspread / bs4 / lxml / boto3 が入る。
WORKDIR /var/task
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/batch/ apps/batch/
RUN uv sync --package idash-batch --no-dev --frozen

# 同期した venv を Lambda ランタイムが import できるよう PATH / PYTHONPATH に通す。
ENV PATH="/var/task/.venv/bin:${PATH}"
ENV PYTHONPATH="/var/task/.venv/lib/python3.13/site-packages"

# 既定 CMD（収集）。CDK 側で関数ごとに上書きする。
CMD ["batch.handler_collect.handler"]
