#!/usr/bin/env bash
# 重建 MySQL 测试库：建表、导入、可选索引、校验。
#
# 用法：bash scripts/init_mysql.sh [baseline|indexed]
# 失败时会打印当前阶段和重跑命令，便于排查和继续。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${1:-baseline}"
CONTAINER="${MYSQL_CONTAINER:-mysql-tpch}"
DATA_DIR="${ROOT}/data/load"

# 当前执行阶段，用于失败时定位
CURRENT_STEP="初始化"

fail_handler() {
  echo "❌ 初始化失败，失败阶段：${CURRENT_STEP}" >&2
  echo "   数据库可能处于半初始化状态（幂等 DDL 支持直接重跑）" >&2
  echo "   重跑：bash scripts/init_mysql.sh ${PROFILE}" >&2
}
trap fail_handler ERR

[[ "${PROFILE}" == "baseline" || "${PROFILE}" == "indexed" ]] || {
  echo "profile 必须是 baseline 或 indexed" >&2
  exit 2
}

CURRENT_STEP="开启 local_infile"
echo "[1/5] 开启 local_infile"
docker exec "${CONTAINER}" mysql -u root -proot \
  -e "SET GLOBAL local_infile = 1;"

CURRENT_STEP="建表"
echo "[2/5] 建表"
docker exec -i "${CONTAINER}" mysql --local-infile=1 -u benchmark -pbenchmark tpch < "${ROOT}/ddl/mysql_tpch.sql"

CURRENT_STEP="导入数据"
echo "[3/5] 导入数据"
for table in region nation supplier customer part partsupp orders lineitem; do
  docker exec "${CONTAINER}" rm -f "/tmp/${table}.tbl"
  docker cp "${DATA_DIR}/${table}.tbl" "${CONTAINER}:/tmp/${table}.tbl"
  docker exec "${CONTAINER}" mysql --local-infile=1 -u benchmark -pbenchmark tpch \
    -e "LOAD DATA LOCAL INFILE '/tmp/${table}.tbl' INTO TABLE ${table} FIELDS TERMINATED BY '|' LINES TERMINATED BY '\\n';"
done

CURRENT_STEP="索引 / ANALYZE"
if [[ "${PROFILE}" == "indexed" ]]; then
  echo "[4/5] 创建索引"
  docker exec -i "${CONTAINER}" mysql -u benchmark -pbenchmark tpch < "${ROOT}/ddl/mysql_indexes.sql"
else
  echo "[4/5] ANALYZE"
  docker exec "${CONTAINER}" mysql -u benchmark -pbenchmark tpch \
    -e "ANALYZE TABLE region, nation, supplier, customer, part, partsupp, orders, lineitem;"
fi

CURRENT_STEP="数据校验"
echo "[5/5] 数据校验"
python3 "${ROOT}/scripts/validate_database.py" --config "${ROOT}/config.4db.yaml" --database MySQL
echo "✅ MySQL 初始化完成（${PROFILE}）"
