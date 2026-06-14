#!/usr/bin/env sh
# pytest をラップする。テスト収集 0 件のとき pytest は exit code 5 を返すが、
# Phase 0 では実テストが無いため 5 を成功（0）として扱う。
# それ以外の非ゼロ終了コードはそのまま伝播させる。
uv run pytest "$@"
code=$?
if [ "$code" -eq 5 ]; then
  echo "scripts/pytest.sh: no tests collected (exit 5) — treated as success."
  exit 0
fi
exit "$code"
