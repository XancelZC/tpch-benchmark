# MatrixBench 测试报告

> 本测试是基于 TPC-H 数据模型与查询模板的派生工作负载，不是经 TPC 审计的正式 TPC-H 结果，不能与公开 TPC-H 榜单直接比较。

## 1. 测试环境

- Run ID：`20260804T040518Z`
- 数据生成器：electrum/tpch-dbgen 2.14.0 (32f1c1b92d1664dba542e927d23d86ffa57aa253)
- Scale Factor：0.1
- 正式轮数：5
- 计时语义：time-to-last-row

## 2. 总体对比

| 基准库 | 对照库 | 总耗时比 | 查询中位数 | 几何均值 | 算术均值（离群敏感） | 胜/负/平 | 成功率 |
|---|---|---:|---:|---:|---:|---:|---:|
| YMatrix | Greenplum | 2.31x | 2.32x | 2.47x | 3.65x | 18/4/0 | 100.0%/100.0% |
| YMatrix | PostgreSQL | 0.70x | 0.95x | 0.78x | 1.03x | 11/11/0 | 100.0%/100.0% |
| YMatrix | MySQL | 2.28x | 2.87x | 2.00x | 3.51x | 15/7/0 | 100.0%/100.0% |

- 总耗时比回答整套串行 workload 的耗时差异。
- 查询中位数回答典型查询的相对表现。
- 几何均值用于汇总等权相对变化。
- 算术平均容易被极端查询放大，仅作为辅助信息。

## 3. 逐查询比较

