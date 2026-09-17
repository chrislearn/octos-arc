#!/bin/sh
# 在和 CI 同样的 ubuntu:24.04（glibc 2.39）容器里编内核，产物放到 arc/bin/octos；
# 之后 `sh arc/pack.sh` 会通过 glibc 校验并把它打进包（见 CHANGELOG 2026-09-17 的 e70711133d37 事故）。
#
# 用法：sh arc/build-kernel-docker.sh                       # --no-default-features --features api（README 的魔改版口径）
#       FEATURES="api,telegram,discord" sh arc/build-kernel-docker.sh
#       sg docker -c "sh arc/build-kernel-docker.sh"          # 刚加入 docker 组、还没重新登录时
# 产物目录 target/docker/ 与本机 target/ 分开：两者的 glibc 不同，不能混用增量产物。
set -eu
cd "$(dirname "$0")/.."
IMAGE=octos-arc-kernel-builder
FEATURES="${FEATURES:-api}"
docker build -q -t "$IMAGE" -f arc/docker/kernel-builder.Dockerfile arc/docker
mkdir -p "$HOME/.cargo/registry" arc/bin target/docker
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/work" \
  -v "$HOME/.cargo/registry:/usr/local/cargo/registry" \
  -e CARGO_TARGET_DIR=/work/target/docker \
  -e HOME=/tmp \
  "$IMAGE" cargo build --locked --release -p octos-cli --no-default-features --features "$FEATURES"
cp target/docker/release/octos arc/bin/octos && chmod 755 arc/bin/octos
echo "内核：arc/bin/octos（$(arc/bin/octos --version)）"
python3 - <<'PY'
import sys; sys.path.insert(0, "arc")
from pathlib import Path
import pack_kernel as pk
b = Path("arc/bin/octos")
need, ceiling = pk.max_glibc(b), pk.glibc_ceiling()
print(f"需要的最高 glibc：{need}，平台上限：{ceiling} -> {pk.usable_kernel(b) or '可自带（sh arc/pack.sh 会打进包）'}")
PY
