"""生成逐轮明细、对比汇总与 Markdown 报告。"""

from __future__ import annotations

import csv
import math
import statistics
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .benchmark import BenchmarkResult
from .stats import aggregate_stats

RAW_FIELDS = [
    "database",
    "query_id",
    "round_num",
    "start_time",
    "end_time",
    "elapsed_ms",
    "row_count",
    "result_hash",
    "success",
    "error_message",
]


def compare_results(base: BenchmarkResult, other: BenchmarkResult) -> list[dict[str, Any]]:
    """按查询比较两个数据库，基准库为 base。"""
    base_stats = aggregate_stats(base.records)
    other_stats = aggregate_stats(other.records)
    query_ids = sorted(set(base_stats) | set(other_stats))
    comparisons: list[dict[str, Any]] = []
    for query_id in query_ids:
        left = base_stats.get(query_id, {})
        right = other_stats.get(query_id, {})
        base_median = float(left.get("median_ms", 0))
        other_median = float(right.get("median_ms", 0))
        speedup = other_median / base_median if base_median > 0 and other_median > 0 else 0.0
        if speedup > 1.001:
            faster = base.database_name
        elif 0 < speedup < 0.999:
            faster = other.database_name
        elif speedup > 0:
            faster = "tie"
        else:
            faster = "N/A"
        comparisons.append(
            {
                "query_id": query_id,
                "base_database": base.database_name,
                "other_database": other.database_name,
                "base_avg_ms": float(left.get("avg_ms", 0)),
                "other_avg_ms": float(right.get("avg_ms", 0)),
                "base_median_ms": base_median,
                "other_median_ms": other_median,
                "base_p95_ms": float(left.get("p95_ms", 0)),
                "other_p95_ms": float(right.get("p95_ms", 0)),
                "speedup": round(speedup, 6),
                "faster": faster,
                "base_success_rate": float(left.get("success_rate", 0)),
                "other_success_rate": float(right.get("success_rate", 0)),
            }
        )
    return comparisons


def compute_summary_metrics(base: BenchmarkResult, other: BenchmarkResult) -> dict[str, Any]:
    """计算总耗时比、中位数、几何均值和胜负数等稳健指标。"""
    comparisons = compare_results(base, other)
    valid = [row for row in comparisons if row["speedup"] > 0]
    speedups = [row["speedup"] for row in valid]
    base_total = sum(row["base_median_ms"] for row in valid)
    other_total = sum(row["other_median_ms"] for row in valid)
    total_records_base = len(base.records)
    total_records_other = len(other.records)
    base_successes = sum(record.success for record in base.records)
    other_successes = sum(record.success for record in other.records)
    return {
        "base_database": base.database_name,
        "other_database": other.database_name,
        "query_count": len(comparisons),
        "total_time_ratio": other_total / base_total if base_total else 0.0,
        "median_speedup": statistics.median(speedups) if speedups else 0.0,
        "geomean_speedup": math.exp(statistics.fmean(math.log(value) for value in speedups))
        if speedups
        else 0.0,
        "arithmetic_mean_speedup": statistics.fmean(speedups) if speedups else 0.0,
        "base_wins": sum(row["faster"] == base.database_name for row in valid),
        "other_wins": sum(row["faster"] == other.database_name for row in valid),
        "ties": sum(row["faster"] == "tie" for row in valid),
        "base_success_rate": base_successes / total_records_base if total_records_base else 0.0,
        "other_success_rate": other_successes / total_records_other if total_records_other else 0.0,
    }


def generate_raw_csv(results: dict[str, BenchmarkResult], path: str) -> None:
    """保存所有数据库的逐轮原始执行记录。"""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS)
        writer.writeheader()
        for result in results.values():
            for record in result.records:
                writer.writerow({field: asdict(record).get(field) for field in RAW_FIELDS})


def generate_summary_csv(
    summaries: list[dict[str, Any]], comparisons: list[dict[str, Any]], path: str
) -> None:
    """将总体指标和逐查询比较写入一个可审计的 CSV。"""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for summary in summaries:
        rows.append({"record_type": "overall", **summary})
    for comparison in comparisons:
        rows.append({"record_type": "query", **comparison})
    fields = sorted({key for row in rows for key in row})
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _format_ratio(value: float) -> str:
    return "—" if value <= 0 else f"{value:.2f}x"


