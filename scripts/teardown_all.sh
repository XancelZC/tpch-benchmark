#!/usr/bin/env bash
# 清理 tpch-benchmark 环境（容器 + 数据）。
# 用法：bash scripts/teardown_all.sh [--keep-data]
#   --keep-data  保留 data/load（重新生成数据较慢）

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEEP_DATA=0
for arg in "$@"; do
  case "${arg}" in
    --keep-data) KEEP_DATA=1 ;;
    *) echo "未知参数: ${arg}" >&2; exit 2 ;;
  esac
done

echo "==> 停止并删除容器"
for c in ymatrix-tpch gp-tpch pg-tpch mysql-tpch; do
  if docker ps -a --format '{{.Names}}' | grep -qx "${c}"; then
    docker rm -f "${c}" >/dev/null
    echo "  已删除 ${c}"
  fi
done

if [[ "${KEEP_DATA}" -eq 0 ]]; then
  echo "==> 清理 data/load 和 data/raw"
  rm -rf "${ROOT}/data/load" "${ROOT}/data/raw"
fi

echo "==> 完成。要重新复现：bash scripts/bootstrap_all.sh"
