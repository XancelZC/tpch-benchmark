# YMatrix 部署记录

> 本文档记录 YMatrix 5.2.1 社区版在 Apple Silicon Mac 上通过 Docker + Rosetta 完整部署的过程、踩坑和解决方案。

## 1. 背景与约束

| 项目 | 说明 |
|------|------|
| 宿主机 | Apple Silicon Mac（arm64） |
| 容器环境 | OrbStack（Docker 兼容层，支持 Rosetta） |
| YMatrix 版本 | 5.2.1 社区版（`matrixdb/matrixdb-community:v5.2.1-v0.13.0`） |
| 镜像架构 | **仅 linux/amd64**（Apple Silicon 需 Rosetta 转译） |
| 数据库内核 | PostgreSQL 12 + Greenplum 7.0 架构 |

**关键约束**：YMatrix 社区版仅提供 x86_64 安装包/镜像，官方 aarch64 支持面向国产 CPU（飞腾/鲲鹏）企业版。在 Apple Silicon 上运行方式选择 amd64 镜像 + Rosetta。

## 2. 部署步骤

### 2.1 拉取镜像并启动容器

```bash
docker pull matrixdb/matrixdb-community:v5.2.1-v0.13.0

# 关键：绕开默认 /usr/sbin/init（在 Rosetta 下崩溃），用 bash 常驻
docker run -d --name ymatrix-tpch -h ymatrix-tpch \
  -p 15432:5432 -p 8240:8240 \
  --privileged=true \
  matrixdb/matrixdb-community:v5.2.1-v0.13.0 \
  /bin/bash -c "sleep infinity"
```

### 2.2 配置 SSH 免密（mxsetup 前置条件）

YMatrix 部署工具需要 SSH 连接本机。容器内执行：

```bash
# 生成 host keys（sshd 需要）
ssh-keygen -A
# 启动 sshd
/usr/sbin/sshd

# mxadmin 用户免密
mkdir -p /home/mxadmin/.ssh
ssh-keygen -t rsa -N '' -f /home/mxadmin/.ssh/id_rsa -q
cat /home/mxadmin/.ssh/id_rsa.pub >> /home/mxadmin/.ssh/authorized_keys
chown -R mxadmin:mxadmin /home/mxadmin/.ssh
chmod 700 /home/mxadmin/.ssh
chmod 600 /home/mxadmin/.ssh/authorized_keys
echo 'Host *' > /home/mxadmin/.ssh/config
echo '  StrictHostKeyChecking no' >> /home/mxadmin/.ssh/config
chown mxadmin:mxadmin /home/mxadmin/.ssh/config
```

### 2.3 启动 supervisord（进程管理服务，端口 4617）

关键：**必须带完整环境变量启动**，否则 `mxbox`/`mxctl` 找不到。

```bash
export MXHOME=/opt/ymatrix/matrixdb5
export MXCONFDIR=/etc/matrixdb5
export MXLOGDIR=/var/log/matrixdb5
export MXDATA=/mxdata
export PATH=$MXHOME/bin:$PATH
export LD_LIBRARY_PATH=$MXHOME/lib:$LD_LIBRARY_PATH
mkdir -p $MXLOGDIR
nohup $MXHOME/bin/supervisord -c /etc/matrixdb5/supervisor.conf > /dev/null 2>&1 &
```

### 2.4 启动 deployer 服务（端口 4627）

```bash
export MX_SUPERVISOR_INET_GRPC_SERVER_PORT=4617
nohup mxbox deployer > /var/log/matrixdb5/deployer_serve.log 2>&1 &
```

### 2.5 部署集群（关键步骤）

**不要用 `mxsetup`**（在 Rosetta 下 launch 阶段超时会自动 revert 清数据）。用 `mxctl setup exec` 分步执行：

