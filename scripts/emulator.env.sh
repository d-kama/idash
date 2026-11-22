# AWS Emulator へ SDK / CLI / DuckDB を向ける環境変数。`source scripts/emulator.env.sh` で読み込む。
# `just emulator-up` の後に使う。認証情報とCAは起動ごとに ~/.aws/emulator/<port>/ へ生成される。

_emu_port="${EMULATOR_PORT:-9297}"
_emu_dir="$HOME/.aws/emulator/${_emu_port}"

# 環境変数は認証情報ファイルより優先される。実 AWS の資格情報が残ると、
# エミュレータに拒否されるか、ENDPOINT 未設定の経路で実 AWS を叩くため必ず消す。
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE

# S3 は IP エンドポイントだとパス形式になる。`localhost` にするとバケット名がホスト名に入り届かない。
export AWS_ENDPOINT_URL="https://127.0.0.1:${_emu_port}"
export AWS_SHARED_CREDENTIALS_FILE="${_emu_dir}/emulator_credentials"
export AWS_CONFIG_FILE="${_emu_dir}/config"
export AWS_CA_BUNDLE="${_emu_dir}/ca.pem"
export AWS_EC2_METADATA_DISABLED=true
export AWS_DISABLE_HOST_PREFIX_INJECTION=true
# エミュレータは region を1つに統一して扱う。us-east-1 が推奨。
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1

unset _emu_port _emu_dir