| 查询 | 基准库 | 对照库 | 基准中位数(ms) | 对照中位数(ms) | 加速比 | 更快 |
|---|---|---|---:|---:|---:|---|
| q1 | YMatrix | Greenplum | 147.92 | 430.58 | 2.91x | YMatrix |
| q10 | YMatrix | Greenplum | 274.28 | 146.71 | 0.53x | Greenplum |
| q11 | YMatrix | Greenplum | 68.85 | 157.32 | 2.28x | YMatrix |
| q12 | YMatrix | Greenplum | 53.70 | 65.41 | 1.22x | YMatrix |
| q13 | YMatrix | Greenplum | 48.55 | 69.80 | 1.44x | YMatrix |
| q14 | YMatrix | Greenplum | 23.99 | 28.48 | 1.19x | YMatrix |
| q15 | YMatrix | Greenplum | 47.82 | 39.71 | 0.83x | Greenplum |
| q16 | YMatrix | Greenplum | 25.48 | 59.94 | 2.35x | YMatrix |
| q17 | YMatrix | Greenplum | 121.84 | 172.61 | 1.42x | YMatrix |
| q18 | YMatrix | Greenplum | 417.60 | 315.04 | 0.75x | Greenplum |
| q19 | YMatrix | Greenplum | 6.91 | 70.35 | 10.18x | YMatrix |
| q2 | YMatrix | Greenplum | 69.49 | 453.81 | 6.53x | YMatrix |
| q20 | YMatrix | Greenplum | 261.03 | 184.20 | 0.71x | Greenplum |
| q21 | YMatrix | Greenplum | 70.39 | 774.71 | 11.01x | YMatrix |
| q22 | YMatrix | Greenplum | 40.34 | 47.99 | 1.19x | YMatrix |
| q3 | YMatrix | Greenplum | 34.30 | 218.99 | 6.38x | YMatrix |
| q4 | YMatrix | Greenplum | 19.93 | 93.36 | 4.68x | YMatrix |
| q5 | YMatrix | Greenplum | 53.96 | 298.15 | 5.53x | YMatrix |
| q6 | YMatrix | Greenplum | 24.09 | 34.05 | 1.41x | YMatrix |
| q7 | YMatrix | Greenplum | 32.01 | 251.15 | 7.85x | YMatrix |
| q8 | YMatrix | Greenplum | 66.89 | 339.56 | 5.08x | YMatrix |
| q9 | YMatrix | Greenplum | 62.00 | 298.59 | 4.82x | YMatrix |
| q1 | YMatrix | PostgreSQL | 147.92 | 223.76 | 1.51x | YMatrix |
| q10 | YMatrix | PostgreSQL | 274.28 | 57.51 | 0.21x | PostgreSQL |
| q11 | YMatrix | PostgreSQL | 68.85 | 25.67 | 0.37x | PostgreSQL |
| q12 | YMatrix | PostgreSQL | 53.70 | 59.18 | 1.10x | YMatrix |
| q13 | YMatrix | PostgreSQL | 48.55 | 78.89 | 1.62x | YMatrix |
| q14 | YMatrix | PostgreSQL | 23.99 | 19.59 | 0.82x | PostgreSQL |
| q15 | YMatrix | PostgreSQL | 47.82 | 22.18 | 0.46x | PostgreSQL |
| q16 | YMatrix | PostgreSQL | 25.48 | 42.87 | 1.68x | YMatrix |
| q17 | YMatrix | PostgreSQL | 121.84 | 71.85 | 0.59x | PostgreSQL |
| q18 | YMatrix | PostgreSQL | 417.60 | 205.50 | 0.49x | PostgreSQL |
| q19 | YMatrix | PostgreSQL | 6.91 | 7.81 | 1.13x | YMatrix |
| q2 | YMatrix | PostgreSQL | 69.49 | 28.89 | 0.42x | PostgreSQL |
| q20 | YMatrix | PostgreSQL | 261.03 | 13.38 | 0.05x | PostgreSQL |
| q21 | YMatrix | PostgreSQL | 70.39 | 76.86 | 1.09x | YMatrix |
| q22 | YMatrix | PostgreSQL | 40.34 | 15.41 | 0.38x | PostgreSQL |
| q3 | YMatrix | PostgreSQL | 34.30 | 61.07 | 1.78x | YMatrix |
| q4 | YMatrix | PostgreSQL | 19.93 | 34.93 | 1.75x | YMatrix |
| q5 | YMatrix | PostgreSQL | 53.96 | 37.22 | 0.69x | PostgreSQL |
| q6 | YMatrix | PostgreSQL | 24.09 | 42.12 | 1.75x | YMatrix |
| q7 | YMatrix | PostgreSQL | 32.01 | 55.34 | 1.73x | YMatrix |
| q8 | YMatrix | PostgreSQL | 66.89 | 50.56 | 0.76x | PostgreSQL |
| q9 | YMatrix | PostgreSQL | 62.00 | 142.46 | 2.30x | YMatrix |
| q1 | YMatrix | MySQL | 147.92 | 851.59 | 5.76x | YMatrix |
| q10 | YMatrix | MySQL | 274.28 | 85.80 | 0.31x | MySQL |
| q11 | YMatrix | MySQL | 68.85 | 224.49 | 3.26x | YMatrix |
| q12 | YMatrix | MySQL | 53.70 | 281.61 | 5.24x | YMatrix |
| q13 | YMatrix | MySQL | 48.55 | 299.83 | 6.18x | YMatrix |
| q14 | YMatrix | MySQL | 23.99 | 86.13 | 3.59x | YMatrix |
| q15 | YMatrix | MySQL | 47.82 | 168.38 | 3.52x | YMatrix |
| q16 | YMatrix | MySQL | 25.48 | 36.56 | 1.43x | YMatrix |
| q17 | YMatrix | MySQL | 121.84 | 63.75 | 0.52x | MySQL |
| q18 | YMatrix | MySQL | 417.60 | 257.51 | 0.62x | MySQL |
| q19 | YMatrix | MySQL | 6.91 | 27.66 | 4.00x | YMatrix |
| q2 | YMatrix | MySQL | 69.49 | 14.88 | 0.21x | MySQL |
| q20 | YMatrix | MySQL | 261.03 | 56.70 | 0.22x | MySQL |
| q21 | YMatrix | MySQL | 70.39 | 707.49 | 10.05x | YMatrix |
| q22 | YMatrix | MySQL | 40.34 | 16.76 | 0.42x | MySQL |
| q3 | YMatrix | MySQL | 34.30 | 232.78 | 6.79x | YMatrix |
| q4 | YMatrix | MySQL | 19.93 | 39.92 | 2.00x | YMatrix |
| q5 | YMatrix | MySQL | 53.96 | 103.36 | 1.92x | YMatrix |
| q6 | YMatrix | MySQL | 24.09 | 189.45 | 7.86x | YMatrix |
| q7 | YMatrix | MySQL | 32.01 | 79.13 | 2.47x | YMatrix |
| q8 | YMatrix | MySQL | 66.89 | 65.55 | 0.98x | MySQL |
| q9 | YMatrix | MySQL | 62.00 | 615.22 | 9.92x | YMatrix |

## 4. 失败记录

无失败记录。

## 5. 限制

- 当前为单用户串行查询延迟测试，不代表并发吞吐性能。
- 本地 Rosetta 环境不能替代原生 x86_64 专用服务器的产品性能测试。
- 小规模数据主要验证工具链和查询行为；评价 MPP 扩展能力需要更大 SF、多 segment 与并发测试。
- 完整原始记录见 `raw_records.csv`，汇总明细见 `comparison_summary.csv`。
