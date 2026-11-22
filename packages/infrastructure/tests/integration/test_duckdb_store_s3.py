"""DuckDbAssetRepository の S3 経路を AWS Emulator に対して検証する統合テスト。

`just test-emulator` で起動・環境変数の読み込み・停止まで行う。エミュレータの接続情報がなければ
モジュールごと skip する。

実 AWS へは絶対に向けない。fixture はダミーキーを消すため、接続先を誤ると `~/.aws/credentials` の
実認証情報で実 S3 にバケットを作成・削除しうる。そこで接続先はループバックの HTTPS に限り、
DuckDB と boto3 の両方へ同じ値を明示して渡す（boto3 は `AWS_ENDPOINT_URL_S3` を
`AWS_ENDPOINT_URL` より優先するため、環境変数任せだと両者の接続先がずれうる）。
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import boto3
import duckdb
import pytest

from domain.asset import Money, PortfolioAsset, ProductAsset
from infrastructure.duckdb_store import DuckDbAssetRepository, DuckDbConfig

# エミュレータは 127.0.0.1 にのみ公開する。これ以外のホストは実 AWS やプロキシの可能性がある。
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _emulator_endpoint_url() -> str | None:
    """ループバックの HTTPS エンドポイントのときだけ `AWS_ENDPOINT_URL` を返す。"""
    url = os.environ.get("AWS_ENDPOINT_URL")
    if not url or not os.environ.get("AWS_CA_BUNDLE"):
        return None
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in _LOOPBACK_HOSTS:
        return None
    return url


pytestmark = [
    pytest.mark.emulator,
    pytest.mark.skipif(
        _emulator_endpoint_url() is None,
        reason="AWS Emulator のループバック接続情報がない（just test-emulator で実行する）",
    ),
]


@pytest.fixture(scope="session")
def endpoint_url() -> str:
    url = _emulator_endpoint_url()
    assert url is not None  # skipif で保証済み
    return url


# 本番が前提とする「事前 INSTALL 済み拡張を LOAD のみ」の経路に揃えるための固定ディレクトリ。
_EXTENSION_DIR = Path.home() / ".cache" / "idash-test" / "duckdb-extensions"

ASSET = PortfolioAsset(
    base_date=date(2026, 6, 18),
    products=(
        ProductAsset(
            name="ファンドA",
            contribution=Money(100_000),
            profit_loss=Money(20_000),
            valuation=Money(120_000),
        ),
        ProductAsset(
            name="ファンドB",
            contribution=Money(50_000),
            profit_loss=Money(-8_000),
            valuation=Money(42_000),
        ),
    ),
)


@pytest.fixture(autouse=True)
def _emulator_credentials(_aws_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest の autouse がダミーのキーを環境変数に入れる。環境変数は資格情報ファイルより
    # 優先されるため、打ち消してエミュレータの資格情報ファイルを読ませる。
    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    monkeypatch.setenv("AWS_DEFAULT_REGION", os.environ["AWS_REGION"])


@pytest.fixture(scope="session")
def extension_directory() -> str:
    _EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute(f"SET extension_directory = '{_EXTENSION_DIR}'")
        # 初回のみネットワークが必要（導入済みなら何もしない）。
        con.execute("INSTALL httpfs")
        con.execute("INSTALL aws")
    finally:
        con.close()
    return str(_EXTENSION_DIR)


@pytest.fixture
def bucket(endpoint_url: str) -> Iterator[str]:
    # テストごとにユニークなバケットを使い、再実行や他テストと干渉させない。
    name = f"idash-test-{uuid.uuid4().hex[:12]}"
    s3 = boto3.client("s3", endpoint_url=endpoint_url, verify=os.environ["AWS_CA_BUNDLE"])
    s3.create_bucket(Bucket=name)
    yield name
    for obj in s3.list_objects_v2(Bucket=name).get("Contents", []):
        s3.delete_object(Bucket=name, Key=obj["Key"])
    s3.delete_bucket(Bucket=name)


@pytest.fixture
def repo(bucket: str, extension_directory: str, endpoint_url: str) -> DuckDbAssetRepository:
    return DuckDbAssetRepository(
        DuckDbConfig(
            location=f"s3://{bucket}/assets.parquet",
            extension_directory=extension_directory,
            # DuckDB の ENDPOINT はスキームなしの host:port。
            s3_endpoint=urlsplit(endpoint_url).netloc,
            s3_url_style="path",
            ca_cert_file=os.environ["AWS_CA_BUNDLE"],
        )
    )


def test_round_trip_including_negative(repo: DuckDbAssetRepository) -> None:
    repo.save(ASSET)

    assert repo.find_all() == [ASSET]


def test_find_returns_empty_when_object_not_exists(repo: DuckDbAssetRepository) -> None:
    # 回帰防止: S3 の glob は未存在でも 1 件返すため、_exists が 404 を未存在と扱う必要がある。
    assert repo.find_all() == []


def test_save_same_base_date_is_idempotent_upsert(repo: DuckDbAssetRepository) -> None:
    updated = PortfolioAsset(
        base_date=ASSET.base_date,
        products=(
            ProductAsset(
                name="ファンドA",
                contribution=Money(110_000),
                profit_loss=Money(30_000),
                valuation=Money(140_000),
            ),
        ),
    )

    repo.save(ASSET)  # 初回 save（既存なし）も通る
    repo.save(updated)

    assert repo.find_all() == [updated]
