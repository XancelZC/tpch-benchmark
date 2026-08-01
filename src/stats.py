"""基于逐轮原始记录计算统计指标。"""

from __future__ import annotations

import math
import statistics

from .benchmark import QueryRecord


def percentile(values: list[float], p: float) -> float:
    if not 0 <= p <= 100:
        raise ValueError("percentile must be between 0 and 100")
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * p / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def query_stats(records: list[QueryRecord]) -> dict[str, float | int]:
    successes = [record for record in records if record.success]
    total = len(records)
    if not successes:
        return {
            "avg_ms": 0.0,
            "median_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "p95_ms": 0.0,
            "success_rate": 0.0,
            "success_count": 0,
            "total_count": total,
        }
    times = [record.elapsed_ms for record in successes]
    return {
        "avg_ms": round(statistics.fmean(times), 2),
        "median_ms": round(statistics.median(times), 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "p95_ms": round(percentile(times, 95), 2),
        "success_rate": round(len(successes) / total, 4),
        "success_count": len(successes),
        "total_count": total,
    }


def aggregate_stats(records: list[QueryRecord]) -> dict[str, dict[str, float | int]]:
    by_query: dict[str, list[QueryRecord]] = {}
    for record in records:
        by_query.setdefault(record.query_id, []).append(record)
    return {query_id: query_stats(items) for query_id, items in by_query.items()}
