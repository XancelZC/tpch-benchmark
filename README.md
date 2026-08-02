# MatrixBench

基于 TPC-H 数据模型与查询模板的多数据库性能测试工具，面向 FDE 的客户 PoC、迁移评估和竞品分析场景。

> 当前结果是基于固定 `dbgen` 数据和查询模板的派生工程微基准，不是经 TPC 审计的正式 TPC-H 结果，不能与公开 TPC-H 榜单直接比较。

## 项目目标

- 配置驱动执行 22 条查询；
- 支持 YMatrix、Greenplum、PostgreSQL、MySQL；
- 支持预热、多轮、超时、逐轮原始记录；
- 校验四库返回结果摘要一致；
- 输出 raw CSV、汇总 CSV、Markdown 报告和图表；
- 记录数据清单、SQL hash、版本、架构和资源限制。

## 目录

```text
src/                 配置、连接器、执行器、统计和报告
queries/             22 条查询模板
ddl/                 四库 DDL 与 indexed profile 索引
scripts/             标准数据、初始化、校验和环境重建
results/final/       最终运行产物
tests/               单元测试
```

## 快速开始（一键复现）

在已安装 Docker（或 OrbStack）的机器上：

```bash
# 1. 安装依赖
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 2. 一键从零复现（启动四库容器 → 生成数据 → 初始化 → 校验 → 跑 5 轮 → 出报告）
bash scripts/bootstrap_all.sh

# 3. 查看结果
open results/final/$(cat results/final/LATEST)/report.md
```

`bootstrap_all.sh` 自动完成：

```text
1. 启动并部署四库容器（YMatrix 含完整部署链，幂等可重复执行）
2. 生成标准 TPC-H 数据（固定 dbgen commit，可审计）
3. 初始化四库（indexed profile：建表 + 导入 + 索引 + ANALYZE）
4. 校验四库数据一致性（行数 + 谓词 + 结果 hash）
5. 执行 benchmark（预热 1 轮 + 正式 5 轮）
6. 生成图表
```

只重建环境不跑 benchmark：

```bash
bash scripts/bootstrap_all.sh --skip-benchmark
```

清理环境（重新复现前使用）：

```bash
bash scripts/teardown_all.sh            # 删容器 + 删数据
bash scripts/teardown_all.sh --keep-data  # 删容器，保留数据
```

## 手动流程（可选）

以下为分步说明，`bootstrap_all.sh` 已封装全部步骤，手动执行用于排查。

### 环境依赖

- macOS + Docker/OrbStack；
- Python 3.10+；
- `psycopg2-binary`、`mysql-connector-python`、`PyYAML`；
- 四个数据库容器；
- amd64 YMatrix 镜像需要 Rosetta。

### 安装与数据

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
bash scripts/generate_data.sh 0.1
python3 scripts/validate_data.py data/load
```

数据生成脚本固定 dbgen 源码 commit，并输出 `data/load/manifest.json`。生成的数据规模为 SF=0.1，完整行数见 manifest，不使用旧的自定义随机生成器作为正式数据入口。

## 初始化数据库

四库脚本支持两种 profile：

- `baseline`：只执行 DDL、分布键和 ANALYZE；
- `indexed`：额外创建四库等价的逻辑主键索引和访问路径索引。

本次最终 run 使用 `indexed` profile：

```bash
bash scripts/init_postgres.sh indexed
bash scripts/init_mysql.sh indexed
bash scripts/init_mpp.sh Greenplum indexed
bash scripts/init_mpp.sh YMatrix indexed
```

脚本完成后必须通过数据库校验：

```bash
python3 scripts/validate_database.py --config config.4db.yaml --database YMatrix
```

## 运行方式

```bash
python3 main.py -c config.4db.yaml
```

`concurrency` 当前必须为 `1`。并发模式没有静默降级：填写大于 1 会直接拒绝运行，因为并发测试需要独立连接、资源隔离和独立吞吐口径。

每次运行创建独立目录：

```text
results/<profile>/<run_id>/
├── raw_records.csv
├── comparison_summary.csv
├── metadata.json
└── report.md
```

## 最终运行结果

最终 run：`results/final/20260801T162440Z/`

环境：四库全部 `x86_64`，每个容器限制为 4 CPU、3 GiB 内存、无额外 swap；预热 1 轮，正式 5 轮，超时 300 秒，串行执行。

```text
原始记录：440 条 = 4 库 × 22 查询 × 5 轮
失败记录：0
结果 hash：440/440
跨库结果不一致：0
```

| 对比 | 总耗时比 | 查询中位数 speedup | 几何均值 | YMatrix 胜/负/平 |
|---|---:|---:|---:|---:|
| YMatrix vs Greenplum | 2.26x | 2.29x | 2.50x | 18/4/0 |
| YMatrix vs PostgreSQL | 0.75x | 1.06x | 0.85x | 11/11/0 |
| YMatrix vs MySQL | 2.27x | 2.29x | 3.51x | 15/7/0 |

这里的总耗时比是对照库总耗时除以 YMatrix 总耗时；大于 1 表示 YMatrix 的整套串行 workload 更快。算术平均只作为辅助指标，避免被离群查询误导。

图表位于最终 run 的 `charts/` 目录，由 CSV 动态生成：

- `overall_total.png`；
- `speedup_summary.png`；
- `query_compare.png`。

## 已知限制

- 这是单节点、串行、小规模派生 workload，不代表并发吞吐、生产容量或正式 TPC-H 成绩；
- 四库版本、编译器、存储引擎和 MPP 拓扑仍不同；统一 amd64 只控制了本地架构和资源的一部分变量；
- 四库使用镜像默认参数（未调优），属于开箱即用对比；实测参数见 `report.md` 5.5 节和最终 run 的 `metadata.json`；
- Rosetta 环境不能替代原生 x86_64 专用服务器；
- 评价 MPP 扩展能力需要更大 SF、多 segment、并发和资源监控；
- 当前结果校验使用跨库规范化后的结果摘要，金额/平均值统一到 6 位小数；
- `data/gen.py` 是历史自制生成器，不是正式数据入口，也不应用于声称标准 TPC-H 结果。

## 交付材料

- `report.md`：项目报告；
- `附加文档.md`：HR 要求的目标、关键判断和验证场景；
- `DECISIONS.md`：设计决策与取舍；
- `ai_usage.md`：AI 使用、错误识别和修正记录；
- `docs/YMatrix部署记录.md`：YMatrix 本地部署排障记录。
