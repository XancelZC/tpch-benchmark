#!/usr/bin/env bash
# 重建 PostgreSQL 测试库：建表、导入、可选索引、校验。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${1:-baseline}"
CONTAINER="${PG_CONTAINER:-pg-tpch}"
DATA_DIR="${ROOT}/data/load"

[[ "${PROFILE}" == "baseline" || "${PROFILE}" == "indexed" ]] || {
  echo "profile 必须是 baseline 或 indexed" >&2
  exit 2
}

docker exec -i "${CONTAINER}" psql -v ON_ERROR_STOP=1 -U benchmark -d tpch < "${ROOT}/ddl/pg_tpch.sql"
for table in region nation supplier customer part partsupp orders lineitem; do
  docker exec -i "${CONTAINER}" psql -v ON_ERROR_STOP=1 -U benchmark -d tpch \
    -c "COPY ${table} FROM STDIN WITH (FORMAT csv, DELIMITER '|')" < "${DATA_DIR}/${table}.tbl"
done
if [[ "${PROFILE}" == "indexed" ]]; then
  docker exec -i "${CONTAINER}" psql -v ON_ERROR_STOP=1 -U benchmark -d tpch < "${ROOT}/ddl/pg_indexes.sql"
else
  docker exec "${CONTAINER}" psql -v ON_ERROR_STOP=1 -U benchmark -d tpch -c "ANALYZE"
fi
python3 "${ROOT}/scripts/validate_database.py" --config "${ROOT}/config.4db.yaml" --database PostgreSQL
