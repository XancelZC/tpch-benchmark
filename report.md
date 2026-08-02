# MatrixBench 项目报告

> 最终 run：`20260801T162440Z`
> 题目：TPC-H 测试执行与结果汇总工具

## 1. 方案设计

### 1.1 核心目标

实现一个配置驱动的多数据库查询测试工具，用于 FDE 场景中的客户 PoC、迁移评估、竞品分析和性能问题定位。工具不只负责“把 SQL 跑起来”，还负责记录证据、校验结果、解释环境差异并生成可交付报告。

### 1.2 总体架构

```text
YAML 配置
   ↓
Config 校验
   ↓
DB-API 连接器（PG/YMatrix/Greenplum、MySQL）
   ↓
预热 → 随机查询顺序 → 多轮串行执行 → 超时/失败记录
   ↓
raw_records.csv + result hash
   ↓
跨库结果校验 → 总耗时/中位数/几何均值/胜负数
   ↓
comparison_summary.csv + metadata.json + report.md + charts
```

### 1.3 数据与测试口径

- 数据生成器：固定 dbgen 兼容源码 commit `32f1c1b92d1664dba542e927d23d86ffa57aa253`；
- 规模：SF=0.1；
- 关系基数：region 5、nation 25、supplier 1,000、customer 15,000、part 20,000、partsupp 80,000、orders 150,000、lineitem 600,572；
- profile：四库统一 `indexed`；
- 环境：四库均 `x86_64`，每个容器 4 CPU、3 GiB 内存、无额外 swap；
- 预热：1 轮；
- 正式测试：5 轮；
- 执行方式：单用户串行；
- 计时语义：time-to-last-row，即完整消费查询结果后停止计时；
- 结果校验：结果集规范化后计算 SHA-256；数值统一到 6 位小数。

> 这是基于 TPC-H 数据模型、dbgen 数据和查询模板的派生工程微基准，不是经 TPC 审计的正式 TPC-H 结果，不能与公开榜单直接比较。

## 2. 实现说明

### 2.1 配置与执行

配置包含数据库连接信息、SQL 目录、预热轮数、正式轮数、并发数、超时时间、随机种子和输出路径。当前 `concurrency` 必须为 1；未实现的并发模式会直接拒绝，而不是悄悄按串行执行。

### 2.2 连接器

- PostgreSQL、YMatrix、Greenplum 复用 PostgreSQL 协议连接器；
- PostgreSQL 系使用 `statement_timeout`；
- MySQL 使用 `max_execution_time` 和独立控制连接 `KILL QUERY` 双保险；
- 查询结果统一消费到最后一行；
- 每条记录保存开始时间、结束时间、耗时、行数、结果摘要、成功状态和错误。

### 2.3 可复现初始化

初始化脚本执行完整闭环：

```text
建表 → 导入标准数据 → 创建 indexed profile 索引 → ANALYZE → 行数/谓词校验
```

索引脚本包含逻辑主键和查询访问路径，已正式纳入 `ddl/`，避免手工索引造成结果不可复现。

## 3. 测试过程

### 3.1 数据验证

在导入数据库前验证：

- 字段数和文件行数与 manifest 一致；
- partsupp 组合无重复；
- lineitem 的 order、part、supplier、partsupp 关系完整；
- `commitdate < receiptdate` 有有效分布；
- Q8/Q9/Q20 等关键选择谓词都有命中；
- 文件 SHA-256 写入 manifest。

### 3.2 跨库正确性预检

标准数据导入四库后，执行 22 条查询单轮预检：

```text
4 库 × 22 条 = 88 条记录
成功：88/88
结果摘要不一致：0
```

预检过程中曾发现 MySQL Q8 因缺少逻辑主键访问路径产生灾难性执行计划，约 120 秒超时。补齐等价索引后，Q8 恢复到百毫秒级，并重新完成四库预检。这一轮结果未用于最终性能结论。

### 3.3 正式 run

最终运行目录：

```text
results/final/20260801T162440Z/
├── raw_records.csv
├── comparison_summary.csv
├── metadata.json
├── report.md
└── charts/
```

