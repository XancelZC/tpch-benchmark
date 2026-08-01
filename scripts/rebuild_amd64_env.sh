#!/usr/bin/env bash
# 将 PostgreSQL、MySQL、Greenplum 重建为统一 amd64 受控环境。
# YMatrix 社区镜像本身为 amd64，仅动态设置相同资源限制。

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CPU_LIMIT=4
MEMORY_LIMIT=3g
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:?请先设置 POSTGRES_PASSWORD}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:?请先设置 MYSQL_ROOT_PASSWORD}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:?请先设置 MYSQL_PASSWORD}"
GREENPLUM_PASSWORD="${GREENPLUM_PASSWORD:?请先设置 GREENPLUM_PASSWORD}"

wait_for() {
  local name="$1"
  local command="$2"
  local attempts="${3:-60}"
  for ((i=1; i<=attempts; i++)); do
    if docker exec "${name}" sh -c "${command}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "${name} 在规定时间内未就绪" >&2
  docker logs "${name}" --tail 80 >&2 || true
  return 1
}

for container in pg-tpch mysql-tpch gp-tpch; do
  docker rm -f "${container}" >/dev/null 2>&1 || true
done

docker run -d --name pg-tpch --platform linux/amd64 \
  --cpus "${CPU_LIMIT}" --memory "${MEMORY_LIMIT}" --memory-swap "${MEMORY_LIMIT}" \
  -e POSTGRES_USER=benchmark -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  -e POSTGRES_DB=tpch -p 5432:5432 postgres:16-alpine >/dev/null

docker run -d --name mysql-tpch --platform linux/amd64 \
  --cpus "${CPU_LIMIT}" --memory "${MEMORY_LIMIT}" --memory-swap "${MEMORY_LIMIT}" \
  -e MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD}" -e MYSQL_USER=benchmark \
  -e MYSQL_PASSWORD="${MYSQL_PASSWORD}" -e MYSQL_DATABASE=tpch \
  -p 3306:3306 mysql:8.0 >/dev/null

docker run -d --name gp-tpch --platform linux/amd64 \
  --cpus "${CPU_LIMIT}" --memory "${MEMORY_LIMIT}" --memory-swap "${MEMORY_LIMIT}" \
  -e GREENPLUM_USER=gpadmin -e GREENPLUM_PASSWORD="${GREENPLUM_PASSWORD}" \
  -e GREENPLUM_DATABASE_NAME=tpch -e GREENPLUM_DEPLOYMENT=singlenode \
  -p 15433:5432 woblerr/greenplum:7.1.0 >/dev/null

docker update --cpus "${CPU_LIMIT}" --memory "${MEMORY_LIMIT}" \
  --memory-swap "${MEMORY_LIMIT}" ymatrix-tpch >/dev/null

wait_for pg-tpch "pg_isready -U benchmark -d tpch"
wait_for mysql-tpch "mysqladmin ping -h 127.0.0.1 -u root -p${MYSQL_ROOT_PASSWORD} --silent"
wait_for gp-tpch "/usr/sbin/runuser -u gpadmin -- /usr/local/greenplum-db/bin/pg_isready -h 127.0.0.1 -p 5432 -d tpch"

for container in ymatrix-tpch gp-tpch pg-tpch mysql-tpch; do
  architecture="$(docker exec "${container}" uname -m)"
  if [[ "${architecture}" != "x86_64" ]]; then
    echo "${container} 架构不是 x86_64：${architecture}" >&2
    exit 1
  fi
  echo "${container}: ${architecture}"
done

cd "${ROOT}"
bash scripts/init_postgres.sh indexed
bash scripts/init_mysql.sh indexed
bash scripts/init_mpp.sh Greenplum indexed
python3 scripts/validate_database.py --config config.4db.yaml --database YMatrix
