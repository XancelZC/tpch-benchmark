#!/usr/bin/env bash
# 重建 MySQL 测试库：建表、导入、可选索引、校验。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${1:-baseline}"
CONTAINER="${MYSQL_CONTAINER:-mysql-tpch}"
DATA_DIR="${ROOT}/data/load"

[[ "${PROFILE}" == "baseline" || "${PROFILE}" == "indexed" ]] || {
  echo "profile 必须是 baseline 或 indexed" >&2
  exit 2
}

docker exec "${CONTAINER}" mysql -u root -proot \
  -e "SET GLOBAL local_infile = 1;"
docker exec -i "${CONTAINER}" mysql --local-infile=1 -u benchmark -pbenchmark tpch < "${ROOT}/ddl/mysql_tpch.sql"
for table in region nation supplier customer part partsupp orders lineitem; do
  docker exec "${CONTAINER}" rm -f "/tmp/${table}.tbl"
  docker cp "${DATA_DIR}/${table}.tbl" "${CONTAINER}:/tmp/${table}.tbl"
  docker exec "${CONTAINER}" mysql --local-infile=1 -u benchmark -pbenchmark tpch \
    -e "LOAD DATA LOCAL INFILE '/tmp/${table}.tbl' INTO TABLE ${table} FIELDS TERMINATED BY '|' LINES TERMINATED BY '\\n';"
done
if [[ "${PROFILE}" == "indexed" ]]; then
  docker exec -i "${CONTAINER}" mysql -u benchmark -pbenchmark tpch < "${ROOT}/ddl/mysql_indexes.sql"
else
  docker exec "${CONTAINER}" mysql -u benchmark -pbenchmark tpch \
    -e "ANALYZE TABLE region, nation, supplier, customer, part, partsupp, orders, lineitem;"
fi
python3 "${ROOT}/scripts/validate_database.py" --config "${ROOT}/config.4db.yaml" --database MySQL
