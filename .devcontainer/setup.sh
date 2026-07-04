#!/bin/bash
set -euo pipefail

# root ユーザーでマウントされる為、存在するディレクトリのみ権限を書き込み可能に上書き
for dir in "$HOME/.config" "$HOME/.claude"; do
  [ -d "$dir" ] && sudo chown -R "$(id -u):$(id -g)" "$dir"
done

# bashrc に追加
echo 'eval "$(mise activate bash)"' >> ~/.bashrc

mise trust && mise install
eval "$(mise activate bash)"

# devcontainer の postCreate は非対話（TTY 無し）で走る。pnpm はホスト側で作られた
# node_modules との構成差を検知すると再作成のため削除確認を求めるが、TTY 無しだと
# ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY で中断する。CI=true で確認をスキップさせる。
CI=true task setup

# git が SSH 形式の URL を HTTPS にリダイレクトするよう設定
git config --global --add url."https://github.com/".insteadOf "git@github.com:"
git config --global --add url."https://github.com/".insteadOf "ssh://git@github.com/"

cat <<'EOF'
============================================================
DevContainer セットアップ完了

初回のみ Fine-grained PAT で GitHub 認証を行ってください:

  1. GitHub Web で Fine-grained PAT を発行
     - Repository access: d-kama/idash のみ
     - Permissions: Contents (R/W), Pull requests (R/W), Issues (R/W), Metadata (R)
                    必要に応じて Workflows (R/W)
     - Expiration: 90 日推奨

  2. コンテナ内で認証
     gh auth login -h github.com -p https --with-token
       → プロンプトに PAT を貼り付け → Ctrl+D
     gh auth setup-git

認証情報は named volume (idash-gh-config) に保存されるため、
次回以降のコンテナ再作成では再ログイン不要です。
PAT 期限切れ時は再発行して同じコマンドで上書き認証してください。
============================================================
EOF
