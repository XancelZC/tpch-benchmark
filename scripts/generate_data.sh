#!/usr/bin/env bash
# 使用固定版本的 dbgen 兼容实现生成可审计的 TPC-H 派生数据。
# 注意：该数据用于工程验证，不构成经 TPC 审计的正式 TPC-H 结果。

set -euo pipefail

SF="${1:-0.1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_DIR="${ROOT}/.cache/tpch-dbgen"
RAW_DIR="${ROOT}/data/raw"
LOAD_DIR="${ROOT}/data/load"
COMMIT="32f1c1b92d1664dba542e927d23d86ffa57aa253"
BUILD_IMAGE="gcc:13-bookworm@sha256:3e239a5ea77200b9163c825a0a5ebc17ca99f3bbb4d08241ee0fb9c174325880"
RUN_IMAGE="debian:bookworm-slim@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818"

mkdir -p "${ROOT}/.cache" "${RAW_DIR}" "${LOAD_DIR}"

if [[ ! -d "${SOURCE_DIR}/.git" ]]; then
  git clone https://github.com/electrum/tpch-dbgen.git "${SOURCE_DIR}"
fi
git -C "${SOURCE_DIR}" fetch --depth 1 origin "${COMMIT}"
git -C "${SOURCE_DIR}" checkout --detach "${COMMIT}"

# 只构建 dbgen；该旧版仓库的 qgen PostgreSQL 宏不完整。
docker run --rm --platform linux/amd64 \
  -v "${SOURCE_DIR}:/src" -w /src "${BUILD_IMAGE}" \
  bash -lc 'make clean >/dev/null 2>&1 || true; make dbgen MACHINE=LINUX DATABASE=POSTGRESQL'

rm -f "${RAW_DIR}"/*.tbl "${LOAD_DIR}"/*.tbl
chmod 777 "${RAW_DIR}"
docker run --rm --platform linux/amd64 --user 0:0 \
  -e DSS_CONFIG=/src -e DSS_PATH=/data \
  -v "${SOURCE_DIR}:/src:ro" -v "${RAW_DIR}:/data" -w /src \
  "${RUN_IMAGE}" /src/dbgen -vf -s "${SF}"

# 保留原始带尾分隔符文件，另生成适用于 COPY/LOAD DATA 的确定性副本。
python3 "${ROOT}/scripts/build_data_manifest.py" \
  --source "${RAW_DIR}" --load-dir "${LOAD_DIR}" \
  --scale-factor "${SF}" --generator-commit "${COMMIT}"

echo "数据生成完成：${LOAD_DIR}"