def generate_report(
    results: dict[str, BenchmarkResult],
    summaries: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    metadata: dict[str, Any],
    path: str,
) -> None:
    """根据最终运行数据动态生成报告，不使用硬编码性能数字。"""
    lines = [
        "# MatrixBench 测试报告",
        "",
        "> 本测试是基于 TPC-H 数据模型与查询模板的派生工作负载，"
        "不是经 TPC 审计的正式 TPC-H 结果，不能与公开 TPC-H 榜单直接比较。",
        "",
        "## 1. 测试环境",
        "",
        f"- Run ID：`{metadata.get('run_id', 'unknown')}`",
        f"- 数据生成器：{metadata.get('data_generator', 'unknown')}",
        f"- Scale Factor：{metadata.get('scale_factor', 'unknown')}",
        f"- 正式轮数：{metadata.get('test_rounds', 'unknown')}",
        f"- 计时语义：{metadata.get('timing_semantics', 'time-to-last-row')}",
        "",
        "## 2. 总体对比",
        "",
        "| 基准库 | 对照库 | 总耗时比 | 查询中位数 | 几何均值 | "
        "算术均值（离群敏感） | 胜/负/平 | 成功率 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        lines.append(
            "| {base_database} | {other_database} | {total} | {median} | {geo} | "
            "{arithmetic} | {wins}/{losses}/{ties} | {base_rate:.1%}/{other_rate:.1%} |".format(
                base_database=item["base_database"],
                other_database=item["other_database"],
                total=_format_ratio(item["total_time_ratio"]),
                median=_format_ratio(item["median_speedup"]),
                geo=_format_ratio(item["geomean_speedup"]),
                arithmetic=_format_ratio(item["arithmetic_mean_speedup"]),
                wins=item["base_wins"],
                losses=item["other_wins"],
                ties=item["ties"],
                base_rate=item["base_success_rate"],
                other_rate=item["other_success_rate"],
            )
        )
    lines.extend(
        [
            "",
            "- 总耗时比回答整套串行 workload 的耗时差异。",
            "- 查询中位数回答典型查询的相对表现。",
            "- 几何均值用于汇总等权相对变化。",
            "- 算术平均容易被极端查询放大，仅作为辅助信息。",
            "",
            "## 3. 逐查询比较",
            "",
            "| 查询 | 基准库 | 对照库 | 基准中位数(ms) | 对照中位数(ms) | 加速比 | 更快 |",
            "|---|---|---|---:|---:|---:|---|",
        ]
    )
    for row in comparisons:
        lines.append(
            f"| {row['query_id']} | {row['base_database']} | {row['other_database']} | "
            f"{row['base_median_ms']:.2f} | {row['other_median_ms']:.2f} | "
            f"{_format_ratio(row['speedup'])} | {row['faster']} |"
        )
    lines.extend(["", "## 4. 失败记录", ""])
    failures = [
        record
        for result in results.values()
        for record in result.records
        if not record.success
    ]
    if not failures:
        lines.append("无失败记录。")
    else:
        lines.extend(["| 数据库 | 查询 | 轮次 | 错误 |", "|---|---|---:|---|"])
        for record in failures:
            lines.append(
                f"| {record.database} | {record.query_id} | {record.round_num} | "
                f"{record.error_message or 'unknown'} |"
            )
    lines.extend(
        [
            "",
            "## 5. 限制",
            "",
            "- 当前为单用户串行查询延迟测试，不代表并发吞吐性能。",
            "- 本地 Rosetta 环境不能替代原生 x86_64 专用服务器的产品性能测试。",
            "- 小规模数据主要验证工具链和查询行为；评价 MPP 扩展能力需要更大 SF、"
            "多 segment 与并发测试。",
            "- 完整原始记录见 `raw_records.csv`，汇总明细见 `comparison_summary.csv`。",
            "",
        ]
    )
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
