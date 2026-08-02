#!/usr/bin/env bash
# 部署 YMatrix 社区版容器（Apple Silicon + Rosetta 专用路径）。
# 幂等：容器已存在且数据库可用时直接跳过。
# 参考：docs/YMatrix部署记录.md

set -euo pipefail

CONTAINER="${YMATRIX_CONTAINER:-ymatrix-tpch}"
IMAGE="matrixdb/matrixdb-community:v5.2.1-v0.13.0"
MXHOME="/opt/ymatrix/matrixdb5"
MXCONFDIR="/etc/matrixdb5"
MXLOGDIR="/var/log/matrixdb5"
MXDATA="/mxdata"
MXENV="MXHOME=${MXHOME} MXCONFDIR=${MXCONFDIR} MXLOGDIR=${MXLOGDIR} MXDATA=${MXDATA} PATH=${MXHOME}/bin:\$PATH LD_LIBRARY_PATH=${MXHOME}/lib"

echo "==> 检查容器 ${CONTAINER}"
if ! docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
  echo "==> 拉取镜像 ${IMAGE}"
  docker pull "${IMAGE}"
  echo "==> 启动容器（绕开 /usr/sbin/init，用 bash 常驻）"
  docker run -d --name "${CONTAINER}" -h "${CONTAINER}" \
    --platform linux/amd64 \
    -p 15432:5432 -p 8240:8240 \
    --privileged=true \
    "${IMAGE}" \
    /bin/bash -c "sleep infinity"
else
  echo "==> 容器已存在，检查是否在运行"
  if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
    docker start "${CONTAINER}"
  fi
fi

# 等待容器内基础环境就绪
echo "==> 等待容器就绪"
for i in $(seq 1 60); do
  if docker exec "${CONTAINER}" test -d "${MXHOME}/bin" 2>/dev/null; then
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    echo "容器内 MatrixDB 目录未就绪" >&2
    docker logs "${CONTAINER}" --tail 40 >&2 || true
    exit 1
  fi
done

# 如果数据库已在运行，直接跳过部署
if docker exec "${CONTAINER}" bash -lc "su - mxadmin -c 'psql -h 127.0.0.1 -p 5432 -d postgres -c \"SELECT 1\"' >/dev/null 2>&1"; then
  echo "==> MatrixDB 已在运行，跳过部署"
  exit 0
fi

echo "==> 配置 SSH（host key + mxadmin 免密）"
docker exec "${CONTAINER}" bash -c "
set -e
ssh-keygen -A
/usr/sbin/sshd || true
mkdir -p /home/mxadmin/.ssh
[ -f /home/mxadmin/.ssh/id_rsa ] || ssh-keygen -t rsa -N '' -f /home/mxadmin/.ssh/id_rsa -q
cat /home/mxadmin/.ssh/id_rsa.pub >> /home/mxadmin/.ssh/authorized_keys
chown -R mxadmin:mxadmin /home/mxadmin/.ssh
chmod 700 /home/mxadmin/.ssh
chmod 600 /home/mxadmin/.ssh/authorized_keys
printf 'Host *\n  StrictHostKeyChecking no\n' > /home/mxadmin/.ssh/config
chown mxadmin:mxadmin /home/mxadmin/.ssh/config
"

echo "==> 启动 supervisord（端口 4617）"
docker exec "${CONTAINER}" bash -c "
set -e
mkdir -p ${MXLOGDIR}
if ! ss -tln | grep -q ':4617'; then
  nohup ${MXHOME}/bin/supervisord -c ${MXCONFDIR}/supervisor.conf > ${MXLOGDIR}/supervisord.log 2>&1 &
  sleep 3
fi
"
docker exec "${CONTAINER}" bash -c "ss -tln | grep ':4617' >/dev/null" || {
  echo "supervisord 未就绪（4617）" >&2
  docker exec "${CONTAINER}" bash -c "tail -30 ${MXLOGDIR}/supervisord.log" >&2 || true
  exit 1
}

echo "==> 启动 deployer（端口 4627）"
docker exec "${CONTAINER}" bash -c "
set -e
if ! ss -tln | grep -q ':4627'; then
  MX_SUPERVISOR_INET_GRPC_SERVER_PORT=4617 nohup mxbox deployer > ${MXLOGDIR}/deployer_serve.log 2>&1 &
  sleep 3
fi
"
docker exec "${CONTAINER}" bash -c "ss -tln | grep ':4627' >/dev/null" || {
  echo "deployer 未就绪（4627）" >&2
  docker exec "${CONTAINER}" bash -c "tail -30 ${MXLOGDIR}/deployer_serve.log" >&2 || true
  exit 1
}

echo "==> 执行 mxctl setup（分步，不自动 revert）"
docker exec "${CONTAINER}" bash -c "
set -e
export MX_SUPERVISOR_INET_GRPC_SERVER_PORT=4617
export PATH=${MXHOME}/bin:\$PATH
export LD_LIBRARY_PATH=${MXHOME}/lib
rm -f /tmp/collect.json /tmp/plan.json
mxctl setup collect --collect-file /tmp/collect.json
mxctl setup plan --collect-file /tmp/collect.json --plan-file /tmp/plan.json
mxctl setup exec --plan-file /tmp/plan.json
"

echo "==> 配置远程访问（trust，仅测试环境）"
docker exec "${CONTAINER}" bash -c "
set -e
for f in /mxdata_*/master/mxseg-1/pg_hba.conf; do
  grep -q 'host all mxadmin 0.0.0.0/0 trust' \"\$f\" || sed -i '1i host all mxadmin 0.0.0.0/0 trust' \"\$f\"
done
su - mxadmin -c 'psql -h 127.0.0.1 -p 5432 -d postgres -c \"SELECT pg_reload_conf();\"' >/dev/null
"

echo "==> 验证"
docker exec "${CONTAINER}" bash -c "su - mxadmin -c 'psql -h 127.0.0.1 -p 5432 -d postgres -t -A -c \"SELECT version();\"'" || {
  echo "MatrixDB 验证失败" >&2
  exit 1
}
echo "==> YMatrix 部署完成"