```bash
export MX_SUPERVISOR_INET_GRPC_SERVER_PORT=4617

# 收集主机信息
mxctl setup collect --collect-file /tmp/collect.json
# 生成部署计划
mxctl setup plan --collect-file /tmp/collect.json --plan-file /tmp/plan.json
# 执行部署（分步，失败不 revert）
mxctl setup exec --plan-file /tmp/plan.json
```

### 2.6 配置远程访问

```bash
# 允许任意来源 mxadmin trust 连接（测试环境）
sed -i '1i host all mxadmin 0.0.0.0/0 trust' /mxdata_*/master/mxseg-1/pg_hba.conf
# reload
su - mxadmin -c 'psql -h 127.0.0.1 -p 5432 -d postgres -c "SELECT pg_reload_conf();"'
```

### 2.7 验证

```bash
# 容器内
su - mxadmin -c 'psql -h 127.0.0.1 -p 5432 -d postgres -c "SELECT version();"'
# 宿主机（端口映射 15432）
python3 -c "import psycopg2; conn=psycopg2.connect(host='localhost',port=15432,dbname='postgres',user='mxadmin'); print(conn.cursor().execute('SELECT version()') and 'OK')"
```

## 3. 踩坑记录

### 坑 1：容器默认 init 崩溃

**现象**：`docker run ... /usr/sbin/init` 报 `Couldn't find an alternative telinit implementation to spawn`，容器秒退。

**原因**：YMatrix 官方镜像用 systemd 风格 init，在 Rosetta 转译环境无法 spawn telinit。

**解决**：改用 `/bin/bash -c "sleep infinity"` 常驻，手动管理服务。

### 坑 2：mxsetup 超时自动 revert

**现象**：`mxsetup` 执行到 `launch_matrixdb` 报 `DeadlineExceeded`，随后自动 revert 清空所有已初始化数据，导致反复重来。

**原因**：Rosetta 下 postgres 启动慢，超过 deployer 的默认超时；mxsetup 是原子操作，失败即回滚。

**解决**：用 `mxctl setup exec --plan-file` 分步执行（无自动 revert），launch 阶段也能成功。

### 坑 3：supervisord 找不到 mxbox/mxctl

**现象**：`mxsetup` 报 `exec: "mxbox": executable file not found in $PATH`。

**原因**：supervisord 继承启动时的 PATH，不含 `/opt/ymatrix/matrixdb5/bin`。

**解决**：启动 supervisord 前 `export PATH=$MXHOME/bin:$PATH`。

### 坑 4：deployer 服务未启动

**现象**：`mxsetup` 报 `dial tcp [::1]:4627: connect: connection refused`。

**原因**：deployer 服务（4627 端口）需要先于部署启动，且需要 `MX_SUPERVISOR_INET_GRPC_SERVER_PORT=4617`。

**解决**：`nohup mxbox deployer &` 先行启动。

### 坑 5：SSH host key 缺失

**现象**：`sshd` 报 `no hostkeys available -- exiting`。

**解决**：`ssh-keygen -A` 生成全部 host keys。

## 4. 性能影响评估

| 项目 | 说明 |
|------|------|
| Rosetta 转译损耗 | 约 20-30%（社区基准：prime sieve 测试 Rosetta 比原生慢 ~20%） |
| 对 benchmark 的影响 | 环境 B（四库全 amd64）中所有库吃同样损耗，**相对结论不受影响** |
| 环境 A（混合） | YMatrix 有损耗、对比库原生，模拟"客户迁移"真实场景 |
| 生产建议 | 实际部署应使用 x86_64 服务器原生运行，消除转译损耗 |

## 5. 备选方案（未采用）

| 方案 | 说明 | 未采用原因 |
|------|------|-----------|
| 云服务器原生跑 | 租 amd64 云服务器，YMatrix 原生 | 需要账号/费用；环境 B 已保证公平 |
| 社区版 aarch64 包 | 官方文档列 aarch64 支持 | 面向国产 CPU 企业版，社区版仅 x86_64 |
| QEMU 全模拟 | `orb create --arch amd64` | 比 Rosetta 慢 5-10 倍，没必要 |
