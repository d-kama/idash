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
from typing import Annotated

from fastapi import Depends, FastAPI
from mangum import Mangum

from application.visualization import (
    GetVisualizationDataInputBoundary,
    GetVisualizationDataUseCase,
)
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


app = FastAPI(title="idash visualization BFF")


@app.get("/api/visualization", response_model=VisualizationResponse)
def get_visualization(
    use_case: Annotated[GetVisualizationDataInputBoundary, Depends(get_use_case)],
) -> VisualizationResponse:
    """全期間の可視化データ（summary + series）を返す。期間フィルタはフロント側で行う。"""
    return use_case.execute()


handler = Mangum(app)
