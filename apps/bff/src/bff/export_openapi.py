"""FastAPI アプリの OpenAPI スキーマを stdout へ出力する（`gen-types` タスクが使用）。

Pydantic → OpenAPI → TS 型の一方向パイプラインの起点。生成物（openapi.json / TS 型）は
コミットせず、`task gen-types` が実行時に生成する（Pydantic を単一の真実源に保つ）。
"""

from __future__ import annotations

import json

from bff.main import app


def main() -> None:
    print(json.dumps(app.openapi()))


if __name__ == "__main__":
    main()
