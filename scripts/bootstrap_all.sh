#!/usr/bin/env bash
# MatrixBench 一键复现：从零到最终 benchmark 完整链路。
#
# 用法：
#   bash scripts/bootstrap_all.sh                 # 完整流程（含 benchmark）
#   bash scripts/bootstrap_all.sh --skip-benchmark # 只重建环境到可跑状态
#
# 前提：
#   - Docker / OrbStack 可用
#   - Apple Silicon（YMatrix 走 Rosetta）或 x86_64
#   - 密码通过环境变量传入（POSTGRES_PASSWORD / MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD / GREENPLUM_PASSWORD）
#   - 不设置则使用与 config.4db.yaml 一致的本地测试默认值

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKIP_BENCHMARK=0
for arg in "$@"; do
  case "${arg}" in
    --skip-benchmark) SKIP_BENCHMARK=1 ;;
    *) echo "未知参数: ${arg}" >&2; exit 2 ;;
  esac
done

# 密码默认值（与 config.4db.yaml 一致，仅本地测试）
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-benchmark}"
export MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-root}"
export MYSQL_PASSWORD="${MYSQL_PASSWORD:-benchmark}"
export GREENPLUM_PASSWORD="${GREENPLUM_PASSWORD:-gpadmin}"

section() {
  echo ""
  echo "================================================================"
  echo "== $1"
  echo "================================================================"
}

step() {
  echo "----> $1"
}

section "0/6 环境检查"
command -v docker >/dev/null || { echo "缺少 Docker" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker 未运行" >&2; exit 1; }
echo "Docker OK"
python3 -c "import yaml" 2>/dev/null || { echo "缺少 PyYAML，请先 pip install -r requirements.txt" >&2; exit 1; }

section "1/6 启动并部署四库容器"
step "YMatrix（含部署链）"
bash "${ROOT}/scripts/deploy_ymatrix.sh"

step "PostgreSQL / MySQL / Greenplum（amd64 受控环境）"
cd "${ROOT}"
if ! docker ps -a --format '{{.Names}}' | grep -qx pg-tpch; then
  bash scripts/rebuild_amd64_env.sh
else
  echo "pg-tpch / mysql-tpch / gp-tpch 已存在，应用资源限制并等待就绪"
  docker update --cpus 4 --memory 3g --memory-swap 3g pg-tpch mysql-tpch gp-tpch >/dev/null
  for c in pg-tpch mysql-tpch gp-tpch; do
    for i in $(seq 1 60); do
      docker exec "${c}" sh -c "true" 2>/dev/null && break
      sleep 2
      [[ $i -eq 60 ]] && { echo "${c} 未就绪" >&2; exit 1; }
    done
  done
fi

section "2/6 生成标准 TPC-H 数据"
if [[ -f "${ROOT}/data/load/manifest.json" ]]; then
  echo "data/load/manifest.json 已存在，跳过数据生成（删除可重新生成）"
else
  bash "${ROOT}/scripts/generate_data.sh" 0.1
fi
python3 "${ROOT}/scripts/validate_data.py" "${ROOT}/data/load"

section "3/6 初始化四库（indexed profile）"
bash "${ROOT}/scripts/init_postgres.sh" indexed
bash "${ROOT}/scripts/init_mysql.sh" indexed
bash "${ROOT}/scripts/init_mpp.sh" Greenplum indexed
bash "${ROOT}/scripts/init_mpp.sh" YMatrix indexed

section "4/6 校验四库数据一致性"
for db in YMatrix Greenplum PostgreSQL MySQL; do
  echo "----> 校验 ${db}"
  python3 "${ROOT}/scripts/validate_database.py" --config "${ROOT}/config.4db.yaml" --database "${db}" >/dev/null
done
echo "四库基数与谓词校验全部通过"

if [[ "${SKIP_BENCHMARK}" -eq 1 ]]; then
  section "完成（--skip-benchmark）"
  echo "环境已就绪。运行 benchmark："
  echo "  python3 main.py -c config.4db.yaml"
  exit 0
fi

section "5/6 执行 benchmark（预热 1 轮 + 正式 5 轮）"
cd "${ROOT}"
python3 main.py -c config.4db.yaml

section "6/6 生成图表"
RUN_DIR="$(cat "${ROOT}/results/final/LATEST" 2>/dev/null || echo '')"
if [[ -n "${RUN_DIR}" && -d "${ROOT}/results/final/${RUN_DIR}" ]]; then
  env -u PYTHONPATH /tmp/chartenv2/bin/python "${ROOT}/tools/make_charts.py" "${ROOT}/results/final/${RUN_DIR}" 2>/dev/null \
    || python3 "${ROOT}/tools/make_charts.py" "${ROOT}/results/final/${RUN_DIR}"
else
  echo "未找到 LATEST run，跳过图表生成"
fi

section "完成"
echo "最新结果目录：${ROOT}/results/final/${RUN_DIR:-（未找到 LATEST）}"
echo "查看报告：${ROOT}/results/final/${RUN_DIR}/report.md"