原始记录为 440 条：

```text
4 库 × 22 查询 × 5 正式轮次 = 440
失败记录：0
结果 hash：440/440
```

## 4. 测试结果

| 对比 | 总耗时比 | 查询中位数 speedup | 几何均值 | 算术均值 | 胜/负/平 |
|---|---:|---:|---:|---:|---:|
| YMatrix vs Greenplum | 2.26x | 2.29x | 2.50x | 3.78x | 18/4/0 |
| YMatrix vs PostgreSQL | 0.75x | 1.06x | 0.85x | 1.12x | 11/11/0 |
| YMatrix vs MySQL | 2.27x | 2.29x | 3.51x | 3.51x | 15/7/0 |

### 4.1 结论边界

- YMatrix 在本次小规模、单节点、统一 amd64、indexed profile 下，对 Greenplum 的整套串行 workload 总耗时约为 2.26 倍优势；逐查询中位数和几何均值方向一致；
- YMatrix 与 PostgreSQL 总耗时比为 0.75x，逐查询胜负为 11/11，当前不能得出 YMatrix 总体优于 PostgreSQL 的结论；
- YMatrix 对 MySQL 的总耗时比为 2.27x，几何均值为 3.51x，但仍有 7 条查询 MySQL 更快，不能表述为“全面领先”；
- 算术平均仅作辅助指标，不能单独作为总体性能结论。

## 5. 问题、风险与处理

### 5.1 自制数据问题

早期自定义随机生成器破坏了 partsupp 和 lineitem 的关系，也导致部分查询谓词天然为空。该问题已经通过固定 dbgen 数据链路解决，旧结果全部废弃。历史 `data/gen.py` 不再作为正式入口。

### 5.2 索引缺失问题

早期容器重建后没有恢复索引，导致 MySQL Q17/Q19、PostgreSQL Q17/Q20 等出现异常耗时。现在索引和 ANALYZE 已纳入初始化脚本，数据库重建后自动恢复。

### 5.3 超时问题

MySQL 的 optimizer timeout 对部分语句并不充分，因此增加独立控制连接执行 `KILL QUERY`，并等待取消线程完成，避免超时线程误杀下一条查询。

### 5.4 环境风险

统一 amd64 和资源限制只控制了架构路径与部分资源变量，仍不能等同于生产 x86_64 服务器。数据库版本、编译器、存储引擎、MPP 拓扑和优化器实现仍不同。

### 5.5 数据库参数披露（默认参数对比）

四库使用各自镜像的**默认参数**，未做调优。最终 run 后实测关键参数如下（详见 `metadata.json` 的 `database_parameters`）：

| 参数 | YMatrix | Greenplum | PostgreSQL | MySQL |
|---|---|---|---|---|
| 排序/哈希内存 | work_mem 32MB | work_mem 32MB | **work_mem 4MB** | sort_buffer 256KB |
| 缓冲池 | shared_buffers ~720MB | shared_buffers ~125MB | shared_buffers 128MB | innodb_buffer_pool 128MB |
| 并行度 | 2 | 2 | 2 | 默认 |
| 服务端超时 | 无（客户端控制） | 无 | 无 | 无（客户端 KILL） |

因此本对比属于**开箱即用（默认参数）对比**，不代表各库参数调优后的峰值性能。参数差异（如 PG work_mem 4MB vs YMatrix 32MB）是整体耗时差异的组成部分，不能简单归因于架构。

## 6. 后续改进方向

1. 使用更大 SF、多 segment 和真实资源监控评价 MPP 扩展性；
2. 增加数据库顺序轮换或 ABBA 设计，量化顺序偏差；
3. 增加并发吞吐测试，但与串行延迟测试分离；
4. 采集 `EXPLAIN`、CPU、内存、I/O 和数据库参数快照；
5. 使用官方授权的 TPC-H tools/qgen 版本做更严格的参数化 workload；
6. 增加跨库结果容差配置和标准 answer 校验；
7. 为初始化脚本增加失败清理、阶段标记和 Docker Compose 编排；
8. 可选：为四库按各自最佳实践调优参数，对比"调优后"与"默认"两档。
