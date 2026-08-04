"""从现有 raw_records.csv 重新生成报告和汇总 CSV（不重跑 benchmark）。

用法：python3 tools/regenerate_report.py <run_dir>
数据完全来自 raw_records.csv，数字不变，只补充 min/max 和 Top 慢 SQL。
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.benchmark import BenchmarkResult, QueryRecord
from main import validate_result_hashes
from src.reporter import (
    compare_results,
    compute_summary_metrics,
    generate_report,
    generate_summary_csv,
)


def load_results(raw_path: Path) -> dict[str, BenchmarkResult]:
    """从 raw_records.csv 重建每个库的 BenchmarkResult。"""
    by_db: dict[str, list[QueryRecord]] = defaultdict(list)
    with raw_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            record = QueryRecord(
                query_id=row["query_id"],
                database=row["database"],
                round_num=int(row["round_num"]),
                start_time=row["start_time"],
                end_time=row["end_time"],
                elapsed_ms=float(row["elapsed_ms"]),
                row_count=int(row["row_count"]) if row["row_count"] else 0,
                result_hash=row["result_hash"] or None,
                success=row["success"] == "True",
                error_message=row["error_message"] or None,
            )
            by_db[row["database"]].append(record)
    return {
        db: BenchmarkResult(database_name=db, records=records)
        for db, records in by_db.items()
    }


def main() -> None:
    run_dir = Path(sys.argv[1])
    raw_path = run_dir / "raw_records.csv"
    if not raw_path.exists():
        raise SystemExit(f"缺少 raw_records.csv：{raw_path}")

    results = load_results(raw_path)
    if len(results) < 2:
        raise SystemExit("至少需要两个数据库的记录")

    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    metadata["result_mismatches"] = validate_result_hashes(results)
    metadata["failure_count"] = sum(
        1 for result in results.values() for record in result.records if not record.success
    )

    base_name = next(iter(results))
    base_result = results[base_name]
    summaries = []
    all_comparisons = []
    for db_name, other_result in results.items():
        if db_name == base_name:
            continue
        summaries.append(compute_summary_metrics(base_result, other_result))
        all_comparisons.extend(compare_results(base_result, other_result))

    generate_summary_csv(summaries, all_comparisons, str(run_dir / "comparison_summary.csv"))
    generate_report(
        results, summaries, all_comparisons, metadata, str(run_dir / "report.md")
    )
    print(f"已重新生成：{run_dir / 'report.md'}")
    print(f"已重新生成：{run_dir / 'comparison_summary.csv'}")
    print(f"数据库：{list(results)}，基准库：{base_name}")


if __name__ == "__main__":
    main()
