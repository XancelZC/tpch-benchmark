#!/usr/bin/env bash
# 重建 YMatrix 或 Greenplum 测试库。
# 所有 SQL 均写入文件后通过 psql -f 执行，避免多层 Shell 引号和登录环境污染。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_NAME="${1:?用法: init_mpp.sh YMatrix|Greenplum [baseline|indexed]}"
PROFILE="${2:-baseline}"
DATA_DIR="${ROOT}/data/load"
TABLES=(region nation supplier customer part partsupp orders lineitem)

case "${DB_NAME}" in
  YMatrix)
    CONTAINER="${YMATRIX_CONTAINER:-ymatrix-tpch}"
    OS_USER="mxadmin"
    PSQL="/opt/ymatrix/matrixdb5/bin/psql"
    ;;
  Greenplum)
    CONTAINER="${GREENPLUM_CONTAINER:-gp-tpch}"
    OS_USER="gpadmin"
    PSQL="/usr/local/greenplum-db/bin/psql"
    ;;
  *)
    echo "数据库必须是 YMatrix 或 Greenplum" >&2
    exit 2
    ;;
esac

if [[ "${PROFILE}" != "baseline" && "${PROFILE}" != "indexed" ]]; then
  echo "profile 必须是 baseline 或 indexed" >&2
  exit 2
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT
LOAD_SQL="${WORK_DIR}/load_all.sql"

cp "${ROOT}/ddl/mpp_tpch.sql" "${LOAD_SQL}"
for table in "${TABLES[@]}"; do
  printf "COPY %s FROM '/tmp/%s.tbl' WITH (FORMAT csv, DELIMITER '|');\n" \
    "${table}" "${table}" >> "${LOAD_SQL}"
done
if [[ "${PROFILE}" == "indexed" ]]; then
  cat "${ROOT}/ddl/mpp_indexes.sql" >> "${LOAD_SQL}"
else
  printf 'ANALYZE;\n' >> "${LOAD_SQL}"
fi

for table in "${TABLES[@]}"; do
  docker cp "${DATA_DIR}/${table}.tbl" "${CONTAINER}:/tmp/${table}.tbl"
done
docker cp "${LOAD_SQL}" "${CONTAINER}:/tmp/load_all.sql"

docker exec "${CONTAINER}" /usr/sbin/runuser -u "${OS_USER}" -- \
  "${PSQL}" -v ON_ERROR_STOP=1 -X -h 127.0.0.1 -p 5432 -d tpch \
  -f /tmp/load_all.sql

python3 "${ROOT}/scripts/validate_database.py" \
  --config "${ROOT}/config.4db.yaml" --database "${DB_NAME}"
