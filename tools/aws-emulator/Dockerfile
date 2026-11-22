# AWS Emulator のローカル実行イメージ（公式の配布イメージはないため自前でビルドする）。
# 元は公式ドキュメント getting-started-docker のもの。`latest` ではなく版を固定している。
FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal

# 頻繁に更新されるため、ある日突然テストが壊れるのを避けて固定する（ADR-0007）。版上げは手動。
# 固定版にはセキュリティ修正が入らない点に注意（ローカル専用で 127.0.0.1 にのみ公開する前提）。
# 版は GitHub releases のタグ（v1.0.564）と同じ MAJOR.MINOR.PATCH を指定する。
# 罠: LTS/versions.json は `1.0.564.1` と4区切りで載るが、rpm の URL に4区切りを入れると 403 になる。
ARG EMULATOR_VERSION=1.0.564
# rpm は arch 別（x86_64 / aarch64）。justfile が `uname -m` から決めて渡す。
ARG RPM_ARCH=aarch64

ADD https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/aws-emulator-${EMULATOR_VERSION}-1-${RPM_ARCH}.rpm /tmp/aws-emulator.rpm
RUN rpm -i /tmp/aws-emulator.rpm && rm /tmp/aws-emulator.rpm \
    && mkdir -p /home/emulator && chown 1000 /home/emulator
USER 1000
# 0.0.0.0 で待ち受けないと Docker がポートを転送できない。公開側は run で 127.0.0.1 に限定する。
ENV HOME=/home/emulator EMULATOR_BIND_ADDRESS=0.0.0.0
ENTRYPOINT ["aws-emulator"]
