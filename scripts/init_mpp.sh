#!/usr/bin/env bash
# 重建 YMatrix 或 Greenplum 测试库。
# 所有 SQL 均写入文件后通过 psql -f 执行，避免多层 Shell 引号和登录环境污染。
#
# 用法：bash scripts/init_mpp.sh YMatrix|Greenplum [baseline|indexed]
# 失败时会打印当前阶段和重跑命令，便于排查和继续。

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

# 当前执行阶段，用于失败时定位
CURRENT_STEP="初始化"

fail_handler() {
  echo "❌ 初始化失败，失败阶段：${CURRENT_STEP}" >&2
  echo "   数据库可能处于半初始化状态（幂等 DDL 支持直接重跑）" >&2
  echo "   重跑：bash scripts/init_mpp.sh ${DB_NAME} ${PROFILE}" >&2
}
trap fail_handler ERR

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT
LOAD_SQL="${WORK_DIR}/load_all.sql"

CURRENT_STEP="生成加载 SQL"
echo "[1/4] 生成加载 SQL"
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

CURRENT_STEP="拷贝数据文件到容器"
echo "[2/4] 拷贝数据文件到容器"
for table in "${TABLES[@]}"; do
  docker cp "${DATA_DIR}/${table}.tbl" "${CONTAINER}:/tmp/${table}.tbl"
done
docker cp "${LOAD_SQL}" "${CONTAINER}:/tmp/load_all.sql"

CURRENT_STEP="执行建表 / 导入 / 索引"
echo "[3/4] 执行建表 / 导入 / 索引"
docker exec "${CONTAINER}" /usr/sbin/runuser -u "${OS_USER}" -- \
  "${PSQL}" -v ON_ERROR_STOP=1 -X -h 127.0.0.1 -p 5432 -d tpch \
  -f /tmp/load_all.sql

CURRENT_STEP="数据校验"
echo "[4/4] 数据校验"
python3 "${ROOT}/scripts/validate_database.py" \
  --config "${ROOT}/config.4db.yaml" --database "${DB_NAME}"
echo "✅ ${DB_NAME} 初始化完成（${PROFILE}）"
