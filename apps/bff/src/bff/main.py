"""可視化 BFF の FastAPI アプリ（composition root 兼エントリポイント）。

環境変数（`DATA_LOCATION`）から設定を読み、DuckDbAssetRepository を構築して
GetVisualizationDataUseCase に DI する。データストアは DuckDB + S3 単一 Parquet（実行ロール
認証・静的キーなし）。`/api` 接頭辞は CloudFront が `/api/*` を BFF へパススルーする配線に
合わせる。Lambda 実行は `handler = Mangum(app)`。

具象の構築はコールドスタート時1回だけ（`functools.cache`）で、以降のリクエストは同一
リポジトリを共有する。DuckDB の拡張同梱先 / スピル先 / メモリ上限は notify ハンドラと同値。
テストは `app.dependency_overrides[get_use_case]` でフェイクを注入する。
"""

from __future__ import annotations

from functools import cache
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from mangum import Mangum

from application.visualization import (
    GetVisualizationDataInputBoundary,
    GetVisualizationDataUseCase,
)
from common import ssm
from common.settings import BffSettings
from infrastructure.duckdb_store import DuckDbAssetRepository, DuckDbConfig
from schemas.visualization import VisualizationResponse

# DuckDB の拡張同梱先（Dockerfile の事前 INSTALL 先）と肥大時スピル先（notify と同値）。
_DUCKDB_EXTENSION_DIR = "/opt/duckdb-extensions"
_DUCKDB_TEMP_DIR = "/tmp"  # noqa: S108 -- Lambda の書き込み可能領域（スピル用）
_DUCKDB_MEMORY_LIMIT = "256MB"  # read のみで軽量。スピル併用で OOM を避ける保険値


@cache
def _build_use_case() -> GetVisualizationDataUseCase:
    """env から具象を組み立てて use case を返す（コールドスタート時1回・以降キャッシュ）。"""
    settings = BffSettings.from_env()
    repository = DuckDbAssetRepository(
        DuckDbConfig(
            location=settings.data_location,
            memory_limit=_DUCKDB_MEMORY_LIMIT,
            temp_directory=_DUCKDB_TEMP_DIR,
            extension_directory=_DUCKDB_EXTENSION_DIR,
        )
    )
    return GetVisualizationDataUseCase(repository)


def get_use_case() -> GetVisualizationDataInputBoundary:
    """FastAPI 依存。テストは dependency_overrides でフェイクへ差し替える。"""
    return _build_use_case()


@cache
def get_origin_secret() -> str | None:
    """origin-verify の期待値（SSM SecureString）を返す。未設定なら None（検証無効）。

    CloudFront 経由限定化（ADR-0006）。CloudFront Function が正規リクエストにのみ注入する
    `x-origin-verify` を照合する。ローカル `task bff` 等 `ORIGIN_VERIFY_PARAM_ARN` 未設定では
    None を返し検証しない。コールドスタート時に1回だけ SSM を引く（`functools.cache`）。
    """
    settings = BffSettings.from_env()
    if settings.origin_verify_param is None:
        return None
    return ssm.get_secure_string(settings.origin_verify_param)


def verify_origin(
    x_origin_verify: Annotated[str | None, Header()] = None,
    expected: Annotated[str | None, Depends(get_origin_secret)] = None,
) -> None:
    """CloudFront が注入する `x-origin-verify` を照合し、不一致/欠落なら 403。

    `expected` が None（未配線/ローカル）なら検証しない。API Gateway を直叩きした相手は秘密値を
    知らず弾かれる（CloudFront は迂回できない）。テストは get_origin_secret を override する。
    """
    if expected is None:
        return
    # 秘密値の比較はタイミング攻撃耐性のある定数時間比較で行う。
    if x_origin_verify is None or not compare_digest(x_origin_verify, expected):
        raise HTTPException(status_code=403, detail="forbidden")


app = FastAPI(title="idash visualization BFF")


@app.get(
    "/api/visualization",
    response_model=VisualizationResponse,
    dependencies=[Depends(verify_origin)],
)
def get_visualization(
    use_case: Annotated[GetVisualizationDataInputBoundary, Depends(get_use_case)],
) -> VisualizationResponse:
    """全期間の可視化データ（summary + series）を返す。期間フィルタはフロント側で行う。"""
    return use_case.execute()


handler = Mangum(app)
