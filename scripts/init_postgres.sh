#!/usr/bin/env bash
# 重建 PostgreSQL 测试库：建表、导入、可选索引、校验。
#
# 用法：bash scripts/init_postgres.sh [baseline|indexed]
# 失败时会打印当前阶段和重跑命令，便于排查和继续。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${1:-baseline}"
CONTAINER="${PG_CONTAINER:-pg-tpch}"
DATA_DIR="${ROOT}/data/load"

# 当前执行阶段，用于失败时定位
CURRENT_STEP="初始化"

fail_handler() {
  echo "❌ 初始化失败，失败阶段：${CURRENT_STEP}" >&2
  echo "   数据库可能处于半初始化状态（幂等 DDL 支持直接重跑）" >&2
  echo "   重跑：bash scripts/init_postgres.sh ${PROFILE}" >&2
}
trap fail_handler ERR

[[ "${PROFILE}" == "baseline" || "${PROFILE}" == "indexed" ]] || {
  echo "profile 必须是 baseline 或 indexed" >&2
  exit 2
}

CURRENT_STEP="建表"
echo "[1/4] 建表"
docker exec -i "${CONTAINER}" psql -v ON_ERROR_STOP=1 -U benchmark -d tpch < "${ROOT}/ddl/pg_tpch.sql"

CURRENT_STEP="导入数据"
echo "[2/4] 导入数据"
for table in region nation supplier customer part partsupp orders lineitem; do
  docker exec -i "${CONTAINER}" psql -v ON_ERROR_STOP=1 -U benchmark -d tpch \
    -c "COPY ${table} FROM STDIN WITH (FORMAT csv, DELIMITER '|')" < "${DATA_DIR}/${table}.tbl"
done

CURRENT_STEP="索引 / ANALYZE"
if [[ "${PROFILE}" == "indexed" ]]; then
  echo "[3/4] 创建索引"
  docker exec -i "${CONTAINER}" psql -v ON_ERROR_STOP=1 -U benchmark -d tpch < "${ROOT}/ddl/pg_indexes.sql"
else
  echo "[3/4] ANALYZE"
  docker exec "${CONTAINER}" psql -v ON_ERROR_STOP=1 -U benchmark -d tpch -c "ANALYZE"
fi

CURRENT_STEP="数据校验"
echo "[4/4] 数据校验"
python3 "${ROOT}/scripts/validate_database.py" --config "${ROOT}/config.4db.yaml" --database PostgreSQL
echo "✅ PostgreSQL 初始化完成（${PROFILE}）"
